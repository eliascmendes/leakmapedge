"""LEAKMAP - gerador do sinal hidraulico da bancada virtual.

O sinal de um vazamento em qualquer ponto sai dos moldes do TSNet (linhas.py):

  1. escolhe a simulacao gravada mais proxima, no mesmo trecho, do mesmo
     tamanho e do mesmo lado do sensor A;
  2. desloca a forma de onda de cada sensor no tempo, para que a chegada caia
     onde a distancia pela tubulacao manda: tempo de percurso do ponto novo
     menos o do ponto simulado;
  3. corrige a amplitude de cada sensor, interpolando a amplitude da frente
     entre as simulacoes vizinhas do mesmo trecho.

No ponto simulado, o resultado e o proprio sinal do TSNet (fonte "tsnet").
Fora dele, a chegada e exata e a forma depois dela e a do ponto simulado mais
proximo (fonte "gerador"); as reflexoes que vem depois ficam deslocadas de ate
o dobro da distancia ate esse ponto, dividido pela velocidade da onda. A
conferencia contra o TSNet esta em validar_gerador.py.

Depois que o molde acaba, o sinal segura o ultimo valor: o vazamento continua
aberto ate a bancada reparar.

As manobras (so na linha do cais) usam os moldes das quatro manobras
simuladas. O sentido contrario de uma manobra (reabrir a valvula do navio,
partir a bomba) e o molde com o sinal trocado, uma aproximacao linear.
"""
import numpy as np

RAMPA_DE_REPARO_S = 0.5         # ao reparar, o efeito do evento some nesse tempo
TOLERANCIA_DO_PONTO_M = 0.5     # a menos disso de um ponto simulado, a fonte e o proprio TSNet

# acao sobre o equipamento -> (molde, sinal, equipamento cujo molde e usado)
MANOBRAS_DO_CAIS = {
    ('B-01', 'parar'): ('parada_bomba', 1.0),
    ('B-01', 'partir'): ('parada_bomba', -1.0),
    ('XV-106', 'fechar'): ('fechamento_106', 1.0),
    ('XV-106', 'abrir'): ('abertura_106', 1.0),
    ('XV-104', 'fechar'): ('fechamento_106', 1.0),
    ('XV-104', 'abrir'): ('abertura_106', 1.0),
    ('XV-108', 'fechar'): ('fechamento_navio', 1.0),
    ('XV-108', 'abrir'): ('fechamento_navio', -1.0),
}


def _lado(trecho, s_m):
    """Antes (-1) ou depois (+1) do sensor A, no trecho que comeca nele."""
    return -1 if trecho in ('principal', 'tronco') and s_m < 0 else 1


def escolher_molde(linha, trecho, s_m, tamanho):
    candidatos = [m for m in linha.moldes_de_vazamento if m.trecho == trecho and m.tamanho == tamanho]
    if not candidatos:
        raise ValueError('nao ha simulacao do tamanho %s no trecho %s' % (tamanho, trecho))
    mesmo_lado = [m for m in candidatos if _lado(m.trecho, m.s_m) == _lado(trecho, s_m)]
    vizinhos = sorted(mesmo_lado or candidatos, key=lambda m: m.s_m)
    molde = min(vizinhos, key=lambda m: abs(m.s_m - s_m))
    escala = {}
    for sensor in molde.delta:
        amp = float(np.interp(s_m, [m.s_m for m in vizinhos], [m.amplitude[sensor] for m in vizinhos]))
        escala[sensor] = amp / molde.amplitude[sensor] if molde.amplitude[sensor] else 1.0
    fonte = 'tsnet' if abs(molde.s_m - s_m) <= TOLERANCIA_DO_PONTO_M else 'gerador'
    return molde, escala, fonte


def vazamento(linha, trecho, s_m, tamanho, t0):
    molde, escala, fonte = escolher_molde(linha, trecho, s_m, tamanho)
    return {'tipo': 'vazamento', 'trecho': trecho, 's_m': float(s_m), 'tamanho': tamanho, 't0': float(t0),
            'molde': molde, 'escala': escala, 'sinal': 1.0, 'fonte': fonte, 'fim': None}


def manobra(linha, equipamento, acao, t0):
    chave = (equipamento, acao)
    if chave not in MANOBRAS_DO_CAIS or not linha.moldes_de_manobra:
        raise ValueError('manobra sem simulacao: %s %s' % (equipamento, acao))
    nome, sinal = MANOBRAS_DO_CAIS[chave]
    molde = linha.moldes_de_manobra[nome]
    s_m = next(e['s_m'] for e in linha.equipamentos if e['id'] == equipamento)
    fonte = 'tsnet' if sinal > 0 and abs(molde.s_m - s_m) <= TOLERANCIA_DO_PONTO_M else 'gerador'
    return {'tipo': 'manobra', 'equipamento': equipamento, 'acao': acao, 'trecho': 'principal', 's_m': float(s_m),
            't0': float(t0), 'molde': molde, 'escala': {k: 1.0 for k in molde.delta}, 'sinal': sinal,
            'fonte': fonte, 'fim': None}


def variacao(linha, evento, sensor, t):
    """Variacao de carga que o evento provoca no sensor, nos instantes t (s, relogio da bancada)."""
    m = evento['molde']
    atraso = linha.tempo_de_percurso(evento['trecho'], evento['s_m'], sensor) - m.chegada[sensor]
    tau = np.asarray(t, dtype=float) - evento['t0'] - atraso
    v = np.interp(tau, m.t_rel, m.delta[sensor], left=0.0, right=m.delta[sensor][-1])
    v = v * evento['escala'][sensor] * evento['sinal']
    if evento['fim'] is not None:
        v = v * np.clip(1.0 - (np.asarray(t) - evento['fim']) / RAMPA_DE_REPARO_S, 0.0, 1.0)
    return v


def carga_limpa(linha, eventos, t):
    """Carga em cada sensor: o regime mais a soma dos eventos (superposicao linear)."""
    saida = {}
    for sensor, h0 in linha.regime.items():
        h = np.full(len(t), float(h0))
        for ev in eventos:
            h += variacao(linha, ev, sensor, t)
        saida[sensor] = h
    return saida

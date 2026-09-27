"""LEAKMAP - previsao do pico de pressao antes da manobra (golpe de ariete).

Complemento do alerta de sobrepressao (sobrepressao.py). O alerta avisa
quando o pico ja aconteceu; a previsao responde antes de o operador fechar
uma valvula: qual o pico previsto, em que nivel ele cai (atencao, alarme) e
em quanto tempo, no minimo, a manobra tem de ser feita para o pico ficar
abaixo do nivel de atencao. Como o alerta, e um recurso a parte: nao mexe na
deteccao nem na localizacao de vazamento.

A previsao tem duas partes.

1. O tamanho do golpe (Joukowsky). Frear de repente a vazao Q0 que passa pelo
   equipamento sobe a carga em

       dH = c / (g A n) * (Q0 - Q1)

   com c a velocidade da onda, A a area interna do tubo e n o numero de
   caminhos por onde a onda sai: 1 no fim da linha (a valvula do navio), 2 no
   meio (a valvula de um berco na linha). A valvula que fica parcialmente
   aberta e um orificio: a vazao que resta cresce com a pressao,
   Q1 = (1 - f) Q0 raiz(1 + dH / H0), com f a fracao da vazao cortada e H0 a
   carga de regime. A equacao e resolvida por bissecao.

2. O alivio pelo tempo de manobra. Numa manobra lenta, a onda refletida
   volta antes de a manobra acabar e alivia o pico. Quanto, depende da
   geometria da linha (reservatorios, bomba, manifold, ramais), e uma formula
   simples nao acerta sempre. Por isso o fator vem do ESTUDO DE TRANSITORIOS
   do equipamento: uma tabela tempo de manobra -> fracao do golpe maximo,
   simulada uma vez por valvula, como se faz na planta; na operacao, so se
   interpola (alem do fim da tabela, o fator cai com 1/t). Sem estudo, vale a
   formula de Michaud, fator = (2L/c) / t, com L a distancia ate o
   reservatorio mais proximo; ela e aproximada e nem sempre conservadora, e o
   resultado sai marcado como estimativa.

Conferencia com o TSNet (08_backend/validar_previsao_de_golpe.py, sobre
02_bancada/codigo/golpe_por_tempo_de_manobra.py), erro da subida prevista:

  41 casos da tabela do estudo           de -6,1% a +10,7%
  7 casos de conferencia, fora da tabela de -16,1% a +2,1%
  so a formula de Michaud, sem estudo    de -40,8% a +48,7%

O pior caso fora da tabela e um corte pequeno (30% da vazao) e lento (4 s),
0,11 bar abaixo do TSNet. A faixa publicada usa MARGEM de 20% e contem todos
os casos; o tempo minimo seguro usa o lado de cima da faixa.

So o fechamento de uma valvula (e a partida de uma bomba) sobe a pressao.
Abrir uma valvula ou parar uma bomba derruba a pressao: sem risco de
sobrepressao. A partida de bomba nao tem previsao: o pico depende da curva da
bomba e do jeito de partir (inversor, valvula de descarga), que ainda nao
estao no cadastro.

Tudo e premissa ate chegarem os dados da planta: vazao de cada equipamento,
diametro, limite de pressao e o estudo de transitorios da linha real.
"""
import numpy as np

import sobrepressao as SP

VERSAO = '1'
G = 9.81
# margem da subida prevista: o erro medido contra o TSNet foi de -16% a +11% (ver o comeco do modulo); a faixa
# publicada e o pico com essa margem, e o tempo minimo seguro usa o lado de cima da faixa
MARGEM = 0.20
TEMPOS_DA_CURVA_S = (0.3, 0.6, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0)
ACAO = {'fechar': 'fechamento', 'abrir': 'abertura', 'partir': 'partida', 'parar': 'parada',
        'fechamento': 'fechamento', 'abertura': 'abertura', 'partida': 'partida', 'parada': 'parada'}
ARTIGO = {'fechamento': 'Fechar', 'abertura': 'Abrir', 'partida': 'Partir', 'parada': 'Parar'}


def subida_m(c, area_m2, vazao_m3_s, fracao, carga_m, ligacoes=1):
    """Subida de carga (m de coluna do produto) de um corte rapido da fracao `fracao` da vazao."""
    q0, f = float(vazao_m3_s), min(max(float(fracao), 0.0), 1.0)
    if q0 <= 0.0 or f <= 0.0:
        return 0.0
    b = float(c) / (G * float(area_m2) * max(int(ligacoes), 1))
    h0 = max(float(carga_m), 1e-6)

    def resto(dh):
        return b * (q0 - (1.0 - f) * q0 * np.sqrt(1.0 + dh / h0)) - dh

    baixo, alto = 0.0, b * q0            # o golpe de um fechamento total e o maior possivel
    for _ in range(80):
        meio = 0.5 * (baixo + alto)
        if resto(meio) > 0.0:
            baixo = meio
        else:
            alto = meio
    return 0.5 * (baixo + alto)


def estudo_da_tabela(resultados, caso):
    """Fator por tempo de um equipamento a partir de simulacoes: [(tempo, fracao do golpe maximo)].

    Para cada fracao cortada simulada, a subida em cada tempo dividida pela do tempo mais curto; entre as
    fracoes, vale o maior fator (o lado conservador). O fator nunca sobe com o tempo.
    """
    por_fracao = {}
    for r in resultados:
        if r['caso'] == caso and r.get('papel', 'grade') == 'grade':
            por_fracao.setdefault(r['fracao_da_vazao_cortada'], []).append(
                (r['tempo_de_manobra_s'], r['maior_subida_no_equipamento_m']))
    if not por_fracao:
        return None
    fatores = {}
    for pontos in por_fracao.values():
        pontos.sort()
        base = pontos[0][1]
        for t, dh in pontos:
            fatores[t] = max(fatores.get(t, 0.0), dh / base if base > 0 else 0.0)
    tabela, menor = [], 1.0
    for t in sorted(fatores):
        menor = min(menor, fatores[t])
        tabela.append((float(t), round(menor, 4)))
    return tabela


def fator_do_tempo(tempo_s, estudo=None, tempo_de_alivio_s=None):
    """(fator, metodo): a fracao do golpe maximo que sobra numa manobra de `tempo_s`."""
    t = max(float(tempo_s), 1e-6)
    if estudo:
        ts = [p[0] for p in estudo]
        fs = [p[1] for p in estudo]
        if t <= ts[0]:
            return 1.0, 'estudo'
        if t <= ts[-1]:
            return float(np.interp(t, ts, fs)), 'estudo'
        return fs[-1] * ts[-1] / t, 'estudo'                  # alem da tabela: cai com 1/t
    if tempo_de_alivio_s:
        return min(1.0, float(tempo_de_alivio_s) / t), 'michaud'
    return 1.0, 'joukowsky'


def tempo_minimo(alvo, estudo=None, tempo_de_alivio_s=None):
    """Menor tempo de manobra com fator <= alvo (0 < alvo < 1)."""
    if estudo:
        ts = [p[0] for p in estudo]
        fs = [p[1] for p in estudo]
        for k in range(1, len(ts)):
            if fs[k] <= alvo:
                if fs[k - 1] == fs[k]:
                    return ts[k]
                return ts[k - 1] + (fs[k - 1] - alvo) * (ts[k] - ts[k - 1]) / (fs[k - 1] - fs[k])
        return ts[-1] * fs[-1] / alvo
    if tempo_de_alivio_s:
        return float(tempo_de_alivio_s) / alvo
    return None


def _bar(v):
    return ('%.2f' % v).replace('.', ',')


def _s(v):
    return ('%.1f' % v).replace('.', ',')


def prever(linha, equipamento, acao, pressao_de_regime_bar, limite_bar, tempo_de_manobra_s=None,
           fracao_da_vazao_cortada=None, modo=None, faixa_bar=None):
    """Previsao padronizada (tipo leakmap.previsao_de_golpe).

    `linha`: {'id', 'velocidade_de_onda_m_s', 'area_m2', 'bar_por_metro'}.
    `equipamento`: {'id', 'tipo', 'hidraulica': {'vazao_m3_s', 'ligacoes', 'distancia_de_alivio_m',
    'sensor_de_referencia', 'estudo', 'origem_do_estudo', 'manobra_padrao': {'fracao_da_vazao_cortada',
    'tempo_de_manobra_s'}}}.
    """
    acao = ACAO[acao]
    hid = equipamento.get('hidraulica') or {}
    padrao = hid.get('manobra_padrao') or {}
    t = float(tempo_de_manobra_s if tempo_de_manobra_s is not None else padrao.get('tempo_de_manobra_s', 0.3))
    f = float(fracao_da_vazao_cortada if fracao_da_vazao_cortada is not None
              else padrao.get('fracao_da_vazao_cortada', 1.0))
    regime = float(pressao_de_regime_bar)
    base = {'tipo': 'leakmap.previsao_de_golpe', 'versao': VERSAO, 'linha': linha['id'],
            'equipamento': equipamento['id'], 'acao': acao, 'tempo_de_manobra_s': round(t, 3),
            'fracao_da_vazao_cortada': round(f, 3), 'limite_bar': round(float(limite_bar), 3),
            'sensor_de_referencia': hid.get('sensor_de_referencia'),
            'pressao_de_regime_bar': round(regime, 3)}
    if modo:
        base['modo'] = modo
    nome = '%s %s' % ('a' if equipamento.get('tipo') == 'valvula' else 'a bomba', equipamento['id'])
    if acao in ('abertura', 'parada'):
        return dict(base, sobe_a_pressao=False, pico_previsto_bar=round(regime, 3), subida_prevista_bar=0.0,
                    fracao_do_limite=round(regime / float(limite_bar), 3), nivel=None, faixa_bar=None,
                    tempo_minimo_seguro_s=None, metodo=None, curva=[],
                    explicacao='%s %s derruba a pressão (onda de queda): não há risco de sobrepressão.'
                               % (ARTIGO[acao], nome))
    if acao == 'partida' or not hid.get('vazao_m3_s'):
        motivo = ('a partida de bomba não tem previsão: o pico depende da curva da bomba e do jeito de partir '
                  '(inversor, válvula de descarga), que ainda não estão no cadastro'
                  if acao == 'partida' else 'faltam os dados hidráulicos do equipamento (vazão) no cadastro')
        return dict(base, sobe_a_pressao=True, pico_previsto_bar=None, subida_prevista_bar=None,
                    fracao_do_limite=None, nivel=None, faixa_bar=None, tempo_minimo_seguro_s=None, metodo=None,
                    curva=[], explicacao='Sem previsão: %s.' % motivo)

    c, bpm = float(linha['velocidade_de_onda_m_s']), float(linha['bar_por_metro'])
    carga = regime / bpm
    maximo_m = subida_m(c, linha['area_m2'], hid['vazao_m3_s'], f, carga, hid.get('ligacoes', 1))
    alivio = (2.0 * hid['distancia_de_alivio_m'] / c) if hid.get('distancia_de_alivio_m') else None
    estudo = hid.get('estudo')

    def pico(tempo):
        fator, metodo = fator_do_tempo(tempo, estudo, alivio)
        return regime + maximo_m * fator * bpm, fator, metodo

    pico_bar, fator, metodo = pico(t)
    limite = float(limite_bar)
    fracao = pico_bar / limite
    nivel = SP.nivel_da_fracao(fracao)
    subida = pico_bar - regime
    faixa = [round(regime + subida * (1 - MARGEM), 3), round(regime + subida * (1 + MARGEM), 3)]
    # tempo minimo para o pico, com a margem, ficar abaixo do nivel de atencao
    folga_bar = SP.FRACAO_ATENCAO * limite - regime
    maximo_bar = maximo_m * bpm * (1 + MARGEM)
    if folga_bar <= 0:
        t_min = None
    elif maximo_bar <= folga_bar:
        t_min = 0.0
    else:
        t_min = tempo_minimo(folga_bar / maximo_bar, estudo, alivio)
        t_min = None if t_min is None else float(np.ceil(t_min * 10.0) / 10.0)
    curva = []
    for tc in sorted(set(TEMPOS_DA_CURVA_S) | {round(t, 3)}):
        p, _, _ = pico(tc)
        curva.append({'tempo_de_manobra_s': tc, 'pico_previsto_bar': round(p, 3),
                      'nivel': SP.nivel_da_fracao(p / limite)})

    partes = ['%s %s cortando %d%% da vazão em %s s: pico previsto de %s bar (sensor %s), %d%% do limite de %s bar'
              % (ARTIGO[acao], nome, int(100 * f + 0.5), _s(t) if t >= 0.1 else ('%.2f' % t).replace('.', ','),
                 _bar(pico_bar), hid.get('sensor_de_referencia') or '-', int(100 * fracao + 0.5), _bar(limite))]
    if nivel is None:
        partes[0] += ': dentro do limite.'
    else:
        partes[0] += ': %s.' % ('ALARME' if nivel == 'alarme' else 'atenção')
    if fracao > 1.0:
        partes.append('O pico passaria do limite.')
    if faixa_bar is not None and pico_bar > float(faixa_bar):
        partes.append('Passaria também da faixa do transmissor (%s bar): o alerta de sobrepressão mediria o pico '
                      'cortado.' % _bar(float(faixa_bar)))
    if nivel is not None:
        if t_min is None:
            partes.append('A pressão de regime já está perto do limite: rever a operação.')
        else:
            partes.append('Para ficar abaixo de %d%% do limite, faça a manobra em pelo menos %s s.'
                          % (int(100 * SP.FRACAO_ATENCAO), _s(t_min)))
    if metodo == 'estudo':
        partes.append('Alívio pelo tempo de manobra: %s.' % (hid.get('origem_do_estudo') or 'estudo de transitórios'))
    elif metodo == 'michaud':
        partes.append('Sem estudo de transitórios deste equipamento: alívio pela fórmula de Michaud, estimativa.')
    partes.append('Previsão com premissas (vazão, diâmetro, limite), com margem de %d%% na subida.'
                  % int(100 * MARGEM))
    return dict(base, sobe_a_pressao=True, pico_previsto_bar=round(pico_bar, 3),
                subida_prevista_bar=round(subida, 3), fracao_do_limite=round(fracao, 3), nivel=nivel,
                faixa_bar=faixa, golpe_maximo_bar=round(maximo_m * bpm, 3), fator_do_tempo=round(fator, 3),
                tempo_minimo_seguro_s=t_min, metodo=metodo, curva=curva, explicacao=' '.join(partes))

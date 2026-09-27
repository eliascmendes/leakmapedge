"""LEAKMAP - as linhas da bancada virtual.

Tres linhas, todas lidas dos arquivos do projeto, sem numero copiado:

  trecho_200   o trecho de teste de 200 m (02_bancada/codigo/build_model.py,
               03_ensaios/amostras/leakmap_amostras_v1.json), o que roda na placa
  cais         a linha de produto do cais (linha_cais.py e manobras_cais.py)
  rede         a rede com manifold e tres ramais (rede_cais.py)

Cada simulacao gravada do TSNet vira um MOLDE: a variacao de carga em cada
sensor em funcao do tempo desde o evento. O gerador (gerador.py) monta o sinal
de qualquer ponto a partir desses moldes.

Manobras, nas tres linhas, pelas simulacoes de manobra de cada uma
(manobras_cais.py, manobras_trecho_200.py, manobras_rede.py): cada simulacao
diz o equipamento e a operacao. A operacao contraria que nao foi simulada
(reabrir a valvula do navio, partir a bomba) usa a mesma onda com o sinal
trocado. Sem o arquivo de manobras de uma linha, ela fica sem equipamentos.

Posicao na linha: sempre (trecho, s_m). Na linha reta ha um trecho so,
"principal", com s_m contado como nas simulacoes (a partir do sensor A na
linha do cais, a partir do inicio no trecho de 200 m). Na rede, s_m conta do
sensor A no tronco e do manifold em cada ramal.
"""
import json
import os

import numpy as np

import projeto as P

G = 9.81
FAIXA_BAR = 15.0                 # transmissor de 0 a 15 bar, como nos ensaios da linha do cais
APOS_A_CHEGADA_S = 0.003         # a amplitude do molde e lida 3 ms depois da chegada
# limite de pressao da linha para o alerta de sobrepressao (07_servico/sobrepressao.py): a pressao maxima
# admissivel do componente mais fraco. PREMISSA ate chegar o dado da planta.
LIMITE_DE_PRESSAO_BAR = {'trecho_200': 8.0, 'cais': 12.0, 'rede': 12.0}
ORIGEM_DO_LIMITE = ('premissa: pressao maxima admissivel do componente mais fraco da linha (mangote, braco de '
                    'carregamento ou flange), ate chegar o dado da planta')
ACAO_DA_BANCADA = {'abertura': 'abrir', 'fechamento': 'fechar', 'parada': 'parar', 'partida': 'partir'}
CONTRARIA = {'abrir': 'fechar', 'fechar': 'abrir', 'parar': 'partir', 'partir': 'parar'}


def _ler(pasta, nome):
    with open(os.path.join(pasta, nome), encoding='utf-8') as f:
        return json.load(f)


class Molde:
    """Uma simulacao gravada: variacao de carga por sensor, com o tempo contado do evento."""

    def __init__(self, ident, trecho, s_m, tamanho, t_rel, deltas, chegadas):
        self.id, self.trecho, self.s_m, self.tamanho = ident, trecho, float(s_m), tamanho
        self.t_rel = np.asarray(t_rel, dtype=float)
        self.delta = {k: np.asarray(v, dtype=float) for k, v in deltas.items()}
        self.chegada = chegadas
        self.amplitude = {k: float(np.interp(chegadas[k] + APOS_A_CHEGADA_S, self.t_rel, self.delta[k]))
                          for k in deltas}


class Linha:
    def __init__(self, ident, nome, tipo, produto, tubo, rho, c, trechos, sensores, regime, referencias,
                 desenho, equipamentos=None, cadastro=None, topo=None, tamanhos=('grande', 'pequeno')):
        self.id, self.nome, self.tipo, self.produto, self.tubo = ident, nome, tipo, produto, tubo
        self.rho, self.c = float(rho), float(c)
        self.trechos, self.sensores, self.regime = trechos, sensores, regime
        self.referencias, self.desenho = referencias, desenho
        self.equipamentos = equipamentos or []
        self.cadastro, self.topo, self.tamanhos = cadastro, topo, list(tamanhos)
        self.moldes_de_vazamento, self.moldes_de_manobra = [], {}
        self.limite_de_pressao_bar = LIMITE_DE_PRESSAO_BAR.get(ident, 12.0)
        self.origem_do_limite = ORIGEM_DO_LIMITE
        self.manobras = {}                # (equipamento, acao da bancada) -> (molde, sinal)
        self.faixa_m = FAIXA_BAR * 1e5 / (self.rho * G)

    # --- geometria ---------------------------------------------------------
    def distancia(self, trecho, s_m, sensor):
        """Distancia pela tubulacao ate um sensor."""
        if self.topo is not None:
            return float(P.RD.distancia(self.topo, trecho, s_m, sensor))
        return abs(float(s_m) - self.sensores[sensor]['s_m'])

    def tempo_de_percurso(self, trecho, s_m, sensor):
        return self.distancia(trecho, s_m, sensor) / self.c

    def espera_s(self):
        """O maior tempo de percurso entre dois sensores: o detector espera isso depois da primeira chegada."""
        nomes = list(self.sensores)
        return max(self.distancia(self.sensores[a]['trecho'], self.sensores[a]['s_m'], b)
                   for a in nomes for b in nomes) / self.c

    def ponto_valido(self, trecho, s_m):
        if trecho not in self.trechos:
            return 'trecho desconhecido: %s' % trecho
        de, ate = self.trechos[trecho]['vazamento_de_s_m'], self.trechos[trecho]['vazamento_ate_s_m']
        if not de <= s_m <= ate:
            return 'posicao fora da linha: o trecho %s aceita de %.0f a %.0f m' % (trecho, de, ate)
        return None

    def bar(self, carga_m):
        return np.asarray(carga_m, dtype=float) * self.rho * G / 1e5

    # --- descricao para a API -----------------------------------------------
    def cenarios_tsnet(self):
        pontos = {}
        for m in self.moldes_de_vazamento:
            pontos.setdefault((m.trecho, m.s_m), []).append(m.tamanho)
        return [{'trecho': t, 's_m': s, 'tamanhos': sorted(v)} for (t, s), v in sorted(pontos.items())]

    def descricao(self, estados_dos_equipamentos=None, limite_bar=None):
        estados = estados_dos_equipamentos or {}
        return {
            'id': self.id, 'nome': self.nome, 'tipo': self.tipo, 'produto': self.produto, 'tubo': self.tubo,
            'velocidade_de_onda_m_s': round(self.c, 2), 'premissas': True,
            'bar_por_metro_de_carga': self.rho * G / 1e5,
            'faixa_do_transmissor_bar': [0.0, FAIXA_BAR],
            'tamanhos_de_vazamento': self.tamanhos,
            'trechos': [{'id': k, 'de_s_m': v['de_s_m'], 'ate_s_m': v['ate_s_m'],
                         'monitorado': {'de_s_m': v['monitorado'][0], 'ate_s_m': v['monitorado'][1]},
                         'vazamento': {'de_s_m': v['vazamento_de_s_m'], 'ate_s_m': v['vazamento_ate_s_m']}}
                        for k, v in self.trechos.items()],
            'sensores': [dict(id=k, **v) for k, v in self.sensores.items()],
            'equipamentos': [dict(e, estado=estados.get(e['id'], e['estado_inicial'])) for e in self.equipamentos],
            'referencias': self.referencias,
            'desenho_esquematico': self.desenho,
            'cenarios_tsnet': self.cenarios_tsnet(),
            'limite_de_pressao_bar': limite_bar if limite_bar is not None else self.limite_de_pressao_bar,
            'origem_do_limite': self.origem_do_limite,
        }


# --- montagem das tres linhas ----------------------------------------------

def _moldes_da_linha_reta(linha, amostras, verdade, instante_padrao):
    por_id = {e['id']: e for e in verdade['ensaios']}
    moldes = []
    for e in amostras['ensaios']:
        v = por_id.get(e['id'])
        if not v or not v.get('posicao_real_m') and v.get('posicao_real_m') != 0:
            continue
        t0 = v.get('instante_do_evento_s') or instante_padrao
        t = np.asarray(e['tempo_s']) - t0
        deltas = {s: np.asarray(e['canal_%s_carga_m' % s]) - e['canal_%s_carga_m' % s][0] for s in ('A', 'B')}
        chegadas = {s: linha.tempo_de_percurso('principal', v['posicao_real_m'], s) for s in ('A', 'B')}
        moldes.append(Molde(e['id'], 'principal', v['posicao_real_m'], v.get('tamanho_do_vazamento', 'grande'),
                            t, deltas, chegadas))
    return moldes


def _existe(pasta, nome):
    return os.path.exists(os.path.join(pasta, nome))


def _carregar_manobras(linha, amostras_nome, verdade_nome, usa_moldes_de=None):
    """Moldes de manobra e a tabela (equipamento, acao) -> (molde, sinal); o cadastro sai dos equipamentos."""
    if not (_existe(P.AMOSTRAS, amostras_nome) and _existe(P.VERDADE, verdade_nome)):
        linha.equipamentos, linha.cadastro = [], None
        return
    amostras = _ler(P.AMOSTRAS, amostras_nome)
    verdade = {e['id']: e for e in _ler(P.VERDADE, verdade_nome)['ensaios']}
    diretas = {}
    for e in amostras['ensaios']:
        v = verdade[e['id']]
        trecho = v.get('trecho', 'principal')
        s_m = v.get('s_m', v.get('posicao_da_manobra_m'))
        t = np.asarray(e['tempo_s']) - v['instante_da_manobra_s']
        if 'canais_carga_m' in e:
            deltas = {k: np.asarray(x) - x[0] for k, x in e['canais_carga_m'].items()}
        else:
            deltas = {s: np.asarray(e['canal_%s_carga_m' % s]) - e['canal_%s_carga_m' % s][0] for s in ('A', 'B')}
        chegadas = {k: linha.tempo_de_percurso(trecho, s_m, k) for k in deltas}
        linha.moldes_de_manobra[v['manobra']] = Molde(e['id'], trecho, s_m, None, t, deltas, chegadas)
        acao = v.get('acao') or v['manobra'].split('_')[0]
        diretas[(v['equipamento'], ACAO_DA_BANCADA[acao])] = v['manobra']
    tabela = {chave: (nome, 1.0) for chave, nome in diretas.items()}
    for (eq, acao), nome in diretas.items():
        tabela.setdefault((eq, CONTRARIA[acao]), (nome, -1.0))
    for eq, fonte in (usa_moldes_de or {}).items():
        for (outro, acao), valor in list(tabela.items()):
            if outro == fonte:
                tabela.setdefault((eq, acao), valor)
    linha.manobras = tabela
    linha.cadastro = {'linha': linha.id, 'equipamentos': [
        {'nome': e['id'], 'tipo': e['tipo'], 'trecho': e['trecho'], 'posicao_m': e['s_m']} for e in linha.equipamentos]}


def trecho_200():
    k = P.constantes_do_trecho_200()
    par = _ler(os.path.join(P.RAIZ, '03_ensaios', 'parametros'), 'leakmap_parametros_v1.json')
    amostras = _ler(P.AMOSTRAS, 'leakmap_amostras_v1.json')
    verdade = _ler(P.VERDADE, 'leakmap_verdade_v1.json')
    sensores = {'A': {'nome': 'Sensor A', 'trecho': 'principal', 's_m': k['SENSOR_A']},
                'B': {'nome': 'Sensor B', 'trecho': 'principal', 's_m': k['SENSOR_B']}}
    regime = {s: amostras['ensaios'][0]['canal_%s_carga_m' % s][0] for s in ('A', 'B')}
    linha = Linha('trecho_200', 'Trecho de teste de 200 m', 'linha', 'agua',
                  '%.0f mm' % (1000 * k['DIAMETRO']), 1000.0, par['velocidade_de_onda']['efetiva_ajustada_m_s'],
                  {'principal': {'de_s_m': 0.0, 'ate_s_m': k['L_TRECHO'], 'monitorado': (k['SENSOR_A'], k['SENSOR_B']),
                                 'vazamento_de_s_m': 5.0, 'vazamento_ate_s_m': k['L_TRECHO'] - 5.0}},
                  sensores, regime,
                  [{'nome': 'reservatório de montante', 'trecho': 'principal', 's_m': 0.0},
                   {'nome': 'tomada 100', 'trecho': 'principal', 's_m': 100.0},
                   {'nome': 'tomada 190', 'trecho': 'principal', 's_m': 190.0},
                   {'nome': 'reservatório de jusante', 'trecho': 'principal', 's_m': k['L_TRECHO']}],
                  {'principal': [[0.0, 0.0], [k['L_TRECHO'], 0.0]]}, tamanhos=('grande',),
                  equipamentos=[{'id': 'XV-100', 'tipo': 'valvula', 'trecho': 'principal', 's_m': 100.0,
                                 'estado_inicial': 'aberta'},
                                {'id': 'XV-190', 'tipo': 'valvula', 'trecho': 'principal', 's_m': 190.0,
                                 'estado_inicial': 'aberta'}])
    # instante do vazamento nas simulacoes do trecho de 200 m (02_bancada/codigo/simular.py, TS_BURST)
    linha.moldes_de_vazamento = _moldes_da_linha_reta(linha, amostras, verdade, 0.05)
    _carregar_manobras(linha, 'leakmap_amostras_manobras_trecho_200_v1.json',
                       'leakmap_verdade_manobras_trecho_200_v1.json')
    return linha


def cais():
    amostras = _ler(P.AMOSTRAS, 'leakmap_amostras_linha_cais_v1.json')
    verdade = _ler(P.VERDADE, 'leakmap_verdade_linha_cais_v1.json')
    pos = amostras['premissas']['posicoes_m']
    regime_ensaio = next(e for e in amostras['ensaios'] if e['id'] == 'LC-REGIME')
    cadastro = P.CD.ler(os.path.join(P.PASTAS['servico'], 'cadastro.exemplo.json'))
    iniciais = {'B-01': 'ligada', 'XV-104': 'fechada', 'XV-106': 'aberta', 'XV-108': 'aberta'}
    equipamentos = [{'id': e['nome'], 'tipo': e['tipo'], 'trecho': 'principal', 's_m': e['posicao_m'],
                     'estado_inicial': iniciais.get(e['nome'], 'aberta')} for e in cadastro['equipamentos']]
    linha = Linha('cais', 'Linha de produto do cais', 'linha', amostras['premissas']['produto'],
                  amostras['premissas']['tubo'].replace('aco_carbono', 'aço carbono').replace(' sch40', ''),
                  amostras['premissas']['massa_especifica_kg_m3'], amostras['velocidade_de_onda_efetiva_m_s'],
                  {'principal': {'de_s_m': pos['bomba'], 'ate_s_m': pos['navio'],
                                 'monitorado': (pos['sensor_A'], pos['sensor_B_berco_108']),
                                 'vazamento_de_s_m': pos['bomba'] + 10.0, 'vazamento_ate_s_m': pos['navio'] - 10.0}},
                  {'A': {'nome': 'Sensor A · início do trecho', 'trecho': 'principal', 's_m': pos['sensor_A']},
                   'B': {'nome': 'Sensor B · berço 108', 'trecho': 'principal', 's_m': pos['sensor_B_berco_108']}},
                  {s: regime_ensaio['canal_%s_carga_m' % s][0] for s in ('A', 'B')},
                  [{'nome': 'bomba', 'trecho': 'principal', 's_m': pos['bomba']},
                   {'nome': 'berço 104', 'trecho': 'principal', 's_m': pos['berco_104']},
                   {'nome': 'berço 106', 'trecho': 'principal', 's_m': pos['berco_106']},
                   {'nome': 'berço 108', 'trecho': 'principal', 's_m': pos['sensor_B_berco_108']},
                   {'nome': 'navio', 'trecho': 'principal', 's_m': pos['navio']}],
                  {'principal': [[pos['bomba'], 0.0], [pos['navio'], 0.0]]},
                  equipamentos=equipamentos)
    linha.moldes_de_vazamento = _moldes_da_linha_reta(linha, amostras, verdade, 0.1)
    # a XV-104 nao foi simulada: usa as manobras da XV-106, deslocadas para a posicao dela
    _carregar_manobras(linha, 'leakmap_amostras_manobras_cais_v1.json', 'leakmap_verdade_manobras_cais_v1.json',
                       usa_moldes_de={'XV-104': 'XV-106'})
    return linha


def rede():
    amostras = _ler(P.AMOSTRAS, 'leakmap_amostras_rede_cais_v1.json')
    verdade = _ler(P.VERDADE, 'leakmap_verdade_rede_cais_v1.json')
    topo = amostras['topologia']
    premissas = amostras['premissas']
    ramais = {k: v['comprimento_monitorado_m'] for k, v in topo['trechos'].items() if k != 'tronco'}
    tronco = topo['trechos']['tronco']['comprimento_monitorado_m']
    bomba = premissas['posicoes_m']['bomba']
    trechos = {'tronco': {'de_s_m': bomba, 'ate_s_m': tronco, 'monitorado': (0.0, tronco),
                          'vazamento_de_s_m': bomba + 10.0, 'vazamento_ate_s_m': tronco}}
    for k, comp in ramais.items():
        trechos[k] = {'de_s_m': 0.0, 'ate_s_m': comp + P.RC.NAVIO_APOS_SENSOR_M, 'monitorado': (0.0, comp),
                      'vazamento_de_s_m': 0.0, 'vazamento_ate_s_m': comp + P.RC.NAVIO_APOS_SENSOR_M - 5.0}
    sensores = {}
    for nome, s in topo['sensores'].items():
        rotulo = 'Sensor A · início do tronco' if nome == 'A' else 'Sensor %s · berço %s' % (nome, nome[1:])
        sensores[nome] = {'nome': rotulo, 'trecho': s['trecho'], 's_m': s['s_m']}
    regime_ensaio = next(e for e in amostras['ensaios'] if e['id'] == 'RC-REGIME')
    abre = {'ramal_104': 150.0, 'ramal_106': 0.0, 'ramal_108': -150.0}
    desenho = {'tronco': [[bomba, 0.0], [tronco, 0.0]]}
    for k, comp in ramais.items():
        fim = tronco + comp + P.RC.NAVIO_APOS_SENSOR_M
        desenho[k] = ([[tronco, 0.0], [fim, 0.0]] if abre[k] == 0 else
                      [[tronco, 0.0], [tronco + 50.0, abre[k]], [fim, abre[k]]])
    referencias = [{'nome': 'bomba', 'trecho': 'tronco', 's_m': bomba},
                   {'nome': 'manifold', 'trecho': 'tronco', 's_m': tronco}]
    referencias += [{'nome': 'berço %s' % k[-3:], 'trecho': k, 's_m': comp} for k, comp in ramais.items()]
    linha = Linha('rede', 'Rede do cais com manifold e três ramais', 'rede', premissas['produto'],
                  premissas['tubo'].replace('aco_carbono', 'aço carbono').replace(' sch40', ''),
                  premissas['massa_especifica_kg_m3'], topo['velocidade_de_onda_m_s'], trechos, sensores,
                  {k: v[0] for k, v in regime_ensaio['canais_carga_m'].items()}, referencias, desenho, topo=topo,
                  equipamentos=[{'id': 'B-01', 'tipo': 'bomba', 'trecho': 'tronco', 's_m': bomba,
                                 'estado_inicial': 'ligada'}] +
                  [{'id': 'XV-%s' % k[-3:], 'tipo': 'valvula', 'trecho': k, 's_m': comp + P.RC.NAVIO_APOS_SENSOR_M,
                    'estado_inicial': 'aberta'} for k, comp in ramais.items()])
    por_id = {e['id']: e for e in verdade['ensaios']}
    for e in amostras['ensaios']:
        v = por_id[e['id']]
        if not v['tem_evento']:
            continue
        t = np.asarray(e['tempo_s']) - v['instante_do_evento_s']
        deltas = {k: np.asarray(x) - x[0] for k, x in e['canais_carga_m'].items()}
        chegadas = {k: linha.tempo_de_percurso(v['trecho_real'], v['s_real_m'], k) for k in deltas}
        linha.moldes_de_vazamento.append(Molde(e['id'], v['trecho_real'], v['s_real_m'],
                                               v['tamanho_do_vazamento'], t, deltas, chegadas))
    _carregar_manobras(linha, 'leakmap_amostras_manobras_rede_v1.json', 'leakmap_verdade_manobras_rede_v1.json')
    return linha


def todas():
    return {linha.id: linha for linha in (trecho_200(), cais(), rede())}

"""LEAKMAP - simulacao transiente TSNet de uma linha de produto do cais.

Cenario de instalacao, com PREMISSAS no lugar do que ainda nao se sabe da
linha real (comprimentos, espessura, vazao). Cada premissa esta em
PREMISSAS e vai gravada junto com os sinais; troque aqui quando chegar o
dado real e rode de novo.

  bomba (tancagem) --- rack ---[A]--- berco 104 --- berco 106 ---[B]-- navio
     -300 m                     0 m        200 m          450 m      700 m  720 m

  - linha de 8" em aco carbono, schedule 40, com diesel;
  - velocidade da onda pela formula de Korteweg (velocidade_de_onda.py);
  - bomba como carga constante de 7 bar (85 m de coluna de diesel) e o navio
    como carga constante ajustada para cerca de 1,5 m/s na linha (~170 m3/h);
  - sensor A no inicio do rack e sensor B no berco 108 (700 m de distancia);
  - vazamentos em sete posicoes entre os sensores e em uma antes do sensor A,
    em dois tamanhos: grande (~20% da vazao) e pequeno (~4% da vazao).

As cargas saem em metros de coluna de diesel. Grava:
  03_ensaios/amostras/leakmap_amostras_linha_cais_v1.json   (sinais, sem posicao)
  03_ensaios/verdade_do_cenario/leakmap_verdade_linha_cais_v1.json  (posicoes)

Precisa do ambiente com TSNet (02_bancada/ambiente/LEIAME.md). Uso:
  python linha_cais.py [--posicoes 50 350] [--tamanhos grande]
"""
import argparse
import json
import math
import os
import sys
import tempfile
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import velocidade_de_onda as VO  # noqa: E402

SAIDA_AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_linha_cais_v1.json')
SAIDA_VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_linha_cais_v1.json')

G = 9.81
PRODUTO = 'diesel'
NOMINAL, MATERIAL, SCHEDULE = '8"', 'aco_carbono', 'sch40'
RHO = VO.PRODUTOS[PRODUTO]['rho_kg_m3']

POS_BOMBA = -300.0
POS_SENSOR_A = 0.0
POS_BERCO_104 = 200.0
POS_BERCO_106 = 450.0
POS_SENSOR_B = 700.0
POS_NAVIO = 720.0
POS_EVENTO = [50.0, 150.0, 250.0, 350.0, 450.0, 550.0, 650.0, -150.0]

PRESSAO_BOMBA_BAR = 7.0
H_BOMBA = PRESSAO_BOMBA_BAR * 1e5 / (RHO * G)
H_NAVIO = H_BOMBA - 55.0          # ~1,5 m/s na linha (~170 m3/h) com o atrito que o TSNet aplica
RUGOSIDADE_MM = 0.046             # aco carbono comercial
FRICCAO_DW = 0.02
DT_SOLICITADO = 2e-4              # s; decimacao por 2 chega a 2,5 kHz
TF = 0.95                         # s
TS_EVENTO = 0.10                  # s
TC_EVENTO = 0.001                 # s
# coeficiente emissor final (m3/s por raiz de m): Q = k * sqrt(H)
TAMANHOS = {'grande': 1.2e-3, 'pequeno': 2.5e-4}


def nome_no(x):
    return ('N%d' % int(round(x))).replace('-', 'M')


def pontos():
    return sorted(set([POS_SENSOR_A, POS_BERCO_104, POS_BERCO_106, POS_SENSOR_B] + POS_EVENTO))


def premissas(c):
    d = VO.diametro_interno_m(NOMINAL, SCHEDULE)
    return {
        'observacao': ('premissas de simulacao no lugar dos dados que ainda faltam da linha real; '
                       'comprimentos, espessura e vazao a confirmar com a planta e o isometrico'),
        'produto': PRODUTO,
        'massa_especifica_kg_m3': RHO,
        'tubo': '%s %s %s' % (NOMINAL, MATERIAL, SCHEDULE),
        'diametro_interno_m': d,
        'velocidade_de_onda_korteweg_m_s': c,
        'posicoes_m': {'bomba': POS_BOMBA, 'sensor_A': POS_SENSOR_A, 'berco_104': POS_BERCO_104,
                       'berco_106': POS_BERCO_106, 'sensor_B_berco_108': POS_SENSOR_B, 'navio': POS_NAVIO},
        'pressao_da_bomba_bar': PRESSAO_BOMBA_BAR,
        'carga_da_bomba_m': H_BOMBA,
        'carga_no_navio_m': H_NAVIO,
        'unidade_de_carga': 'metro de coluna de %s (1 bar = %.2f m)' % (PRODUTO, 1e5 / (RHO * G)),
        'evento': ('abertura de vazamento (add_burst do TSNet) em %.3f s, desenvolvimento em %.4f s'
                   % (TS_EVENTO, TC_EVENTO)),
        'tamanhos_de_vazamento_coeficiente_emissor': TAMANHOS,
    }


def escrever_inp(caminho, d):
    import wntr
    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.headloss = 'D-W'
    wn.options.time.duration = 0
    wn.add_reservoir('BOMBA', base_head=H_BOMBA, coordinates=(POS_BOMBA, 0.0))
    wn.add_reservoir('NAVIO', base_head=H_NAVIO, coordinates=(POS_NAVIO, 0.0))
    xs = pontos()
    for x in xs:
        wn.add_junction(nome_no(x), base_demand=0.0, elevation=0.0, coordinates=(x, 0.0))
    seq = ['BOMBA'] + [nome_no(x) for x in xs] + ['NAVIO']
    pos = [POS_BOMBA] + xs + [POS_NAVIO]
    for i in range(len(seq) - 1):
        wn.add_pipe('T%d' % (i + 1), seq[i], seq[i + 1], length=pos[i + 1] - pos[i],
                    diameter=d, roughness=RUGOSIDADE_MM, minor_loss=0.0)
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho


def rodar(inp, c, posicao=None, coeficiente=None, pasta='.'):
    import tsnet
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(c)
    tm.set_time(TF, DT_SOLICITADO)
    tm.set_roughness(FRICCAO_DW)
    if posicao is not None:
        tm.add_burst(nome_no(posicao), TS_EVENTO, TC_EVENTO, coeficiente)
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    nome = 'linha_%s' % ('regime' if posicao is None else '%s_%g' % (nome_no(posicao), coeficiente))
    tm = tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, nome))
    return tm


def velocidade_efetiva(tm):
    """Velocidade efetiva entre os sensores, lida de volta do solucionador."""
    xs = {nome: no.coordinates[0] for nome, no in tm.nodes()}
    tempo = comp = 0.0
    for _, tubo in tm.pipes():
        x0, x1 = xs[tubo.start_node.name], xs[tubo.end_node.name]
        if min(x0, x1) >= POS_SENSOR_A - 1e-9 and max(x0, x1) <= POS_SENSOR_B + 1e-9:
            tempo += tubo.length / tubo.wavev
            comp += tubo.length
    return comp / tempo


def serie(tm, x):
    return np.asarray(tm.get_node(nome_no(x))._head, dtype=float)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--posicoes', nargs='*', type=float, default=POS_EVENTO)
    ap.add_argument('--tamanhos', nargs='*', default=list(TAMANHOS))
    args = ap.parse_args()

    import tsnet
    import wntr
    c = VO.velocidade(PRODUTO, NOMINAL, MATERIAL, SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(NOMINAL, SCHEDULE)
    pasta = tempfile.mkdtemp(prefix='leakmap_linha_')
    inp = escrever_inp(os.path.join(pasta, 'linha_cais.inp'), d)

    inicio = time.time()
    regime = rodar(inp, c, pasta=pasta)
    t = np.asarray(regime.simulation_timestamps, dtype=float)
    c_ef = velocidade_efetiva(regime)
    ts = float(regime.time_step)
    vazao = float(np.asarray(regime.get_link('T1').start_node_flowrate).ravel()[0])
    area = math.pi * d * d / 4.0
    print('regime: passo %.6e s, c efetiva %.3f m/s, vazao %.4f m3/s (%.2f m/s), carga A %.2f m, B %.2f m (%.1f s)'
          % (ts, c_ef, vazao, vazao / area, serie(regime, POS_SENSOR_A)[0], serie(regime, POS_SENSOR_B)[0],
             time.time() - inicio), flush=True)

    ensaios, verdade = [], []
    ensaios.append({'id': 'LC-REGIME', 'n_pontos': int(len(t)), 'tempo_s': [float(v) for v in t],
                    'canal_A_carga_m': [float(v) for v in serie(regime, POS_SENSOR_A)],
                    'canal_B_carga_m': [float(v) for v in serie(regime, POS_SENSOR_B)]})
    verdade.append({'id': 'LC-REGIME', 'tem_evento': False, 'posicao_real_m': None,
                    'instante_do_evento_s': None, 'evento': 'nenhum: regime permanente'})

    k = 0
    for tamanho in args.tamanhos:
        for pos in args.posicoes:
            k += 1
            inicio = time.time()
            tm = rodar(inp, c, pos, TAMANHOS[tamanho], pasta)
            a, b = serie(tm, POS_SENSOR_A), serie(tm, POS_SENSOR_B)
            identificador = 'LC-%02d' % k
            ensaios.append({'id': identificador, 'n_pontos': int(len(a)),
                            'tempo_s': [float(v) for v in tm.simulation_timestamps],
                            'canal_A_carga_m': [float(v) for v in a],
                            'canal_B_carga_m': [float(v) for v in b]})
            verdade.append({'id': identificador, 'tem_evento': True, 'posicao_real_m': pos,
                            'tamanho_do_vazamento': tamanho,
                            'coeficiente_emissor': TAMANHOS[tamanho],
                            'dentro_do_trecho_entre_sensores': POS_SENSOR_A <= pos <= POS_SENSOR_B,
                            'instante_do_evento_s': TS_EVENTO,
                            'vazao_do_vazamento_estimada_m3_s': TAMANHOS[tamanho] * math.sqrt(max(a[0], 0.0)),
                            'fracao_da_vazao_de_regime_estimada': (TAMANHOS[tamanho]
                                                                   * math.sqrt(max(a[0], 0.0)) / vazao),
                            'queda_no_sensor_A_m': float(a[0] - a.min()),
                            'queda_no_sensor_B_m': float(b[0] - b.min())})
            print('%s: vazamento %s em %6.1f m | queda A %.2f m, B %.2f m (%.0f s)'
                  % (identificador, tamanho, pos, a[0] - a.min(), b[0] - b.min(), time.time() - inicio),
                  flush=True)

    comum = {
        'ferramenta': 'TSNet 0.3.1 / wntr %s / numpy %s' % (wntr.__version__, np.__version__),
        'metodo': 'Metodo das caracteristicas (MOC), friction="steady"',
        'premissas': premissas(c),
        'velocidade_de_onda_efetiva_m_s': c_ef,
        'vazao_de_regime_m3_s': vazao,
        'velocidade_do_escoamento_m_s': vazao / area,
        'passo_de_tempo_efetivo_s': ts,
    }
    os.makedirs(os.path.dirname(SAIDA_AMOSTRAS), exist_ok=True)
    with open(SAIDA_AMOSTRAS, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao=('Sinais da simulacao de uma linha de produto do cais, nos '
                                          'sensores A e B. Nao contem a posicao do vazamento.'),
                       base_de_tempo_s=ts,
                       sensores={'A': {'posicao_m': POS_SENSOR_A}, 'B': {'posicao_m': POS_SENSOR_B},
                                 'distancia_entre_sensores_L_m': POS_SENSOR_B - POS_SENSOR_A},
                       unidades={'carga': 'm de coluna de %s' % PRODUTO},
                       ensaios=ensaios), f, ensure_ascii=False)
    with open(SAIDA_VERDADE, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao=('VERDADE DO CENARIO da linha do cais. Uso exclusivo do '
                                          'avaliador. Nunca entra no detector.'),
                       ensaios=verdade), f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_AMOSTRAS, RAIZ))
    print('escrito: %s' % os.path.relpath(SAIDA_VERDADE, RAIZ))


if __name__ == '__main__':
    main()

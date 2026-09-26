"""LEAKMAP - manobras operacionais na linha de produto do cais (TSNet).

A mesma linha de linha_cais.py, com os dois pontos de carregamento como
retiradas de vazao, para gerar as ondas que uma operacao normal produz e que
nao podem virar alarme de vazamento:

                                        berco 106 (retirada)
                                               |
  bomba --- rack ---[A]--- 104 ------------- 450 m ---[B]--- 710 m: navio do berco 108 (retirada)
                    0 m                                700 m

  fechamento_navio  a retirada do navio do 108 cai a metade em 0,3 s (a
                    valvula do fim de carregamento fechando): onda de ALTA
                    vinda de fora do trecho, do lado do sensor B;
  fechamento_106    a retirada do berco 106 cai a metade em 0,3 s: onda de
                    ALTA nascida DENTRO do trecho, em 450 m, onde um
                    vazamento tambem seria localizado. So a polaridade
                    separa uma coisa da outra.

Por que retirada e nao valvula: no TSNet 0.3.1 a valvula parte de um regime
inicial fora de equilibrio (o EPANET e o TSNet discordam da perda da valvula
aberta, e o TSNet avisa "Initial condition discrepancy"), o que gera uma
onda falsa no inicio. A retirada no no e um orificio (Q = k * raiz de H) que
o TSNet inicializa em equilibrio; reduzir k e, na fisica, o mesmo que fechar
a valvula daquele ramal.

O caso "evento fora do trecho, do lado do sensor A" ja esta no vazamento em
-150 m de linha_cais.py.

Grava:
  03_ensaios/amostras/leakmap_amostras_manobras_cais_v1.json
  03_ensaios/verdade_do_cenario/leakmap_verdade_manobras_cais_v1.json

Uso: python manobras_cais.py [--manobras fechamento_106] [--tf 0.95] [--sem-gravar]
"""
import argparse
import json
import os
import tempfile
import time

import linha_cais as LC
import velocidade_de_onda as VO

SAIDA_AMOSTRAS = os.path.join(LC.RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_manobras_cais_v1.json')
SAIDA_VERDADE = os.path.join(LC.RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_manobras_cais_v1.json')

POS_NAVIO_108 = 710.0
RETIRADA_108_M3_S = 0.040        # ~145 m3/h no navio do 108
RETIRADA_106_M3_S = 0.015        # ~55 m3/h no berco 106, carregando ao mesmo tempo
MANOBRAS = {
    'fechamento_navio': {'posicao_m': POS_NAVIO_108, 'onda': 'alta', 'dentro_do_trecho': False},
    'fechamento_106': {'posicao_m': LC.POS_BERCO_106, 'onda': 'alta', 'dentro_do_trecho': True},
}
RAMPA_S = 0.3
MULTIPLICADOR = -0.5             # a retirada cai a metade


def escrever_inp(caminho, d):
    import wntr
    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.headloss = 'D-W'
    wn.options.time.duration = 0
    wn.add_reservoir('BOMBA', base_head=LC.H_BOMBA, coordinates=(LC.POS_BOMBA, 0.0))
    xs = sorted(set([LC.POS_SENSOR_A, LC.POS_BERCO_104, LC.POS_BERCO_106, LC.POS_SENSOR_B, POS_NAVIO_108]))
    retirada = {LC.POS_BERCO_106: RETIRADA_106_M3_S, POS_NAVIO_108: RETIRADA_108_M3_S}
    for x in xs:
        wn.add_junction(LC.nome_no(x), base_demand=retirada.get(x, 0.0), elevation=0.0, coordinates=(x, 0.0))
    seq = ['BOMBA'] + [LC.nome_no(x) for x in xs]
    pos = [LC.POS_BOMBA] + xs
    for i in range(len(seq) - 1):
        wn.add_pipe('T%d' % (i + 1), seq[i], seq[i + 1], length=pos[i + 1] - pos[i], diameter=d,
                    roughness=LC.RUGOSIDADE_MM, minor_loss=0.0)
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho


def rodar(inp, c, manobra, pasta, tf, rampa=RAMPA_S, multiplicador=MULTIPLICADOR):
    import tsnet
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(c)
    tm.set_time(tf, LC.DT_SOLICITADO)
    tm.set_roughness(LC.FRICCAO_DW)
    # pulso mais longo que a simulacao: na pratica, um degrau com rampa
    tm.add_demand_pulse(LC.nome_no(MANOBRAS[manobra]['posicao_m']), [10.0 * tf, LC.TS_EVENTO, rampa, multiplicador])
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    return tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, manobra))


def maior_variacao(x):
    subida, descida = x.max() - x[0], x[0] - x.min()
    return subida if subida >= descida else -descida


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--manobras', nargs='*', default=list(MANOBRAS))
    ap.add_argument('--tf', type=float, default=LC.TF)
    ap.add_argument('--sem-gravar', action='store_true')
    args = ap.parse_args()
    c = VO.velocidade(LC.PRODUTO, LC.NOMINAL, LC.MATERIAL, LC.SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(LC.NOMINAL, LC.SCHEDULE)
    pasta = tempfile.mkdtemp(prefix='leakmap_manobras_')
    inp = escrever_inp(os.path.join(pasta, 'manobras.inp'), d)
    ensaios, verdade = [], []
    ts = None
    for k, manobra in enumerate(args.manobras, 1):
        inicio = time.time()
        tm = rodar(inp, c, manobra, pasta, args.tf)
        ts = float(tm.time_step)
        a, b = LC.serie(tm, LC.POS_SENSOR_A), LC.serie(tm, LC.POS_SENSOR_B)
        identificador = 'MN-%02d' % k
        ensaios.append({'id': identificador, 'n_pontos': int(len(a)),
                        'tempo_s': [float(v) for v in tm.simulation_timestamps],
                        'canal_A_carga_m': [float(v) for v in a], 'canal_B_carga_m': [float(v) for v in b]})
        verdade.append({'id': identificador, 'tem_evento': False, 'manobra': manobra,
                        'posicao_da_manobra_m': MANOBRAS[manobra]['posicao_m'],
                        'dentro_do_trecho_entre_sensores': MANOBRAS[manobra]['dentro_do_trecho'],
                        'onda_esperada': MANOBRAS[manobra]['onda'],
                        'instante_da_manobra_s': LC.TS_EVENTO,
                        'maior_variacao_no_sensor_A_m': float(maior_variacao(a)),
                        'maior_variacao_no_sensor_B_m': float(maior_variacao(b)),
                        'carga_minima_m': float(min(a.min(), b.min()))})
        print('%s %s: maior variacao A %+.2f m, B %+.2f m, carga A %.1f m, B %.1f m (%.0f s)'
              % (identificador, manobra, maior_variacao(a), maior_variacao(b), a[0], b[0],
                 time.time() - inicio), flush=True)
    if args.sem_gravar:
        return
    comum = {'premissas': dict(LC.premissas(c),
                                retiradas_m3_s={'berco_106_em_450_m': RETIRADA_106_M3_S,
                                                'navio_108_em_710_m': RETIRADA_108_M3_S},
                                manobra=('a retirada do ponto cai %d%% em rampa de %.1f s a partir de %.2f s'
                                         % (-100 * MULTIPLICADOR, RAMPA_S, LC.TS_EVENTO)))}
    with open(SAIDA_AMOSTRAS, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='Sinais das manobras na linha do cais. Nao diz qual manobra e qual.',
                       base_de_tempo_s=ts, ensaios=ensaios), f, ensure_ascii=False)
    with open(SAIDA_VERDADE, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='VERDADE das manobras na linha do cais. Uso exclusivo do avaliador.',
                       ensaios=verdade), f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_AMOSTRAS, LC.RAIZ))


if __name__ == '__main__':
    main()

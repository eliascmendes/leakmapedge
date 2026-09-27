"""LEAKMAP - manobras operacionais no trecho de teste de 200 m (TSNet).

O trecho de build_model.py (reservatorios nas duas pontas, sensores em 40 e
160 m), com duas tomadas que retiram vazao, cada uma pela sua valvula:

  XV-100   tomada em 100 m, entre os sensores
  XV-190   tomada em 190 m, depois do sensor B

  abertura_100 / abertura_190   a retirada da tomada dobra em 20 ms: onda de
                                QUEDA, a mesma assinatura de um vazamento ali
  fechamento_100 / fechamento_190  a retirada da tomada vai a zero em 20 ms:
                                onda de ALTA

As tomadas sao de acao rapida (solenoide). Com 0,3 s, como na linha do cais,
a onda num trecho de 200 m entre dois reservatorios vira uma rampa lenta e
pequena (1,8 m), desfeita pelas reflexoes enquanto acontece: sem frente, o
detector marca as chegadas em pontos diferentes da rampa.

Atrito: rugosidade real do aco comercial, sem set_roughness, para o regime
partir em equilibrio (02_bancada/ambiente/LEIAME.md, armadilha 7). As
simulacoes de vazamento do trecho (rodada v1) continuam como estao; a bancada
usa so a variacao de carga de cada simulacao.

Grava:
  03_ensaios/amostras/leakmap_amostras_manobras_trecho_200_v1.json
  03_ensaios/verdade_do_cenario/leakmap_verdade_manobras_trecho_200_v1.json

Uso: python manobras_trecho_200.py [--manobras abertura_100] [--sem-gravar]
"""
import argparse
import json
import os
import tempfile
import time

import numpy as np

import build_model as BM
import linha_cais as LC

SAIDA_AMOSTRAS = os.path.join(LC.RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_manobras_trecho_200_v1.json')
SAIDA_VERDADE = os.path.join(LC.RAIZ, '03_ensaios', 'verdade_do_cenario',
                             'leakmap_verdade_manobras_trecho_200_v1.json')

C_SOLICITADA = 1200.0             # a mesma do trecho de 200 m (simular.py)
DT_SOLICITADO = 1e-4
TS_MANOBRA = 0.05
TF = 0.8
RUGOSIDADE_M = 0.046e-3
# valvula de tomada de acao rapida (solenoide): no trecho curto, a onda leva 0,1 s de um sensor ao outro e os
# reservatorios ficam a 40 m deles; uma manobra de 0,3 s, como a da linha do cais, vira uma rampa lenta que as
# reflexoes desfazem enquanto ela acontece, sem frente para o detector marcar
RAMPA_S = 0.02
TOMADAS = {100.0: 0.010, 190.0: 0.010}   # m3/s retirados em cada tomada, em regime
MANOBRAS = {}
for _x in TOMADAS:
    _n = '%d' % _x
    MANOBRAS['abertura_' + _n] = {'s_m': _x, 'multiplicador': 1.0, 'onda': 'queda', 'equipamento': 'XV-' + _n,
                                  'acao': 'abertura', 'dentro': BM.SENSOR_A <= _x <= BM.SENSOR_B}
    MANOBRAS['fechamento_' + _n] = {'s_m': _x, 'multiplicador': -1.0, 'onda': 'alta', 'equipamento': 'XV-' + _n,
                                    'acao': 'fechamento', 'dentro': BM.SENSOR_A <= _x <= BM.SENSOR_B}


def escrever_inp(caminho):
    import wntr
    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.headloss = 'D-W'
    wn.options.time.duration = 0
    wn.add_reservoir('R1', base_head=BM.H_MONTANTE, coordinates=(0.0, 0.0))
    wn.add_reservoir('R2', base_head=BM.H_JUSANTE, coordinates=(BM.L_TRECHO, 0.0))
    nos = sorted(set([BM.SENSOR_A, BM.SENSOR_B] + list(TOMADAS)))
    for x in nos:
        wn.add_junction(BM.nome_no(x), base_demand=TOMADAS.get(x, 0.0), elevation=0.0, coordinates=(x, 0.0))
    seq = ['R1'] + [BM.nome_no(x) for x in nos] + ['R2']
    pos = [0.0] + nos + [BM.L_TRECHO]
    for i in range(len(seq) - 1):
        wn.add_pipe('P%d' % (i + 1), seq[i], seq[i + 1], length=pos[i + 1] - pos[i], diameter=BM.DIAMETRO,
                    roughness=RUGOSIDADE_M, minor_loss=0.0)
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho


def rodar(inp, manobra, pasta):
    import tsnet
    m = MANOBRAS[manobra]
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(C_SOLICITADA)
    tm.set_time(TF, DT_SOLICITADO)
    tm.add_demand_pulse(BM.nome_no(m['s_m']), [10.0 * TF, TS_MANOBRA, RAMPA_S, m['multiplicador']])
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    return tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, manobra))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--manobras', nargs='*', default=list(MANOBRAS))
    ap.add_argument('--sem-gravar', action='store_true')
    args = ap.parse_args()
    pasta = tempfile.mkdtemp(prefix='leakmap_manobras_200_')
    inp = escrever_inp(os.path.join(pasta, 'trecho200.inp'))
    ensaios, verdade, ts = [], [], None
    for k, manobra in enumerate(args.manobras, 1):
        inicio = time.time()
        tm = rodar(inp, manobra, pasta)
        ts = float(tm.time_step)
        t = np.asarray(tm.simulation_timestamps)
        a = np.asarray(tm.get_node(BM.nome_no(BM.SENSOR_A))._head, dtype=float)
        b = np.asarray(tm.get_node(BM.nome_no(BM.SENSOR_B))._head, dtype=float)
        m = MANOBRAS[manobra]
        ident = 'M2-%02d' % k
        pre = t < TS_MANOBRA
        ensaios.append({'id': ident, 'n_pontos': int(len(t)), 'tempo_s': [float(v) for v in t],
                        'canal_A_carga_m': [float(v) for v in a], 'canal_B_carga_m': [float(v) for v in b]})
        verdade.append({'id': ident, 'tem_evento': False, 'manobra': manobra, 'posicao_da_manobra_m': m['s_m'],
                        'dentro_do_trecho_entre_sensores': m['dentro'], 'onda_esperada': m['onda'],
                        'equipamento': m['equipamento'], 'acao': m['acao'], 'instante_da_manobra_s': TS_MANOBRA,
                        'deriva_antes_da_manobra_m': float(max(np.ptp(a[pre]), np.ptp(b[pre])))})
        print('%s %s: A %+.2f m, B %+.2f m, regime A %.2f B %.2f | deriva antes %.1e m (%.0f s)' % (
            ident, manobra, a[np.argmax(np.abs(a - a[0]))] - a[0], b[np.argmax(np.abs(b - b[0]))] - b[0], a[0], b[0],
            verdade[-1]['deriva_antes_da_manobra_m'], time.time() - inicio), flush=True)
    if args.sem_gravar:
        return
    comum = {'premissas': {'trecho': 'build_model.py: %.0f m, %.0f mm, reservatorios de %.0f e %.0f m'
                           % (BM.L_TRECHO, 1000 * BM.DIAMETRO, BM.H_MONTANTE, BM.H_JUSANTE),
                           'tomadas_m3_s': {'%d m' % x: q for x, q in TOMADAS.items()},
                           'rugosidade_m': RUGOSIDADE_M, 'velocidade_de_onda_solicitada_m_s': C_SOLICITADA,
                           'manobras': {k: 'a retirada da tomada muda %+d%% em %.1f s' % (100 * v['multiplicador'],
                                                                                            RAMPA_S)
                                        for k, v in MANOBRAS.items()}}}
    with open(SAIDA_AMOSTRAS, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='Sinais das manobras no trecho de 200 m. Nao diz qual e qual.',
                       base_de_tempo_s=ts, ensaios=ensaios), f, ensure_ascii=False)
    with open(SAIDA_VERDADE, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='VERDADE das manobras no trecho de 200 m. Uso do avaliador e da bancada.',
                       ensaios=verdade), f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_AMOSTRAS, LC.RAIZ))


if __name__ == '__main__':
    main()

"""LEAKMAP - manobras operacionais na rede do cais com manifold (TSNet).

A mesma rede de rede_cais.py, com uma bomba de verdade no modelo (curva de
carga, succao num tanque), como em manobras_cais.py, para que a parada dela
possa ser simulada. Os tres navios retiram vazao no fim dos ramais, cada um
pela sua valvula (XV-104, XV-106, XV-108), 20 m depois do sensor do berco.

  fechamento_104/106/108  a retirada do navio cai a metade em 0,3 s: onda de
                          ALTA vinda de fora da rede monitorada, do lado do
                          sensor daquele berco
  abertura_104/106/108    a retirada do navio dobra em 0,3 s: onda de QUEDA
                          vinda do mesmo lugar, a assinatura de um vazamento
                          alem do sensor do berco
  parada_bomba            a bomba perde rotacao ate parar em 2 s: onda de
                          QUEDA vinda de fora, do lado do sensor A

Grava:
  03_ensaios/amostras/leakmap_amostras_manobras_rede_v1.json
  03_ensaios/verdade_do_cenario/leakmap_verdade_manobras_rede_v1.json

Uso: python manobras_rede.py [--manobras abertura_106 parada_bomba] [--sem-gravar]
"""
import argparse
import json
import os
import tempfile
import time

import numpy as np

import linha_cais as LC
import manobras_cais as MC
import rede_cais as RC
import velocidade_de_onda as VO

SAIDA_AMOSTRAS = os.path.join(LC.RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_manobras_rede_v1.json')
SAIDA_VERDADE = os.path.join(LC.RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_manobras_rede_v1.json')

TF_MANOBRAS = 1.3                 # s; a parada da bomba chega ao sensor mais distante perto de 1,0 s
Q_PROJETO_M3_S = 3 * RC.RETIRADA_POR_NAVIO_M3_S
GANHO_PROJETO_M = LC.H_BOMBA - MC.H_TANQUE
GANHO_SHUTOFF_M = 1.25 * GANHO_PROJETO_M

MANOBRAS = {'parada_bomba': {'tipo': 'bomba', 'trecho': 'tronco', 's_m': LC.POS_BOMBA, 'onda': 'queda',
                             'equipamento': 'B-01', 'acao': 'parada'}}
for _r, _comp in RC.RAMAIS_M.items():
    _berco = _r[-3:]
    _s = _comp + RC.NAVIO_APOS_SENSOR_M
    MANOBRAS['fechamento_' + _berco] = {'tipo': 'retirada', 'trecho': _r, 's_m': _s, 'onda': 'alta',
                                        'multiplicador': -0.5, 'equipamento': 'XV-' + _berco, 'acao': 'fechamento'}
    MANOBRAS['abertura_' + _berco] = {'tipo': 'retirada', 'trecho': _r, 's_m': _s, 'onda': 'queda',
                                      'multiplicador': 1.0, 'equipamento': 'XV-' + _berco, 'acao': 'abertura'}


def curva_da_bomba():
    b = (GANHO_SHUTOFF_M - GANHO_PROJETO_M) / Q_PROJETO_M3_S ** 2
    return [(0.0, GANHO_SHUTOFF_M), (Q_PROJETO_M3_S, GANHO_PROJETO_M),
            (1.4 * Q_PROJETO_M3_S, GANHO_SHUTOFF_M - b * (1.4 * Q_PROJETO_M3_S) ** 2)]


def escrever_inp(caminho, d):
    """A rede sem os nos de vazamento, com tanque, bomba e a descarga no inicio do tronco."""
    import wntr
    wn = LC.rede_base()
    wn.add_reservoir('TANQUE', base_head=MC.H_TANQUE, coordinates=(LC.POS_BOMBA - 20.0, 0.0))
    wn.add_junction('SUCCAO', base_demand=0.0, elevation=0.0, coordinates=(LC.POS_BOMBA - 10.0, 0.0))
    wn.add_curve('CURVA_B01', 'HEAD', curva_da_bomba())
    pts = {'tronco': [LC.POS_BOMBA, 0.0, RC.COMPRIMENTO_TRONCO_M]}
    for r, comp in RC.RAMAIS_M.items():
        pts[r] = [0.0, comp, comp + RC.NAVIO_APOS_SENSOR_M]
    wn.add_junction('MANIFOLD', base_demand=0.0, elevation=0.0, coordinates=(RC.COMPRIMENTO_TRONCO_M, 0.0))
    for k, (trecho, xs) in enumerate(sorted(pts.items())):
        for s in xs:
            n = RC.nome_do_no(trecho, s)
            if n == 'MANIFOLD':
                continue
            navio = trecho != 'tronco' and s == xs[-1]
            wn.add_junction(n, base_demand=RC.RETIRADA_POR_NAVIO_M3_S if navio else 0.0, elevation=0.0,
                            coordinates=((s, 0.0) if trecho == 'tronco' else (RC.COMPRIMENTO_TRONCO_M + s, 50.0 * k)))
        for i in range(len(xs) - 1):
            wn.add_pipe('%s_T%d' % (trecho, i + 1), RC.nome_do_no(trecho, xs[i]), RC.nome_do_no(trecho, xs[i + 1]),
                        length=xs[i + 1] - xs[i], diameter=d, roughness=LC.RUGOSIDADE_M, minor_loss=0.0)
    wn.add_pipe('SUC', 'TANQUE', 'SUCCAO', length=10.0, diameter=d, roughness=LC.RUGOSIDADE_M, minor_loss=0.0)
    wn.add_pump('B01', 'SUCCAO', RC.nome_do_no('tronco', LC.POS_BOMBA), pump_type='HEAD', pump_parameter='CURVA_B01')
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho


def rodar(inp, c, manobra, pasta, tf):
    import tsnet
    m = MANOBRAS[manobra]
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(c)
    tm.set_time(tf, LC.DT_SOLICITADO)
    if m['tipo'] == 'bomba':
        tm.pump_shut_off('B01', [MC.PARADA_DA_BOMBA_S, LC.TS_EVENTO, 0.0, 1])
    else:
        tm.add_demand_pulse(RC.nome_do_no(m['trecho'], m['s_m']),
                            [10.0 * tf, LC.TS_EVENTO, MC.RAMPA_S, m['multiplicador']])
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    return tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, manobra))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--manobras', nargs='*', default=list(MANOBRAS))
    ap.add_argument('--tf', type=float, default=TF_MANOBRAS)
    ap.add_argument('--sem-gravar', action='store_true')
    args = ap.parse_args()
    c = VO.velocidade(LC.PRODUTO, LC.NOMINAL, LC.MATERIAL, LC.SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(LC.NOMINAL, LC.SCHEDULE)
    pasta = tempfile.mkdtemp(prefix='leakmap_manobras_rede_')
    inp = escrever_inp(os.path.join(pasta, 'manobras_rede.inp'), d)
    ensaios, verdade, ts = [], [], None
    for k, manobra in enumerate(args.manobras, 1):
        inicio = time.time()
        tm = rodar(inp, c, manobra, pasta, args.tf)
        ts = float(tm.time_step)
        canais = {s: np.asarray(tm.get_node(RC.nome_do_no(*RC.SENSORES[s]))._head, dtype=float) for s in RC.SENSORES}
        m = MANOBRAS[manobra]
        ident = 'MR-%02d' % k
        pre = np.asarray(tm.simulation_timestamps) < LC.TS_EVENTO
        ensaios.append({'id': ident, 'n_pontos': int(len(tm.simulation_timestamps)),
                        'tempo_s': [float(v) for v in tm.simulation_timestamps],
                        'canais_carga_m': {s: [float(v) for v in x] for s, x in canais.items()}})
        verdade.append({'id': ident, 'tem_evento': False, 'manobra': manobra, 'trecho': m['trecho'], 's_m': m['s_m'],
                        'onda_esperada': m['onda'], 'equipamento': m['equipamento'], 'acao': m['acao'],
                        'instante_da_manobra_s': LC.TS_EVENTO,
                        'maior_variacao_por_sensor_m': {s: float(MC.maior_variacao(x)) for s, x in canais.items()},
                        'deriva_antes_da_manobra_m': float(max(np.ptp(x[pre]) for x in canais.values()))})
        print('%s %s: %s | deriva antes %.1e m (%.0f s)' % (
            ident, manobra, ', '.join('%s %+.2f' % (s, MC.maior_variacao(x)) for s, x in canais.items()),
            verdade[-1]['deriva_antes_da_manobra_m'], time.time() - inicio), flush=True)
    if args.sem_gravar:
        return
    comum = {'premissas': dict(LC.premissas(c), rede=('como rede_cais.py, com bomba no modelo: tanque a %.0f m de '
                                                      'coluna, curva parabolica com %.0f m de ganho em %.3f m3/s'
                                                      % (MC.H_TANQUE, GANHO_PROJETO_M, Q_PROJETO_M3_S)),
                               manobras={k: ('a bomba perde rotacao ate parar em %.1f s' % MC.PARADA_DA_BOMBA_S
                                             if v['tipo'] == 'bomba' else 'a retirada do navio muda %+d%% em %.1f s'
                                             % (100 * v['multiplicador'], MC.RAMPA_S)) for k, v in MANOBRAS.items()}),
             'topologia': RC.topologia(c)}
    with open(SAIDA_AMOSTRAS, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='Sinais das manobras na rede do cais, nos quatro sensores. Nao diz qual e qual.',
                       base_de_tempo_s=ts, ensaios=ensaios), f, ensure_ascii=False)
    with open(SAIDA_VERDADE, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='VERDADE das manobras na rede do cais. Uso exclusivo do avaliador e da bancada.',
                       ensaios=verdade), f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_AMOSTRAS, LC.RAIZ))


if __name__ == '__main__':
    main()

"""LEAKMAP - simulacao transiente TSNet de uma rede do cais com ramais.

A linha de linha_cais.py e reta: dois sensores, um trecho. No cais real a
linha que sai da tancagem chega a um manifold e se divide em ramais, um por
berco. Aqui, com PREMISSAS no lugar do que ainda nao se sabe da instalacao:

                                               ramal 104 (250 m) --[B104]-- navio
                                              /
  bomba --- tronco ---[A]------ 300 m ----- manifold -- ramal 106 (400 m) --[B106]-- navio
   -300 m              0 m                     \
                                               ramal 108 (550 m) --[B108]-- navio

  - tronco e ramais de 8" em aco carbono com diesel, a mesma onda de
    linha_cais.py; a bomba como carga constante de 7 bar;
  - quatro sensores: A no inicio do tronco e um no fim de cada ramal, junto
    ao berco; cada navio a 20 m do sensor do seu ramal, retirando vazao;
  - vazamentos no tronco, em cada ramal (um deles perto do manifold, o caso
    mais dificil) e um antes do sensor A, em dois tamanhos.

Posicao de um ponto da rede: (trecho, s), com s em metros a partir do sensor
A no tronco e a partir do manifold em cada ramal.

Grava:
  03_ensaios/amostras/leakmap_amostras_rede_cais_v1.json   (sinais dos 4 sensores, sem posicao)
  03_ensaios/verdade_do_cenario/leakmap_verdade_rede_cais_v1.json  (posicoes)

Precisa do ambiente com TSNet (02_bancada/ambiente/LEIAME.md). Uso:
  python rede_cais.py [--casos 0 3] [--tamanhos grande]
"""
import argparse
import json
import math
import os
import tempfile
import time

import numpy as np

import linha_cais as LC
import velocidade_de_onda as VO

SAIDA_AMOSTRAS = os.path.join(LC.RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_rede_cais_v1.json')
SAIDA_VERDADE = os.path.join(LC.RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_rede_cais_v1.json')

COMPRIMENTO_TRONCO_M = 300.0              # do sensor A ao manifold
RAMAIS_M = {'ramal_104': 250.0, 'ramal_106': 400.0, 'ramal_108': 550.0}   # do manifold ao sensor do berco
NAVIO_APOS_SENSOR_M = 20.0
RETIRADA_POR_NAVIO_M3_S = 0.020           # ~72 m3/h por navio, os tres carregando
SENSORES = {'A': ('tronco', 0.0), 'B104': ('ramal_104', RAMAIS_M['ramal_104']),
            'B106': ('ramal_106', RAMAIS_M['ramal_106']), 'B108': ('ramal_108', RAMAIS_M['ramal_108'])}
# (trecho, s): no tronco a partir do sensor A; nos ramais a partir do manifold
VAZAMENTOS = [('tronco', 150.0), ('ramal_104', 100.0), ('ramal_104', 200.0), ('ramal_106', 30.0),
              ('ramal_106', 250.0), ('ramal_108', 150.0), ('ramal_108', 450.0), ('tronco', -150.0)]
TAMANHOS = LC.TAMANHOS


def nome(trecho, s):
    return ('%s_%d' % (trecho, int(round(s)))).replace('-', 'M')


def pontos_por_trecho():
    """Nos de cada trecho: sensores, pontos de vazamento, manifold e fim do ramal."""
    pts = {'tronco': {LC.POS_BOMBA, 0.0, COMPRIMENTO_TRONCO_M}}
    for r, comp in RAMAIS_M.items():
        pts[r] = {0.0, comp, comp + NAVIO_APOS_SENSOR_M}
    for trecho, s in VAZAMENTOS:
        pts[trecho].add(s)
    return {k: sorted(v) for k, v in pts.items()}


def nome_do_no(trecho, s):
    """O manifold e um no so; a ponta de cada ramal em s = 0 e o manifold."""
    if (trecho == 'tronco' and s == COMPRIMENTO_TRONCO_M) or (trecho != 'tronco' and s == 0.0):
        return 'MANIFOLD'
    return nome(trecho, s)


def escrever_inp(caminho, d):
    import wntr
    wn = LC.rede_base()
    pts = pontos_por_trecho()
    wn.add_reservoir('BOMBA', base_head=LC.H_BOMBA, coordinates=(LC.POS_BOMBA, 0.0))
    wn.add_junction('MANIFOLD', base_demand=0.0, elevation=0.0, coordinates=(COMPRIMENTO_TRONCO_M, 0.0))
    for k, (trecho, xs) in enumerate(sorted(pts.items())):
        for s in xs:
            n = nome_do_no(trecho, s)
            if n == 'MANIFOLD' or (trecho == 'tronco' and s == LC.POS_BOMBA):
                continue
            navio = trecho != 'tronco' and s == xs[-1]
            wn.add_junction(n, base_demand=RETIRADA_POR_NAVIO_M3_S if navio else 0.0, elevation=0.0,
                            coordinates=((s, 0.0) if trecho == 'tronco' else (COMPRIMENTO_TRONCO_M + s, 50.0 * k)))
        for i in range(len(xs) - 1):
            a = 'BOMBA' if trecho == 'tronco' and i == 0 else nome_do_no(trecho, xs[i])
            wn.add_pipe('%s_T%d' % (trecho, i + 1), a, nome_do_no(trecho, xs[i + 1]), length=xs[i + 1] - xs[i],
                        diameter=d, roughness=LC.RUGOSIDADE_M, minor_loss=0.0)
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho


def rodar(inp, c, vazamento=None, coeficiente=None, pasta='.'):
    import tsnet
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(c)
    tm.set_time(LC.TF, LC.DT_SOLICITADO)
    if vazamento is not None:
        tm.add_burst(nome_do_no(*vazamento), LC.TS_EVENTO, LC.TC_EVENTO, coeficiente)
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    rotulo = 'regime' if vazamento is None else '%s_%g' % (nome_do_no(*vazamento), coeficiente)
    return tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, 'rede_' + rotulo))


def serie(tm, sensor):
    return np.asarray(tm.get_node(nome_do_no(*SENSORES[sensor]))._head, dtype=float)


def velocidade_efetiva(tm):
    """Velocidade efetiva na parte monitorada (sem o tubo da bomba), lida de volta do solucionador:
    o TSNet ajusta a onda de cada tubo para caber no passo de tempo."""
    tempo = comp = 0.0
    for _, tubo in tm.pipes():
        if tubo.start_node.name == 'BOMBA':
            continue
        tempo += tubo.length / tubo.wavev
        comp += tubo.length
    return comp / tempo


def topologia(c):
    """O que o detector sabe da rede: trechos, sensores e a velocidade da onda."""
    return {
        'descricao': ('arvore com um manifold: o tronco vai do sensor A (s = 0) ao manifold (s = %.0f m); '
                      'cada ramal vai do manifold (s = 0) ao sensor do berco' % COMPRIMENTO_TRONCO_M),
        'no_de_juncao': 'manifold',
        'trechos': dict({'tronco': {'comprimento_monitorado_m': COMPRIMENTO_TRONCO_M,
                                    'juncao_em_s_m': COMPRIMENTO_TRONCO_M}},
                        **{r: {'comprimento_monitorado_m': comp, 'juncao_em_s_m': 0.0}
                           for r, comp in RAMAIS_M.items()}),
        'sensores': {k: {'trecho': t, 's_m': s} for k, (t, s) in SENSORES.items()},
        'velocidade_de_onda_m_s': c,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--casos', nargs='*', type=int, default=list(range(len(VAZAMENTOS))))
    ap.add_argument('--tamanhos', nargs='*', default=list(TAMANHOS))
    args = ap.parse_args()

    import wntr
    c = VO.velocidade(LC.PRODUTO, LC.NOMINAL, LC.MATERIAL, LC.SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(LC.NOMINAL, LC.SCHEDULE)
    pasta = tempfile.mkdtemp(prefix='leakmap_rede_')
    inp = escrever_inp(os.path.join(pasta, 'rede_cais.inp'), d)

    inicio = time.time()
    regime = rodar(inp, c, pasta=pasta)
    t = np.asarray(regime.simulation_timestamps, dtype=float)
    ts = float(regime.time_step)
    c_ef = velocidade_efetiva(regime)
    cargas = {k: float(serie(regime, k)[0]) for k in SENSORES}
    print('regime: passo %.6e s, c efetiva %.2f m/s, cargas %s (%.0f s)'
          % (ts, c_ef, ', '.join('%s %.1f m' % kv for kv in cargas.items()), time.time() - inicio), flush=True)

    def canais(tm):
        return {k: [float(v) for v in serie(tm, k)] for k in SENSORES}

    ensaios = [{'id': 'RC-REGIME', 'n_pontos': int(len(t)), 'tempo_s': [float(v) for v in t],
                'canais_carga_m': canais(regime)}]
    verdade = [{'id': 'RC-REGIME', 'tem_evento': False, 'trecho_real': None, 's_real_m': None,
                'instante_do_evento_s': None, 'evento': 'nenhum: regime permanente'}]
    k = 0
    for tamanho in args.tamanhos:
        for i in args.casos:
            trecho, s = VAZAMENTOS[i]
            k += 1
            inicio = time.time()
            tm = rodar(inp, c, (trecho, s), TAMANHOS[tamanho], pasta)
            identificador = 'RC-%02d' % k
            ch = canais(tm)
            ensaios.append({'id': identificador, 'n_pontos': int(len(t)),
                            'tempo_s': [float(v) for v in tm.simulation_timestamps], 'canais_carga_m': ch})
            quedas = {n: float(v[0] - min(v)) for n, v in ch.items()}
            verdade.append({'id': identificador, 'tem_evento': True, 'trecho_real': trecho, 's_real_m': s,
                            'tamanho_do_vazamento': tamanho, 'coeficiente_emissor': TAMANHOS[tamanho],
                            'dentro_da_rede_monitorada': not (trecho == 'tronco' and s < 0.0),
                            'instante_do_evento_s': LC.TS_EVENTO, 'queda_por_sensor_m': quedas})
            print('%s: vazamento %s em %s, s = %.0f m | quedas %s (%.0f s)'
                  % (identificador, tamanho, trecho, s, ', '.join('%s %.2f' % kv for kv in quedas.items()),
                     time.time() - inicio), flush=True)

    comum = {
        'ferramenta': 'TSNet 0.3.1 / wntr %s / numpy %s' % (wntr.__version__, np.__version__),
        'premissas': dict(LC.premissas(c),
                          rede=('tronco de %.0f m do sensor A ao manifold, ramais de %s m ate os sensores dos '
                                'bercos, navios a %.0f m depois de cada sensor retirando %.3f m3/s cada'
                                % (COMPRIMENTO_TRONCO_M, ', '.join('%.0f' % v for v in RAMAIS_M.values()),
                                   NAVIO_APOS_SENSOR_M, RETIRADA_POR_NAVIO_M3_S))),
        'topologia': topologia(c_ef),
        'velocidade_de_onda_korteweg_m_s': c,
        'passo_de_tempo_efetivo_s': ts,
    }
    with open(SAIDA_AMOSTRAS, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao=('Sinais da simulacao da rede do cais com ramais, nos quatro sensores. '
                                          'Nao contem a posicao do vazamento.'),
                       base_de_tempo_s=ts, unidades={'carga': 'm de coluna de %s' % LC.PRODUTO},
                       ensaios=ensaios), f, ensure_ascii=False)
    with open(SAIDA_VERDADE, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao=('VERDADE DO CENARIO da rede do cais. Uso exclusivo do avaliador. '
                                          'Nunca entra no detector.'),
                       ensaios=verdade), f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_AMOSTRAS, LC.RAIZ))
    print('escrito: %s' % os.path.relpath(SAIDA_VERDADE, LC.RAIZ))


if __name__ == '__main__':
    main()

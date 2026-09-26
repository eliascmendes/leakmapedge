"""LEAKMAP - manobras operacionais na linha de produto do cais (TSNet).

A mesma linha de linha_cais.py, com os dois pontos de carregamento como
retiradas de vazao, para gerar as ondas que uma operacao normal produz e que
nao podem virar alarme de vazamento:

                                             berco 106 (retirada)
                                                    |
  tanque -> bomba --- rack ---[A]--- 104 ------- 450 m ---[B]--- 710 m: navio do berco 108 (retirada)
            -300 m             0 m                        700 m

  fechamento_navio  a retirada do navio do 108 cai a metade em 0,3 s (a
                    valvula do fim de carregamento fechando): onda de ALTA
                    vinda de fora do trecho, do lado do sensor B;
  fechamento_106    a retirada do berco 106 cai a metade em 0,3 s: onda de
                    ALTA nascida DENTRO do trecho, em 450 m, onde um
                    vazamento tambem seria localizado. So a polaridade
                    separa uma coisa da outra.
  abertura_106      a retirada do berco 106 dobra em 0,3 s (a valvula do
                    ramal abrindo para comecar um carregamento): onda de
                    QUEDA nascida em 450 m, a mesma assinatura de um
                    vazamento ali. Nem a polaridade nem a posicao separam;
                    so o cadastro de equipamentos com o registro da operacao
                    (07_servico/cadastro.py);
  parada_bomba      a bomba desliga e perde rotacao em 2 s (rotacao linear
                    ate zero): onda de QUEDA vinda de fora do trecho, do lado
                    do sensor A, como um vazamento antes do rack.

A bomba aqui e uma bomba de verdade no modelo (curva de carga, succao num
tanque), e nao uma carga constante como em linha_cais.py, para que a parada
possa ser simulada. As outras manobras rodam na mesma rede.

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

  03_ensaios/amostras/leakmap_operacoes_manobras_cais_v1.json
      o registro de operacao que o sistema de controle da planta daria: qual
      equipamento foi operado e quando, por ensaio. E entrada legitima do
      produto (07_servico/cadastro.py), como o sinal dos sensores.

Uso: python manobras_cais.py [--manobras fechamento_106] [--tf 1.2] [--sem-gravar] [--so-operacoes]
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
SAIDA_OPERACOES = os.path.join(LC.RAIZ, '03_ensaios', 'amostras', 'leakmap_operacoes_manobras_cais_v1.json')

POS_NAVIO_108 = 710.0
RETIRADA_108_M3_S = 0.040        # ~145 m3/h no navio do 108
RETIRADA_106_M3_S = 0.015        # ~55 m3/h no berco 106, carregando ao mesmo tempo
H_TANQUE = 5.0                   # nivel do tanque de succao, m de coluna
POS_TANQUE = LC.POS_BOMBA - 20.0
# curva da bomba: parabola com a carga de projeto (7 bar na descarga) na vazao das duas retiradas
Q_PROJETO_M3_S = RETIRADA_108_M3_S + RETIRADA_106_M3_S
GANHO_PROJETO_M = LC.H_BOMBA - H_TANQUE
GANHO_SHUTOFF_M = 1.25 * GANHO_PROJETO_M
RAMPA_S = 0.3
PARADA_DA_BOMBA_S = 2.0          # tempo ate a rotacao zerar
TF_MANOBRAS = 1.2                # s; a parada da bomba chega em B perto de 0,92 s
# tipo 'retirada': a retirada do no muda pelo multiplicador, em rampa; tipo 'bomba': a bomba para.
# 'equipamento' e o nome no cadastro de exemplo de 07_servico/cadastro.py
MANOBRAS = {
    'fechamento_navio': {'posicao_m': POS_NAVIO_108, 'onda': 'alta', 'dentro_do_trecho': False,
                         'tipo': 'retirada', 'multiplicador': -0.5, 'equipamento': 'XV-108',
                         'acao': 'fechamento'},
    'fechamento_106': {'posicao_m': LC.POS_BERCO_106, 'onda': 'alta', 'dentro_do_trecho': True,
                       'tipo': 'retirada', 'multiplicador': -0.5, 'equipamento': 'XV-106',
                       'acao': 'fechamento'},
    'abertura_106': {'posicao_m': LC.POS_BERCO_106, 'onda': 'queda', 'dentro_do_trecho': True,
                     'tipo': 'retirada', 'multiplicador': 1.0, 'equipamento': 'XV-106',
                     'acao': 'abertura'},
    'parada_bomba': {'posicao_m': LC.POS_BOMBA, 'onda': 'queda', 'dentro_do_trecho': False,
                     'tipo': 'bomba', 'equipamento': 'B-01', 'acao': 'parada'},
}


def curva_da_bomba():
    """Tres pontos da parabola H = H0 - b Q^2 (o TSNet so aceita curva de um ou tres pontos)."""
    b = (GANHO_SHUTOFF_M - GANHO_PROJETO_M) / Q_PROJETO_M3_S ** 2
    return [(0.0, GANHO_SHUTOFF_M), (Q_PROJETO_M3_S, GANHO_PROJETO_M),
            (1.4 * Q_PROJETO_M3_S, GANHO_SHUTOFF_M - b * (1.4 * Q_PROJETO_M3_S) ** 2)]


def escrever_inp(caminho, d):
    import wntr
    wn = LC.rede_base()
    wn.add_reservoir('TANQUE', base_head=H_TANQUE, coordinates=(POS_TANQUE, 0.0))
    wn.add_junction('SUCCAO', base_demand=0.0, elevation=0.0, coordinates=(POS_TANQUE + 10.0, 0.0))
    wn.add_curve('CURVA_B01', 'HEAD', curva_da_bomba())
    xs = sorted(set([LC.POS_BOMBA, LC.POS_SENSOR_A, LC.POS_BERCO_104, LC.POS_BERCO_106, LC.POS_SENSOR_B,
                     POS_NAVIO_108]))
    retirada = {LC.POS_BERCO_106: RETIRADA_106_M3_S, POS_NAVIO_108: RETIRADA_108_M3_S}
    for x in xs:
        wn.add_junction(LC.nome_no(x), base_demand=retirada.get(x, 0.0), elevation=0.0, coordinates=(x, 0.0))
    wn.add_pipe('SUC', 'TANQUE', 'SUCCAO', length=10.0, diameter=d, roughness=LC.RUGOSIDADE_M, minor_loss=0.0)
    wn.add_pump('B01', 'SUCCAO', LC.nome_no(LC.POS_BOMBA), pump_type='HEAD', pump_parameter='CURVA_B01')
    for i in range(len(xs) - 1):
        wn.add_pipe('T%d' % (i + 1), LC.nome_no(xs[i]), LC.nome_no(xs[i + 1]), length=xs[i + 1] - xs[i],
                    diameter=d, roughness=LC.RUGOSIDADE_M, minor_loss=0.0)
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho


def rodar(inp, c, manobra, pasta, tf):
    import tsnet
    m = MANOBRAS[manobra]
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(c)
    tm.set_time(tf, LC.DT_SOLICITADO)
    if m['tipo'] == 'bomba':
        # [duracao, inicio, abertura final, expoente]: rotacao linear ate zero
        tm.pump_shut_off('B01', [PARADA_DA_BOMBA_S, LC.TS_EVENTO, 0.0, 1])
    else:
        # pulso mais longo que a simulacao: na pratica, um degrau com rampa
        tm.add_demand_pulse(LC.nome_no(m['posicao_m']), [10.0 * tf, LC.TS_EVENTO, RAMPA_S, m['multiplicador']])
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    return tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, manobra))


def gravar_operacoes(verdade):
    """Registro de operacao por ensaio, no instante em que a manobra comecou."""
    operacoes = {v['id']: [{'equipamento': MANOBRAS[v['manobra']]['equipamento'],
                            'acao': MANOBRAS[v['manobra']]['acao'],
                            'instante_s': v['instante_da_manobra_s'],
                            'origem': 'sistema de controle (simulado)'}] for v in verdade}
    with open(SAIDA_OPERACOES, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Registro de operacao dos equipamentos durante os ensaios de manobra, como o '
                                 'sistema de controle da planta daria. Instantes na base de tempo do ensaio.'),
                   'operacoes_por_ensaio': operacoes}, f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_OPERACOES, LC.RAIZ))


def maior_variacao(x):
    subida, descida = x.max() - x[0], x[0] - x.min()
    return subida if subida >= descida else -descida


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--manobras', nargs='*', default=list(MANOBRAS))
    ap.add_argument('--tf', type=float, default=TF_MANOBRAS)
    ap.add_argument('--sem-gravar', action='store_true')
    ap.add_argument('--so-operacoes', action='store_true', help='regrava so o registro de operacao')
    args = ap.parse_args()
    if args.so_operacoes:
        with open(SAIDA_VERDADE, encoding='utf-8') as f:
            gravar_operacoes(json.load(f)['ensaios'])
        return
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
                        'equipamento': MANOBRAS[manobra]['equipamento'],
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
                                bomba=('bomba centrifuga em %.0f m, succao num tanque a %.0f m de coluna, curva '
                                       'parabolica com %.0f m de ganho em %.3f m3/s e %.0f m sem vazao'
                                       % (LC.POS_BOMBA, H_TANQUE, GANHO_PROJETO_M, Q_PROJETO_M3_S,
                                          GANHO_SHUTOFF_M)),
                                manobras={k: ('a bomba perde rotacao ate parar em %.1f s' % PARADA_DA_BOMBA_S
                                              if m['tipo'] == 'bomba' else
                                              'a retirada do no muda %+d%% em rampa de %.1f s'
                                              % (100 * m['multiplicador'], RAMPA_S))
                                          for k, m in MANOBRAS.items()},
                                instante_das_manobras_s=LC.TS_EVENTO)}
    with open(SAIDA_AMOSTRAS, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='Sinais das manobras na linha do cais. Nao diz qual manobra e qual.',
                       base_de_tempo_s=ts, ensaios=ensaios), f, ensure_ascii=False)
    with open(SAIDA_VERDADE, 'w', encoding='utf-8') as f:
        json.dump(dict(comum, descricao='VERDADE das manobras na linha do cais. Uso exclusivo do avaliador.',
                       ensaios=verdade), f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA_AMOSTRAS, LC.RAIZ))
    gravar_operacoes(verdade)


if __name__ == '__main__':
    main()

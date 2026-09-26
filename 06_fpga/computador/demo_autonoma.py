"""LEAKMAP - demonstracao autonoma na placa: modelo de referencia em Python.

Na demonstracao, a propria FPGA gera os sinais dos dois sensores para uma
posicao de rompimento escolhida nos botoes, entrega as amostras aos dois
detectores no ritmo da amostragem, marca as chegadas e calcula a posicao, sem
computador. Este arquivo e a referencia que o Verilog tem de igualar:

  - o gerador de sinais (sinais()), bit a bit igual a rtl/leakmap_demo.v;
  - o mesmo detector inteiro da placa (placa_referencia.DetectorInteiro);
  - a conta da posicao em aritmetica inteira, sem divisao.

O sinal e sintetico e simples, nao e a hidraulica do TSNet: carga constante,
e a partir da chegada da onda em cada sensor, uma queda em rampa de
QUEDA_CODIGOS em RAMPA_AMOSTRAS amostras. A chegada em cada sensor sai da
distancia ate o vazamento e da velocidade de onda da matriz. O ruido, ligado
na chave SW1, vem de um registrador de deslocamento com realimentacao (LFSR)
por canal.

Autoteste dos canais: nas chaves SW2 e SW3 a placa estraga um sensor de
proposito a partir da amostra AMOSTRA_DA_FALHA, antes da onda chegar. SW2
rompe o cabo do sensor A (codigo 0); SW3 trava o transmissor B (repete o
ultimo codigo). O mesmo autoteste do cenario B (placa_referencia.SaudeDoCanal,
rtl/leakmap_saude.v) acompanha os dois canais, e a placa mostra a falha em vez
da posicao. A faixa e a do transmissor da demonstracao (a palavra inteira,
sem os extremos), o salto e meia faixa, e o congelamento so e conferido com
ruido: sem ruido o sinal e ideal e fica constante de verdade, como na matriz.

Uso:
  python demo_autonoma.py              grava rtl/leakmap_demo_parametros.vh e
                                       mostra o erro em todas as posicoes
  python demo_autonoma.py --vetores ARQ
                                       grava tambem o esperado do testbench
"""
import argparse
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import detector_ponto_fixo as PF  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import protocolo as PR  # noqa: E402
import selo as SE  # noqa: E402

PARAMETROS_VH = os.path.join(RAIZ, '06_fpga', 'rtl', 'leakmap_demo_parametros.vh')

SENSOR_A_M, SENSOR_B_M = 40, 160
POSICAO_MIN_M, POSICAO_MAX_M, POSICAO_INICIAL_M = 40, 160, 80
N_AMOSTRAS = 512              # 0,2 s de sinal; a chegada mais tardia e na amostra 399
AMOSTRA_DO_EVENTO = 150         # a abertura do vazamento, na amostra 150
BASE_CODIGOS = 58000            # 58 m de carga, degrau de 1 mm
QUEDA_CODIGOS = 400             # 0,4 m de queda
RAMPA_AMOSTRAS = 8              # a queda leva 8 amostras
DEGRAU_M = 1e-3
SEMENTE_A, SEMENTE_B = 0xACE1, 0x1D2F
POLINOMIO = 0xB400              # LFSR de Galois de 16 bits, periodo maximo
AMOSTRA_DA_FALHA = 100          # o sensor estragado de proposito falha aqui, antes da onda
FALHA_A_ROMPIDO, FALHA_B_TRAVADO = 1, 2
POSICOES_COM_FALHA = (60, 80, 130)


def constantes():
    """Tudo que o Verilog precisa, calculado a partir da matriz de ensaios."""
    pacote = json.load(open(SE.PACOTE, encoding='utf-8'))
    ts = float(pacote['amostragem']['periodo_de_amostragem_s'])
    par = pacote['ensaios'][0]['parametros_do_detector']
    c = float(par['velocidade_de_onda_m_s'])
    cal = D.calibracao_padrao()
    p = PF.parametros_inteiros(cal, ts, DEGRAU_M, pacote['escala']['resolucao_declarada_m'])
    return {
        'ts': ts, 'c': c, 'parametros': p,
        # amostras de atraso por metro de distancia ate o sensor, em Q16
        'amostras_por_metro_q16': round(65536 / (c * ts)),
        # metros de posicao por amostra de diferenca entre as chegadas, em Q16
        'metros_por_amostra_q16': round(65536 * c * ts / 2),
    }


def lfsr(estado):
    """Um passo do LFSR de Galois de 16 bits."""
    saida = estado & 1
    estado >>= 1
    if saida:
        estado ^= POLINOMIO
    return estado


def atraso(distancia_m, k):
    return (distancia_m * k['amostras_por_metro_q16'] + 32768) >> 16


def limites_de_saude(ruido):
    return {'limite_congelado': PP.SEQUENCIA_DE_CONGELAMENTO if ruido else 0,
            'codigo_minimo': 1, 'codigo_maximo': 0xFFFE, 'limite_salto': 0x7FFF}


def sinais(posicao_m, ruido, k, falha=0):
    """Codigos dos canais A e B, amostra a amostra, iguais aos do Verilog."""
    chegada_a = AMOSTRA_DO_EVENTO + atraso(abs(posicao_m - SENSOR_A_M), k)
    chegada_b = AMOSTRA_DO_EVENTO + atraso(abs(SENSOR_B_M - posicao_m), k)
    passo = QUEDA_CODIGOS // RAMPA_AMOSTRAS
    la, lb = SEMENTE_A, SEMENTE_B
    a, b = [], []
    for i in range(N_AMOSTRAS):
        queda_a = passo * min(max(i - chegada_a, 0), RAMPA_AMOSTRAS)
        queda_b = passo * min(max(i - chegada_b, 0), RAMPA_AMOSTRAS)
        ra = ((la & 7) - 3) if ruido else 0
        rb = ((lb & 7) - 3) if ruido else 0
        a.append(0 if falha & FALHA_A_ROMPIDO and i >= AMOSTRA_DA_FALHA else BASE_CODIGOS - queda_a + ra)
        b.append(b[-1] if falha & FALHA_B_TRAVADO and i > AMOSTRA_DA_FALHA else BASE_CODIGOS - queda_b + rb)
        la, lb = lfsr(la), lfsr(lb)
    return a, b, chegada_a, chegada_b


def posicao_estimada(chegada_a, chegada_b, k):
    """x = 100 m + (chegada_A - chegada_B) * c * ts / 2, arredondado ao metro, em inteiros."""
    delta = chegada_a - chegada_b
    x = 100 + ((delta * k['metros_por_amostra_q16'] + 32768) >> 16)
    return max(0, min(255, x))


def rodar(posicao_m, ruido, k, falha=0):
    a, b, _, _ = sinais(posicao_m, ruido, k, falha)
    det_a, det_b = PLACA.DetectorInteiro(k['parametros']), PLACA.DetectorInteiro(k['parametros'])
    saude_a, saude_b = PLACA.SaudeDoCanal(), PLACA.SaudeDoCanal()
    for va, vb in zip(a, b):
        det_a.amostra(va)
        det_b.amostra(vb)
        saude_a.amostra(va)
        saude_b.amostra(vb)
    limites = limites_de_saude(ruido)
    ra, rb = det_a.resultado(), det_b.resultado()
    detectou_a, detectou_b = bool(ra['bandeiras'] & 1), bool(rb['bandeiras'] & 1)
    ch_a = ra['indice_de_chegada'] if detectou_a else 0
    ch_b = rb['indice_de_chegada'] if detectou_b else 0
    estimada = posicao_estimada(ch_a, ch_b, k) if detectou_a and detectou_b else 0
    return {'detectou_a': detectou_a, 'chegada_a': ch_a, 'detectou_b': detectou_b, 'chegada_b': ch_b,
            'posicao_estimada_m': estimada,
            'saude_a': PR.bandeiras_de_saude(saude_a.estatisticas, limites),
            'saude_b': PR.bandeiras_de_saude(saude_b.estatisticas, limites)}


def gravar_parametros(k, caminho=PARAMETROS_VH):
    p = k['parametros']
    linhas = [
        '// Gerado por 06_fpga/computador/demo_autonoma.py. Nao editar a mao.',
        '// Constantes da demonstracao autonoma (rtl/leakmap_demo.v): gerador de sinais,',
        '// conta da posicao e configuracao do detector, a mesma do modelo em Python.',
        'localparam integer DEMO_N_AMOSTRAS       = %d;' % N_AMOSTRAS,
        'localparam integer DEMO_AMOSTRA_EVENTO   = %d;' % AMOSTRA_DO_EVENTO,
        'localparam integer DEMO_BASE             = %d;' % BASE_CODIGOS,
        'localparam integer DEMO_PASSO_QUEDA      = %d;' % (QUEDA_CODIGOS // RAMPA_AMOSTRAS),
        'localparam integer DEMO_RAMPA            = %d;' % RAMPA_AMOSTRAS,
        'localparam integer DEMO_SENSOR_A         = %d;' % SENSOR_A_M,
        'localparam integer DEMO_SENSOR_B         = %d;' % SENSOR_B_M,
        'localparam integer DEMO_AMOSTRAS_POR_M   = %d;   // Q16' % k['amostras_por_metro_q16'],
        'localparam integer DEMO_METROS_POR_AMOS  = %d;   // Q16' % k['metros_por_amostra_q16'],
        "localparam [15:0]  DEMO_SEMENTE_A        = 16'h%04X;" % SEMENTE_A,
        "localparam [15:0]  DEMO_SEMENTE_B        = 16'h%04X;" % SEMENTE_B,
        "localparam [15:0]  DEMO_POLINOMIO        = 16'h%04X;" % POLINOMIO,
        'localparam integer DEMO_AMOSTRA_FALHA    = %d;' % AMOSTRA_DA_FALHA,
        "localparam [15:0]  DEMO_SAUDE_CONGELADO  = 16'd%d;   // so com ruido" % PP.SEQUENCIA_DE_CONGELAMENTO,
        "localparam [15:0]  DEMO_SAUDE_MINIMO     = 16'd%d;" % limites_de_saude(True)['codigo_minimo'],
        "localparam [15:0]  DEMO_SAUDE_MAXIMO     = 16'd%d;" % limites_de_saude(True)['codigo_maximo'],
        "localparam [15:0]  DEMO_SAUDE_SALTO      = 16'd%d;" % limites_de_saude(True)['limite_salto'],
        "localparam [31:0]  DEMO_CFG_COEF         = 32'd%d;" % p['coeficiente_do_filtro'],
        "localparam [7:0]   DEMO_CFG_FRACAO       = 8'd%d;" % p['fracao'],
        "localparam [7:0]   DEMO_CFG_DESLOCA      = 8'd%d;" % p['desloca_energia'],
        "localparam [7:0]   DEMO_CFG_N_CURTA      = 8'd%d;" % p['n_curta'],
        "localparam [7:0]   DEMO_CFG_N_GUARDA     = 8'd%d;" % p['n_guarda'],
        "localparam [7:0]   DEMO_CFG_N_LONGA      = 8'd%d;" % p['n_longa'],
        "localparam [15:0]  DEMO_CFG_LIMIAR       = 16'd%d;" % p['limiar_de_razao'],
        "localparam [15:0]  DEMO_CFG_K2           = 16'd%d;" % p['k2_faixa_de_ruido'],
        "localparam [31:0]  DEMO_CFG_PISO         = 32'd%d;" % p['piso_em_ye'],
        "localparam [31:0]  DEMO_CFG_PISO_ENERGIA = 32'd%d;" % p['piso_energia_por_amostra'],
        "localparam integer DEMO_PERIODO_S_NS     = %d;   // periodo de amostragem, em ns" % round(k['ts'] * 1e9),
    ]
    with open(caminho, 'w', newline='\n') as f:
        f.write('\n'.join(linhas) + '\n')


def varrer(k):
    """Todas as posicoes com os sensores bons, e algumas com cada sensor estragado."""
    linhas = []
    for falha in (0, FALHA_A_ROMPIDO, FALHA_B_TRAVADO, FALHA_A_ROMPIDO | FALHA_B_TRAVADO):
        for ruido in (False, True):
            posicoes = range(POSICAO_MIN_M, POSICAO_MAX_M + 1) if not falha else POSICOES_COM_FALHA
            for x in posicoes:
                r = rodar(x, ruido, k, falha)
                r.update({'posicao_m': x, 'ruido': ruido, 'falha': falha})
                linhas.append(r)
    return linhas


def autoteste_errado(l):
    """Sensor bom acusado, ou sensor estragado sem acusacao (travado sem ruido nao se distingue)."""
    if not l['falha']:
        return bool(l['saude_a'] or l['saude_b'])
    a_ok = not l['falha'] & FALHA_A_ROMPIDO or l['saude_a']
    b_ok = not l['falha'] & FALHA_B_TRAVADO or l['saude_b'] or not l['ruido']
    return not (a_ok and b_ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--vetores', help='grava o esperado do testbench neste arquivo')
    ap.add_argument('--parametros', default=PARAMETROS_VH)
    args = ap.parse_args()
    k = constantes()
    gravar_parametros(k, args.parametros)
    linhas = varrer(k)
    boas = [l for l in linhas if not l['falha']]
    sem = [l for l in boas if not (l['detectou_a'] and l['detectou_b'])]
    erros = [abs(l['posicao_estimada_m'] - l['posicao_m']) for l in boas if l['detectou_a'] and l['detectou_b']]
    errados = [l for l in linhas if autoteste_errado(l)]
    print('parametros: %s' % os.path.relpath(args.parametros, RAIZ))
    print('posicoes de %d a %d m, com e sem ruido: %d casos, %d sem as duas chegadas, erro maximo %d m'
          % (POSICAO_MIN_M, POSICAO_MAX_M, len(boas), len(sem), max(erros) if erros else -1))
    print('autoteste: %d casos com sensor estragado de proposito; %d erros do autoteste'
          % (len(linhas) - len(boas), len(errados)))
    if args.vetores:
        with open(args.vetores, 'w', newline='\n') as f:
            for l in linhas:
                f.write('%d %d %d %d %d %d %d %d %d %d\n'
                        % (l['posicao_m'], l['ruido'], l['falha'], l['detectou_a'], l['chegada_a'],
                           l['detectou_b'], l['chegada_b'], l['posicao_estimada_m'], l['saude_a'], l['saude_b']))
        print('esperado do testbench: %s (%d linhas)' % (args.vetores, len(linhas)))
    if sem:
        raise SystemExit('a demonstracao nao detectou nos dois canais em %d casos' % len(sem))
    if errados:
        raise SystemExit('o autoteste da demonstracao errou em %d casos' % len(errados))


if __name__ == '__main__':
    main()

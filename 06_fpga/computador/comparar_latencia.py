"""LEAKMAP - latencia de declaracao: o mesmo detector no notebook e na FPGA.

Mede, nos ensaios com evento da matriz, quanto tempo passa entre a hora em que
a amostra do cruzamento chega e o evento ser declarado, com o mesmo detector em
aritmetica inteira dos dois lados:

  notebook  DetectorInteiro (placa_referencia.py), em Python, recebendo uma
            amostra por periodo de amostragem. A espera ate a hora de cada
            amostra e ativa (laco ocupado), o melhor caso para a CPU: o que
            sobra de variacao vem do sistema operacional e do proprio Python.
  FPGA      o mesmo ensaio executado em tempo real na placa
            (EXECUTAR_TEMPO_REAL); o proprio circuito conta os ciclos da
            entrega da amostra do cruzamento ate a declaracao (TEMPOS).

Cada ensaio roda `--repeticoes` vezes dos dois lados. O que se compara e a
variacao, nao so a media: num computador comum a mesma conta demora mais ou
menos conforme o que mais esta rodando; no circuito, o numero de ciclos e fixo.
O detector em Python e mais lento que um em C; a comparacao de velocidade
bruta fica registrada, mas o ponto e a variacao.

Uso:
  python comparar_latencia.py --sem-fpga                 so o notebook
  python comparar_latencia.py --jtag                     notebook e FPGA pelo cabo de gravacao
  python comparar_latencia.py --jtag --repeticoes 20 --ensaios MX-001 MX-021

Grava 06_fpga/resultados/leakmap_latencia_fpga_e_cpu_v1.json.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import hospedeiro as HO  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import registro_b as RB  # noqa: E402
import selo as SE  # noqa: E402
import transporte as TR  # noqa: E402

SAIDA = os.path.join(RAIZ, '06_fpga', 'resultados', 'leakmap_latencia_fpga_e_cpu_v1.json')


def resumo(valores):
    if not valores:
        return None
    v = sorted(valores)
    return {
        'n': len(v), 'min': v[0], 'mediana': statistics.median(v),
        'p99': v[min(len(v) - 1, int(round(0.99 * (len(v) - 1))))], 'max': v[-1],
        'desvio_padrao': statistics.pstdev(v),
    }


def cpu_em_tempo_real(codigos_a, codigos_b, parametros, ts):
    """Uma execucao no notebook, amostra a amostra no ritmo da amostragem.

    Devolve, em microssegundos: a latencia de declaracao de cada canal (da hora
    da amostra ate o fim da conta que declarou), o processamento por amostra e o
    quanto cada amostra comecou atrasada em relacao a hora dela.
    """
    det_a, det_b = PLACA.DetectorInteiro(parametros), PLACA.DetectorInteiro(parametros)
    latencia, processamento, atraso = {}, [], []
    t0 = time.perf_counter() + 0.002
    for k in range(len(codigos_a)):
        hora = t0 + k * ts
        while time.perf_counter() < hora:
            pass
        inicio = time.perf_counter()
        det_a.amostra(codigos_a[k])
        det_b.amostra(codigos_b[k])
        fim = time.perf_counter()
        processamento.append((fim - inicio) * 1e6)
        atraso.append((inicio - hora) * 1e6)
        for canal, det in (('A', det_a), ('B', det_b)):
            if det.detectou and canal not in latencia:
                latencia[canal] = (fim - hora) * 1e6
    return latencia, processamento, atraso


def cpu_em_lote(codigos_a, codigos_b, parametros):
    det_a, det_b = PLACA.DetectorInteiro(parametros), PLACA.DetectorInteiro(parametros)
    inicio = time.perf_counter()
    for a, b in zip(codigos_a, codigos_b):
        det_a.amostra(a)
        det_b.amostra(b)
    return (time.perf_counter() - inicio) * 1e6


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--jtag', action='store_true', help='FPGA pelo cabo de gravacao')
    ap.add_argument('--serial', help='FPGA pela porta serial')
    ap.add_argument('--sem-fpga', action='store_true', help='so o notebook')
    ap.add_argument('--repeticoes', type=int, default=10)
    ap.add_argument('--ensaios', nargs='*', help='sem eles, os ensaios com evento da matriz')
    ap.add_argument('--saida', default=SAIDA)
    args = ap.parse_args()
    if not (args.jtag or args.serial or args.sem_fpga):
        ap.error('escolha --jtag, --serial ou --sem-fpga')

    pacote = json.load(open(SE.PACOTE, encoding='utf-8'))
    selos = json.load(open(SE.SELOS, encoding='utf-8'))
    verdade = json.load(open(os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario',
                                          'leakmap_verdade_matriz_v1.json'), encoding='utf-8'))
    com_evento = [v['id'] for v in verdade['ensaios'] if v['tem_evento']]
    ids = args.ensaios or com_evento
    cal = D.calibracao_padrao()

    preparados = []
    for ident in ids:
        ensaio = SE.selecionar(ident, pacote, selos)
        p = PP.preparar_ensaio(ensaio, pacote['escala'], cal)
        preparados.append((ident, RB.periodo(ensaio), p['conversao']['canal_A']['codigos'],
                           p['conversao']['canal_B']['codigos'], p['parametros']))

    # --- notebook ------------------------------------------------------------------------
    print('notebook: %d ensaios x %d repeticoes, uma amostra por periodo de amostragem'
          % (len(ids), args.repeticoes), flush=True)
    cpu_lat, cpu_proc, cpu_atraso, cpu_lote, por_ensaio = [], [], [], [], {}
    for ident, ts, ca, cb, par in preparados:
        lats = []
        for _ in range(args.repeticoes):
            latencia, processamento, atraso = cpu_em_tempo_real(ca, cb, par, ts)
            lats += list(latencia.values())
            cpu_proc += processamento
            cpu_atraso += atraso
            cpu_lote.append(cpu_em_lote(ca, cb, par))
        cpu_lat += lats
        por_ensaio[ident] = {'notebook_latencia_us': resumo(lats)}
    cpu = {
        'onde': 'notebook, %s, Python %s' % (platform.platform(), platform.python_version()),
        'latencia_de_declaracao_us': resumo(cpu_lat),
        'processamento_por_amostra_us': resumo(cpu_proc),
        'atraso_da_entrega_us': resumo(cpu_atraso),
        'ensaio_inteiro_em_lote_us': resumo(cpu_lote),
    }

    # --- FPGA ------------------------------------------------------------------------------
    fpga = None
    if not args.sem_fpga:
        transporte = TR.TransporteJtag() if args.jtag else TR.TransporteSerial(args.serial)
        try:
            host = HO.Hospedeiro(transporte, tempo_limite_s=3.0)
            frequencia = host.pedir_tempos()['frequencia_hz']
            print('FPGA: %s, relogio de %d Hz' % (getattr(transporte, 'descricao', transporte.origem), frequencia),
                  flush=True)
            lat_ciclos, lat_us, proc_max, execucao_lote, atrasadas = [], [], [], [], 0
            for ident, ts, ca, cb, par in preparados:
                periodo = round(frequencia * ts)
                ciclos_do_ensaio = {'A': set(), 'B': set()}
                for _ in range(args.repeticoes):
                    real = host.rodar(ident, ca, cb, par, periodo_ciclos=periodo)['tempos_na_placa']
                    lote = host.rodar(ident, ca, cb, par)['tempos_na_placa']
                    atrasadas += real['amostras_atrasadas']
                    execucao_lote.append(lote['ciclos_execucao'] / frequencia * 1e6)
                    proc_max.append(real['ciclos_por_amostra_max'])
                    for canal in 'AB':
                        c = real['latencia_declaracao_' + canal]
                        if c is not None:
                            lat_ciclos.append(c)
                            lat_us.append(c / frequencia * 1e6)
                            ciclos_do_ensaio[canal].add(c)
                por_ensaio[ident]['fpga_latencia_ciclos'] = {k: sorted(v) for k, v in ciclos_do_ensaio.items()}
                print('  %s: declaracao em %s ciclos' % (ident, por_ensaio[ident]['fpga_latencia_ciclos']),
                      flush=True)
            fpga = {
                'onde': getattr(transporte, 'descricao', transporte.origem),
                'frequencia_hz': frequencia,
                'latencia_de_declaracao_ciclos': resumo(lat_ciclos),
                'latencia_de_declaracao_us': resumo(lat_us),
                'processamento_por_amostra_max_ciclos': max(proc_max),
                'ensaio_inteiro_em_lote_us': resumo(execucao_lote),
                'amostras_atrasadas': atrasadas,
                'ensaios_com_o_mesmo_numero_de_ciclos_em_todas_as_repeticoes': sum(
                    1 for e in por_ensaio.values()
                    if all(len(v) <= 1 for v in e.get('fpga_latencia_ciclos', {}).values())),
            }
        finally:
            transporte.fechar()

    resultado = {
        'descricao': ('Latencia de declaracao do evento, da hora da amostra do cruzamento ate o evento '
                      'declarado, com o mesmo detector em aritmetica inteira no notebook e na FPGA.'),
        'ensaios': ids,
        'repeticoes': args.repeticoes,
        'notebook': cpu,
        'fpga': fpga,
        'por_ensaio': por_ensaio,
        'observacao': ('reproducao de sinais digitais: as amostras sao as da matriz de ensaios, entregues '
                       'no ritmo da amostragem. No notebook a espera e ativa, o melhor caso para a CPU; o '
                       'detector em Python e mais lento que um em C, entao o que se compara e a variacao.'),
    }
    os.makedirs(os.path.dirname(args.saida), exist_ok=True)
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(args.saida, RAIZ))

    c = cpu['latencia_de_declaracao_us']
    print('notebook: declaracao %.1f us mediana, %.1f us no p99, %.1f us no pior caso (desvio %.1f us)'
          % (c['mediana'], c['p99'], c['max'], c['desvio_padrao']))
    if fpga:
        f = fpga['latencia_de_declaracao_us']
        print('FPGA:     declaracao %.2f us mediana, %.2f us no pior caso, %d a %d ciclos; amostras atrasadas: %d'
              % (f['mediana'], f['max'], fpga['latencia_de_declaracao_ciclos']['min'],
                 fpga['latencia_de_declaracao_ciclos']['max'], fpga['amostras_atrasadas']))


if __name__ == '__main__':
    main()

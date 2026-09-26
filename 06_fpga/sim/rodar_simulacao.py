"""LEAKMAP - roda o Verilog do cenario B contra o modelo Python da placa.

1. gera os vetores (06_fpga/computador/gerar_vetores.py);
2. compila 06_fpga/rtl com o testbench no Icarus Verilog;
3. roda cada caso e exige a resposta do Verilog igual, byte a byte, a do
   modelo de referencia (criterios 1 a 4 de 06_fpga/ESPECIFICACAO.md);
4. roda a demonstracao autonoma (tb_demo.v, as 242 posicoes contra o modelo, e
   tb_demo_de10.v, o topo da placa com botoes e displays);
5. roda o modulo de topo inteiro, com a serial, num ensaio curto; roda o
   topo da DE10-Standard pelo JTAG (tb_leakmap_jtag.v, o mesmo testbench do
   Questa) e confere que o roteiro dele, gravado no git, e o que o modelo da
   placa gera hoje;
5. com tudo igual, roda prova_cenario_b.py, que decodifica a resposta gravada
   do proprio Verilog e confere os criterios B-06 a B-09.

Precisa do Icarus Verilog (iverilog e vvp no PATH, ou em C:\\iverilog\\bin).
Sai com codigo diferente de zero se algum caso falhar.
"""
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FPGA = os.path.dirname(AQUI)
RAIZ = os.path.dirname(FPGA)

RTL_NUCLEO = ['rtl/leakmap_multiplicador.v', 'rtl/leakmap_detector.v', 'rtl/leakmap_saude.v', 'rtl/leakmap_nucleo.v']
RTL_TOPO = RTL_NUCLEO + ['rtl/leakmap_uart.v', 'rtl/leakmap_topo.v']
# topo da DE10-Standard pelo JTAG, com o modelo do sld_virtual_jtag no lugar do da Intel
RTL_JTAG = RTL_NUCLEO + ['rtl/leakmap_ponte_jtag.v', 'placas/intel/leakmap_topo_jtag.v',
                         'sim/modelos/sld_virtual_jtag.v']
ROTEIRO_JTAG = 'sim/questa/roteiro_jtag.hex'
# demonstracao autonoma: o nucleo da demonstracao e o topo da DE10-Standard
RTL_DEMO = ['rtl/leakmap_multiplicador.v', 'rtl/leakmap_detector.v', 'rtl/leakmap_saude.v', 'rtl/leakmap_demo.v']
RTL_DEMO_DE10 = ['rtl/leakmap_sete_segmentos.v', 'placas/de10_standard/demo/leakmap_demo_de10.v']


def achar(programa):
    caminho = shutil.which(programa)
    if caminho:
        return caminho
    for pasta in (r'C:\iverilog\bin', r'C:\Program Files\iverilog\bin'):
        candidato = os.path.join(pasta, programa + '.exe')
        if os.path.exists(candidato):
            return candidato
    return None


def compilar(iverilog, fontes, testbench, saida):
    comando = [iverilog, '-g2005', '-Wall', '-I', 'rtl', '-o', saida] + fontes + [testbench]
    processo = subprocess.run(comando, cwd=FPGA, capture_output=True, text=True)
    avisos = [l for l in (processo.stdout + processo.stderr).splitlines() if l.strip()]
    if processo.returncode != 0:
        print('\n'.join(avisos))
        raise SystemExit('falha ao compilar %s' % testbench)
    return avisos


def main():
    iverilog, vvp = achar('iverilog'), achar('vvp')
    if not iverilog or not vvp:
        raise SystemExit('Icarus Verilog nao encontrado (iverilog e vvp)')

    subprocess.run([sys.executable, os.path.join(FPGA, 'computador', 'gerar_vetores.py')],
                   check=True, cwd=RAIZ)
    casos = json.load(open(os.path.join(FPGA, 'vetores', 'casos.json'), encoding='utf-8'))['casos']

    avisos = compilar(iverilog, RTL_NUCLEO, 'sim/tb_nucleo.v', 'sim/tb_nucleo.vvp')
    if avisos:
        print('avisos do compilador:\n  ' + '\n  '.join(avisos))

    passaram, falharam = [], []
    for nome in casos:
        processo = subprocess.run(
            [vvp, '-n', 'sim/tb_nucleo.vvp', '+caso=%s' % nome,
             '+entrada=vetores/%s.entrada.hex' % nome, '+esperado=vetores/%s.saida.hex' % nome,
             '+mascara=vetores/%s.mascara.hex' % nome,
             '+obtido=vetores/%s.verilog.txt' % nome],
            cwd=FPGA, capture_output=True, text=True)
        linha = next((l for l in processo.stdout.splitlines() if l.startswith('RESULTADO')), None)
        if linha and ' PASSOU ' in linha:
            passaram.append(linha)
        else:
            falharam.append(linha or processo.stdout[-400:])
            print(processo.stdout[-800:])

    compilar(iverilog, RTL_TOPO, 'sim/tb_topo.v', 'sim/tb_topo.vvp')
    processo = subprocess.run([vvp, '-n', 'sim/tb_topo.vvp'], cwd=FPGA, capture_output=True, text=True)
    linha = next((l for l in processo.stdout.splitlines() if l.startswith('RESULTADO')), None)
    if linha and ' PASSOU ' in linha:
        passaram.append(linha)
    else:
        falharam.append(linha or processo.stdout[-400:])
        print(processo.stdout[-800:])

    # demonstracao autonoma: as constantes no git tem de ser as que o modelo gera hoje,
    # e o Verilog tem de dar os mesmos numeros que o modelo, posicao por posicao
    esperado_demo = os.path.join(FPGA, 'vetores', 'demo_esperado.txt')
    parametros_demo = os.path.join(FPGA, 'vetores', 'leakmap_demo_parametros.vh')
    subprocess.run([sys.executable, os.path.join(FPGA, 'computador', 'demo_autonoma.py'),
                    '--vetores', esperado_demo, '--parametros', parametros_demo],
                   check=True, cwd=RAIZ, capture_output=True)
    with open(os.path.join(FPGA, 'rtl', 'leakmap_demo_parametros.vh')) as gravado, open(parametros_demo) as gerado:
        if gravado.read() != gerado.read():
            falharam.append('rtl/leakmap_demo_parametros.vh esta desatualizado: rode 06_fpga/computador/demo_autonoma.py')
    for testbench, fontes in (('sim/tb_demo.v', RTL_DEMO), ('sim/tb_demo_de10.v', RTL_DEMO + RTL_DEMO_DE10)):
        saida = testbench.replace('.v', '.vvp')
        compilar(iverilog, fontes, testbench, saida)
        processo = subprocess.run([vvp, '-n', saida, '+esperado=vetores/demo_esperado.txt'],
                                  cwd=FPGA, capture_output=True, text=True)
        linha = next((l for l in processo.stdout.splitlines() if l.startswith('RESULTADO')), None)
        if linha and ' PASSOU ' in linha:
            passaram.append(linha)
        else:
            falharam.append(linha or processo.stdout[-400:])
            print(processo.stdout[-1500:])

    # topo pelo JTAG: o roteiro no git tem de ser o que o modelo gera hoje
    novo = os.path.join(FPGA, 'vetores', 'roteiro_jtag.hex')
    subprocess.run([sys.executable, os.path.join(FPGA, 'computador', 'gerar_roteiro_jtag.py'), novo],
                   check=True, cwd=RAIZ, capture_output=True)
    with open(os.path.join(FPGA, ROTEIRO_JTAG)) as gravado, open(novo) as gerado:
        if gravado.read() != gerado.read():
            falharam.append('o roteiro %s esta desatualizado: rode 06_fpga/computador/gerar_roteiro_jtag.py'
                            % ROTEIRO_JTAG)
    compilar(iverilog, RTL_JTAG, 'sim/tb_leakmap_jtag.v', 'sim/tb_leakmap_jtag.vvp')
    processo = subprocess.run([vvp, '-n', 'sim/tb_leakmap_jtag.vvp', '+roteiro=' + ROTEIRO_JTAG],
                              cwd=FPGA, capture_output=True, text=True)
    linha = next((l for l in processo.stdout.splitlines() if l.startswith('RESULTADO tb_leakmap_jtag')), None)
    if linha and ' PASSOU ' in linha:
        passaram.append(linha)
    else:
        falharam.append(linha or processo.stdout[-400:])
        print(processo.stdout[-1500:])

    ciclos = [int(m.group(1)) for l in passaram for m in [re.search(r'ciclos=(\d+)', l)] if m]
    print('casos: %d | passaram: %d | falharam: %d' % (len(passaram) + len(falharam),
                                                         len(passaram), len(falharam)))
    if ciclos:
        print('maior caso: %d ciclos de relogio' % max(ciclos))
    for f in falharam:
        print('  ' + str(f))
    if falharam:
        raise SystemExit(1)

    subprocess.run([sys.executable, os.path.join(AQUI, 'prova_cenario_b.py')], check=True, cwd=RAIZ)


if __name__ == '__main__':
    main()

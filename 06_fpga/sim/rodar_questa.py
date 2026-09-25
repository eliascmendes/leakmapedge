"""LEAKMAP - roda o testbench completo da placa pelo JTAG no Questa, sem janela.

E o mesmo que abrir o Questa em 06_fpga/sim/questa e digitar `do rodar.do`,
so que em modo texto. Usa o vsim do PATH, da variavel QUESTA_HOME ou da
instalacao do Quartus Prime (questa_fse). O Questa Starter precisa da licenca
gratuita da Intel configurada (variavel SALT_LICENSE_SERVER ou LM_LICENSE_FILE).
Sai com codigo diferente de zero se o testbench falhar.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, 'questa')


def achar_vsim():
    candidatos = [shutil.which('vsim') or '']
    if os.environ.get('QUESTA_HOME'):
        candidatos.append(os.path.join(os.environ['QUESTA_HOME'], 'win64', 'vsim.exe'))
    for disco in ('C:', 'D:', 'E:', 'F:'):
        for pasta in ('altera', 'altera_lite', 'intelFPGA', 'intelFPGA_lite'):
            candidatos += sorted(glob.glob('%s/%s/*/questa_fse/win64/vsim.exe' % (disco, pasta)), reverse=True)
    candidatos += sorted(glob.glob('/opt/*/*/questa_fse/bin/vsim'), reverse=True)
    return next((c for c in candidatos if c and os.path.exists(c)), None)


def main():
    vsim = achar_vsim()
    if not vsim:
        raise SystemExit('Questa (vsim) nao encontrado: ele vem com o Quartus Prime Lite')
    processo = subprocess.run([vsim, '-c', '-do', 'do rodar.do; quit -f'], cwd=PASTA,
                              capture_output=True, text=True, errors='replace')
    saida = processo.stdout + processo.stderr
    for linha in saida.splitlines():
        if re.search(r'ESTADO|CASO|RESULTADO|mensagens|Error|Fatal|licen', linha):
            print(linha.lstrip('# '))
    if not re.search(r'RESULTADO tb_leakmap_jtag PASSOU', saida):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

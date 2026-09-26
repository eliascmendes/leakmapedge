"""LEAKMAP - monta e compila o projeto do Quartus de uma placa numa pasta sem acento.

O Quartus nao aceita projeto em caminho com acento ou cedilha (por exemplo
"Area de Trabalho" com acento). Este script copia o projeto da placa e os
arquivos Verilog para uma pasta com caminho simples, ajusta os caminhos do
.qsf e, com --compilar, roda a compilacao completa e resume ocupacao e tempo.

Uso:
  python preparar_quartus.py                      so copia, para abrir no Quartus
  python preparar_quartus.py --compilar           copia e compila
  python preparar_quartus.py --destino D:/leakmap_quartus --compilar

Padrao: placa de10_standard, destino <pasta do usuario>/leakmap_quartus/de10_standard.
A demonstracao autonoma: --placa de10_standard/demo.
O arquivo para gravar a placa sai em <destino>/output_files/<projeto>.sof.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FPGA = os.path.dirname(AQUI)


def achar_quartus_sh():
    raiz = os.environ.get('QUARTUS_ROOTDIR')
    candidatos = [os.path.join(raiz, 'bin64', 'quartus_sh.exe')] if raiz else []
    candidatos.append(shutil.which('quartus_sh') or '')
    for disco in ('C:', 'D:', 'E:', 'F:'):
        for pasta in ('altera', 'altera_lite', 'intelFPGA', 'intelFPGA_lite'):
            candidatos += sorted(glob.glob('%s/%s/*/quartus/bin64/quartus_sh.exe' % (disco, pasta)), reverse=True)
    return next((c for c in candidatos if c and os.path.exists(c)), None)


def copiar(placa, destino):
    origem = os.path.join(AQUI, placa)
    qsf = glob.glob(os.path.join(origem, '*.qsf'))[0]
    projeto = os.path.splitext(os.path.basename(qsf))[0]
    os.makedirs(destino, exist_ok=True)
    for arq in glob.glob(os.path.join(origem, '*.q?f')) + glob.glob(os.path.join(origem, '*.sdc')):
        if not arq.endswith('.qsf'):
            shutil.copy(arq, destino)
    linhas = []
    with open(qsf, encoding='utf-8') as f:
        for linha in f:
            m = re.match(r'(set_global_assignment -name VERILOG_(?:INCLUDE_)?FILE )(\S+)', linha)
            if m:
                fonte = os.path.normpath(os.path.join(origem, m.group(2)))
                shutil.copy(fonte, destino)
                linha = m.group(1) + os.path.basename(fonte) + '\n'
            linhas.append(linha)
    with open(os.path.join(destino, projeto + '.qsf'), 'w', encoding='utf-8') as f:
        f.writelines(linhas)
    return projeto


def resumir(destino, projeto):
    saida = os.path.join(destino, 'output_files')
    with open(os.path.join(saida, projeto + '.flow.rpt'), encoding='utf-8', errors='replace') as f:
        fluxo = f.read()
    for chave in ('Flow Status', 'Device', 'Logic utilization', 'Total registers', 'Total block memory bits'):
        m = re.search(r';\s*%s[^;]*;\s*([^;]+);' % re.escape(chave), fluxo)
        if m:
            print('%-24s %s' % (chave, m.group(1).strip()))
    with open(os.path.join(saida, projeto + '.sta.summary'), encoding='utf-8', errors='replace') as f:
        tempo = f.read()
    folgas = re.findall(r"Type\s*:\s*(.+?)\nSlack\s*:\s*(-?[\d.]+)", tempo)
    piores = [(t.strip(), float(s)) for t, s in folgas]
    for t, s in piores:
        if 'Slow' in t and ('Setup' in t or 'Hold' in t) and '85C' in t:
            print('%-24s %+.3f ns  (%s)' % ('Folga', s, t))
    negativas = [(t, s) for t, s in piores if s < 0]
    sof = os.path.join(saida, projeto + '.sof')
    print('arquivo para gravar     %s' % sof)
    return not negativas and os.path.exists(sof)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--placa', default='de10_standard')
    ap.add_argument('--destino', help='pasta sem acento para o projeto')
    ap.add_argument('--compilar', action='store_true')
    args = ap.parse_args()

    destino = args.destino or os.path.join(os.path.expanduser('~'), 'leakmap_quartus', args.placa)
    if not destino.isascii():
        raise SystemExit('o destino tem acento ou cedilha, e o Quartus nao aceita: %s' % destino)
    projeto = copiar(args.placa, destino)
    print('projeto copiado para %s' % os.path.join(destino, projeto + '.qpf'))
    if not args.compilar:
        return
    quartus_sh = achar_quartus_sh()
    if not quartus_sh:
        raise SystemExit('quartus_sh nao encontrado: instale o Quartus Prime Lite')
    print('compilando (alguns minutos)...', flush=True)
    processo = subprocess.run([quartus_sh, '--flow', 'compile', projeto], cwd=destino,
                              capture_output=True, text=True, errors='replace')
    if processo.returncode != 0:
        print('\n'.join(l for l in processo.stdout.splitlines() if l.startswith(('Error', 'Critical'))))
        raise SystemExit('a compilacao falhou; o relatorio completo esta em %s' % os.path.join(destino, 'output_files'))
    if not resumir(destino, projeto):
        raise SystemExit('a compilacao terminou, mas o tempo nao fechou ou falta o .sof')


if __name__ == '__main__':
    sys.exit(main())

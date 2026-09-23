"""LEAKMAP - trilha de software, etapas A-09 a A-17.

Roda a cadeia inteira, cada etapa em seu proprio processo, na ordem de
dependencia:

  1. 04_detector/gerar_ensaios.py        A-09 modelo de sensor
                                         A-10 amostragem e pacote do ensaio
  2. 04_detector/rodar_detector.py       A-11 a A-15 deteccao e localizacao
  3. 04_detector/detector_ponto_fixo.py  bonus, porte em ponto fixo
  4. 05_avaliacao/gerar_verdade_matriz.py  verdade do cenario da matriz
  5. 05_avaliacao/avaliador.py           A-17 avaliacao independente
  6. web/gerar_gabarito.py               gabarito do Python para o front-end
  7. web/gerar_dados_web.py              dados do simulador do painel
  8. 06_fpga/computador                  cenario B, lado do computador: selos,
                                         dimensionamento e execucao contra a
                                         referencia Python da placa
  9. testes do detector, do avaliador e do cenario B (Python) e teste de
     paridade da adaptacao em JavaScript contra o gabarito do Python (Node)

O passo 5 roda em processo separado do passo 2 de proposito: e o criterio de
conclusao de A-17. O avaliador nunca importa modulo do detector.

O Python e a implementacao de referencia. A adaptacao em
web/leakmap_detector.js so existe para o painel e tem de reproduzir o
gabarito que o Python grava no passo 6; se divergir, a trilha falha. Sem
Node instalado o teste de paridade e pulado com aviso, e o GitHub Actions
(.github/workflows/testes.yml) o executa a cada envio.

As etapas A-01 a A-08 (modelo hidraulico e simulacao) nao entram aqui: elas
dependem do TSNet e ja produziram 03_ensaios/amostras/leakmap_amostras_v1.json,
que e a entrada desta trilha.
"""
import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

PASSOS = [
    ('A-09 e A-10  modelo de sensor e pacote do ensaio',
     os.path.join('04_detector', 'gerar_ensaios.py')),
    ('A-11 a A-15  deteccao, marcacao, decisao e posicao',
     os.path.join('04_detector', 'rodar_detector.py')),
    ('bonus        porte de referencia em ponto fixo',
     os.path.join('04_detector', 'detector_ponto_fixo.py')),
    ('verdade      verdade do cenario da matriz',
     os.path.join('05_avaliacao', 'gerar_verdade_matriz.py')),
    ('A-17         avaliacao independente',
     os.path.join('05_avaliacao', 'avaliador.py')),
    ('front-end    gabarito do Python para a adaptacao em JavaScript',
     os.path.join('web', 'gerar_gabarito.py')),
    ('front-end    dados do simulador do painel',
     os.path.join('web', 'gerar_dados_web.py')),
    ('cenario B    selos de verificacao (B-01)',
     os.path.join('06_fpga', 'computador', 'selo.py')),
    ('cenario B    dimensionamento (B-05)',
     os.path.join('06_fpga', 'computador', 'dimensionamento.py')),
    ('cenario B    execucao contra a referencia Python da placa',
     os.path.join('06_fpga', 'computador', 'executar_cenario_b.py')),
]

TESTES = [
    ('testes do detector', os.path.join('04_detector', 'testes')),
    ('testes do avaliador', os.path.join('05_avaliacao', 'testes')),
    ('testes do cenario B', os.path.join('06_fpga', 'computador', 'testes')),
]


def executar(titulo, comando, cwd):
    print('\n=== %s ===' % titulo, flush=True)
    processo = subprocess.run(comando, cwd=cwd)
    if processo.returncode != 0:
        raise SystemExit('falhou: %s (codigo %d)'
                         % (titulo, processo.returncode))


def main():
    for titulo, script in PASSOS:
        executar(titulo, [sys.executable, os.path.basename(script)],
                 os.path.join(RAIZ, os.path.dirname(script)))

    for titulo, pasta in TESTES:
        executar(titulo,
                 [sys.executable, '-m', 'unittest', 'discover',
                  '-s', pasta, '-p', 'teste_*.py'],
                 RAIZ)

    node = shutil.which('node')
    if node:
        executar('paridade do JavaScript com o Python',
                 [node, '--test',
                  os.path.join('web', 'testes', 'teste_paridade.js')],
                 RAIZ)
    else:
        print('\n=== AVISO: Node nao encontrado; teste de paridade do '
              'JavaScript nao executado nesta maquina ===')

    print('\n=== trilha de software concluida ===')


if __name__ == '__main__':
    main()

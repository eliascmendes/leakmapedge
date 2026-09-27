"""LEAKMAP - acesso do backend aos modulos do projeto.

O backend nao reescreve logica: importa o detector (04_detector), o autoteste
(06_fpga/computador), a escala de alerta e o cadastro (07_servico) e as
premissas das linhas (02_bancada/codigo). Este modulo arruma o caminho de
importacao num lugar so.

Dois arquivos tem o mesmo nome, `linha_cais.py`: o da bancada (premissas da
simulacao, importado por rede_cais.py como `linha_cais`) e o do detector (as
configuracoes de transmissor). O da bancada fica com o nome; o do detector e
carregado pelo caminho, como `detector_linha_cais`.
"""
import ast
import importlib.util
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PASTAS = {
    'bancada': os.path.join(RAIZ, '02_bancada', 'codigo'),
    'detector': os.path.join(RAIZ, '04_detector'),
    'placa': os.path.join(RAIZ, '06_fpga', 'computador'),
    'servico': os.path.join(RAIZ, '07_servico'),
}
AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras')
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario')

for _pasta in ('servico', 'placa', 'detector', 'bancada'):       # a bancada fica na frente
    if PASTAS[_pasta] not in sys.path:
        sys.path.insert(0, PASTAS[_pasta])

import linha_cais as LC  # noqa: E402  (premissas da linha do cais, 02_bancada)
import rede_cais as RC  # noqa: E402
import velocidade_de_onda as VO  # noqa: E402
import detector as D  # noqa: E402
import modelo_sensor as MS  # noqa: E402
import rede as RD  # noqa: E402
import refino as RF  # noqa: E402
import alerta as AL  # noqa: E402
import cadastro as CD  # noqa: E402
import integracao as IN  # noqa: E402
import sobrepressao as SP  # noqa: E402
import previsao_de_golpe as PG  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import protocolo as PR  # noqa: E402
import representacao as RP  # noqa: E402


def _carregar(nome, caminho):
    especificacao = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    sys.modules[nome] = modulo
    especificacao.loader.exec_module(modulo)
    return modulo


# as seis configuracoes de transmissor da linha do cais (04_detector/linha_cais.py)
TX = _carregar('detector_linha_cais', os.path.join(PASTAS['detector'], 'linha_cais.py'))


def constantes_do_trecho_200():
    """Constantes do trecho de 200 m, lidas de build_model.py sem importar o wntr que ele usa."""
    return constantes_de('build_model.py')


def constantes_de(arquivo):
    """Constantes literais de um script de 02_bancada/codigo, lidas sem importar o wntr que ele usa."""
    with open(os.path.join(PASTAS['bancada'], arquivo), encoding='utf-8') as f:
        arvore = ast.parse(f.read())
    saida = {}
    for no in arvore.body:
        if isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name):
            try:
                saida[no.targets[0].id] = ast.literal_eval(no.value)
            except ValueError:
                pass
    return saida

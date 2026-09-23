"""LEAKMAP - preparo de um ensaio para a placa (B-02, B-03 e B-07).

Converte os dois canais para inteiros com a representacao declarada e
calcula os parametros inteiros que a placa recebe na configuracao. Os
parametros saem de 04_detector/detector_ponto_fixo.py, com a mesma
calibracao e a mesma escala que o cenario A usou no mesmo ensaio.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector_ponto_fixo as PF  # noqa: E402
import registro_b as RB  # noqa: E402
import representacao as RP  # noqa: E402


def preparar_ensaio(ensaio, escala, cal):
    espec = RP.especificacao(RP.degrau_do_ensaio(ensaio))
    conversao = {}
    for canal in ('canal_A', 'canal_B'):
        codigos, abaixo, acima = RP.converter(ensaio[canal + '_carga_m'], espec)
        conversao[canal] = {'codigos': codigos, 'abaixo': abaixo, 'acima': acima}
    parametros = PF.parametros_inteiros(cal, RB.periodo(ensaio), espec['degrau_m'],
                                        (escala or {}).get('resolucao_declarada_m'))
    return {'representacao': espec, 'conversao': conversao, 'parametros': parametros}

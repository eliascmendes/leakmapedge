"""Testes do refino da diferenca de tempo por correlacao cruzada (04_detector/refino.py).

As frentes sinteticas tem o atraso entre canais escolhido pelo proprio teste,
inclusive em fracao de amostra, entao o valor esperado e conhecido sem abrir
a verdade do cenario.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detector as D  # noqa: E402
import refino as RF  # noqa: E402

TS = 4.0130559895570352e-4
L_M, C_M_S, POS_A = 120.0, 1200.899544131626, 40.0
ESCALA = {'minimo_m': 0.0, 'maximo_m': 100.0, 'resolucao_declarada_m': 1e-3}


def frente(n, inicio_amostras, amplitude=-5.0, largura_amostras=1.5):
    """Queda suave de pressao, com o centro da frente em fracao de amostra."""
    k = np.arange(n, dtype=float)
    return 58.0 + amplitude * 0.5 * (1.0 + np.tanh((k - inicio_amostras) / largura_amostras))


def ensaio(a, b):
    n = len(a)
    return {'id': 'R', 'n_pontos': n, 'indice': list(range(n)), 'tempo_s': [i * TS for i in range(n)],
            'canal_A_carga_m': [float(v) for v in a], 'canal_B_carga_m': [float(v) for v in b],
            'parametros_do_detector': {'posicao_sensor_A_m': POS_A, 'posicao_sensor_B_m': POS_A + L_M,
                                       'distancia_entre_sensores_L_m': L_M, 'velocidade_de_onda_m_s': C_M_S,
                                       'incerteza_de_velocidade_de_onda_m_s': 0.0}}


class RefinoPorCorrelacao(unittest.TestCase):

    def rodar(self, atraso_amostras):
        e = ensaio(frente(900, 300.0), frente(900, 300.0 + atraso_amostras))
        registro = D.processar_ensaio(e, ESCALA)
        return registro, RF.refinar(e, registro)

    def test_recupera_atraso_em_fracao_de_amostra(self):
        registro, refino = self.rodar(40.3)
        self.assertEqual(registro['classe'], D.CLASSE_LOCALIZADO)
        self.assertTrue(refino['aplicado'])
        # as marcas so enxergam amostras inteiras; o refino chega perto da fracao
        erro_marcas = abs(-registro['delta_t_amostras'] - 40.3)
        erro_refino = abs(-refino['delta_t_s'] / TS - 40.3)
        self.assertLess(erro_refino, 0.1)
        self.assertLess(erro_refino, erro_marcas)

    def test_atraso_inteiro_continua_inteiro(self):
        _, refino = self.rodar(40.0)
        self.assertAlmostEqual(refino['delta_t_s'] / TS, -40.0, delta=0.05)

    def test_posicao_refinada_sai_do_mesmo_calculo_de_posicao(self):
        registro, refino = self.rodar(0.0)
        self.assertAlmostEqual(refino['posicao_estimada_m'], POS_A + L_M / 2.0, delta=0.05)
        self.assertEqual(refino['posicao_estimada_m'] >= POS_A, True)

    def test_sem_localizacao_nao_ha_refino(self):
        e = ensaio(frente(900, 300.0), np.full(900, 52.0))
        registro = D.processar_ensaio(e, ESCALA)
        self.assertNotEqual(registro['classe'], D.CLASSE_LOCALIZADO)
        self.assertIsNone(RF.refinar(e, registro))

    def test_refino_nao_muda_a_posicao_publicada(self):
        e = ensaio(frente(900, 300.0), frente(900, 340.3))
        registros = [D.processar_ensaio(e, ESCALA)]
        antes = registros[0]['posicao_estimada_m']
        RF.refinar_pacote({'ensaios': [e]}, registros)
        self.assertEqual(registros[0]['posicao_estimada_m'], antes)
        self.assertIn('refino_por_correlacao', registros[0])


if __name__ == '__main__':
    unittest.main()

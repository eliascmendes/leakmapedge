"""Testes da fisica da linha (04_detector/fisica.py): cada principio contra a conta feita a mao.

Roda com: python -m unittest discover -s 04_detector/testes -p "teste_*.py"
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detector as D  # noqa: E402
import fisica as F  # noqa: E402

D8 = 0.20274                      # 8" sch40
AREA = math.pi * D8 ** 2 / 4.0
C = 1226.6
G = F.G


class Escoamento(unittest.TestCase):

    def test_darcy_weisbach_devolve_a_velocidade_que_gerou_a_perda(self):
        # perda de carga calculada a mao para 1,46 m/s de diesel em 700 m de 8"; a inversao volta a 1,46 m/s
        v, rug, nu, l_m = 1.46, 0.046e-3, 3.0e-6, 700.0
        f = F.fator_de_atrito(v * D8 / nu, rug / D8)
        h_f = f * (l_m / D8) * v ** 2 / (2 * G)
        r = F.escoamento_de_regime(80.0, 80.0 - h_f, l_m, D8, rug, nu)
        self.assertAlmostEqual(r['velocidade_m_s'], v, places=4)
        self.assertAlmostEqual(r['vazao_m3_s'], v * AREA, places=5)
        self.assertTrue(r['dentro_da_faixa_de_validade'])
        # sentido do escoamento pelo sinal da perda
        self.assertLess(F.escoamento_de_regime(80.0 - h_f, 80.0, l_m, D8, rug, nu)['velocidade_m_s'], 0)

    def test_fator_de_atrito_laminar_e_faixa_de_validade(self):
        self.assertAlmostEqual(F.fator_de_atrito(1000.0, 1e-4), 0.064)
        fora = F.escoamento_de_regime(60.0, 54.0, 120.0, 0.3, 0.25, 1e-6)
        self.assertFalse(fora['dentro_da_faixa_de_validade'])      # rugosidade de 0,83 do diametro

    def test_atenuacao_teorica_e_medida(self):
        alpha = F.atenuacao_por_atrito(0.0192, 1.46, D8, C)
        self.assertAlmostEqual(alpha, 0.0192 * 1.46 / (2 * D8 * C))
        # duas amplitudes geradas com um alpha conhecido devolvem o mesmo alpha
        a0, x = 18.0, 100.0
        da, db = a0 * math.exp(-alpha * x), a0 * math.exp(-alpha * (700 - x))
        self.assertAlmostEqual(F.atenuacao_medida(da, db, x, 700 - x, 700.0), alpha, places=10)
        self.assertIsNone(F.atenuacao_medida(da, db, 340.0, 360.0, 700.0))   # perto do meio nao informa


class Vazamento(unittest.TestCase):

    def test_joukowsky_e_orificio(self):
        # vazamento de coeficiente conhecido: a carga cai o que a Joukowsky manda e o orificio devolve o coeficiente
        c_e, h0 = 0.0012, 79.0
        dh = 0.0
        for _ in range(50):                 # dH = c q / (2 g A), com q = C_e raiz(h0 - dH)
            dh = C * c_e * math.sqrt(h0 - dh) / (2 * G * AREA)
        q = F.vazao_por_joukowsky(dh, C, AREA)
        self.assertAlmostEqual(q, c_e * math.sqrt(h0 - dh), places=8)
        o = F.orificio_equivalente(q, h0 - dh)
        self.assertAlmostEqual(o['coeficiente_de_emissor_m2_5_s'], c_e, places=8)
        self.assertAlmostEqual(o['diametro_equivalente_m'], 0.0238, delta=0.0002)   # furo de cerca de 24 mm
        self.assertIsNone(F.orificio_equivalente(q, -1.0))

    def test_caracterizar_vazamento_sintetico(self):
        # dois canais com um degrau limpo, amplitude do furo conhecida e atenuacao exp(-alpha d)
        ts, l_m, x = 1 / 2500, 700.0, 150.0
        t = np.arange(0, 1.0, ts)
        h_a, h_b, c_e = 81.0, 74.0, 0.0012
        h_furo = h_a + (h_b - h_a) * x / l_m
        dh = 0.0
        for _ in range(50):
            dh = C * c_e * math.sqrt(h_furo - dh) / (2 * G * AREA)
        geo = {'diametro_interno_m': D8, 'rugosidade_m': 0.046e-3, 'viscosidade_m2_s': 3.0e-6}
        regime = F.escoamento_de_regime(h_a, h_b, l_m, D8, 0.046e-3, 3.0e-6)
        alpha = F.atenuacao_por_atrito(regime['fator_de_atrito'], regime['velocidade_m_s'], D8, C)
        ta, tb = 0.2 + x / C, 0.2 + (l_m - x) / C
        sa = np.where(t >= ta, h_a - dh * math.exp(-alpha * x), h_a)
        sb = np.where(t >= tb, h_b - dh * math.exp(-alpha * (l_m - x)), h_b)
        ia, ib = int(np.searchsorted(t, ta)), int(np.searchsorted(t, tb))
        ensaio = {'tempo_s': t, 'canal_A_carga_m': sa, 'canal_B_carga_m': sb,
                  'parametros_do_detector': {'distancia_entre_sensores_L_m': l_m, 'velocidade_de_onda_m_s': C}}
        registro = {'classe': D.CLASSE_LOCALIZADO, 'posicao_estimada_rel_sensor_A_m': x,
                    'canal_A': {'indice_de_chegada': ia}, 'canal_B': {'indice_de_chegada': ib}}
        f = F.caracterizar_vazamento(ensaio, registro, geo)
        self.assertTrue(f['aplicado'])
        self.assertAlmostEqual(f['onda']['atenuacao_por_atrito_1_m'], alpha, delta=alpha * 0.02)
        self.assertAlmostEqual(f['vazamento']['coeficiente_de_emissor_m2_5_s'], c_e, delta=c_e * 0.01)
        self.assertAlmostEqual(f['escoamento_de_regime']['velocidade_m_s'], regime['velocidade_m_s'], places=6)
        # manobra ou evento sem posicao nao e caracterizado
        self.assertIsNone(F.caracterizar_vazamento(ensaio, dict(registro, classe=D.CLASSE_MANOBRA), geo))

    def test_janela_para_antes_da_reflexao(self):
        self.assertEqual(F.janela_depois(None, C), (0.004, 0.024))
        inicio, fim = F.janela_depois(10.0, C)            # contorno a 10 m: reflexao volta em 16,3 ms
        self.assertAlmostEqual(fim, 2 * 10.0 / C - 0.003)
        self.assertIsNone(F.janela_depois(20.0, C, periodo_de_atualizacao_s=0.05))   # transmissor lento demais


class Posicao(unittest.TestCase):

    def test_incerteza_com_o_periodo_de_atualizacao(self):
        r = {'delta_t_s': 0.1, 'incerteza_de_delta_t_s': 0.0005,
             'parametros_do_detector': {'velocidade_de_onda_m_s': C, 'incerteza_de_velocidade_de_onda_m_s': 5.0}}
        so_marcas = F.incerteza_de_posicao(r)
        com_10ms = F.incerteza_de_posicao(r, 0.010)
        self.assertAlmostEqual(com_10ms['componentes_m']['atualizacao_do_transmissor_m'], C * 0.010 / math.sqrt(6) / 2)
        self.assertGreater(com_10ms['incerteza_m'], so_marcas['incerteza_m'])
        self.assertAlmostEqual(so_marcas['componentes_m']['velocidade_da_onda_m'], 0.1 * 5.0 / 2)

    def test_calibracao_da_velocidade_e_descarte(self):
        c_real, l_m = 1210.0, 700.0
        fontes = [-150.0, 800.0, 50.0, 250.0, 600.0, -300.0]
        eventos = [{'delta_t_s': F.diferenca_de_percurso(x, l_m) / c_real, 'incerteza_de_delta_t_s': 1e-4,
                    'diferenca_de_percurso_m': F.diferenca_de_percurso(x, l_m)} for x in fontes]
        self.assertAlmostEqual(F.calibrar_velocidade(eventos)['velocidade_m_s'], c_real, places=6)
        ruim = dict(eventos[2], delta_t_s=-eventos[2]['delta_t_s'])        # frente perdida: sinal trocado
        cal = F.calibrar_velocidade(eventos + [ruim])
        self.assertAlmostEqual(cal['velocidade_m_s'], c_real, places=3)
        self.assertEqual(cal['n_descartados'], 1)
        self.assertIsNone(F.calibrar_velocidade([{'delta_t_s': 0.0, 'diferenca_de_percurso_m': 0.0}]))

    def test_relocalizar_e_adveccao(self):
        r = {'delta_t_s': -0.1, 'incerteza_de_delta_t_s': 0.0,
             'parametros_do_detector': {'distancia_entre_sensores_L_m': 700.0, 'posicao_sensor_A_m': 0.0}}
        self.assertAlmostEqual(F.relocalizar(r, 1200.0)['posicao_estimada_m'], (700 - 120) / 2)
        # com o escoamento parado a advecao nao muda nada; com 1,46 m/s o vies e cerca de -L V / 2c
        self.assertAlmostEqual(F.posicao_com_adveccao(700, C, 0.0, 0.05), (700 + C * 0.05) / 2)
        x = 350.0
        dt = x / (C - 1.46) - (700 - x) / (C + 1.46)
        self.assertAlmostEqual(F.posicao_com_adveccao(700, C, 1.46, dt), x, places=6)
        self.assertAlmostEqual((700 + C * dt) / 2 - x, 700 * 1.46 / (2 * C), delta=0.01)


class Detectabilidade(unittest.TestCase):

    def test_limiar_em_carga_e_em_vazao(self):
        cal = D.calibracao_padrao()
        k = F.fator_da_janela_curta(cal, 1 / 2491.87)
        self.assertAlmostEqual(k, 0.75, delta=0.02)
        m = F.menor_vazamento_detectavel(0.026, C, AREA, cal, 0.0028, 1 / 2491.87)
        self.assertAlmostEqual(m['degrau_minimo_m'], math.sqrt(12 / k) * 0.026, places=6)
        self.assertEqual(m['limitado_por'], 'ruido')
        self.assertAlmostEqual(m['vazao_minima_m3_s'], 2 * G * AREA * m['degrau_minimo_m'] / C)


if __name__ == '__main__':
    unittest.main()

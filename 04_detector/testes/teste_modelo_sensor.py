"""Testes da etapa A-09 (modelo dos sensores).

Criterio de conclusao de A-09, verificado aqui:

  1. desligando todos os efeitos, a saida e identica a entrada;
  2. ligando um efeito por vez, o resultado muda apenas na caracteristica
     esperada daquele efeito.

Roda com: python -m unittest discover -s 04_detector/testes -p "teste_*.py"
"""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import modelo_sensor as MS  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras',
                        'leakmap_amostras_v1.json')


def sinal_de_ensaio():
    """Sinal real do ensaio EV-01, para nao testar sobre curva inventada."""
    with open(AMOSTRAS, encoding='utf-8') as f:
        dados = json.load(f)
    ensaio = dados['ensaios'][0]
    return (np.array(ensaio['canal_A_carga_m'], dtype=float),
            np.array(ensaio['canal_B_carga_m'], dtype=float),
            float(dados['base_de_tempo_s']))


class TodosDesligados(unittest.TestCase):

    def test_saida_identica_bit_a_bit(self):
        a, b, ts = sinal_de_ensaio()
        sa, sb, registro = MS.aplicar(a, b, ts, MS.config_neutra())
        np.testing.assert_array_equal(sa, a)
        np.testing.assert_array_equal(sb, b)
        self.assertEqual(registro, [])

    def test_resolucao_declarada_nao_existe_sem_quantizacao(self):
        self.assertIsNone(MS.resolucao_declarada_m(MS.config_neutra()))


class UmEfeitoPorVez(unittest.TestCase):
    """Cada teste liga um unico efeito e checa so a caracteristica dele."""

    def setUp(self):
        self.a, self.b, self.ts = sinal_de_ensaio()
        self.cfg = MS.config_neutra()

    def aplicar(self):
        return MS.aplicar(self.a, self.b, self.ts, self.cfg)

    def test_banda_suaviza_sem_mover_o_regime(self):
        self.cfg['banda'].update(ligado=True, corte_hz=300.0, ordem=2)
        sa, sb, reg = self.aplicar()
        # o regime permanente anterior ao evento nao se desloca
        self.assertAlmostEqual(sa[0], self.a[0], places=12)
        # a frente de onda fica mais suave: o maior salto entre amostras cai
        self.assertLess(np.abs(np.diff(sa)).max(),
                        np.abs(np.diff(self.a)).max())
        # e o sinal de fato mudou
        self.assertFalse(np.array_equal(sa, self.a))
        self.assertEqual([r['efeito'] for r in reg], ['banda'])

    def test_atraso_comum_desloca_os_dois_canais_igualmente(self):
        k = 5
        self.cfg['atraso_comum'].update(ligado=True, atraso_s=k * self.ts)
        sa, sb, _ = self.aplicar()
        np.testing.assert_allclose(sa[k:], self.a[:-k], rtol=0, atol=1e-12)
        np.testing.assert_allclose(sb[k:], self.b[:-k], rtol=0, atol=1e-12)
        # antes do inicio o sinal e segurado no regime permanente
        np.testing.assert_allclose(sa[:k], self.a[0], rtol=0, atol=1e-12)

    def test_diferenca_de_atraso_afeta_apenas_o_canal_B(self):
        k = 3
        self.cfg['diferenca_de_atraso'].update(ligado=True,
                                               atraso_s=k * self.ts)
        sa, sb, _ = self.aplicar()
        np.testing.assert_array_equal(sa, self.a)
        np.testing.assert_allclose(sb[k:], self.b[:-k], rtol=0, atol=1e-12)

    def test_ruido_tem_o_desvio_padrao_pedido(self):
        sigma = 0.05
        self.cfg['ruido'].update(ligado=True, desvio_padrao_m=sigma,
                                 semente=7)
        sa, sb, _ = self.aplicar()
        residuo_a = sa - self.a
        residuo_b = sb - self.b
        self.assertAlmostEqual(residuo_a.std(), sigma, delta=0.1 * sigma)
        self.assertAlmostEqual(residuo_a.mean(), 0.0, delta=0.1 * sigma)
        # canais independentes: realizacoes diferentes
        self.assertFalse(np.array_equal(residuo_a, residuo_b))

    def test_ruido_e_reprodutivel_pela_semente(self):
        self.cfg['ruido'].update(ligado=True, desvio_padrao_m=0.05, semente=7)
        primeira, _, _ = self.aplicar()
        segunda, _, _ = self.aplicar()
        np.testing.assert_array_equal(primeira, segunda)

    def test_offset_e_uma_constante_exata(self):
        self.cfg['offset'].update(ligado=True, offset_A_m=0.25,
                                  offset_B_m=-0.40)
        sa, sb, _ = self.aplicar()
        np.testing.assert_allclose(sa - self.a, 0.25, rtol=0, atol=1e-12)
        np.testing.assert_allclose(sb - self.b, -0.40, rtol=0, atol=1e-12)

    def test_saturacao_corta_so_o_que_passa_dos_limites(self):
        # limites escolhidos dentro da excursao real do sinal
        minimo, maximo = 30.0, 55.0
        self.cfg['saturacao'].update(ligado=True, minimo_m=minimo,
                                     maximo_m=maximo)
        sa, _, _ = self.aplicar()
        self.assertGreaterEqual(sa.min(), minimo - 1e-12)
        self.assertLessEqual(sa.max(), maximo + 1e-12)
        dentro = (self.a >= minimo) & (self.a <= maximo)
        np.testing.assert_array_equal(sa[dentro], self.a[dentro])
        self.assertTrue((~dentro).any(), 'o ensaio precisa exercitar o corte')

    def test_quantizacao_poe_tudo_na_grade(self):
        bits, vmin, vmax = 12, 0.0, 100.0
        self.cfg['quantizacao'].update(ligado=True, bits=bits,
                                       fundo_de_escala_min_m=vmin,
                                       fundo_de_escala_max_m=vmax)
        sa, _, _ = self.aplicar()
        passo = MS.degrau_de_quantizacao(bits, vmin, vmax)
        codigos = (sa - vmin) / passo
        np.testing.assert_allclose(codigos, np.rint(codigos), atol=1e-9)
        self.assertLessEqual(np.abs(sa - self.a).max(), passo / 2 + 1e-12)
        self.assertAlmostEqual(MS.resolucao_declarada_m(self.cfg), passo)

    def test_sincronizacao_com_jitter_zero_e_identidade(self):
        self.cfg['erro_de_sincronizacao'].update(ligado=True, jitter_s=0.0,
                                                 semente=3)
        sa, sb, _ = self.aplicar()
        np.testing.assert_array_equal(sa, self.a)
        np.testing.assert_array_equal(sb, self.b)

    def test_sincronizacao_nao_afeta_sinal_sem_inclinacao(self):
        constante = np.full(500, 58.0)
        sa, _, _ = MS.aplicar(constante, constante, self.ts,
                              {**MS.config_neutra(),
                               'erro_de_sincronizacao': {
                                   'ligado': True, 'jitter_s': 1e-4,
                                   'semente': 3}})
        np.testing.assert_allclose(sa, constante, rtol=0, atol=1e-12)

    def test_sincronizacao_limitada_pela_inclinacao(self):
        jitter = 2e-5
        rampa = np.linspace(0.0, 10.0, 800)
        inclinacao = abs(rampa[1] - rampa[0]) / self.ts
        cfg = MS.config_neutra()
        cfg['erro_de_sincronizacao'].update(ligado=True, jitter_s=jitter,
                                            semente=3)
        sa, _, _ = MS.aplicar(rampa, rampa, self.ts, cfg)
        # desvio maximo plausivel: inclinacao vezes seis desvios de jitter
        self.assertLessEqual(np.abs(sa - rampa).max(),
                             inclinacao * 6.0 * jitter)
        self.assertFalse(np.array_equal(sa, rampa))


class Registro(unittest.TestCase):

    def test_registro_segue_a_ordem_da_cadeia(self):
        a, b, ts = sinal_de_ensaio()
        cfg = MS.config_neutra()
        cfg['quantizacao']['ligado'] = True
        cfg['ruido'].update(ligado=True, desvio_padrao_m=0.01)
        cfg['banda']['ligado'] = True
        _, _, reg = MS.aplicar(a, b, ts, cfg)
        self.assertEqual([r['efeito'] for r in reg],
                         ['banda', 'ruido', 'quantizacao'])
        self.assertIn('parametros', reg[0])
        self.assertNotIn('ligado', reg[0]['parametros'])


if __name__ == '__main__':
    unittest.main()

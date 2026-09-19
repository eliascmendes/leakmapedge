"""Testes da etapa A-10 (amostragem e referencia temporal comum).

Checa que a frequencia sai de criterio e nao de costume, que a decimacao
preserva o alinhamento do indice comum e que o atraso do antisserrilhamento e
igual nos dois canais, portanto se cancela em delta_t.
"""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import amostragem as AM  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PARAMETROS = os.path.join(RAIZ, '03_ensaios', 'parametros',
                          'leakmap_parametros_v1.json')


def parametros():
    with open(PARAMETROS, encoding='utf-8') as f:
        return json.load(f)


class EscolhaDaFrequencia(unittest.TestCase):

    def setUp(self):
        par = parametros()
        self.c = float(par['velocidade_de_onda']['efetiva_ajustada_m_s'])
        self.ts = float(par['passo_de_tempo']['efetivo_s'])

    def test_resolucao_obtida_cumpre_o_requisito(self):
        e = AM.escolher_frequencia(self.c, self.ts)
        self.assertLessEqual(e['resolucao_de_posicao_m'],
                             e['resolucao_de_projeto_m'])
        self.assertLessEqual(e['resolucao_de_posicao_m'],
                             e['requisito_de_resolucao_m'])

    def test_resolucao_e_c_vezes_periodo_sobre_dois(self):
        e = AM.escolher_frequencia(self.c, self.ts)
        self.assertAlmostEqual(
            e['resolucao_de_posicao_m'],
            self.c * e['periodo_de_amostragem_s'] / 2.0, places=12)

    def test_fator_e_o_maior_inteiro_que_ainda_atende(self):
        e = AM.escolher_frequencia(self.c, self.ts)
        fator = e['fator_de_decimacao']
        self.assertGreaterEqual(fator, 1)
        # o proximo fator inteiro ja violaria o requisito de projeto
        proxima_resolucao = self.c * (self.ts * (fator + 1)) / 2.0
        self.assertGreater(proxima_resolucao, e['resolucao_de_projeto_m'])

    def test_requisito_impossivel_e_recusado(self):
        with self.assertRaises(ValueError):
            AM.escolher_frequencia(self.c, self.ts,
                                   resolucao_requisito_m=1e-6)

    def test_janela_de_referencia_e_verificada_e_nao_suposta(self):
        e = AM.escolher_frequencia(self.c, self.ts)
        ok = AM.verificar_janela_de_referencia(200, e['fator_de_decimacao'],
                                               6, 3, 30)
        self.assertTrue(ok['aprovado'])
        apertado = AM.verificar_janela_de_referencia(40, e['fator_de_decimacao'],
                                                     6, 3, 30)
        self.assertFalse(apertado['aprovado'])


class Decimacao(unittest.TestCase):

    def setUp(self):
        self.ts = 1e-4
        self.n = 600

    def test_fator_um_nao_altera_nada(self):
        x = np.random.default_rng(0).normal(size=self.n)
        np.testing.assert_array_equal(AM.decimar(x, 1), x)

    def test_sem_antisserrilhamento_pega_as_amostras_originais(self):
        x = np.arange(self.n, dtype=float)
        y = AM.decimar(x, 4, antisserrilhamento=False)
        np.testing.assert_array_equal(y, x[::4])

    def test_media_movel_preserva_nivel_constante(self):
        x = np.full(self.n, 58.0)
        np.testing.assert_allclose(AM.media_movel(x, 4), 58.0, atol=1e-12)

    def test_atraso_do_antisserrilhamento_e_igual_nos_dois_canais(self):
        # Dois degraus separados por um atraso conhecido. Depois da decimacao
        # a diferenca entre as marcas tem de continuar a mesma, porque o
        # atraso de grupo do filtro e comum aos dois canais.
        fator = 4
        atraso_em_amostras = 40
        a = np.zeros(self.n)
        a[200:] = 1.0
        b = np.zeros(self.n)
        b[200 + atraso_em_amostras:] = 1.0

        da = AM.decimar(a, fator)
        db = AM.decimar(b, fator)
        ia = int(np.argmax(da > 0.5))
        ib = int(np.argmax(db > 0.5))
        self.assertEqual(ib - ia, atraso_em_amostras // fator)

    def test_atraso_de_grupo_declarado_bate_com_a_formula(self):
        self.assertAlmostEqual(AM.atraso_de_grupo_s(4, self.ts),
                               1.5 * self.ts, places=15)
        self.assertEqual(AM.atraso_de_grupo_s(1, self.ts), 0.0)
        self.assertEqual(AM.atraso_de_grupo_s(4, self.ts,
                                              antisserrilhamento=False), 0.0)


class Pacote(unittest.TestCase):

    def test_pacote_traz_tudo_que_a_especificacao_exige(self):
        par = parametros()
        c = float(par['velocidade_de_onda']['efetiva_ajustada_m_s'])
        ts = float(par['passo_de_tempo']['efetivo_s'])
        escolha = AM.escolher_frequencia(c, ts)
        n = 400
        t = np.arange(n) * ts
        ensaio = AM.montar_ensaio('T-01', t, np.full(n, 58.0),
                                  np.full(n, 52.0), {'L': 120.0}, [], escolha)
        pacote = AM.montar_pacote('teste', escolha,
                                  {'minimo_m': 0.0, 'maximo_m': 100.0},
                                  [ensaio], ts)

        for campo in ('versao_do_formato', 'amostragem', 'unidades', 'escala',
                      'atraso_de_grupo_do_antisserrilhamento_s', 'ensaios'):
            self.assertIn(campo, pacote)
        for campo in ('id', 'n_pontos', 'indice', 'tempo_s', 'canal_A_carga_m',
                      'canal_B_carga_m', 'parametros_do_detector',
                      'efeitos_de_sensor_aplicados'):
            self.assertIn(campo, ensaio)

        # indice comum aos dois canais e do mesmo tamanho das series
        self.assertEqual(ensaio['indice'], list(range(ensaio['n_pontos'])))
        self.assertEqual(len(ensaio['canal_A_carga_m']), ensaio['n_pontos'])
        self.assertEqual(len(ensaio['canal_B_carga_m']), ensaio['n_pontos'])
        self.assertEqual(len(ensaio['tempo_s']), ensaio['n_pontos'])

    def test_pacote_nao_carrega_a_verdade_do_cenario(self):
        par = parametros()
        c = float(par['velocidade_de_onda']['efetiva_ajustada_m_s'])
        ts = float(par['passo_de_tempo']['efetivo_s'])
        escolha = AM.escolher_frequencia(c, ts)
        ensaio = AM.montar_ensaio('T-01', np.arange(100) * ts,
                                  np.full(100, 58.0), np.full(100, 52.0),
                                  {'L': 120.0}, [], escolha)
        texto = json.dumps(AM.montar_pacote('teste', escolha, {}, [ensaio],
                                            ts))
        for proibido in ('posicao_real', 'no_do_evento', 'verdade'):
            self.assertNotIn(proibido, texto)


class PacoteGravado(unittest.TestCase):
    """O pacote da matriz, ja gravado em 03_ensaios, precisa ser legivel."""

    def setUp(self):
        caminho = os.path.join(RAIZ, '03_ensaios', 'pacotes',
                               'leakmap_pacote_matriz_v1.json')
        if not os.path.exists(caminho):
            self.skipTest('pacote ainda nao gerado; rode gerar_ensaios.py')
        with open(caminho, encoding='utf-8') as f:
            self.pacote = json.load(f)

    def test_base_de_tempo_e_comum_e_uniforme(self):
        esperado = self.pacote['amostragem']['periodo_de_amostragem_s']
        for ensaio in self.pacote['ensaios']:
            t = np.asarray(ensaio['tempo_s'], dtype=float)
            passos = np.diff(t)
            self.assertTrue(np.allclose(passos, esperado, rtol=1e-9),
                            'base de tempo nao uniforme em %s' % ensaio['id'])

    def test_nenhum_ensaio_expoe_a_posicao_real(self):
        texto = json.dumps(self.pacote)
        self.assertNotIn('posicao_real', texto)
        self.assertNotIn('no_do_evento', texto)


if __name__ == '__main__':
    unittest.main()

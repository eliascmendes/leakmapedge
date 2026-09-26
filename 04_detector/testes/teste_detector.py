"""Testes das etapas A-11, A-12, A-13 e A-14.

Tudo aqui e verificado sem abrir 03_ensaios/verdade_do_cenario. Os ensaios
sinteticos usados nos testes de A-12 e A-13 tem o atraso entre canais injetado
pelo proprio teste, entao o valor esperado e conhecido sem consultar a verdade
do cenario. Os testes que precisam da posicao real do vazamento ficam do lado
do avaliador, em 05_avaliacao/testes/teste_avaliador.py.
"""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detector as D  # noqa: E402
import posicao as P  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes',
                      'leakmap_pacote_matriz_v1.json')
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_matriz_v1.json')

TS = 4.0130559895570352e-4   # periodo de amostragem da matriz, em s
L_M = 120.0
C_M_S = 1200.899544131626
POS_A = 40.0


def parametros_padrao(c_m_s=C_M_S):
    return {
        'posicao_sensor_A_m': POS_A,
        'posicao_sensor_B_m': POS_A + L_M,
        'distancia_entre_sensores_L_m': L_M,
        'velocidade_de_onda_m_s': c_m_s,
        'incerteza_de_velocidade_de_onda_m_s': 0.0,
    }


def degrau(n, inicio, amplitude=-5.0, nivel=58.0, subida=3):
    """Frente de onda simples: nivel constante e uma rampa curta de descida."""
    x = np.full(n, float(nivel))
    rampa = np.linspace(0.0, amplitude, subida + 1)[1:]
    fim = min(n, inicio + subida)
    x[inicio:fim] = nivel + rampa[:fim - inicio]
    x[fim:] = nivel + amplitude
    return x


def ensaio_sintetico(identificador, canal_a, canal_b, c_m_s=C_M_S):
    n = len(canal_a)
    return {
        'id': identificador,
        'n_pontos': n,
        'indice': list(range(n)),
        'tempo_s': [i * TS for i in range(n)],
        'canal_A_carga_m': [float(v) for v in canal_a],
        'canal_B_carga_m': [float(v) for v in canal_b],
        'parametros_do_detector': parametros_padrao(c_m_s),
        'efeitos_de_sensor_aplicados': {},
    }


ESCALA_LARGA = {'minimo_m': 0.0, 'maximo_m': 100.0,
                'resolucao_declarada_m': 1.526e-3}


class A11Deteccao(unittest.TestCase):

    def test_evento_forte_e_detectado_nos_dois_canais(self):
        a = degrau(800, 300)
        b = degrau(800, 340)
        r = D.processar_ensaio(ensaio_sintetico('S-01', a, b), ESCALA_LARGA)
        self.assertTrue(r['canal_A']['detectado'])
        self.assertTrue(r['canal_B']['detectado'])
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO)

    def test_sinal_em_regime_nao_dispara(self):
        constante = np.full(800, 58.0)
        r = D.processar_ensaio(ensaio_sintetico('S-02', constante, constante),
                               ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_SEM_DETECCAO)
        self.assertGreater(r['canal_A']['n_oportunidades_de_decisao'], 0)

    def test_limiar_minimo_fica_acima_da_resolucao_do_sensor(self):
        cal = D.calibracao_padrao()
        grosseira = 0.5   # resolucao declarada maior que o piso absoluto
        self.assertGreaterEqual(D.piso_de_amplitude(cal, grosseira), grosseira)
        # e sem resolucao declarada vale o piso absoluto explicito
        self.assertEqual(D.piso_de_amplitude(cal, None),
                         cal['piso_de_amplitude_m'])

    def test_variacao_abaixo_da_resolucao_nao_dispara(self):
        # Degrau de 1e-6 m, da ordem do ruido numerico do simulador. E a falha
        # que A-11 manda tratar: o detector nao pode chamar isso de evento.
        a = degrau(800, 300, amplitude=-1e-6)
        b = degrau(800, 340, amplitude=-1e-6)
        r = D.processar_ensaio(ensaio_sintetico('S-03', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_SEM_DETECCAO)

    def test_passa_altas_remove_o_nivel_de_regime(self):
        x = np.full(500, 58.0)
        y = D.passa_altas(x, D.CORTE_PASSA_ALTAS_HZ, TS)
        np.testing.assert_allclose(y, 0.0, atol=1e-12)


class A12Marcacao(unittest.TestCase):
    """Criterio: delta_t medido bate com o atraso injetado, dentro de uma
    amostra."""

    def verificar(self, atraso_em_amostras, ruido=0.0, semente=0):
        n = 900
        inicio = 300
        a = degrau(n, inicio)
        b = degrau(n, inicio + atraso_em_amostras)
        if ruido:
            rng = np.random.default_rng(semente)
            a = a + rng.normal(0.0, ruido, n)
            b = b + rng.normal(0.0, ruido, n)
        r = D.processar_ensaio(ensaio_sintetico('S-1%d' % atraso_em_amostras,
                                                a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO, r.get('motivo'))
        esperado = -atraso_em_amostras * TS
        self.assertLessEqual(abs(r['delta_t_s'] - esperado), TS,
                             'delta_t medido %.6e s, esperado %.6e s, '
                             'diferenca maior que uma amostra'
                             % (r['delta_t_s'], esperado))
        return r

    def test_delta_t_bate_com_o_atraso_injetado(self):
        for atraso in (0, 10, 40, 120, 200):
            with self.subTest(atraso=atraso):
                self.verificar(atraso)

    def test_delta_t_bate_mesmo_com_ruido(self):
        for atraso in (0, 40, 120):
            with self.subTest(atraso=atraso):
                self.verificar(atraso, ruido=0.02, semente=atraso)

    def test_marca_nunca_e_posterior_ao_cruzamento(self):
        for ruido in (0.0, 0.02, 0.2):
            with self.subTest(ruido=ruido):
                r = self.verificar(40, ruido=ruido, semente=5)
                for canal in ('canal_A', 'canal_B'):
                    self.assertLessEqual(r[canal]['indice_de_chegada'],
                                         r[canal]['indice_de_cruzamento'])
                    self.assertGreaterEqual(
                        r[canal]['amostras_retrocedidas'], 0)

    def test_frente_forte_e_marcada_na_propria_chegada(self):
        # Com frente muito acima do ruido o cruzamento ja cai na primeira
        # amostra perturbada e nao ha atraso de janela para desfazer.
        r = self.verificar(40)
        self.assertEqual(r['canal_A']['indice_de_chegada'], 300)
        self.assertEqual(r['canal_B']['indice_de_chegada'], 340)

    def test_retrocesso_atua_quando_a_frente_emerge_devagar_do_ruido(self):
        # Frente fraca e lenta: o limiar so e cruzado varias amostras depois
        # da chegada, e o retrocesso e o que recupera parte desse atraso.
        n, inicio = 900, 300
        rng = np.random.default_rng(11)   # semente fixa: teste deterministico
        a = degrau(n, inicio, amplitude=-0.5, subida=40) + rng.normal(0, 0.02, n)
        b = degrau(n, inicio, amplitude=-0.5, subida=40) + rng.normal(0, 0.02, n)
        r = D.processar_ensaio(ensaio_sintetico('S-14', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO, r.get('motivo'))
        canal = r['canal_A']
        self.assertGreater(canal['amostras_retrocedidas'], 0)
        self.assertLess(canal['indice_de_chegada'],
                        canal['indice_de_cruzamento'])
        # e o retrocesso aproxima a marca da chegada verdadeira
        self.assertLess(abs(canal['indice_de_chegada'] - inicio),
                        abs(canal['indice_de_cruzamento'] - inicio))

    def test_incerteza_e_positiva_e_composta(self):
        r = self.verificar(40, ruido=0.02)
        for canal in ('canal_A', 'canal_B'):
            self.assertGreater(r[canal]['incerteza_s'], 0.0)
            componentes = r[canal]['componentes_da_incerteza_s']
            self.assertEqual(set(componentes),
                             {'quantizacao_temporal',
                              'ruido_sobre_inclinacao',
                              'ambiguidade_do_retrocesso'})
        self.assertGreater(r['incerteza_de_delta_t_s'], 0.0)


class A13Evidencia(unittest.TestCase):

    def test_evento_em_um_so_canal_fica_inconclusivo(self):
        a = degrau(800, 300)
        b = np.full(800, 52.0)
        r = D.processar_ensaio(ensaio_sintetico('S-20', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_SEM_LOCALIZACAO)
        self.assertIn('canal B', r['motivo'])
        self.assertIsNone(r.get('posicao_estimada_m'))

    def test_canal_saturado_sai_inconclusivo_e_nao_posicao_errada(self):
        # fundo de escala estreito: o canal A encosta no limite inferior
        escala = {'minimo_m': 54.0, 'maximo_m': 60.0,
                  'resolucao_declarada_m': 1e-3}
        a = np.clip(degrau(800, 300), 54.0, 60.0)
        b = np.clip(degrau(800, 340), 54.0, 60.0)
        r = D.processar_ensaio(ensaio_sintetico('S-21', a, b), escala)
        self.assertEqual(r['classe'], D.CLASSE_SEM_LOCALIZACAO)
        self.assertIn('fundo de escala', r['motivo'])
        self.assertIsNone(r.get('posicao_estimada_m'))

    def test_delta_t_fora_da_faixa_fisica_fica_inconclusivo(self):
        limite_em_amostras = int(np.ceil(P.limite_fisico_de_delta_t(L_M, C_M_S)
                                         / TS))
        n = 2 * limite_em_amostras + 700
        a = degrau(n, 300)
        b = degrau(n, 300 + limite_em_amostras + 60)
        r = D.processar_ensaio(ensaio_sintetico('S-22', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_SEM_LOCALIZACAO)
        self.assertIn('faixa fisica', r['motivo'])
        self.assertIsNone(r.get('posicao_estimada_m'))

    def test_delta_t_zero_e_valido_e_nao_inconclusivo(self):
        a = degrau(800, 300)
        b = degrau(800, 300)
        r = D.processar_ensaio(ensaio_sintetico('S-23', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO)
        self.assertEqual(r['delta_t_s'], 0.0)
        self.assertAlmostEqual(r['posicao_estimada_m'], POS_A + L_M / 2.0,
                               places=9)

    def test_falha_de_execucao_ainda_produz_registro(self):
        ensaio = ensaio_sintetico('S-24', degrau(800, 300), degrau(800, 340))
        del ensaio['parametros_do_detector']['velocidade_de_onda_m_s']
        r = D.processar_ensaio(ensaio, ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_FALHA)
        self.assertEqual(r['id'], 'S-24')
        self.assertTrue(r['motivo'])


class ClassificacaoFisica(unittest.TestCase):
    """Polaridade e origem (secao 5.4 do projeto): so queda nos dois canais,
    dentro do trecho, e vazamento."""

    def test_queda_nos_dois_canais_dentro_do_trecho_e_vazamento(self):
        r = D.processar_ensaio(ensaio_sintetico('S-30', degrau(800, 300), degrau(800, 340)), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO)
        self.assertEqual((r['canal_A']['polaridade'], r['canal_B']['polaridade']), ('queda', 'queda'))

    def test_alta_nos_dois_canais_e_manobra(self):
        a, b = degrau(800, 300, amplitude=+5.0), degrau(800, 340, amplitude=+5.0)
        r = D.processar_ensaio(ensaio_sintetico('S-31', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_MANOBRA)
        self.assertIsNone(r.get('posicao_estimada_m'))
        self.assertIsNotNone(r.get('posicao_da_origem_m'))

    def test_polaridades_opostas_sao_manobra_entre_os_sensores(self):
        a, b = degrau(800, 300, amplitude=+5.0), degrau(800, 340, amplitude=-5.0)
        r = D.processar_ensaio(ensaio_sintetico('S-32', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_MANOBRA)
        self.assertIn('opostas', r['motivo'])

    def test_alta_num_canal_so_e_manobra(self):
        r = D.processar_ensaio(ensaio_sintetico('S-33', degrau(800, 300, amplitude=+5.0),
                                                np.full(800, 52.0)), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_MANOBRA)

    def test_queda_no_limite_fisico_e_fora_do_trecho_do_lado_certo(self):
        limite = int(round(P.limite_fisico_de_delta_t(L_M, C_M_S) / TS))
        n = limite + 900
        a, b = degrau(n, 300), degrau(n, 300 + limite)         # A viu primeiro, L/c antes
        r = D.processar_ensaio(ensaio_sintetico('S-34', a, b), ESCALA_LARGA)
        self.assertEqual(r['classe'], D.CLASSE_FORA_DO_TRECHO)
        self.assertEqual(r['lado_da_origem'], 'A')
        r = D.processar_ensaio(ensaio_sintetico('S-35', b, a), ESCALA_LARGA)
        self.assertEqual(r['lado_da_origem'], 'B')

    def test_sem_classificacao_volta_ao_detector_de_antes(self):
        a, b = degrau(800, 300, amplitude=+5.0), degrau(800, 340, amplitude=+5.0)
        r = D.processar_ensaio(ensaio_sintetico('S-36', a, b), ESCALA_LARGA, classificar=False)
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO)


class A14Posicao(unittest.TestCase):

    def test_formula_no_meio_do_trecho(self):
        self.assertAlmostEqual(
            P.posicao_a_partir_do_sensor_A(L_M, C_M_S, 0.0), L_M / 2.0)

    def test_extremos_caem_sobre_os_sensores(self):
        limite = P.limite_fisico_de_delta_t(L_M, C_M_S)
        self.assertAlmostEqual(
            P.posicao_a_partir_do_sensor_A(L_M, C_M_S, -limite), 0.0,
            places=9)
        self.assertAlmostEqual(
            P.posicao_a_partir_do_sensor_A(L_M, C_M_S, limite), L_M, places=9)

    def test_posicao_acompanha_delta_t_de_forma_monotona(self):
        limite = P.limite_fisico_de_delta_t(L_M, C_M_S)
        deltas = np.linspace(-limite, limite, 41)
        xs = [P.posicao_a_partir_do_sensor_A(L_M, C_M_S, d) for d in deltas]
        self.assertTrue(np.all(np.diff(xs) > 0))

    def test_posicao_nunca_sai_do_trecho(self):
        fora = P.limite_fisico_de_delta_t(L_M, C_M_S) * 1.5
        for delta in (-fora, fora):
            loc = P.localizar(L_M, C_M_S, delta, POS_A)
            self.assertGreaterEqual(loc['posicao_estimada_rel_sensor_A_m'], 0.0)
            self.assertLessEqual(loc['posicao_estimada_rel_sensor_A_m'], L_M)
            self.assertTrue(loc['posicao_limitada_a_faixa'])

    def test_propagacao_de_erro_temporal(self):
        # dx = c * d(delta_t) / 2
        u = 1e-4
        self.assertAlmostEqual(P.incerteza_de_posicao_m(C_M_S, 0.0, u, 0.0),
                               C_M_S * u / 2.0, places=12)

    def test_propagacao_de_erro_de_velocidade(self):
        # dx = delta_t * dc / 2
        delta_t, uc = 0.05, 24.0
        self.assertAlmostEqual(
            P.incerteza_de_posicao_m(C_M_S, delta_t, 0.0, uc),
            delta_t * uc / 2.0, places=12)


class PacoteDaMatriz(unittest.TestCase):
    """Criterio de conclusao de A-11 sobre os ensaios de verdade gravados."""

    def setUp(self):
        if not os.path.exists(PACOTE) or not os.path.exists(PLANO):
            self.skipTest('matriz ainda nao gerada; rode gerar_ensaios.py')
        with open(PACOTE, encoding='utf-8') as f:
            self.pacote = json.load(f)
        with open(PLANO, encoding='utf-8') as f:
            self.plano = {e['id']: e for e in json.load(f)['ensaios']}
        self.registros = D.processar_pacote(self.pacote)

    def test_um_registro_por_ensaio(self):
        self.assertEqual(len(self.registros), len(self.pacote['ensaios']))
        identificadores = [r['id'] for r in self.registros]
        self.assertEqual(len(set(identificadores)), len(identificadores))

    def test_evento_forte_detectado_nos_dois_canais(self):
        for r in self.registros:
            if not self.plano[r['id']]['tem_evento']:
                continue
            with self.subTest(ensaio=r['id']):
                self.assertTrue(r['canal_A']['detectado'])
                self.assertTrue(r['canal_B']['detectado'])

    def test_taxa_de_falso_alarme_medida_e_zero_com_oportunidades_contadas(self):
        falsos = 0
        oportunidades = 0
        for r in self.registros:
            if self.plano[r['id']]['tem_evento']:
                continue
            if r['classe'] != D.CLASSE_SEM_DETECCAO:
                falsos += 1
            for canal in ('canal_A', 'canal_B'):
                oportunidades += r[canal]['n_oportunidades_de_decisao']
        self.assertGreater(oportunidades, 1000,
                           'a taxa de falso alarme precisa de denominador')
        self.assertEqual(falsos, 0)

    def test_nenhuma_posicao_cai_fora_do_trecho(self):
        for r in self.registros:
            x = r.get('posicao_estimada_rel_sensor_A_m')
            if x is None:
                continue
            with self.subTest(ensaio=r['id']):
                self.assertGreaterEqual(x, 0.0)
                self.assertLessEqual(x, L_M)


if __name__ == '__main__':
    unittest.main()

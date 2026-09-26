"""Testes da localizacao numa rede em arvore (04_detector/rede.py).

As chegadas saem da propria geometria da topologia de teste, para um ponto
escolhido pelo teste; nao abrem a verdade de nenhum cenario.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detector as D  # noqa: E402
import rede as RD  # noqa: E402

C = 1200.0
TS = 4e-4
TOPO = {
    'trechos': {'tronco': {'comprimento_monitorado_m': 300.0, 'juncao_em_s_m': 300.0},
                'ramal_1': {'comprimento_monitorado_m': 250.0, 'juncao_em_s_m': 0.0},
                'ramal_2': {'comprimento_monitorado_m': 400.0, 'juncao_em_s_m': 0.0},
                'ramal_3': {'comprimento_monitorado_m': 550.0, 'juncao_em_s_m': 0.0}},
    'sensores': {'A': {'trecho': 'tronco', 's_m': 0.0}, 'B1': {'trecho': 'ramal_1', 's_m': 250.0},
                 'B2': {'trecho': 'ramal_2', 's_m': 400.0}, 'B3': {'trecho': 'ramal_3', 's_m': 550.0}},
    'velocidade_de_onda_m_s': C,
}


def chegadas(trecho, s, t0=0.1, sensores=None):
    return {n: t0 + float(RD.distancia(TOPO, trecho, s, n)) / C for n in (sensores or TOPO['sensores'])}


def localizar(ch):
    return RD.localizar_na_rede(ch, {n: TS / 2 for n in ch}, TOPO, C, TS)


class LocalizacaoNaRede(unittest.TestCase):

    def test_distancias_pela_tubulacao(self):
        self.assertAlmostEqual(float(RD.distancia(TOPO, 'ramal_2', 100.0, 'A')), 400.0)
        self.assertAlmostEqual(float(RD.distancia(TOPO, 'ramal_2', 100.0, 'B2')), 300.0)
        self.assertAlmostEqual(float(RD.distancia(TOPO, 'ramal_2', 100.0, 'B1')), 350.0)
        self.assertAlmostEqual(float(RD.distancia(TOPO, 'tronco', 120.0, 'B3')), 730.0)

    def test_acha_o_trecho_e_o_ponto(self):
        for trecho, s in (('tronco', 150.0), ('ramal_1', 100.0), ('ramal_2', 30.0), ('ramal_3', 451.3)):
            classe, _, d = localizar(chegadas(trecho, s))
            self.assertEqual(classe, D.CLASSE_LOCALIZADO, (trecho, s))
            self.assertEqual(d['trecho_estimado'], trecho)
            self.assertAlmostEqual(d['s_estimado_m'], s, delta=RD.PASSO_DE_BUSCA_M)

    def test_erro_de_tempo_de_uma_amostra_desloca_meia_amostra_de_onda(self):
        ch = chegadas('ramal_3', 300.0)
        ch['B3'] += TS
        classe, _, d = localizar(ch)
        self.assertEqual((classe, d['trecho_estimado']), (D.CLASSE_LOCALIZADO, 'ramal_3'))
        self.assertLess(abs(d['s_estimado_m'] - 300.0), C * TS)

    def test_vazamento_antes_do_sensor_A_sai_fora_do_trecho(self):
        # antes do sensor A, a onda chega a todos como se nascesse em cima dele
        ch = {n: t + 150.0 / C for n, t in chegadas('tronco', 0.0).items()}
        classe, _, d = localizar(ch)
        self.assertEqual((classe, d['lado_da_origem']), (D.CLASSE_FORA_DO_TRECHO, 'A'))

    def test_chegadas_incoerentes_nao_localizam(self):
        ch = chegadas('ramal_2', 200.0)
        ch['A'] += 0.02
        self.assertEqual(localizar(ch)[0], D.CLASSE_SEM_LOCALIZACAO)

    def test_periodo_de_atualizacao_declarado_entra_na_incerteza(self):
        # transmissor que atualiza a cada 10 ms: cada chegada atrasa ate 10 ms, sem relacao entre canais
        ch = chegadas('ramal_2', 250.0)
        for nome, atraso in zip(sorted(ch), (0.0081, 0.0012, 0.0064, 0.0037)):
            ch[nome] += atraso
        sem = RD.localizar_na_rede(ch, {n: TS / 2 for n in ch}, TOPO, C, TS)
        self.assertEqual(sem[0], D.CLASSE_SEM_LOCALIZACAO)
        u = float(np.hypot(TS / 2, 0.010 / np.sqrt(12.0)))
        classe, _, d = RD.localizar_na_rede(ch, {n: u for n in ch}, TOPO, C, TS)
        self.assertEqual((classe, d['trecho_estimado']), (D.CLASSE_LOCALIZADO, 'ramal_2'))
        self.assertLess(abs(d['s_estimado_m'] - 250.0), C * 0.010)

    def test_dois_sensores_do_mesmo_lado_do_manifold_sao_ambiguos(self):
        # so A e B1: um vazamento no ramal 2 ou no ramal 3 da o mesmo par de chegadas
        ch = chegadas('ramal_2', 100.0, sensores=['A', 'B1'])
        classe, motivo, _ = localizar(ch)
        self.assertEqual(classe, D.CLASSE_SEM_LOCALIZACAO)
        self.assertIn('ambigua', motivo)


class EnsaioNaRede(unittest.TestCase):

    def test_processa_quatro_canais_sinteticos(self):
        n, t0 = 2000, 0.1
        t = np.arange(n) * TS
        canais = {}
        for nome, chegada in chegadas('ramal_1', 180.0, t0).items():
            canais[nome] = 70.0 - 4.0 * 0.5 * (1.0 + np.tanh((t - chegada) / (1.5 * TS)))
        r = RD.processar_ensaio_rede({'id': 'R', 'tempo_s': list(t), 'canais_carga_m': canais},
                                     {'minimo_m': 0.0, 'maximo_m': 180.0, 'resolucao_declarada_m': 1e-3}, TOPO)
        self.assertEqual(r['classe'], D.CLASSE_LOCALIZADO, r.get('motivo'))
        self.assertEqual(r['trecho_estimado'], 'ramal_1')
        self.assertAlmostEqual(r['s_estimado_m'], 180.0, delta=C * TS)


if __name__ == '__main__':
    unittest.main()

"""Testes da previsao do golpe antes da manobra (07_servico/previsao_de_golpe.py).

Roda com: python -m unittest discover -s 07_servico/testes -p "teste_*.py"
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import previsao_de_golpe as PG  # noqa: E402
import sobrepressao as SP  # noqa: E402

C, D = 1227.0, 0.20274
AREA = math.pi * D ** 2 / 4.0
BPM = 840.0 * 9.81 / 1e5                 # bar por metro de coluna de diesel
LINHA = {'id': 'cais', 'velocidade_de_onda_m_s': C, 'area_m2': AREA, 'bar_por_metro': BPM}
ESTUDO = [(0.3, 1.0), (1.0, 0.9), (2.0, 0.8), (3.0, 0.6)]


def valvula(estudo=ESTUDO, vazao=0.040, ligacoes=1):
    return {'id': 'XV-108', 'tipo': 'valvula',
            'hidraulica': {'vazao_m3_s': vazao, 'ligacoes': ligacoes, 'distancia_de_alivio_m': 1030.0,
                           'sensor_de_referencia': 'B', 'estudo': estudo, 'origem_do_estudo': 'estudo de teste',
                           'manobra_padrao': {'fracao_da_vazao_cortada': 0.5, 'tempo_de_manobra_s': 0.3}}}


class Fisica(unittest.TestCase):

    def test_fechamento_total_rapido_e_joukowsky(self):
        dh = PG.subida_m(C, AREA, 0.040, 1.0, 74.6, 1)
        self.assertAlmostEqual(dh, C * 0.040 / (9.81 * AREA), places=6)

    def test_meio_da_linha_divide_por_dois_e_corte_parcial_com_orificio(self):
        total = PG.subida_m(C, AREA, 0.040, 1.0, 74.6, 1)
        self.assertAlmostEqual(PG.subida_m(C, AREA, 0.040, 1.0, 74.6, 2), total / 2, places=6)
        metade = PG.subida_m(C, AREA, 0.040, 0.5, 74.6, 1)
        # a vazao que resta cresce com a pressao: o golpe de meio corte e menor que metade do golpe total
        self.assertLess(metade, total / 2)
        # o valor que o TSNet deu para esse corte (fechar a XV-108 na linha do cais): 53,5 m
        self.assertAlmostEqual(metade, 53.5, delta=1.0)
        self.assertEqual(PG.subida_m(C, AREA, 0.0, 1.0, 74.6), 0.0)

    def test_fator_do_tempo(self):
        self.assertEqual(PG.fator_do_tempo(0.1, ESTUDO), (1.0, 'estudo'))
        self.assertAlmostEqual(PG.fator_do_tempo(1.5, ESTUDO)[0], 0.85)
        self.assertAlmostEqual(PG.fator_do_tempo(6.0, ESTUDO)[0], 0.3)          # alem da tabela: 1/t
        self.assertAlmostEqual(PG.fator_do_tempo(3.36, None, 1.68)[0], 0.5)      # Michaud
        self.assertEqual(PG.fator_do_tempo(3.0)[0], 1.0)

    def test_estudo_da_tabela_normaliza_e_nunca_sobe(self):
        r = [{'caso': 'x', 'fracao_da_vazao_cortada': f, 'tempo_de_manobra_s': t, 'maior_subida_no_equipamento_m': dh}
             for f, t, dh in ((0.5, 0.3, 50.0), (0.5, 1.0, 45.0), (0.5, 2.0, 47.0), (1.0, 0.3, 100.0),
                              (1.0, 1.0, 80.0), (1.0, 2.0, 70.0))]
        r.append({'caso': 'x', 'papel': 'conferencia', 'fracao_da_vazao_cortada': 0.7, 'tempo_de_manobra_s': 1.0,
                  'maior_subida_no_equipamento_m': 1.0})
        self.assertEqual(PG.estudo_da_tabela(r, 'x'), [(0.3, 1.0), (1.0, 0.9), (2.0, 0.9)])
        self.assertIsNone(PG.estudo_da_tabela(r, 'outro'))


class Previsao(unittest.TestCase):

    def test_fechamento_da_valvula_do_navio(self):
        p = PG.prever(LINHA, valvula(), 'fechar', 6.15, 12.0)
        self.assertEqual((p['tipo'], p['acao'], p['nivel'], p['metodo']), ('leakmap.previsao_de_golpe', 'fechamento',
                                                                         'atencao', 'estudo'))
        self.assertAlmostEqual(p['pico_previsto_bar'], 10.55, delta=0.05)     # o alerta mede 10,55 bar
        self.assertAlmostEqual(p['faixa_bar'][0], 6.15 + p['subida_prevista_bar'] * (1 - PG.MARGEM), delta=0.002)
        self.assertAlmostEqual(p['faixa_bar'][1], 6.15 + p['subida_prevista_bar'] * (1 + PG.MARGEM), delta=0.002)
        self.assertIn('pelo menos', p['explicacao'])
        # no tempo minimo, o pico com a margem fica abaixo do nivel de atencao
        q = PG.prever(LINHA, valvula(), 'fechar', 6.15, 12.0, tempo_de_manobra_s=p['tempo_minimo_seguro_s'])
        self.assertLess(q['faixa_bar'][1], SP.FRACAO_ATENCAO * 12.0 + 1e-6)
        self.assertIsNone(q['nivel'])
        self.assertEqual([c['tempo_de_manobra_s'] for c in p['curva']][0], 0.3)

    def test_alarme_e_faixa_do_transmissor(self):
        p = PG.prever(LINHA, valvula(), 'fechamento', 6.15, 12.0, fracao_da_vazao_cortada=1.0, faixa_bar=15.0)
        self.assertEqual(p['nivel'], 'alarme')
        self.assertIn('passaria do limite', p['explicacao'])
        self.assertIn('faixa do transmissor', p['explicacao'])

    def test_manobra_segura_e_regime_ja_alto(self):
        p = PG.prever(LINHA, valvula(vazao=0.005), 'fechar', 6.15, 12.0)
        self.assertIsNone(p['nivel'])
        self.assertEqual(p['tempo_minimo_seguro_s'], 0.0)
        p = PG.prever(LINHA, valvula(), 'fechar', 9.8, 12.0)
        self.assertIsNone(p['tempo_minimo_seguro_s'])
        self.assertIn('regime', p['explicacao'])

    def test_sem_estudo_usa_michaud_e_avisa(self):
        p = PG.prever(LINHA, valvula(estudo=None), 'fechar', 6.15, 12.0, tempo_de_manobra_s=3.0)
        self.assertEqual(p['metodo'], 'michaud')
        self.assertIn('Michaud', p['explicacao'])

    def test_abrir_parar_e_partir(self):
        p = PG.prever(LINHA, valvula(), 'abrir', 6.15, 12.0)
        self.assertEqual((p['sobe_a_pressao'], p['nivel'], p['pico_previsto_bar']), (False, None, 6.15))
        bomba = {'id': 'B-01', 'tipo': 'bomba', 'hidraulica': None}
        self.assertFalse(PG.prever(LINHA, bomba, 'parar', 6.75, 12.0)['sobe_a_pressao'])
        p = PG.prever(LINHA, bomba, 'partir', 6.75, 12.0)
        self.assertIsNone(p['pico_previsto_bar'])
        self.assertIn('Sem previsão', p['explicacao'])


if __name__ == '__main__':
    unittest.main()

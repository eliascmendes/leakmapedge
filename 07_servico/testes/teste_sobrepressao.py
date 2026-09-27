"""Testes do alerta de sobrepressao (07_servico/sobrepressao.py).

Roda com: python -m unittest discover -s 07_servico/testes -p "teste_*.py"
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sobrepressao as SP  # noqa: E402

PASSO = 0.1
N = 250


def bloco(k, valores):
    """Bloco k de 0,1 s com a pressao constante de cada sensor, salvo um pico no meio."""
    t = k * PASSO + np.arange(1, N + 1) * (PASSO / N)
    return t, {s: np.full(N, v, dtype=float) for s, v in valores.items()}


def rodar(monitor, sequencia, excluir=()):
    """sequencia: lista de {sensor: bar} por bloco. Devolve [(bloco, acontecimento, nivel)]."""
    saida = []
    for k, valores in enumerate(sequencia):
        t, p = bloco(k, valores)
        for acontecimento, ep in monitor.passo(t, p, excluir):
            saida.append((k, acontecimento, ep['nivel']))
    return saida


class Monitor(unittest.TestCase):

    def test_regime_abaixo_do_limiar_nao_abre_episodio(self):
        m = SP.Monitor(12.0)
        self.assertEqual(rodar(m, [{'A': 6.7, 'B': 6.1}] * 30), [])

    def test_pico_abre_publica_depois_de_1_s_e_encerra(self):
        m = SP.Monitor(12.0)
        seq = [{'A': 6.7, 'B': 6.1}] * 5 + [{'A': 7.0, 'B': 10.4}] * 3 + [{'A': 6.7, 'B': 6.1}] * 25
        r = rodar(m, seq)
        self.assertEqual([a for _, a, _ in r], ['abrir', 'encerrar'])
        self.assertEqual(r[0][2], 'atencao')                   # 10,4 bar = 87% de 12 bar
        self.assertGreaterEqual(r[0][0], 5 + 9)                 # publicado ~1 s depois do inicio
        self.assertIsNone(m.episodio)

    def test_sobe_de_atencao_para_alarme(self):
        m = SP.Monitor(12.0)
        seq = [{'A': 10.0}] * 12 + [{'A': 11.6}] * 3 + [{'A': 6.0}] * 15
        self.assertEqual([(a, n) for _, a, n in rodar(m, seq)],
                         [('abrir', 'atencao'), ('subir', 'alarme'), ('encerrar', 'alarme')])

    def test_histerese_segura_o_episodio_perto_do_limiar(self):
        m = SP.Monitor(12.0)                                    # limiar 9,6 bar; folga ate 9,3 bar
        seq = [{'A': 9.7}] * 3 + [{'A': 9.4}] * 20 + [{'A': 6.0}] * 12
        self.assertEqual([a for _, a, _ in rodar(m, seq)], ['abrir', 'encerrar'])

    def test_sensor_reprovado_fica_de_fora(self):
        m = SP.Monitor(12.0)
        self.assertEqual(rodar(m, [{'A': 6.7, 'B': 14.9}] * 20, excluir=('B',)), [])


class Evento(unittest.TestCase):

    def episodio(self, pico=10.4):
        m = SP.Monitor(12.0)
        for _, ep in m.passo(*bloco(0, {'A': 7.0, 'B': pico})):
            pass
        return m.episodio

    def test_causa_provavel_e_explicacao(self):
        ep = self.episodio()
        ep['nivel'] = 'atencao'
        ops = [{'equipamento': 'XV-108', 'acao': 'fechamento', 'instante_s': 0.0},
               {'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': -30.0}]
        e = SP.montar_evento(ep, 'cais', 12.0, 'premissa', ops, '2026-09-27T00:00:00Z', em_curso=True)
        self.assertEqual((e['tipo'], e['nivel'], e['sensor_do_pico'], e['revisao']),
                         ('leakmap.sobrepressao', 'atencao', 'B', 1))
        self.assertAlmostEqual(e['fracao_do_limite'], 10.4 / 12.0, places=3)
        self.assertEqual(e['causa_provavel']['equipamento'], 'XV-108')
        self.assertIn('fechamento da XV-108, registrado', e['explicacao'])
        self.assertIn('mais devagar', e['explicacao'])

    def test_sem_operacao_registrada_pede_para_conferir(self):
        ep = self.episodio()
        ep['nivel'] = 'atencao'
        e = SP.montar_evento(ep, 'cais', 12.0, 'premissa', [], 'x', em_curso=True)
        self.assertIsNone(e['causa_provavel'])
        self.assertIn('conferir', e['explicacao'])

    def test_pico_na_faixa_do_transmissor_avisa_que_pode_ser_maior(self):
        ep = self.episodio(pico=15.0)
        ep['nivel'] = 'alarme'
        e = SP.montar_evento(ep, 'cais', 12.0, 'premissa', [], 'x', em_curso=True, faixa_bar=15.0)
        self.assertTrue(e['pico_pode_ser_maior'])
        self.assertIn('mangotes', e['explicacao'])


if __name__ == '__main__':
    unittest.main()

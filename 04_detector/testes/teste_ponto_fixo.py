"""Testes do porte de referencia em ponto fixo (bonus, etapas A-11 e A-12).

Criterio: o porte inteiro tem de reproduzir a versao em ponto flutuante nos
mesmos ensaios da matriz, com a mesma decisao de deteccao, o mesmo indice de
cruzamento e a mesma marca de chegada, canal a canal.

Os dois portes recebem a mesma entrada ja quantizada. Sem isso a comparacao
mediria a quantizacao da entrada, que e efeito de A-09, e nao a aritmetica
inteira, que e o que este porte muda.
"""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detector as D  # noqa: E402
import detector_ponto_fixo as PF  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes',
                      'leakmap_pacote_matriz_v1.json')


class Conversao(unittest.TestCase):

    def test_codigo_e_inteiro_e_reversivel_dentro_de_meio_degrau(self):
        degrau = 100.0 / (2 ** 16 - 1)
        x = np.linspace(0.0, 100.0, 5000)
        codigo = PF.para_codigo(x, degrau)
        self.assertEqual(codigo.dtype, np.int64)
        reconstruido = codigo.astype(float) * degrau
        self.assertLessEqual(np.abs(reconstruido - x).max(), degrau / 2 + 1e-9)

    def test_limiar_nao_inteiro_e_recusado(self):
        cal = D.calibracao_padrao()
        cal['limiar_de_razao'] = 12.5
        with self.assertRaises(ValueError):
            PF.detectar_canal_inteiro(np.full(400, 58.0), 4e-4, 1e-3, cal)


class ContraPontoFlutuante(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(PACOTE):
            self.skipTest('matriz ainda nao gerada; rode gerar_ensaios.py')
        with open(PACOTE, encoding='utf-8') as f:
            self.pacote = json.load(f)
        self.relatorio = PF.comparar_pacote(self.pacote)

    def test_todos_os_canais_da_matriz_batem(self):
        self.assertEqual(self.relatorio['n_comparacoes'],
                         2 * len(self.pacote['ensaios']))
        for c in self.relatorio['comparacoes']:
            with self.subTest(ensaio=c['id'], canal=c['canal']):
                self.assertTrue(c['mesma_deteccao'])
                self.assertTrue(c['mesmo_cruzamento'])
                self.assertTrue(c['mesma_chegada'],
                                'chegada %r em ponto fixo contra %r em ponto '
                                'flutuante' % (c['indice_de_chegada_ponto_fixo'],
                                               c['indice_de_chegada_ponto_flutuante']))
        self.assertEqual(self.relatorio['divergentes'], 0)

    def test_larguras_de_palavra_cabem_em_sessenta_e_quatro_bits(self):
        larguras = self.relatorio['larguras_de_palavra_observadas_bits']
        self.assertTrue(larguras)
        for estagio, bits in larguras.items():
            with self.subTest(estagio=estagio):
                self.assertLessEqual(bits, PF.BITS_MAXIMOS)

    def test_erro_do_filtro_fica_em_poucos_degraus_de_entrada(self):
        # O deslocamento a direita trunca em vez de arredondar, entao o estado
        # do filtro em ponto fixo fica alguns degraus abaixo do de ponto
        # flutuante. O que importa e que isso nao mova nenhuma marca, o que o
        # teste acima ja verifica; aqui so se registra a ordem de grandeza.
        self.assertLess(
            self.relatorio['erro_maximo_do_passa_altas_em_degraus'], 5.0)


class EstouroDeLarguraDeclarado(unittest.TestCase):

    def test_estagio_largo_demais_para_a_execucao(self):
        larguras = {}
        arranjo = np.array([2 ** 20], dtype=np.int64)
        limite_original = PF.BITS_MAXIMOS
        PF.BITS_MAXIMOS = 10
        try:
            with self.assertRaises(PF.EstouroDeLargura):
                PF._conferir('teste', arranjo, larguras)
        finally:
            PF.BITS_MAXIMOS = limite_original
        # dentro do limite, o estagio passa e a largura fica registrada
        PF._conferir('teste', arranjo, larguras)
        self.assertEqual(larguras['teste'], 22)


if __name__ == '__main__':
    unittest.main()

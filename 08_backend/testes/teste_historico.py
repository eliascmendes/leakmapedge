"""Testes do historico da bancada, em SQLite e, quando houver, em PostgreSQL.

O PostgreSQL entra quando LEAKMAP_BANCO_DE_TESTE tem o endereco de um banco
descartavel (o GitHub Actions sobe um; localmente, qualquer PostgreSQL de
teste). Sem ele, esses testes sao pulados.

Roda com: python -m unittest discover -s 08_backend/testes -p "teste_*.py"
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import historico as HI  # noqa: E402

PG = os.environ.get('LEAKMAP_BANCO_DE_TESTE')


def evento(ident, instante, nivel='provavel', linha='cais'):
    return {'id': ident, 'instante_utc': instante, 'linha': linha, 'nivel': nivel, 'explicacao': 'Queda de pressão'}


class Comum:
    """Os mesmos testes para os dois bancos; a subclasse diz o endereco."""

    def abrir(self):
        raise NotImplementedError

    def setUp(self):
        self.h = self.abrir()

    def tearDown(self):
        self.h.fechar()

    def test_gravar_obter_e_sinal(self):
        self.h.gravar(evento('a', '2026-09-27T01:00:00Z'), {'s_m': 320.0}, {'periodo_s': 0.0004, 'pressao_bar': {'A': [6.7]}})
        self.assertEqual(self.h.obter('a')['evento']['explicacao'], 'Queda de pressão')
        self.assertEqual(self.h.obter('a')['verdade'], {'s_m': 320.0})
        self.assertEqual(self.h.sinal('a')['pressao_bar']['A'], [6.7])
        self.assertIsNone(self.h.obter('nao-existe'))

    def test_revisao_substitui_o_mesmo_id(self):
        self.h.gravar(evento('b', '2026-09-27T01:00:00Z'), None, {})
        self.h.gravar(dict(evento('b', '2026-09-27T01:00:00Z', 'confirmado'), revisao=2), None, {})
        self.assertEqual(self.h.contar(), 1)
        self.assertEqual(self.h.obter('b')['evento']['nivel'], 'confirmado')

    def test_listar_com_filtros_do_mais_novo_para_o_mais_antigo(self):
        self.h.gravar(evento('c1', '2026-09-27T01:00:00Z', 'suspeita'), None, {})
        self.h.gravar(evento('c2', '2026-09-27T02:00:00Z', 'provavel', 'rede'), None, {})
        self.h.gravar(evento('c3', '2026-09-27T03:00:00Z', 'provavel'), None, {})
        self.assertEqual([e['evento']['id'] for e in self.h.listar()], ['c3', 'c2', 'c1'])
        self.assertEqual([e['evento']['id'] for e in self.h.listar(nivel='provavel', linha='cais')], ['c3'])
        self.assertEqual([e['evento']['id'] for e in self.h.listar(desde='2026-09-27T02:00:00Z')], ['c3', 'c2'])
        self.assertEqual(len(self.h.listar(limite=1)), 1)


class Sqlite(Comum, unittest.TestCase):

    def abrir(self):
        return HI.Historico(':memory:')

    def test_arquivo_sobrevive_a_reabrir(self):
        caminho = os.path.join(tempfile.mkdtemp(), 'historico.sqlite3')
        h = HI.Historico(caminho)
        h.gravar(evento('d', '2026-09-27T01:00:00Z'), None, {})
        h.fechar()
        h = HI.Historico(caminho)
        self.assertEqual(h.obter('d')['evento']['id'], 'd')
        h.fechar()


@unittest.skipUnless(PG, 'sem LEAKMAP_BANCO_DE_TESTE: testes do PostgreSQL pulados')
class Postgres(Comum, unittest.TestCase):

    def abrir(self):
        h = HI.Historico(PG)
        h._executar('DELETE FROM eventos')
        return h

    def test_e_postgres(self):
        self.assertEqual(self.h.tipo, 'postgresql')

    def test_sobrevive_a_reabrir(self):
        self.h.gravar(evento('e', '2026-09-27T01:00:00Z'), None, {})
        outro = HI.Historico(PG)
        self.assertEqual(outro.obter('e')['evento']['id'], 'e')
        outro.fechar()

    def test_reconecta_quando_a_conexao_cai(self):
        self.h.gravar(evento('f', '2026-09-27T01:00:00Z'), None, {})
        self.h._db.close()                              # como o banco gerenciado derrubando a conexao parada
        self.assertEqual(self.h.obter('f')['evento']['id'], 'f')


if __name__ == '__main__':
    unittest.main()

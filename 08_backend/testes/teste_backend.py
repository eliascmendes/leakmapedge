"""Testes do backend da bancada virtual.

Roda com: python -m unittest discover -s 08_backend/testes -p "teste_*.py"
Precisa de 08_backend/requirements.txt (FastAPI e httpx para o cliente de teste).
"""
import json
import os
import sys
import unittest

import numpy as np

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
os.environ['LEAKMAP_CHAVE'] = 'chave-de-teste'
import bancada as BA  # noqa: E402
import gerador as GE  # noqa: E402
import linhas as LN  # noqa: E402
import projeto as P  # noqa: E402

LINHAS = LN.todas()


def rodar(b, passos):
    """Avanca a bancada e devolve os eventos que sairam."""
    eventos = []
    for _ in range(passos):
        for m in b.passo()[2]:
            if m['tipo'] == 'evento':
                eventos.append(m)
    return eventos


def nova(linha='cais', transmissor='rapido'):
    b = BA.Bancada(linhas=LINHAS, linha=linha, transmissor=transmissor, semente=3)
    rodar(b, 20)
    return b


class Gerador(unittest.TestCase):

    def test_no_ponto_simulado_reproduz_o_tsnet(self):
        for linha in LINHAS.values():
            for molde in linha.moldes_de_vazamento:
                ev = GE.vazamento(linha, molde.trecho, molde.s_m, molde.tamanho, 0.0)
                self.assertEqual(ev['fonte'], 'tsnet')
                for s in linha.sensores:
                    v = GE.variacao(linha, ev, s, molde.t_rel)
                    self.assertLess(float(np.max(np.abs(v - molde.delta[s]))), 1e-9, (linha.id, molde.id, s))

    def test_fora_do_ponto_desloca_a_chegada_pela_distancia(self):
        linha = LINHAS['cais']
        ev = GE.vazamento(linha, 'principal', 320.0, 'grande', 1.0)
        for s in ('A', 'B'):
            chegada = 1.0 + linha.tempo_de_percurso('principal', 320.0, s)
            t = np.array([chegada - 0.002, chegada + 0.003])
            v = GE.variacao(linha, ev, s, t)
            self.assertAlmostEqual(v[0], 0.0, delta=0.01)
            self.assertLess(v[1], -10.0)


class BancadaAoVivo(unittest.TestCase):

    def test_vazamento_na_linha_do_cais(self):
        b = nova()
        b.vazamento('principal', 320.0, 'grande')
        ev = rodar(b, 20)
        self.assertEqual(len(ev), 1)
        e, v = ev[0]['evento'], ev[0]['verdade']
        self.assertEqual((e['nivel'], e['classificacao'], e['modo']), ('provavel', 'vazamento', 'simulacao'))
        self.assertLess(abs(e['posicao_m'] - 320.0), 1.0)
        self.assertEqual((v['tipo'], v['s_m']), ('vazamento', 320.0))
        self.assertLess(v['erro_m'], 1.0)
        self.assertTrue(e['explicacao'])

    def test_vazamento_antes_do_sensor_A(self):
        b = nova()
        b.vazamento('principal', -120.0, 'grande')
        e = rodar(b, 20)[0]['evento']
        self.assertEqual((e['classificacao'], e['lado'], e['posicao_m']), ('fora_do_trecho', 'A', None))

    def test_manobra_com_e_sem_registro_de_operacao(self):
        b = nova()
        b.equipamento('XV-106', 'fechar', True)
        rodar(b, 30)
        b.equipamento('XV-106', 'abrir', True)
        self.assertEqual(rodar(b, 30)[0]['evento']['nivel'], 'registro')
        b.equipamento('XV-106', 'fechar', False)
        rodar(b, 30)
        b.equipamento('XV-106', 'abrir', False)
        e = rodar(b, 30)[0]['evento']
        self.assertEqual(e['nivel'], 'provavel')           # a mesma onda de um vazamento em 450 m

    def test_acao_incompativel_com_o_estado(self):
        b = nova()
        with self.assertRaises(BA.ErroDaBancada) as ctx:
            b.equipamento('XV-106', 'abrir')                # ja esta aberta
        self.assertEqual(ctx.exception.codigo, 409)
        with self.assertRaises(BA.ErroDaBancada) as ctx:
            b.vazamento('principal', 5000.0, 'grande')
        self.assertEqual(ctx.exception.codigo, 422)

    def test_cabo_rompido_reprova_o_sensor_e_retem_a_posicao(self):
        b = nova()
        b.sensor('A', 'cabo_rompido')
        eventos = rodar(b, 20)
        self.assertEqual(b.mensagem_de_saude()['sensores']['A']['situacao'], 'reprovado')
        self.assertEqual(b.mensagem_de_saude()['monitoramento'], 'degradado')
        self.assertEqual(eventos[0]['verdade']['tipo'], 'falha_de_sensor')
        b.vazamento('principal', 400.0, 'grande')
        e = rodar(b, 20)[0]['evento']
        self.assertEqual((e['nivel'], e['posicao_m']), ('suspeita', None))
        b.reparar()
        rodar(b, 10)
        self.assertEqual(b.mensagem_de_saude()['monitoramento'], 'normal')

    def test_gas_confirma_o_provavel(self):
        b = nova()
        b.vazamento('principal', 250.0, 'grande')
        e = rodar(b, 20)[0]['evento']
        revisto = b.definir_gas(True)[0]['evento']
        self.assertEqual((revisto['id'], revisto['nivel'], revisto['revisao']), (e['id'], 'confirmado', 2))

    def test_rede_aponta_o_ramal(self):
        b = nova('rede')
        b.vazamento('ramal_106', 180.0, 'grande')
        e = rodar(b, 20)[0]['evento']
        self.assertEqual((e['nivel'], e['trecho']), ('provavel', 'ramal_106'))
        self.assertLess(abs(e['posicao_m'] - 180.0), 1.0)
        self.assertEqual(set(e['canais']), {'A', 'B104', 'B106', 'B108'})

    def test_regime_sem_evento_nao_alarma(self):
        for transmissor in BA.TRANSMISSORES:
            b = nova('cais', transmissor)
            self.assertEqual(rodar(b, 50), [], transmissor)

    def test_evento_em_fluxo_igual_ao_detector_em_lote(self):
        b = nova()
        b.vazamento('principal', 320.0, 'grande')
        e = rodar(b, 20)[0]['evento']
        sa, sb = 0.0, 700.0
        registro = P.D.processar_ensaio(
            {'id': 'L', 'tempo_s': b.buf_t, 'canal_A_carga_m': b.buf['A'], 'canal_B_carga_m': b.buf['B'],
             'parametros_do_detector': {'posicao_sensor_A_m': sa, 'posicao_sensor_B_m': sb,
                                        'distancia_entre_sensores_L_m': sb - sa, 'velocidade_de_onda_m_s': b.linha.c,
                                        'incerteza_de_velocidade_de_onda_m_s': 0.0}}, b.escala())
        self.assertEqual(registro['classe'], 'localizado')
        self.assertAlmostEqual(registro['posicao_estimada_m'], e['posicao_m'], delta=b.linha.c * BA.TS / 2 + 1e-6)


class Api(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import app as APP
        cls.APP = APP
        cls.cm = TestClient(APP.app)
        cls.c = cls.cm.__enter__()
        cls.chave = {'X-LEAKMAP-Chave': 'chave-de-teste'}

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)

    def test_consultas(self):
        s = self.c.get('/api/servico').json()
        self.assertEqual((s['situacao'], s['modo'], s['comandos_exigem_chave']), ('ok', 'simulacao', True))
        linhas = self.c.get('/api/linhas').json()
        self.assertEqual({l['id'] for l in linhas['linhas']}, {'trecho_200', 'cais', 'rede'})
        self.assertEqual(self.c.get('/api/linhas/xyz').status_code, 404)
        self.assertEqual(len(self.c.get('/api/transmissores').json()), 6)
        self.assertNotIn('vazamentos_abertos', self.c.get('/api/estado?perfil=operador').json())

    def test_comando_exige_a_chave(self):
        r = self.c.post('/api/bancada/reparar', json={})
        self.assertEqual(r.status_code, 401)
        self.assertIn('erro', r.json())
        self.assertEqual(self.c.post('/api/bancada/reparar', json={}, headers=self.chave).status_code, 200)

    def test_erros_com_texto(self):
        r = self.c.post('/api/bancada/vazamento', json={'trecho': 'principal', 's_m': 5000}, headers=self.chave)
        self.assertEqual(r.status_code, 422)
        self.assertIn('fora da linha', r.json()['erro'])

    def test_websocket_boas_vindas_e_amostras(self):
        with self.c.websocket_connect('/ws?perfil=operador&taxa=20') as ws:
            m = ws.receive_json()
            self.assertEqual((m['tipo'], m['perfil']), ('boas_vindas', 'operador'))
            self.assertNotIn('vazamentos_abertos', m['estado'])
            tipos = set()
            for _ in range(5):
                tipos.add(ws.receive_json()['tipo'])
            self.assertIn('amostras', tipos)

    def test_perfil_operador_nao_recebe_a_verdade(self):
        msg = {'tipo': 'evento', 'evento': {}, 'verdade': {'s_m': 1.0}}
        self.assertNotIn('verdade', self.APP.para_o_perfil(msg, 'operador'))
        self.assertIn('verdade', self.APP.para_o_perfil(msg, 'demonstracao'))


if __name__ == '__main__':
    unittest.main()

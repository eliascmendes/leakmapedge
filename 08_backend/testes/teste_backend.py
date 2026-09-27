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

    def test_operacao_continua_sem_falso_alarme_de_ruido(self):
        # 6 minutos de regime com transmissor real; antes da confirmacao do degrau, o ruido
        # passava do limiar num canal so cerca de uma vez a cada 2,5 minutos
        b = BA.Bancada(linhas=LINHAS, linha='cais', transmissor='rapido', semente=5)
        self.assertEqual(rodar(b, 3600), [])
        self.assertGreater(b.descartadas_como_ruido, 0)

    def test_evento_real_num_canal_so_continua_saindo(self):
        b = nova('cais', 'inteligente_100ms')
        b.vazamento('principal', 320.0, 'grande')        # com 100 ms, o sensor B costuma perder o pulso curto
        e = rodar(b, 20)
        self.assertEqual(len(e), 1)
        b.reparar()
        rodar(b, 20)
        b.sensor('B', 'cabo_rompido')
        self.assertEqual(len(rodar(b, 20)), 1)

    def test_parada_de_bomba_registrada_nao_alarma(self):
        b = nova()
        b.equipamento('B-01', 'parar', True)
        self.assertEqual(rodar(b, 30)[0]['evento']['nivel'], 'registro')

    def test_equipamentos_nas_tres_linhas(self):
        esperado = {'trecho_200': {'XV-100', 'XV-190'}, 'cais': {'B-01', 'XV-104', 'XV-106', 'XV-108'},
                    'rede': {'B-01', 'XV-104', 'XV-106', 'XV-108'}}
        for linha, eqs in esperado.items():
            self.assertEqual({e['id'] for e in LINHAS[linha].equipamentos}, eqs, linha)
            self.assertTrue(all((e, a) in LINHAS[linha].manobras for e in eqs
                                for a in (('abrir', 'fechar') if e.startswith('XV') else ('parar', 'partir'))))

    def test_manobras_no_trecho_200(self):
        b = nova('trecho_200')
        b.equipamento('XV-100', 'fechar', True)
        self.assertEqual(rodar(b, 35)[0]['evento']['nivel'], 'registro')
        b.equipamento('XV-100', 'abrir', True)
        self.assertEqual(rodar(b, 35)[0]['evento']['nivel'], 'registro')
        b.equipamento('XV-100', 'fechar', False)
        rodar(b, 35)
        b.equipamento('XV-100', 'abrir', False)          # a mesma onda de um vazamento em 100 m
        e = rodar(b, 35)[0]['evento']
        self.assertEqual((e['nivel'], e['cadastro']['decisao']), ('provavel', 'conferir'))
        self.assertLess(abs(e['posicao_m'] - 100.0), 3.0)

    def test_manobras_na_rede(self):
        b = nova('rede')
        b.equipamento('XV-106', 'fechar', True)
        self.assertEqual(rodar(b, 35)[0]['evento']['nivel'], 'registro')
        b.equipamento('XV-106', 'abrir', True)
        e = rodar(b, 35)[0]['evento']
        self.assertEqual((e['nivel'], e['cadastro']['equipamento']), ('registro', 'XV-106'))
        b.equipamento('B-01', 'parar', True)
        e = rodar(b, 35)[0]['evento']
        self.assertEqual((e['nivel'], e['cadastro']['equipamento']), ('registro', 'B-01'))

    def test_parada_da_bomba_so_com_o_sensor_b_declarando_sai_do_lado_a(self):
        # com este ruido, a frente lenta da parada nao passa do limiar no sensor A, so no B, 0,57 s depois;
        # sem a chegada pelo nivel, saia "suspeita do lado B, conferir XV-108"
        b = nova()
        rodar(b, 20)
        b.equipamento('B-01', 'parar', True)
        e = rodar(b, 30)[0]['evento']
        self.assertEqual((e['nivel'], e['lado'], e['cadastro']['equipamento']), ('registro', 'A', 'B-01'))
        self.assertIn('queda de nivel no sensor A', e['motivo'])
        self.assertFalse(e['canais']['A']['detectou'])

    def test_previsao_do_golpe_bate_com_o_que_o_alerta_mede(self):
        b = nova()
        p = b.prever_golpe('XV-108', 'fechar')
        self.assertEqual((p['nivel'], p['sensor_de_referencia'], p['metodo']), ('atencao', 'B', 'estudo'))
        r = b.equipamento('XV-108', 'fechar', True)
        self.assertAlmostEqual(r['previsao_do_golpe']['pico_previsto_bar'], p['pico_previsto_bar'])
        msgs = []
        for _ in range(40):
            msgs += [m for m in b.passo()[2] if m['tipo'] == 'sobrepressao']
        medido = msgs[0]['evento']['pico_bar']
        self.assertTrue(p['faixa_bar'][0] <= medido <= p['faixa_bar'][1], (p['faixa_bar'], medido))
        # a valvula do berco 106, no meio da linha, com menos vazao: golpe pequeno; abrir nunca sobe a pressao
        self.assertIsNone(b.prever_golpe('XV-106', 'fechar')['nivel'])
        self.assertFalse(b.prever_golpe('XV-104', 'abrir')['sobe_a_pressao'])

    def test_previsao_do_golpe_erros_e_outras_linhas(self):
        b = nova()
        for args, codigo in ((('XV-104', 'fechar'), 409), (('XV-999', 'fechar'), 404), (('XV-108', 'partir'), 422)):
            with self.assertRaises(BA.ErroDaBancada) as erro:
                b.prever_golpe(*args)
            self.assertEqual(erro.exception.codigo, codigo)
        with self.assertRaises(BA.ErroDaBancada):
            b.prever_golpe('XV-108', 'fechar', tempo_de_manobra_s=500)
        p = b.prever_golpe('XV-100', 'fechar', linha='trecho_200')
        self.assertEqual((p['linha'], p['nivel'], p['metodo']), ('trecho_200', 'atencao', 'estudo'))
        self.assertEqual(b.prever_golpe('XV-190', 'fechar', linha='trecho_200')['metodo'], 'michaud')
        self.assertIn('Sem previsão', b.prever_golpe('B-01', 'partir', linha='rede')['explicacao'])

    def test_sobrepressao_no_fechamento_da_valvula_do_navio(self):
        b = nova()
        b.equipamento('XV-108', 'fechar', True)
        msgs = []
        for _ in range(60):
            msgs += [m for m in b.passo()[2] if m['tipo'] == 'sobrepressao']
        self.assertEqual([m['evento']['revisao'] for m in msgs], [1, 2])
        abre, fecha = msgs[0]['evento'], msgs[1]['evento']
        self.assertEqual((abre['nivel'], abre['sensor_do_pico'], abre['em_curso']), ('atencao', 'B', True))
        self.assertAlmostEqual(abre['pico_bar'], 10.55, delta=0.2)
        self.assertEqual(abre['causa_provavel']['equipamento'], 'XV-108')
        self.assertEqual(msgs[0]['verdade']['equipamento'], 'XV-108')
        self.assertEqual((fecha['id'], fecha['em_curso']), (abre['id'], False))
        self.assertGreater(fecha['duracao_s'], 0.0)
        self.assertEqual(b.historico.contar('sobrepressoes'), 1)

    def test_limite_mais_baixo_vira_alarme_e_limite_invalido(self):
        b = nova()
        self.assertIsNone(b.definir_limite(10.5)['aviso'])
        b.equipamento('XV-108', 'fechar', True)
        niveis = [m['evento']['nivel'] for _ in range(40) for m in b.passo()[2] if m['tipo'] == 'sobrepressao']
        self.assertEqual(niveis[0], 'alarme')
        with self.assertRaises(BA.ErroDaBancada):
            b.definir_limite(20.0)
        self.assertIsNotNone(b.definir_limite(7.0)['aviso'])     # o proprio regime (6,75 bar) ja passa de 80%

    def test_vazamento_e_manobra_abaixo_do_limite_nao_geram_sobrepressao(self):
        b = nova()
        b.vazamento('principal', 320.0, 'grande')
        b.equipamento('XV-106', 'fechar', True)
        tipos = [m['tipo'] for _ in range(40) for m in b.passo()[2]]
        self.assertNotIn('sobrepressao', tipos)
        self.assertIn('evento', tipos)

    def test_manobras_antigas_saem_da_conta(self):
        b = nova()
        b.equipamento('XV-108', 'fechar', True)
        rodar(b, 200)                                     # 20 s: o efeito ja decaiu
        self.assertEqual([e for e in b.eventos if e['tipo'] == 'manobra'], [])

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


class Webhook(unittest.TestCase):

    def setUp(self):
        import tempfile
        import threading
        import receptor_teste as RT
        self.RT = RT
        RT.Receptor.recebidos.clear()
        self.servidor = RT.servidor(0)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d/leakmap' % self.servidor.server_address[1]
        self.pendentes = os.path.join(tempfile.mkdtemp(), 'pendentes.jsonl')

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    def esperar(self, condicao, limite=5.0):
        import time
        fim = time.monotonic() + limite
        while time.monotonic() < fim and not condicao():
            time.sleep(0.05)
        return condicao()

    def test_evento_da_bancada_sai_pelo_webhook_sem_a_verdade(self):
        import repasse as RE
        r = RE.Repasse(dict(P.IN.PADRAO, ligado=True, url=self.url), self.pendentes)
        b = nova()
        b.vazamento('principal', 320.0, 'grande')
        m = rodar(b, 20)[0]
        r.por(m['evento'])
        self.assertTrue(self.esperar(lambda: len(self.RT.Receptor.recebidos) == 1))
        recebido = self.RT.Receptor.recebidos[0]
        self.assertEqual((recebido['id'], recebido['nivel'], recebido['modo']), (m['evento']['id'], 'provavel', 'simulacao'))
        self.assertNotIn('verdade', recebido)
        self.assertTrue(self.esperar(lambda: r.situacao()['contagem']['enviado'] == 1))

    def test_filtro_por_nivel(self):
        import repasse as RE
        r = RE.Repasse(dict(P.IN.PADRAO, ligado=True, url=self.url, niveis=['confirmado']), self.pendentes)
        r.por({'id': 'x', 'nivel': 'provavel'})
        self.assertTrue(self.esperar(lambda: r.situacao()['contagem']['filtrado'] == 1))
        self.assertEqual(self.RT.Receptor.recebidos, [])

    def test_destino_fora_do_ar_vai_para_a_fila_local(self):
        import repasse as RE
        cfg = dict(P.IN.PADRAO, ligado=True, url='http://127.0.0.1:9/leakmap', tentativas=1, tempo_limite_s=0.5)
        r = RE.Repasse(cfg, self.pendentes)
        r.por({'id': 'y', 'nivel': 'provavel'})
        self.assertTrue(self.esperar(lambda: r.situacao()['contagem']['pendente'] == 1))
        self.assertEqual(r.situacao()['na_fila_local_para_reenvio'], 1)

    def test_sobrepressao_sai_pelo_webhook_com_niveis_proprios(self):
        import repasse as RE
        r = RE.Repasse(dict(P.IN.PADRAO, ligado=True, url=self.url), self.pendentes)
        r.por({'tipo': 'leakmap.sobrepressao', 'id': 's', 'nivel': 'atencao'})
        self.assertTrue(self.esperar(lambda: len(self.RT.Receptor.recebidos) == 1))
        self.assertEqual(self.RT.Receptor.recebidos[0]['tipo'], 'leakmap.sobrepressao')

    def test_desligado_sem_configuracao(self):
        import repasse as RE
        r = RE.Repasse(dict(P.IN.PADRAO), self.pendentes)
        r.por({'id': 'z', 'nivel': 'provavel'})
        self.assertEqual((r.ligado, r.situacao()['contagem']['enviado']), (False, 0))


class ApiComWebhook(unittest.TestCase):
    """De ponta a ponta: comando pela API, detector na bancada, evento no receptor do webhook."""

    def test_vazamento_chega_ao_receptor(self):
        import threading
        import time
        from fastapi.testclient import TestClient
        import app as APP
        import receptor_teste as RT
        RT.Receptor.recebidos.clear()
        servidor = RT.servidor(0)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        os.environ['LEAKMAP_WEBHOOK_URL'] = 'http://127.0.0.1:%d/leakmap' % servidor.server_address[1]
        try:
            with TestClient(APP.app) as c:
                self.assertTrue(c.get('/api/servico').json()['webhook_ligado'])
                time.sleep(2.0)                     # a bancada ignora deteccoes no 1,5 s depois de iniciar
                c.post('/api/bancada/vazamento', json={'trecho': 'principal', 's_m': 320.0},
                       headers={'X-LEAKMAP-Chave': 'chave-de-teste'})
                fim = time.monotonic() + 10.0
                while time.monotonic() < fim and not RT.Receptor.recebidos:
                    time.sleep(0.1)
                self.assertEqual(len(RT.Receptor.recebidos), 1)
                e = RT.Receptor.recebidos[0]
                self.assertEqual((e['nivel'], e['modo'], e['trecho']), ('provavel', 'simulacao', 'principal'))
                self.assertNotIn('verdade', e)
                self.assertEqual(c.get('/api/integracao').json()['contagem']['enviado'], 1)
        finally:
            del os.environ['LEAKMAP_WEBHOOK_URL']
            servidor.shutdown()
            servidor.server_close()


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
        r = self.c.post('/api/bancada/transmissor', json={'transmissor': 'xyz'}, headers=self.chave)
        self.assertEqual(r.status_code, 422)
        self.assertIn('transmissor', r.json()['erro'])

    def test_websocket_boas_vindas_e_amostras(self):
        with self.c.websocket_connect('/ws?perfil=operador&taxa=20') as ws:
            m = ws.receive_json()
            self.assertEqual((m['tipo'], m['perfil']), ('boas_vindas', 'operador'))
            self.assertNotIn('vazamentos_abertos', m['estado'])
            tipos = set()
            for _ in range(5):
                tipos.add(ws.receive_json()['tipo'])
            self.assertIn('amostras', tipos)

    def test_integracao_desligada_por_padrao(self):
        i = self.c.get('/api/integracao').json()
        self.assertFalse(i['ligado'])
        r = self.c.post('/api/integracao/teste', headers=self.chave).json()
        self.assertEqual(r['resultado'], 'desligado')

    def test_rotas_da_sobrepressao(self):
        s = self.c.get('/api/sobrepressao').json()
        self.assertEqual(set(s['limites_por_linha_bar']), {'trecho_200', 'cais', 'rede'})
        self.assertIn('premissa', s['origem_do_limite'])
        self.assertEqual(self.c.post('/api/sobrepressao/limite', json={'limite_bar': 11.0}).status_code, 401)
        r = self.c.post('/api/sobrepressao/limite', json={'limite_bar': 11.0}, headers=self.chave).json()
        self.assertEqual(r['estado']['sobrepressao']['limite_bar'], 11.0)
        self.assertEqual(self.c.post('/api/sobrepressao/limite', json={'limite_bar': 40}, headers=self.chave)
                         .status_code, 422)
        self.c.post('/api/sobrepressao/limite', json={'limite_bar': 12.0}, headers=self.chave)
        self.assertIsInstance(self.c.get('/api/sobrepressao/eventos').json(), list)
        self.assertEqual(self.c.get('/api/linhas/cais').json()['limite_de_pressao_bar'], 12.0)
        p = self.c.get('/api/sobrepressao/previsao', params={'equipamento': 'XV-108', 'tempo_de_manobra_s': 5}).json()
        self.assertEqual((p['acao'], p['tempo_de_manobra_s']), ('fechamento', 5.0))
        self.assertLess(p['pico_previsto_bar'], 10.0)
        self.assertEqual(self.c.get('/api/sobrepressao/previsao', params={'equipamento': 'XV-108',
                                                                          'acao': 'girar'}).status_code, 422)
        eq = next(e for e in self.c.get('/api/linhas/cais').json()['equipamentos'] if e['id'] == 'XV-108')
        self.assertEqual(eq['manobra_padrao'], {'fracao_da_vazao_cortada': 0.5, 'tempo_de_manobra_s': 0.3})

    def test_perfil_operador_nao_recebe_a_verdade(self):
        msg = {'tipo': 'evento', 'evento': {}, 'verdade': {'s_m': 1.0}}
        self.assertNotIn('verdade', self.APP.para_o_perfil(msg, 'operador'))
        self.assertIn('verdade', self.APP.para_o_perfil(msg, 'demonstracao'))


if __name__ == '__main__':
    unittest.main()

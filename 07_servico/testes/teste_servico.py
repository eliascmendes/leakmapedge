"""Testes da escala de alerta, do evento padronizado e da saida por webhook.

Roda com: python -m unittest discover -s 07_servico/testes -p "teste_*.py"
"""
import json
import os
import sys
import tempfile
import threading
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
import alerta as AL  # noqa: E402
import integracao as IN  # noqa: E402
import receptor_teste as RT  # noqa: E402

SENSORES = {'A': {'nome': 'inicio do trecho', 'posicao_m': 0.0}, 'B': {'nome': 'berco 108', 'posicao_m': 700.0}}


def registro(classe, **extra):
    base = {'id': 'LQ-001', 'classe': classe, 'motivo': 'teste',
            'canal_A': {'detectado': True, 'polaridade': 'queda', 'tempo_de_chegada_s': 0.3},
            'canal_B': {'detectado': True, 'polaridade': 'queda', 'tempo_de_chegada_s': 0.5}}
    base.update(extra)
    return base


class Escala(unittest.TestCase):

    def test_niveis_por_classe(self):
        self.assertIsNone(AL.nivel_do_evento(registro('sem_deteccao')))
        self.assertIsNone(AL.nivel_do_evento(registro('falha_execucao')))
        self.assertEqual(AL.nivel_do_evento(registro('manobra')), 'registro')
        self.assertEqual(AL.nivel_do_evento(registro('detectado_sem_localizacao')), 'suspeita')
        self.assertEqual(AL.nivel_do_evento(registro('fora_do_trecho')), 'suspeita')
        self.assertEqual(AL.nivel_do_evento(registro('localizado')), 'provavel')
        self.assertEqual(AL.nivel_do_evento(registro('localizado'), gas_na_regiao=True), 'confirmado')

    def test_gas_nao_confirma_o_que_nao_e_vazamento_localizado(self):
        self.assertEqual(AL.nivel_do_evento(registro('manobra'), gas_na_regiao=True), 'registro')
        self.assertEqual(AL.nivel_do_evento(registro('fora_do_trecho'), gas_na_regiao=True), 'suspeita')

    def test_monitoramento_degradado_diz_o_motivo(self):
        saude = {'canal_A': {'falhas': []}, 'canal_B': {'falhas': ['congelado']}}
        estado = AL.estado_do_monitoramento(saude)
        self.assertEqual(estado['monitoramento'], 'degradado')
        self.assertEqual(estado['motivos'], ['canal B: congelado'])
        self.assertEqual(AL.estado_do_monitoramento(None)['monitoramento'], 'sem_autoteste')


class Evento(unittest.TestCase):

    def test_vazamento_localizado_leva_posicao_e_saude(self):
        r = registro('localizado', posicao_estimada_m=252.4, incerteza_de_posicao_m=0.4)
        e = AL.montar_evento(r, 'L-01', SENSORES, 'notebook',
                             saude={'canal_A': {'falhas': []}, 'canal_B': {'falhas': []}})
        self.assertEqual((e['tipo'], e['versao'], e['nivel'], e['classificacao']),
                         ('leakmap.evento', '1', 'provavel', 'vazamento'))
        self.assertEqual((e['posicao_m'], e['incerteza_m'], e['linha']), (252.4, 0.4, 'L-01'))
        self.assertEqual(e['saude']['monitoramento'], 'normal')
        self.assertEqual(e['canais']['A']['polaridade'], 'queda')
        json.dumps(e)                                   # serializavel como veio

    def test_manobra_e_fora_do_trecho_nao_levam_posicao_de_vazamento(self):
        e = AL.montar_evento(registro('manobra', posicao_da_origem_m=450.0), 'L-01', SENSORES, 'notebook')
        self.assertEqual((e['nivel'], e['classificacao'], e['posicao_m']), ('registro', 'manobra', None))
        e = AL.montar_evento(registro('fora_do_trecho', lado_da_origem='A'), 'L-01', SENSORES, 'notebook')
        self.assertEqual((e['nivel'], e['classificacao'], e['lado']), ('suspeita', 'fora_do_trecho', 'A'))

    def test_sem_evento_nada_a_informar(self):
        self.assertIsNone(AL.montar_evento(registro('sem_deteccao'), 'L-01', SENSORES, 'notebook'))


class Webhook(unittest.TestCase):

    def setUp(self):
        RT.Receptor.recebidos = []
        self.servidor = RT.servidor(0)                   # porta livre escolhida pelo sistema
        self.porta = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.pasta = tempfile.mkdtemp()
        self.pendentes = os.path.join(self.pasta, 'pendentes.jsonl')
        self.evento = AL.montar_evento(registro('localizado', posicao_estimada_m=100.0,
                                                incerteza_de_posicao_m=0.3), 'L-01', SENSORES, 'notebook')

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    def cfg(self, **mudar):
        return dict(IN.PADRAO, ligado=True, url='http://127.0.0.1:%d/leakmap' % self.porta, **mudar)

    def test_desligado_por_padrao(self):
        self.assertFalse(IN.ler_config(os.path.join(self.pasta, 'nao_existe.json'))['ligado'])
        self.assertEqual(IN.enviar(self.evento, dict(IN.PADRAO), self.pendentes), 'desligado')

    def test_evento_chega_ao_receptor_igual_ao_enviado(self):
        self.assertEqual(IN.enviar(self.evento, self.cfg(), self.pendentes), 'enviado')
        self.assertEqual(RT.Receptor.recebidos, [self.evento])

    def test_nivel_fora_da_lista_nao_sai(self):
        self.assertEqual(IN.enviar(self.evento, self.cfg(niveis=['confirmado']), self.pendentes), 'filtrado')
        self.assertEqual(RT.Receptor.recebidos, [])

    def test_sem_destino_o_evento_espera_na_fila_e_sai_depois(self):
        fora = dict(self.cfg(), url='http://127.0.0.1:1/leakmap', tentativas=1, tempo_limite_s=0.5)
        self.assertEqual(IN.enviar(self.evento, fora, self.pendentes), 'pendente')
        self.assertTrue(os.path.exists(self.pendentes))
        self.assertEqual(IN.reenviar(self.cfg(), self.pendentes), 1)
        self.assertEqual(RT.Receptor.recebidos, [self.evento])
        self.assertFalse(os.path.exists(self.pendentes))


if __name__ == '__main__':
    unittest.main()

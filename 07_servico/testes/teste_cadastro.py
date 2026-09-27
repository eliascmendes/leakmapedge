"""Testes do cadastro de equipamentos e do registro de operacao (07_servico/cadastro.py).

Roda com: python -m unittest discover -s 07_servico/testes -p "teste_*.py"
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
import alerta as AL  # noqa: E402
import cadastro as CD  # noqa: E402

SENSORES = {'A': {'nome': 'inicio do trecho', 'posicao_m': 0.0}, 'B': {'nome': 'berco 108', 'posicao_m': 700.0}}
CADASTRO = CD.ler(os.path.join(AQUI, 'cadastro.exemplo.json'))
T = 1000.0


def localizado(posicao, polaridade='queda', incerteza=0.3):
    canal = {'detectado': True, 'polaridade': polaridade, 'tempo_de_chegada_s': 0.3}
    return {'id': 'LQ-1', 'classe': 'localizado', 'motivo': 'evidencia suficiente',
            'posicao_estimada_m': posicao, 'incerteza_de_posicao_m': incerteza,
            'canal_A': dict(canal), 'canal_B': dict(canal)}


def fora(lado):
    canal = {'detectado': True, 'polaridade': 'queda', 'tempo_de_chegada_s': 0.3}
    return {'id': 'LQ-2', 'classe': 'fora_do_trecho', 'motivo': 'origem fora do trecho',
            'lado_da_origem': lado, 'canal_A': dict(canal), 'canal_B': dict(canal)}


class Cadastro(unittest.TestCase):

    def test_posicao_e_operacao_registrada_viram_manobra(self):
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': T - 1.0}]
        c = CD.conferir(localizado(452.0), CADASTRO, ops, T, SENSORES)
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_MANOBRA, 'XV-106'))
        r = CD.aplicar(localizado(452.0), c)
        self.assertEqual(r['classe'], 'manobra')
        self.assertNotIn('posicao_estimada_m', r)
        self.assertEqual(r['posicao_da_origem_m'], 452.0)
        self.assertEqual(AL.nivel_do_evento(r), 'registro')

    def test_so_a_coincidencia_de_posicao_nao_rebaixa(self):
        c = CD.conferir(localizado(452.0), CADASTRO, [], T, SENSORES)
        self.assertEqual(c['decisao'], CD.DECISAO_CONFERIR)
        r = CD.aplicar(localizado(452.0), c)
        self.assertEqual(r['classe'], 'localizado')
        self.assertEqual(AL.nivel_do_evento(r), 'provavel')
        self.assertIn('XV-106', r['motivo'])
        self.assertIn('conferir', r['motivo'])

    def test_operacao_fora_da_janela_nao_explica(self):
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': T - 60.0}]
        self.assertEqual(CD.conferir(localizado(452.0), CADASTRO, ops, T, SENSORES)['decisao'], CD.DECISAO_CONFERIR)

    def test_operacao_de_outro_equipamento_nao_explica(self):
        ops = [{'equipamento': 'XV-104', 'acao': 'abertura', 'instante_s': T - 1.0}]
        self.assertEqual(CD.conferir(localizado(452.0), CADASTRO, ops, T, SENSORES)['decisao'], CD.DECISAO_CONFERIR)

    def test_operacao_incompativel_com_a_onda_nao_explica(self):
        # fechar a valvula gera onda de alta; uma queda ali nao e explicada por isso
        ops = [{'equipamento': 'XV-106', 'acao': 'fechamento', 'instante_s': T - 1.0}]
        self.assertEqual(CD.conferir(localizado(452.0), CADASTRO, ops, T, SENSORES)['decisao'], CD.DECISAO_CONFERIR)

    def test_longe_de_qualquer_equipamento_nada_muda(self):
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': T - 1.0}]
        c = CD.conferir(localizado(320.0), CADASTRO, ops, T, SENSORES)
        self.assertEqual(c['decisao'], CD.DECISAO_NADA)
        self.assertEqual(CD.aplicar(localizado(320.0), c)['classe'], 'localizado')

    def test_tolerancia_cresce_com_a_incerteza_declarada(self):
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': T - 1.0}]
        self.assertEqual(CD.conferir(localizado(480.0, incerteza=0.3), CADASTRO, ops, T, SENSORES)['decisao'],
                         CD.DECISAO_NADA)
        self.assertEqual(CD.conferir(localizado(480.0, incerteza=12.0), CADASTRO, ops, T, SENSORES)['decisao'],
                         CD.DECISAO_MANOBRA)

    def test_parada_de_bomba_explica_o_evento_fora_do_trecho_do_lado_A(self):
        ops = [{'equipamento': 'B-01', 'acao': 'parada', 'instante_s': T - 0.5}]
        c = CD.conferir(fora('A'), CADASTRO, ops, T, SENSORES)
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_MANOBRA, 'B-01'))
        self.assertEqual(AL.nivel_do_evento(CD.aplicar(fora('A'), c)), 'registro')
        # do lado B a bomba nao pode ser a origem
        self.assertNotEqual(CD.conferir(fora('B'), CADASTRO, ops, T, SENSORES)['equipamento'], 'B-01')

    def test_frente_lenta_alem_do_limite_fisico_usa_o_lado(self):
        # parada de bomba: a marca em B sai tarde e dt passa de L/c; o sinal de dt diz o lado
        r = fora('A')
        r.update(classe='detectado_sem_localizacao', lado_da_origem=None, delta_t_s=-0.5738,
                 parametros_do_detector={'distancia_entre_sensores_L_m': 700.0, 'velocidade_de_onda_m_s': 1226.6})
        ops = [{'equipamento': 'B-01', 'acao': 'parada', 'instante_s': T - 0.3}]
        c = CD.conferir(r, CADASTRO, ops, T, SENSORES)
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_MANOBRA, 'B-01'))
        self.assertEqual(CD.aplicar(r, c)['lado_da_origem'], 'A')
        # dentro do limite fisico nao ha lado a inferir: nada muda
        r['delta_t_s'] = -0.30
        self.assertEqual(CD.conferir(r, CADASTRO, ops, T, SENSORES)['decisao'], CD.DECISAO_NADA)

    def test_so_um_canal_viu_a_queda_o_lado_e_o_dele(self):
        r = fora('A')
        r.update(classe='detectado_sem_localizacao', lado_da_origem=None)
        r['canal_B'] = {'detectado': False}
        ops = [{'equipamento': 'B-01', 'acao': 'parada', 'instante_s': T - 0.3}]
        c = CD.conferir(r, CADASTRO, ops, T, SENSORES)
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_MANOBRA, 'B-01'))
        # sem registro de operacao, nada rebaixa: so a anotacao
        self.assertEqual(CD.conferir(r, CADASTRO, [], T, SENSORES)['decisao'], CD.DECISAO_CONFERIR)

    def test_rede_posicao_pela_tubulacao_e_lado_alem_do_sensor(self):
        topo = {'trechos': {'tronco': {'juncao_em_s_m': 300.0}, 'ramal_106': {'juncao_em_s_m': 0.0},
                            'ramal_104': {'juncao_em_s_m': 0.0}},
                'sensores': {'A': {'trecho': 'tronco', 's_m': 0.0}, 'B106': {'trecho': 'ramal_106', 's_m': 400.0},
                             'B104': {'trecho': 'ramal_104', 's_m': 250.0}}}
        geo = CD.GeometriaDaRede(topo)
        cad = {'equipamentos': [{'nome': 'B-01', 'tipo': 'bomba', 'trecho': 'tronco', 'posicao_m': -300.0},
                                {'nome': 'XV-106', 'tipo': 'valvula', 'trecho': 'ramal_106', 'posicao_m': 420.0},
                                {'nome': 'XV-104', 'tipo': 'valvula', 'trecho': 'ramal_104', 'posicao_m': 270.0}]}
        canal = {'detectado': True, 'polaridade': 'queda'}
        # localizado no ramal 106 perto da valvula: coincide pela tubulacao, nao no ramal 104 no mesmo s
        r = {'classe': 'localizado', 'trecho_estimado': 'ramal_106', 's_estimado_m': 410.0,
             'canais': {'A': canal, 'B106': canal}}
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': T - 0.5}]
        c = CD.conferir(r, cad, ops, T, None, geo)
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_MANOBRA, 'XV-106'))
        self.assertIn('ramal_106', c['texto'])
        aplicado = CD.aplicar(r, c)
        self.assertEqual((aplicado['classe'], aplicado['trecho_da_origem']), ('manobra', 'ramal_106'))
        # fora da rede, do lado do sensor B106: so a valvula alem dele
        f = {'classe': 'fora_do_trecho', 'lado_da_origem': 'B106', 'canais': {'B106': canal, 'A': canal}}
        self.assertEqual(CD.conferir(f, cad, ops, T, None, geo)['decisao'], CD.DECISAO_MANOBRA)
        f['lado_da_origem'] = 'A'
        c = CD.conferir(f, cad, [], T, None, geo)
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_CONFERIR, 'B-01'))
        # so um sensor viu a queda: o lado e o dele
        u = {'classe': 'detectado_sem_localizacao', 'canais': {'B104': canal, 'A': {'detectado': False}}}
        ops = [{'equipamento': 'XV-104', 'acao': 'abertura', 'instante_s': T - 0.5}]
        self.assertEqual(CD.conferir(u, cad, ops, T, None, geo)['equipamento'], 'XV-104')

    def test_sem_posicao_o_lado_e_o_do_sensor_que_viu_primeiro(self):
        topo = {'trechos': {'tronco': {'juncao_em_s_m': 300.0}, 'ramal_106': {'juncao_em_s_m': 0.0}},
                'sensores': {'A': {'trecho': 'tronco', 's_m': 0.0}, 'B106': {'trecho': 'ramal_106', 's_m': 400.0}}}
        cad = {'equipamentos': [{'nome': 'XV-106', 'tipo': 'valvula', 'trecho': 'ramal_106', 'posicao_m': 420.0}]}
        r = {'classe': 'detectado_sem_localizacao', 'motivo': 'chegadas incoerentes com qualquer ponto da rede',
             'canais': {'A': {'detectado': True, 'polaridade': 'queda', 'tempo_de_chegada_s': 10.60},
                        'B106': {'detectado': True, 'polaridade': 'queda', 'tempo_de_chegada_s': 10.27}}}
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': 10.2}]
        c = CD.conferir(r, cad, ops, 10.3, None, CD.GeometriaDaRede(topo))
        self.assertEqual((c['decisao'], c['equipamento']), (CD.DECISAO_MANOBRA, 'XV-106'))
        self.assertEqual(CD.conferir(r, cad, [], 10.3, None, CD.GeometriaDaRede(topo))['decisao'], CD.DECISAO_CONFERIR)

    def test_operacao_usada_nao_explica_outro_evento(self):
        ops = [{'equipamento': 'XV-106', 'acao': 'abertura', 'instante_s': T - 1.0, 'usada': True}]
        self.assertEqual(CD.conferir(localizado(452.0), CADASTRO, ops, T, SENSORES)['decisao'], CD.DECISAO_CONFERIR)

    def test_o_evento_leva_a_conferencia(self):
        c = CD.conferir(localizado(452.0), CADASTRO, [], T, SENSORES)
        e = AL.montar_evento(CD.aplicar(localizado(452.0), c), 'L-01', SENSORES, 'software')
        self.assertEqual(e['cadastro']['equipamento'], 'XV-106')
        self.assertEqual(e['nivel'], 'provavel')


if __name__ == '__main__':
    unittest.main()

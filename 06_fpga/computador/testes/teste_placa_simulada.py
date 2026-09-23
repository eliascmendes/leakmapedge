"""Testes de ponta a ponta do computador do cenario B contra a placa simulada.

O computador fala com placa_simulada.py pelo mesmo TransporteSerial que vai
usar com a FPGA, por um endereco socket:// em vez de uma porta COM. Passam
pelo teste o receptor (hospedeiro e leitor de quadros), o registro, o calculo
de posicao, a comparacao com o cenario A e o avaliador independente.

Precisa do pyserial. O motor verilog precisa tambem do Icarus Verilog; sem ele
esses testes sao pulados.

Roda com: python -m unittest discover -s 06_fpga/computador/testes -p "teste_*.py"
"""
import json
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import executar_cenario_b as EX  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import placa_simulada as PS  # noqa: E402
import transporte as TR  # noqa: E402

try:
    import serial  # noqa: F401
    TEM_PYSERIAL = True
except ImportError:
    TEM_PYSERIAL = False

sys.path.insert(0, os.path.join(RAIZ, '06_fpga', 'sim'))
import rodar_simulacao as RS  # noqa: E402

TEM_ICARUS = bool(RS.achar('iverilog') and RS.achar('vvp'))


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


REFERENCIA = {r['id']: r for r in ler(os.path.join(
    RAIZ, '06_fpga', 'resultados', 'leakmap_cenario_b_resultado_referencia_v1.json'))['resultados']}
AVALIACAO_A = ler(os.path.join(RAIZ, '05_avaliacao', 'leakmap_avaliacao_matriz_v1.json'))
CAMPOS = ('classe', 'posicao_estimada_m', 'delta_t_amostras', 'incerteza_de_posicao_m')


def rodar(placa, ids=None, tentativas=3, tempo_limite_s=1.0):
    """Roda o cenario B pela serial contra a placa simulada; devolve relatorio e registros."""
    with PS.ServidorTCP(placa, ('127.0.0.1', 0)) as servidor, tempfile.TemporaryDirectory() as pasta:
        transporte = TR.TransporteSerial(servidor.url)
        try:
            relatorio = EX.executar(transporte, ids, tentativas=tentativas,
                                    tempo_limite_s=tempo_limite_s, saida=pasta)
        finally:
            transporte.fechar()
        arquivos = EX.caminhos(relatorio['origem'], pasta)
        registros = {r['id']: r for r in ler(arquivos['resultado'])['resultados']}
    return relatorio, registros


class PlacaMuda:
    """Faz o papel da FPGA no fio: responde ao protocolo e ignora IDENTIFICAR."""

    def __init__(self):
        self.placa = PLACA.PlacaReferencia()

    def receber(self, dados):
        return self.placa.receber(dados)


@unittest.skipUnless(TEM_PYSERIAL, 'precisa do pyserial')
class PontaAPontaComOModelo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.placa = PS.PlacaSimulada(PS.criar_motor('referencia'))
        cls.relatorio, cls.registros = rodar(cls.placa)

    def test_a_placa_simulada_se_identifica_e_nunca_vira_fpga(self):
        self.assertEqual(self.relatorio['origem'], 'placa_simulada')
        self.assertIn('placa simulada', self.relatorio['identidade_da_placa'])
        for r in self.registros.values():
            self.assertEqual(r['origem'], 'placa_simulada')

    def test_todos_os_ensaios_concluidos_com_o_mesmo_resultado_da_referencia(self):
        self.assertEqual(self.relatorio['ensaios']['concluidos'], len(REFERENCIA))
        for ident, ref in REFERENCIA.items():
            with self.subTest(ensaio=ident):
                for campo in CAMPOS:
                    self.assertEqual(self.registros[ident].get(campo), ref.get(campo))

    def test_avaliador_independente_da_os_numeros_do_cenario_a(self):
        av = self.relatorio['avaliacao_contra_a_verdade']
        self.assertEqual(av['contagens'], AVALIACAO_A['contagens'])

    def test_tempo_de_comunicacao_medido_no_enlace(self):
        self.assertIsNotNone(self.relatorio['tempos']['comunicacao_medida_no_computador_s'])


@unittest.skipUnless(TEM_PYSERIAL, 'precisa do pyserial')
class EnlaceRuim(unittest.TestCase):
    """Bits trocados nos dois sentidos e resultados perdidos, com semente fixa."""

    def test_nunca_sai_resultado_errado_em_silencio(self):
        for semente in (1, 2):
            placa = PS.PlacaSimulada(PS.criar_motor('referencia'), ruido=3e-4, perder_resultado=0.2,
                                     semente=semente)
            relatorio, registros = rodar(placa, tempo_limite_s=0.3)
            eventos = relatorio['eventos_de_comunicacao_somados']
            self.assertGreater(eventos['reenvios_de_bloco'], 0)
            self.assertGreater(eventos['pedidos_de_resultado'], 0)
            for ident, ref in REFERENCIA.items():
                r = registros[ident]
                with self.subTest(semente=semente, ensaio=ident):
                    if r['classe'] == 'falha_execucao':
                        self.assertTrue(r['motivo'])        # falha explicita, com motivo
                    else:
                        for campo in CAMPOS:
                            self.assertEqual(r.get(campo), ref.get(campo))

    def test_com_tentativas_suficientes_todos_concluem(self):
        placa = PS.PlacaSimulada(PS.criar_motor('referencia'), ruido=3e-4, perder_resultado=0.2, semente=1)
        relatorio, registros = rodar(placa, tentativas=6, tempo_limite_s=0.3)
        self.assertEqual(relatorio['ensaios']['concluidos'], len(REFERENCIA))
        for ident, ref in REFERENCIA.items():
            self.assertEqual(registros[ident].get('posicao_estimada_m'), ref.get('posicao_estimada_m'))


@unittest.skipUnless(TEM_PYSERIAL, 'precisa do pyserial')
class Identificacao(unittest.TestCase):

    def test_quem_nao_responde_a_identificar_fica_como_fpga(self):
        with PS.ServidorTCP(PlacaMuda(), ('127.0.0.1', 0)) as servidor:
            transporte = TR.TransporteSerial(servidor.url)
            try:
                self.assertIsNone(transporte.identificar(0.2))
                self.assertEqual(transporte.origem, 'fpga')
            finally:
                transporte.fechar()

    def test_nomes_de_arquivo_separados_por_origem(self):
        nomes = {o: os.path.basename(EX.caminhos(o)['resultado']) for o in EX.SUFIXO}
        self.assertEqual(len(set(nomes.values())), len(nomes))
        self.assertIn('placa_simulada', nomes['placa_simulada'])
        self.assertNotIn('fpga', nomes['placa_simulada'])


@unittest.skipUnless(TEM_PYSERIAL and TEM_ICARUS, 'precisa do pyserial e do Icarus Verilog')
class PontaAPontaComOVerilog(unittest.TestCase):
    """O proprio Verilog da placa atras da porta, ciclo a ciclo no Icarus."""

    def test_verilog_atras_da_porta_da_o_mesmo_resultado(self):
        placa = PS.PlacaSimulada(PS.criar_motor('verilog'), ruido=2e-4, semente=5)
        try:
            ids = ['MX-001', 'MX-017', 'MX-027', 'MX-039', 'MX-044']
            relatorio, registros = rodar(placa, ids, tentativas=6, tempo_limite_s=1.0)
        finally:
            placa.fechar()
        self.assertEqual(relatorio['origem'], 'placa_simulada')
        self.assertIn('Verilog', relatorio['identidade_da_placa'])
        self.assertEqual(relatorio['ensaios']['concluidos'], len(ids))
        self.assertGreater(placa.contagem['ciclos_de_processamento'], 0)
        for ident in ids:
            with self.subTest(ensaio=ident):
                for campo in CAMPOS:
                    self.assertEqual(registros[ident].get(campo), REFERENCIA[ident].get(campo))


if __name__ == '__main__':
    unittest.main()

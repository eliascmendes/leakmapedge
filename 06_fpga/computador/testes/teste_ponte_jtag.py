"""Testes do caminho pelo cabo de gravacao (JTAG virtual), sem placa.

O TransporteJtag conversa com o testbench 06_fpga/sim/tb_ponte_jtag.v, que
fala as mesmas linhas do quartus_stp com ponte_jtag.tcl, mas desloca os bits
no proprio Verilog da ponte e do nucleo. Passam pelo teste a ponte, as filas
entre os dois relogios, o transporte e o computador inteiro do cenario B.

Precisa do Icarus Verilog. O teste do script do quartus_stp precisa do
Quartus Prime e so roda onde ele estiver instalado.

Roda com: python -m unittest discover -s 06_fpga/computador/testes -p "teste_*.py"
"""
import json
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
FPGA = os.path.join(RAIZ, '06_fpga')
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))
sys.path.insert(0, os.path.join(FPGA, 'sim'))

import executar_cenario_b as EX  # noqa: E402
import rodar_simulacao as RS  # noqa: E402
import transporte as TR  # noqa: E402

VVP = RS.achar('vvp')
IVERILOG = RS.achar('iverilog')
FONTES = ['rtl/leakmap_multiplicador.v', 'rtl/leakmap_detector.v', 'rtl/leakmap_nucleo.v',
          'rtl/leakmap_ponte_jtag.v']
REFERENCIA = {r['id']: r for r in json.load(open(os.path.join(
    FPGA, 'resultados', 'leakmap_cenario_b_resultado_referencia_v1.json'), encoding='utf-8'))['resultados']}
CAMPOS = ('classe', 'posicao_estimada_m', 'delta_t_amostras')


def jtag_simulado(*extras):
    return TR.TransporteJtag(comando=[VVP, '-n', 'sim/tb_ponte_jtag.vvp'] + list(extras), pasta=FPGA,
                             origem='simulacao_do_verilog')


@unittest.skipUnless(VVP and IVERILOG, 'precisa do Icarus Verilog')
class PonteJtagNoSimulador(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        RS.compilar(IVERILOG, FONTES, 'sim/tb_ponte_jtag.v', 'sim/tb_ponte_jtag.vvp')

    def rodar(self, ids, *extras):
        transporte = jtag_simulado(*extras)
        with tempfile.TemporaryDirectory() as pasta:
            try:
                relatorio = EX.executar(transporte, ids, tempo_limite_s=5.0, saida=pasta)
            finally:
                transporte.fechar()
            arquivos = EX.caminhos(relatorio['origem'], pasta)
            registros = {r['id']: r for r in json.load(open(arquivos['resultado'], encoding='utf-8'))['resultados']}
        return transporte, relatorio, registros

    def conferir(self, registros):
        for ident, r in registros.items():
            with self.subTest(ensaio=ident):
                for campo in CAMPOS:
                    self.assertEqual(r.get(campo), REFERENCIA[ident].get(campo))

    def test_marca_da_ponte_e_versao(self):
        transporte = jtag_simulado()
        try:
            self.assertEqual(transporte.estado['versao'], 1)
            self.assertFalse(transporte.estado['fila_de_entrada_transbordou'])
            self.assertFalse(transporte.invertido)
        finally:
            transporte.fechar()

    def test_ensaios_pelo_jtag_iguais_a_referencia(self):
        ids = ['MX-001', 'MX-021', 'MX-039', 'MX-044']
        _, relatorio, registros = self.rodar(ids)
        self.assertEqual(relatorio['ensaios']['concluidos'], len(ids))
        self.conferir(registros)

    def test_cabo_que_desloca_na_outra_ordem_e_percebido_sozinho(self):
        transporte, relatorio, registros = self.rodar(['MX-013'], '+invertido')
        self.assertTrue(transporte.invertido)
        self.assertEqual(relatorio['ensaios']['concluidos'], 1)
        self.conferir(registros)


@unittest.skipUnless(TR.achar_quartus_stp(), 'precisa do Quartus Prime')
class ScriptDoQuartus(unittest.TestCase):

    def test_conversa_pela_porta_local_e_placa_sem_o_projeto_para_com_mensagem_clara(self):
        # no modo --teste o script nao abre o JTAG e devolve o proprio valor:
        # a conexao funciona, mas a marca "LK" da ponte nao aparece
        with self.assertRaises(TR.FalhaNaConexao) as erro:
            TR.TransporteJtag(cabo='--teste')
        self.assertIn('esta gravado na placa', str(erro.exception))


if __name__ == '__main__':
    unittest.main()

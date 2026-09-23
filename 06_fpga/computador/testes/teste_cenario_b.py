"""Testes do lado do computador do cenario B.

Cada classe cobre o criterio de conclusao de uma etapa do fluxograma. A
"placa" dos testes e o modelo de referencia em Python (placa_referencia.py);
nenhum resultado daqui e resultado de FPGA.

Roda com: python -m unittest discover -s 06_fpga/computador/testes -p "teste_*.py"
"""
import copy
import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))
sys.path.insert(0, os.path.join(RAIZ, '05_avaliacao'))

import avaliador as AV  # noqa: E402
import comparador as CP  # noqa: E402
import detector as D  # noqa: E402
import detector_ponto_fixo as PF  # noqa: E402
import dimensionamento as DM  # noqa: E402
import executar_cenario_b as EX  # noqa: E402
import hospedeiro as HO  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import protocolo as PR  # noqa: E402
import registro_b as RB  # noqa: E402
import representacao as RP  # noqa: E402
import selo as SE  # noqa: E402
import transporte as TR  # noqa: E402


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


PACOTE = ler(SE.PACOTE)
RESULTADO_A = ler(SE.RESULTADO_A)
ESCALA = PACOTE['escala']
CAL = D.calibracao_padrao()
POR_ID = {e['id']: e for e in PACOTE['ensaios']}


def rodar_na_referencia(ensaio, placa=None, corromper=None, tentativas=3):
    placa = placa or PLACA.PlacaReferencia()
    preparo = PP.preparar_ensaio(ensaio, ESCALA, CAL)
    host = HO.Hospedeiro(TR.TransporteMemoria(placa, corromper), tentativas=tentativas)
    rodada = host.rodar(ensaio['id'], preparo['conversao']['canal_A']['codigos'],
                        preparo['conversao']['canal_B']['codigos'], preparo['parametros'])
    return preparo, rodada, placa


class B02eB03Representacao(unittest.TestCase):

    def test_ida_e_volta_dentro_de_meio_degrau(self):
        for ensaio in PACOTE['ensaios'][::7]:
            espec = RP.especificacao(RP.degrau_do_ensaio(ensaio))
            for canal in ('canal_A_carga_m', 'canal_B_carga_m'):
                codigos, abaixo, acima = RP.converter(ensaio[canal], espec)
                volta = RP.desconverter(codigos, espec)
                self.assertEqual((abaixo, acima), (0, 0))
                self.assertLessEqual(np.max(np.abs(volta - np.asarray(ensaio[canal]))),
                                     espec['degrau_m'] / 2 + 1e-12)

    def test_tabela_de_bordas_nos_degraus_da_matriz(self):
        for degrau in (RP.DEGRAU_PADRAO_M, 100.0 / 65535, 100.0 / 4095):
            espec = RP.especificacao(degrau)
            for caso in RP.tabela_de_bordas(espec):
                with self.subTest(degrau=degrau, caso=caso['caso']):
                    codigo, _, _ = RP.converter([caso['entrada_m']], espec)
                    self.assertEqual(codigo[0], caso['codigo_esperado'])

    def test_empate_vai_para_o_par_com_degrau_exato(self):
        espec = RP.especificacao(2.0 ** -10)
        d = espec['degrau_m']
        codigos, _, _ = RP.converter([0.5 * d, 1.5 * d, 2.5 * d, 3.5 * d], espec)
        self.assertEqual(codigos, [0, 2, 2, 4])

    def test_saturacao_nunca_e_silenciosa(self):
        espec = RP.especificacao(1e-3)
        codigos, abaixo, acima = RP.converter([-1.0, 10.0, 70.0, 80.0], espec)
        self.assertEqual(codigos, [0, 10000, RP.CODIGO_MAXIMO, RP.CODIGO_MAXIMO])
        self.assertEqual((abaixo, acima), (1, 2))

    def test_valor_nao_numerico_recusa_o_ensaio(self):
        with self.assertRaises(RP.ValorInvalido):
            RP.converter([1.0, float('nan')], RP.especificacao(1e-3))


class B04eB06Protocolo(unittest.TestCase):

    def test_crc_confere_com_o_vetor_padrao(self):
        self.assertEqual(PR.crc16(b'123456789'), 0x29B1)

    def test_bloco_ida_e_volta(self):
        pares = [(i, 65535 - i) for i in range(PR.PARES_POR_BLOCO)]
        carga = PR.carga_amostras('MX-007', 3, 96, pares)
        self.assertEqual(PR.ler_amostras(carga), ('MX-007', 3, 96, pares))

    def test_leitor_aceita_bytes_picados_e_lixo_antes(self):
        quadro = PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('MX-001', 4, 101))
        leitor = PR.LeitorDeQuadros()
        eventos = []
        dados = b'\x00\xff\xa5' + quadro + quadro
        for k in range(len(dados)):
            eventos += leitor.alimentar(dados[k:k + 1])
        self.assertEqual([e[0] for e in eventos], ['ok', 'ok'])
        self.assertEqual(PR.ler_executar(eventos[0][2]), ('MX-001', 4, 101))

    def test_byte_corrompido_vira_evento_de_crc(self):
        quadro = bytearray(PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('MX-001', 4, 101)))
        quadro[9] ^= 0x40
        eventos = PR.LeitorDeQuadros().alimentar(bytes(quadro))
        self.assertEqual(eventos[0][0], 'crc_invalido')

    def test_bloco_corrompido_e_recusado_e_reenviado(self):
        """Criterio de B-06: bloco corrompido de proposito nao e processado em silencio."""
        ensaio = POR_ID['MX-001']
        limpo = rodar_na_referencia(ensaio)[1]['resultado']

        def corromper(quadro, n):
            if n == 3:                       # segundo bloco de amostras
                quadro = bytearray(quadro)
                quadro[20] ^= 0x01
            return bytes(quadro)

        _, rodada, placa = rodar_na_referencia(ensaio, corromper=corromper)
        self.assertEqual(rodada['eventos_de_comunicacao']['reenvios_de_bloco'], 1)
        self.assertEqual(rodada['resultado']['contadores']['falhas_de_crc'], 1)
        for canal in ('canal_A', 'canal_B'):
            self.assertEqual(rodada['resultado'][canal], limpo[canal])

    def test_bloco_fora_de_sequencia_impede_a_execucao(self):
        ensaio = POR_ID['MX-001']
        preparo = PP.preparar_ensaio(ensaio, ESCALA, CAL)
        blocos = PR.blocos_do_ensaio(ensaio['id'], preparo['conversao']['canal_A']['codigos'],
                                     preparo['conversao']['canal_B']['codigos'])
        placa = PLACA.PlacaReferencia()
        placa.receber(PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(
            ensaio['id'], preparo['parametros'], ensaio['n_pontos'])))
        respostas = PR.LeitorDeQuadros().alimentar(b''.join(placa.receber(b) for b in (blocos[0], blocos[2])))
        situacoes = [PR.ler_bloco_recebido(c)[2] for _, t, c in respostas]
        self.assertEqual(situacoes, [PR.BLOCO_OK, PR.BLOCO_FORA_DE_SEQUENCIA])
        self.assertEqual(placa.contadores['descontinuidades_de_sequencia'], 1)
        saida = placa.receber(PR.montar_quadro(PR.EXECUTAR, PR.carga_executar(
            ensaio['id'], len(blocos), ensaio['n_pontos'])))
        resultado = PR.ler_resultado(PR.LeitorDeQuadros().alimentar(saida)[0][2])
        self.assertEqual(resultado['situacao'], PR.RESULTADO_RECUSADO_AMOSTRAS_FALTANDO)
        self.assertEqual(placa.execucoes, 0)


class RegrasQueOHardwareSegue(unittest.TestCase):
    """Regras que o Verilog implementa byte a byte; a referencia segue as mesmas."""

    def recibos(self, placa, dados):
        return [PR.ler_bloco_recebido(c) for s, t, c in PR.LeitorDeQuadros().alimentar(placa.receber(dados))
                if t == PR.BLOCO_RECEBIDO]

    def test_mensagem_com_tamanho_errado_e_mal_formada(self):
        placa = PLACA.PlacaReferencia()
        quadro = PR.montar_quadro(PR.CONFIGURAR, b'\x00' * 30)
        self.assertEqual(self.recibos(placa, quadro), [('', PR.CONTAGEM_NAO_CONFIAVEL, PR.BLOCO_MAL_FORMADO)])
        quadro = PR.montar_quadro(PR.EXECUTAR, b'\x00' * 13)
        self.assertEqual(self.recibos(placa, quadro)[0][2], PR.BLOCO_MAL_FORMADO)

    def test_bloco_que_nao_comeca_onde_o_anterior_terminou_e_recusado(self):
        ensaio = POR_ID['MX-001']
        preparo = PP.preparar_ensaio(ensaio, ESCALA, CAL)
        placa = PLACA.PlacaReferencia()
        placa.receber(PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(
            ensaio['id'], preparo['parametros'], ensaio['n_pontos'])))
        pares = [(1, 2)] * 4
        fora = PR.montar_quadro(PR.AMOSTRAS, PR.carga_amostras(ensaio['id'], 0, 8, pares))
        self.assertEqual(self.recibos(placa, fora), [(ensaio['id'], 0, PR.BLOCO_MAL_FORMADO)])
        certo = PR.montar_quadro(PR.AMOSTRAS, PR.carga_amostras(ensaio['id'], 0, 0, pares))
        self.assertEqual(self.recibos(placa, certo), [(ensaio['id'], 0, PR.BLOCO_OK)])

    def test_cabecalho_com_tamanho_absurdo_e_descartado_e_a_placa_se_recupera(self):
        placa = PLACA.PlacaReferencia()
        lixo = PR.SINCRONISMO + bytes([PR.EXECUTAR]) + (5000).to_bytes(2, 'little')
        valido = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(
            'MX-001', PF.parametros_inteiros(CAL, 4e-4, 1e-3, 0.0244), 101))
        eventos = PR.LeitorDeQuadros().alimentar(placa.receber(lixo + valido))
        self.assertEqual([t for _, t, _ in eventos], [PR.BLOCO_RECEBIDO, PR.CONFIGURACAO_LIDA])
        self.assertEqual(PR.ler_bloco_recebido(eventos[0][2])[2], PR.BLOCO_CRC_INVALIDO)


class B01Selo(unittest.TestCase):

    def test_todos_os_ensaios_da_matriz_tem_selo(self):
        selos = SE.gerar_selos(PACOTE, RESULTADO_A)
        self.assertEqual(selos['n_selados'], len(PACOTE['ensaios']))
        self.assertEqual(selos, ler(SE.SELOS), 'selos gravados desatualizados')

    def test_ensaio_alterado_depois_do_selo_e_recusado(self):
        pacote = copy.deepcopy(PACOTE)
        pacote['ensaios'][0]['canal_A_carga_m'][10] += 1e-9
        with self.assertRaises(SE.EnsaioSemSelo):
            SE.selecionar(pacote['ensaios'][0]['id'], pacote, ler(SE.SELOS))

    def test_ensaio_sem_registro_no_cenario_a_nao_recebe_selo(self):
        resultado = copy.deepcopy(RESULTADO_A)
        resultado['resultados'] = [r for r in resultado['resultados'] if r['id'] != 'MX-003']
        selos = SE.gerar_selos(PACOTE, resultado)
        self.assertIn('MX-003', selos['recusados'])
        with self.assertRaises(SE.EnsaioSemSelo):
            SE.selecionar('MX-003', PACOTE, selos)

    def test_identificador_e_o_mesmo_do_cenario_a(self):
        ensaio = SE.selecionar('MX-021', PACOTE, ler(SE.SELOS))
        self.assertEqual(ensaio['id'], 'MX-021')
        self.assertIn('MX-021', {r['id'] for r in RESULTADO_A['resultados']})


class B05Dimensionamento(unittest.TestCase):

    def test_exemplos_do_fluxograma(self):
        self.assertEqual(DM.memoria_por_duracao_bits(2, 10000), 640000)
        self.assertAlmostEqual(DM.memoria_por_duracao_bits(2, 10000) / 8 / 1024, 78.125)
        self.assertEqual(DM.memoria_por_duracao_bits(10, 50000), 16000000)
        self.assertAlmostEqual(DM.memoria_por_duracao_bits(10, 50000) / 8 / 2 ** 20, 1.907, places=3)
        self.assertEqual(DM.capacidade_serial_bytes_s(115200), 11520)
        self.assertEqual(DM.capacidade_serial_bytes_s(115200) / 4, 2880)

    def test_decisao_registrada_e_via_1_em_todas_as_candidatas(self):
        relatorio = ler(DM.SAIDA)
        self.assertEqual(relatorio['decisao']['via'], 1)
        self.assertTrue(all(p['via'] == 1 for p in relatorio['placas_candidatas']))
        self.assertIn('bits', relatorio['decisao']['conta'])


class B07Configuracao(unittest.TestCase):

    def test_leitura_de_volta_confere_e_contadores_zerados(self):
        _, rodada, _ = rodar_na_referencia(POR_ID['MX-005'])
        conf = rodada['configuracao']
        self.assertFalse(any(conf['contadores_lidos'].values()))

    def test_leitura_de_volta_divergente_para_a_execucao(self):
        class PlacaDefeituosa(PLACA.PlacaReferencia):
            def _configurar(self, carga):
                resposta = bytearray(super()._configurar(carga))
                corpo = bytearray(resposta[5:-2])
                corpo[9] ^= 0x01                         # altera um byte do coeficiente
                return PR.montar_quadro(PR.CONFIGURACAO_LIDA, bytes(corpo))
        with self.assertRaises(HO.FalhaNaPlaca):
            rodar_na_referencia(POR_ID['MX-005'], placa=PlacaDefeituosa())

    def test_mesmo_ensaio_duas_vezes_da_o_mesmo_resultado(self):
        placa = PLACA.PlacaReferencia()
        primeiro = rodar_na_referencia(POR_ID['MX-021'], placa=placa)[1]['resultado']
        rodar_na_referencia(POR_ID['MX-001'], placa=placa)
        segundo = rodar_na_referencia(POR_ID['MX-021'], placa=placa)[1]['resultado']
        self.assertEqual(primeiro, segundo)


class B08IndiceComum(unittest.TestCase):

    def test_atraso_conhecido_entre_canais_aparece_inteiro_na_saida(self):
        base = POR_ID['MX-005']
        ts = RB.periodo(base)
        for atraso in (0, 7, 40):
            with self.subTest(atraso=atraso):
                ensaio = copy.deepcopy(base)
                a = list(base['canal_A_carga_m'])
                ensaio['canal_A_carga_m'] = a
                ensaio['canal_B_carga_m'] = [a[0]] * atraso + a[:len(a) - atraso]
                ensaio['id'] = 'ATRASO%02d' % atraso
                _, rodada, _ = rodar_na_referencia(ensaio)
                r = rodada['resultado']
                self.assertTrue(r['canal_A']['detectado'] and r['canal_B']['detectado'])
                self.assertEqual(r['canal_B']['indice_de_chegada'] - r['canal_A']['indice_de_chegada'], atraso)
                self.assertGreater(ts, 0)


class B09ReferenciaEmPontoFixo(unittest.TestCase):
    """O modelo em fluxo da placa tem de igualar 04_detector/detector_ponto_fixo.py."""

    def test_mesmos_indices_nos_90_canais_da_matriz(self):
        for ensaio in PACOTE['ensaios']:
            preparo = PP.preparar_ensaio(ensaio, ESCALA, CAL)
            ts = RB.periodo(ensaio)
            espec = preparo['representacao']
            for canal in ('canal_A', 'canal_B'):
                with self.subTest(ensaio=ensaio['id'], canal=canal):
                    detector = PLACA.DetectorInteiro(preparo['parametros'])
                    for codigo in preparo['conversao'][canal]['codigos']:
                        detector.amostra(codigo)
                    fluxo = detector.resultado()
                    sinal = RP.desconverter(preparo['conversao'][canal]['codigos'], espec)
                    ref, _, _, _ = PF.detectar_canal_inteiro(sinal, ts, espec['degrau_m'], CAL,
                                                             ESCALA['resolucao_declarada_m'])
                    self.assertEqual(bool(fluxo['bandeiras'] & PR.BANDEIRA_DETECTADO), ref['detectado'])
                    self.assertEqual(fluxo['n_oportunidades_de_decisao'], ref['n_oportunidades_de_decisao'])
                    if ref['detectado']:
                        self.assertEqual(fluxo['indice_de_cruzamento'], ref['indice_de_cruzamento'])
                        self.assertEqual(fluxo['indice_de_chegada'], ref['indice_de_chegada'])
                        self.assertEqual(bool(fluxo['bandeiras'] & PR.BANDEIRA_RETROCESSO_TRUNCADO),
                                         ref['retrocesso_truncado'])


class B09CasosQueForcamORetrocesso(unittest.TestCase):
    """Na matriz a frente e forte e o retrocesso anda no maximo uma amostra.
    Estes sinais sinteticos exercitam o retrocesso longo e o truncado, para
    que o Verilog nao possa errar nessa parte sem o teste perceber."""

    DEGRAU = 1e-3
    TS = 4.0130559895570352e-4

    def comparar(self, codigos):
        params = PF.parametros_inteiros(CAL, self.TS, self.DEGRAU, ESCALA['resolucao_declarada_m'])
        detector = PLACA.DetectorInteiro(params)
        for c in codigos:
            detector.amostra(int(c))
        fluxo = detector.resultado()
        ref, _, _, _ = PF.detectar_canal_inteiro(np.asarray(codigos) * self.DEGRAU, self.TS,
                                                 self.DEGRAU, CAL, ESCALA['resolucao_declarada_m'])
        self.assertTrue(ref['detectado'])
        self.assertEqual(fluxo['indice_de_cruzamento'], ref['indice_de_cruzamento'])
        self.assertEqual(fluxo['indice_de_chegada'], ref['indice_de_chegada'])
        self.assertEqual(bool(fluxo['bandeiras'] & PR.BANDEIRA_RETROCESSO_TRUNCADO),
                         ref['retrocesso_truncado'])
        return ref

    def test_rampa_lenta_e_limpa_trunca_o_retrocesso(self):
        # Truncar exige frente fora da faixa de ruido por mais de n_curta + n_guarda
        # amostras antes do cruzamento; numa varredura de rampas de passo 2,0 a 3,0,
        # so o passo 2,9 faz isso. E um caso raro, e por isso fica fixo aqui.
        rampa = np.concatenate([np.zeros(120), np.arange(1, 200), np.full(80, 199)])
        codigos = np.rint(58000 - 2.9 * rampa).astype(int)
        ref = self.comparar(codigos)
        self.assertTrue(ref['retrocesso_truncado'])
        self.assertEqual(ref['amostras_retrocedidas'], CAL['n_curta'] + CAL['n_guarda'])

    def test_frente_fraca_com_ruido_retrocede_varias_amostras(self):
        retrocessos = []
        for semente in range(12):
            rng = np.random.default_rng(semente)
            rampa = np.concatenate([np.zeros(150), np.linspace(0, -500, 40), np.full(120, -500)])
            codigos = np.rint(52000 + rampa + rng.normal(0, 20, rampa.size)).astype(int)
            with self.subTest(semente=semente):
                retrocessos.append(self.comparar(codigos)['amostras_retrocedidas'])
        self.assertGreater(max(retrocessos), 1, 'os casos precisam exercitar retrocesso longo')


class B10Resultado(unittest.TestCase):

    def test_resultado_perdido_e_pedido_de_novo(self):
        placa = PLACA.PlacaReferencia(perder_resultados=2)
        _, rodada, _ = rodar_na_referencia(POR_ID['MX-001'], placa=placa)
        self.assertIsNotNone(rodada['resultado'])
        self.assertEqual(rodada['eventos_de_comunicacao']['pedidos_de_resultado'], 2)
        self.assertEqual(rodada['resultado']['id'], 'MX-001')

    def test_sem_resultado_vira_registro_de_falha_e_nao_some(self):
        placa = PLACA.PlacaReferencia(perder_resultados=99)
        ensaio = POR_ID['MX-001']
        preparo, rodada, _ = rodar_na_referencia(ensaio, placa=placa)
        self.assertIsNone(rodada['resultado'])
        registro = RB.montar_registro(ensaio, preparo, rodada, ESCALA, CAL, 'referencia_python_da_placa')
        self.assertEqual(registro['classe'], D.CLASSE_FALHA)
        self.assertIn('sem resultado', registro['motivo'])


class B11aB14Execucao(unittest.TestCase):
    """Execucao completa da matriz numa pasta temporaria."""

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        cls.relatorio = EX.executar(TR.TransporteMemoria(PLACA.PlacaReferencia()), saida=cls.pasta.name)
        cls.arquivos = EX.caminhos('referencia_python_da_placa', cls.pasta.name)
        cls.resultado = ler(cls.arquivos['resultado'])
        cls.comparacao = ler(cls.arquivos['comparacao'])

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def test_b11_origem_obrigatoria_e_nunca_fpga_na_referencia(self):
        self.assertEqual(self.resultado['origem'], 'referencia_python_da_placa')
        for r in self.resultado['resultados']:
            self.assertEqual(r['origem'], 'referencia_python_da_placa')

    def test_b11_registro_lido_pelo_mesmo_avaliador_do_cenario_a(self):
        avaliacao = AV.avaliar(self.resultado, ler(EX.VERDADE))
        self.assertEqual(avaliacao['n_ensaios'], len(PACOTE['ensaios']))
        self.assertEqual(avaliacao['contagens']['falha_de_execucao'], 0)

    def test_b13_toda_divergencia_tem_causa_e_a_posicao_nao_muda(self):
        resumo = self.comparacao['resumo']
        self.assertTrue(resumo['toda_divergencia_tem_causa'])
        self.assertLess(resumo['maior_divergencia_de_posicao_m'], 1e-9)
        for linha in self.comparacao['ensaios']:
            if not linha['igual']:
                self.assertTrue(linha['causas'])

    def test_b13_chegadas_iguais_as_do_software_em_todos_os_ensaios(self):
        for linha in self.comparacao['ensaios']:
            with self.subTest(ensaio=linha['id']):
                self.assertEqual(linha['classe_A'], linha['classe_B'])
                for canal in ('canal_A', 'canal_B'):
                    self.assertIn(linha['%s_indice_de_chegada_divergencia_amostras' % canal], (0, None))

    def test_b14_tentativas_gravadas_e_contas_fecham(self):
        tentativas = ler(self.arquivos['tentativas'])
        e = self.relatorio['ensaios']
        self.assertEqual(tentativas['n_tentativas'], e['tentados'])
        self.assertEqual(e['concluidos'] + e['nao_concluidos'], e['tentados'])
        self.assertEqual(self.relatorio['nome_correto'], 'reproducao de sinais digitais em FPGA fisica')

    def test_b14_contra_a_verdade_igual_ao_cenario_a(self):
        av = self.relatorio['avaliacao_contra_a_verdade']
        ref = ler(os.path.join(RAIZ, '05_avaliacao', 'leakmap_avaliacao_matriz_v1.json'))
        self.assertEqual(av['contagens'], ref['contagens'])
        self.assertTrue(math.isclose(av['erro_de_localizacao_geral']['mediano_m'],
                                     ref['erro_de_localizacao_geral']['mediano_m'], abs_tol=1e-9))


if __name__ == '__main__':
    unittest.main()

"""LEAKMAP - modelo de referencia do lado da placa (cenario B).

O que a FPGA faz, escrito em Python, amostra a amostra, so com inteiros e com
memorias de tamanho fixo, do jeito que o hardware vai fazer:

  B-06  confere CRC e sequencia de cada bloco, do lado da placa
  B-07  guarda a configuracao, zera contadores e devolve tudo para conferencia
  B-08  reproduz a memoria com um indice comum aos dois canais
  B-09  passa-altas, somas de energia, limiar e marcacao da chegada
  B-10  monta o resultado e o repete ate o computador confirmar

Serve a dois propositos. E a especificacao executavel que o Verilog tem de
igualar, e e a "placa" usada nos testes do computador enquanto nao ha placa.
Nenhum resultado produzido por este modelo pode ser apresentado como
resultado de FPGA: o registro sai marcado com a origem
`referencia_python_da_placa`.

O detector daqui foi escrito de novo, em forma de fluxo, a partir so dos
parametros inteiros. Os testes exigem que ele de exatamente os mesmos
indices que 04_detector/detector_ponto_fixo.py nos 45 ensaios da matriz.
"""
from collections import deque

import protocolo as PR

LIMITE_64_BITS = (1 << 64) - 1
LIMITE_32_BITS = (1 << 32) - 1


class EstouroDeLargura(OverflowError):
    pass


class DetectorInteiro:
    """A-11 e A-12 em fluxo: recebe um codigo por amostra.

    Memoria interna, em amostras:
      - quadrados de Ye: n_curta + n_guarda + n_longa + 1
      - Ye e Y anteriores ao disparo: n_curta + n_guarda + 2
    """

    def __init__(self, p):
        self.p = p
        self.nc, self.ng, self.nl = p['n_curta'], p['n_guarda'], p['n_longa']
        self.recuo = self.nc + self.ng
        janela = self.recuo + self.nl
        self.quadrados = deque(maxlen=janela + 1)
        self.historico_ye = deque(maxlen=self.recuo + 2)
        self.historico_y = deque(maxlen=self.recuo + 2)
        self.limiar_energia_longa = self.nl * p['piso_energia_por_amostra']
        self.limiar_amplitude = self.nc * p['piso_em_ye'] * p['piso_em_ye']
        self.n = 0
        self.x_anterior = None
        self.y = 0
        self.s_curta = 0
        self.s_longa = 0
        self.oportunidades = 0
        self.saida = {
            'bandeiras': 0, 'indice_de_cruzamento': 0, 'indice_de_chegada': 0,
            'n_oportunidades_de_decisao': 0, 's_curta_no_cruzamento': 0,
            's_longa_no_cruzamento': 0, 'maior_salto_q': 0,
        }
        self.detectou = False

    def amostra(self, codigo):
        p, n = self.p, self.n
        if self.x_anterior is None:
            self.y = 0
        else:
            diferenca = (codigo - self.x_anterior) << p['fracao']
            self.y = (p['coeficiente_do_filtro'] * (self.y + diferenca)) >> p['fracao']
        self.x_anterior = codigo
        ye = self.y >> p['desloca_energia']
        q = ye * ye

        # somas moveis: a curta termina em n, a longa termina em n - recuo
        self.quadrados.append(q)
        self.s_curta += q
        if len(self.quadrados) > self.nc:
            self.s_curta -= self.quadrados[-1 - self.nc]
        if n >= self.recuo:
            self.s_longa += self.quadrados[-1 - self.recuo]
            if n >= self.recuo + self.nl:
                self.s_longa -= self.quadrados[-1 - self.recuo - self.nl]
        self.historico_ye.append(ye)
        self.historico_y.append(self.y)

        for valor in (self.s_curta, self.s_longa):
            if valor > LIMITE_64_BITS:
                raise EstouroDeLargura('soma de energia acima de 64 bits na amostra %d' % n)

        valido = n >= self.recuo + self.nl - 1
        if valido:
            self.oportunidades += 1
            if not self.detectou:
                self._decidir(n)
        self.n += 1

    def _decidir(self, n):
        p = self.p
        s_longa_efetiva = (self.s_longa if self.s_longa > self.limiar_energia_longa
                           else self.limiar_energia_longa)
        esquerda = self.s_curta * self.nl
        direita = s_longa_efetiva * (p['limiar_de_razao'] * self.nc)
        if max(esquerda, direita) > LIMITE_64_BITS:
            raise EstouroDeLargura('comparacao acima de 64 bits na amostra %d' % n)
        if not (esquerda >= direita and self.s_curta >= self.limiar_amplitude):
            return

        # A-12: retrocesso sobre o historico anterior ao disparo
        self.detectou = True
        referencia = self.s_longa
        limite = max(0, n - self.recuo)
        k2 = p['k2_faixa_de_ruido']

        def ye_em(indice):
            return self.historico_ye[len(self.historico_ye) - 1 - (n - indice)]

        def fora(indice):
            return ye_em(indice) ** 2 * self.nl > k2 * referencia

        i = n
        while i > limite and fora(i - 1):
            i -= 1
        truncado = i == limite and fora(i) and i > 0 and fora(i - 1)

        maior = 0
        for k in range(i, n):
            a = self.historico_y[len(self.historico_y) - 1 - (n - k)]
            b = self.historico_y[len(self.historico_y) - 1 - (n - k - 1)]
            maior = max(maior, abs(b - a))
        if maior > LIMITE_32_BITS:
            raise EstouroDeLargura('maior salto acima de 32 bits')

        self.saida.update({
            'bandeiras': PR.BANDEIRA_DETECTADO | (PR.BANDEIRA_RETROCESSO_TRUNCADO if truncado else 0),
            'indice_de_cruzamento': n,
            'indice_de_chegada': i,
            's_curta_no_cruzamento': self.s_curta,
            's_longa_no_cruzamento': referencia,
            'maior_salto_q': maior,
        })

    def resultado(self):
        saida = dict(self.saida)
        saida['n_oportunidades_de_decisao'] = self.oportunidades
        return saida


class PlacaReferencia:
    """Maquina de estados da placa: recebe bytes, devolve bytes.

    `perder_resultados` descarta as N primeiras mensagens de resultado, para
    testar a repeticao com confirmacao de B-10.
    """

    def __init__(self, capacidade_de_amostras=4096, perder_resultados=0):
        self.capacidade = capacidade_de_amostras
        self.perder_resultados = perder_resultados
        self.leitor = PR.LeitorDeQuadros()
        self._zerar()
        self.configurado = False
        self.resultado_pendente = None
        self.execucoes = 0

    def _zerar(self):
        self.identificador = None
        self.parametros = None
        self.n_amostras = 0
        self.memoria_a = []
        self.memoria_b = []
        self.sequencia_esperada = 0
        self.contadores = {'falhas_de_crc': 0, 'descontinuidades_de_sequencia': 0,
                           'eventos_de_buffer': 0, 'blocos_recebidos': 0}

    def receber(self, dados):
        saida = bytearray()
        for situacao, tipo, carga in self.leitor.alimentar(dados):
            if situacao != 'ok':
                self.contadores['falhas_de_crc'] += 1
                saida += PR.montar_quadro(PR.BLOCO_RECEBIDO, PR.carga_bloco_recebido(
                    '', PR.CONTAGEM_NAO_CONFIAVEL, PR.BLOCO_CRC_INVALIDO))
                continue
            saida += self._tratar(tipo, carga)
        return bytes(saida)

    def _tratar(self, tipo, carga):
        if tipo == PR.CONFIGURAR:
            return self._configurar(carga)
        if tipo == PR.AMOSTRAS:
            return self._amostras(carga)
        if tipo == PR.EXECUTAR:
            return self._executar(carga)
        if tipo == PR.PEDIR_RESULTADO:
            return self._enviar_resultado()
        if tipo == PR.CONFIRMAR_RESULTADO:
            if self.resultado_pendente and PR.decodificar_id(carga) == self.identificador:
                self.resultado_pendente = None
            return b''
        return b''

    # --- B-07 ------------------------------------------------------------------
    def _configurar(self, carga):
        identificador, valores = PR.ler_configurar(carga)
        self._zerar()
        n = valores.pop('n_amostras')
        self.identificador = identificador
        self.parametros = valores
        self.n_amostras = n
        self.memoria_a = [None] * n
        self.memoria_b = [None] * n
        self.configurado = n <= self.capacidade
        self.resultado_pendente = None
        return PR.montar_quadro(PR.CONFIGURACAO_LIDA, PR.carga_configuracao_lida(
            identificador, self.parametros, n, self.contadores))

    # --- B-04 e B-06 ---------------------------------------------------------------
    def _amostras(self, carga):
        try:
            identificador, seq, inicio, pares = PR.ler_amostras(carga)
        except (PR.QuadroInvalido, ValueError):
            return self._recibo('', PR.CONTAGEM_NAO_CONFIAVEL, PR.BLOCO_MAL_FORMADO)
        if not self.configurado or identificador != self.identificador:
            return self._recibo(identificador, seq, PR.BLOCO_DE_OUTRO_ENSAIO)
        if seq < self.sequencia_esperada:
            return self._recibo(identificador, seq, PR.BLOCO_OK)   # repetido: ja guardado
        if seq != self.sequencia_esperada:
            self.contadores['descontinuidades_de_sequencia'] += 1
            return self._recibo(identificador, seq, PR.BLOCO_FORA_DE_SEQUENCIA)
        if inicio + len(pares) > self.n_amostras:
            return self._recibo(identificador, seq, PR.BLOCO_FORA_DA_MEMORIA)
        for k, (a, b) in enumerate(pares):
            self.memoria_a[inicio + k] = a
            self.memoria_b[inicio + k] = b
        self.sequencia_esperada += 1
        self.contadores['blocos_recebidos'] += 1
        return self._recibo(identificador, seq, PR.BLOCO_OK)

    def _recibo(self, identificador, seq, situacao):
        return PR.montar_quadro(PR.BLOCO_RECEBIDO, PR.carga_bloco_recebido(identificador, seq, situacao))

    # --- B-08, B-09, B-10 ------------------------------------------------------------
    def _executar(self, carga):
        identificador, n_blocos, n_amostras = PR.ler_executar(carga)
        vazio = {k: 0 for k in PR.CAMPOS_DO_CANAL}
        if not self.configurado or identificador != self.identificador:
            self.resultado_pendente = PR.carga_resultado(
                identificador, PR.RESULTADO_RECUSADO_SEM_CONFIGURACAO, 0, self.contadores, vazio, vazio)
            return self._enviar_resultado()
        completo = (n_amostras == self.n_amostras
                    and n_blocos == self.contadores['blocos_recebidos']
                    and None not in self.memoria_a and None not in self.memoria_b)
        if not completo:
            self.resultado_pendente = PR.carga_resultado(
                identificador, PR.RESULTADO_RECUSADO_AMOSTRAS_FALTANDO, 0, self.contadores, vazio, vazio)
            return self._enviar_resultado()

        detector_a = DetectorInteiro(self.parametros)
        detector_b = DetectorInteiro(self.parametros)
        situacao = PR.RESULTADO_CONCLUIDO
        try:
            for indice in range(self.n_amostras):          # indice comum aos dois canais
                detector_a.amostra(self.memoria_a[indice])
                detector_b.amostra(self.memoria_b[indice])
            canal_a, canal_b = detector_a.resultado(), detector_b.resultado()
        except EstouroDeLargura:
            situacao, canal_a, canal_b = PR.RESULTADO_RECUSADO_ESTOURO, vazio, vazio
        self.execucoes += 1
        self.resultado_pendente = PR.carga_resultado(
            identificador, situacao, self.n_amostras if situacao == PR.RESULTADO_CONCLUIDO else 0,
            self.contadores, canal_a, canal_b)
        return self._enviar_resultado()

    def _enviar_resultado(self):
        if self.resultado_pendente is None:
            return b''
        if self.perder_resultados > 0:
            self.perder_resultados -= 1
            return b''
        return PR.montar_quadro(PR.RESULTADO, self.resultado_pendente)

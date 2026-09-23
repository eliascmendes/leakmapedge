"""LEAKMAP - meios de transporte entre o computador e a placa.

TransporteMemoria  liga o computador ao modelo de referencia da placa, no
                   mesmo processo. E o que roda nos testes e no GitHub. Pode
                   corromper bytes de proposito, para testar B-06.
TransporteSerial   liga o computador a placa pela porta serial: a FPGA
                   (COM5, /dev/ttyUSB0) ou a placa simulada
                   (socket://127.0.0.1:5555, ver placa_simulada.py). O codigo
                   e o mesmo nos dois casos; so muda o endereco. Precisa do
                   pacote pyserial, carregado so quando usado.
TransporteSimulacaoDoVerilog
                   devolve ao computador os bytes que o Verilog da placa
                   respondeu no simulador (06_fpga/sim), conferindo que o
                   computador manda exatamente o que foi simulado.
"""
import time

import protocolo as PR


class TransporteMemoria:
    origem = 'referencia_python_da_placa'
    sincrono = True   # a resposta chega junto com o envio, ou nao chega

    def __init__(self, placa, corromper=None):
        """`corromper(quadro, n)` pode devolver o quadro alterado; n conta envios."""
        self.placa = placa
        self.corromper = corromper
        self.recebido = bytearray()
        self.envios = 0

    def enviar(self, dados):
        self.envios += 1
        if self.corromper:
            dados = self.corromper(bytes(dados), self.envios)
        self.recebido += self.placa.receber(dados)

    def receber(self, tempo_limite_s):
        dados, self.recebido = bytes(self.recebido), bytearray()
        return dados

    def fechar(self):
        pass


class TransporteSerial:
    """Porta serial ou endereco do pyserial (COM5, socket://127.0.0.1:5555).

    A origem comeca como `fpga` e so muda se a placa se identificar como
    simulada (identificar()). A FPGA nao responde a IDENTIFICAR.
    """
    origem = 'fpga'

    def __init__(self, porta, baud=115200):
        try:
            import serial  # pyserial
        except ImportError as e:
            raise RuntimeError('a porta serial precisa do pacote pyserial: '
                               'pip install pyserial') from e
        self.endereco = porta
        self.identidade = None
        self.porta = serial.serial_for_url(porta, baudrate=baud, timeout=0.01)
        self.porta.reset_input_buffer()

    def identificar(self, tempo_limite_s=0.5):
        """Pergunta quem responde. Resposta so vem da placa simulada."""
        self.enviar(PR.montar_quadro(PR.IDENTIFICAR, b''))
        leitor, fim = PR.LeitorDeQuadros(), time.monotonic() + tempo_limite_s
        while time.monotonic() < fim:
            for situacao, tipo, carga in leitor.alimentar(self.receber(fim - time.monotonic())):
                if situacao == 'ok' and tipo == PR.IDENTIDADE:
                    self.identidade = PR.ler_identidade(carga)
                    self.origem = 'placa_simulada'
                    return self.identidade
        return None

    def enviar(self, dados):
        self.porta.write(dados)
        self.porta.flush()

    def receber(self, tempo_limite_s):
        """Devolve assim que chegar algum byte, ou vazio no tempo limite.

        Quem junta os bytes em quadros e o LeitorDeQuadros do hospedeiro, entao
        nao ha por que esperar a linha ficar em silencio.
        """
        fim = time.monotonic() + max(0.0, tempo_limite_s)
        while True:
            dados = self.porta.read(max(1, self.porta.in_waiting))
            if dados:
                return dados + self.porta.read(self.porta.in_waiting)
            if time.monotonic() >= fim:
                return b''

    def fechar(self):
        self.porta.close()


class DivergenciaDaSimulacao(RuntimeError):
    pass


class TransporteSimulacaoDoVerilog:
    """Liga o computador a resposta gravada do Verilog no simulador.

    `gravacoes` e uma lista de conversas, na ordem em que o computador vai
    roda-las. Cada conversa e (entrada, saidas): os bytes que o simulador
    recebeu e, para cada byte que o Verilog devolveu, o par (byte,
    bytes_de_entrada_consumidos). Como a placa so responde depois de consumir
    a mensagem inteira, o byte devolvido pertence a resposta da mensagem que
    termina naquela posicao.

    Cada envio do computador tem de ser identico ao trecho seguinte da
    entrada simulada; se nao for, a conversa saiu do que foi simulado e o
    transporte para com DivergenciaDaSimulacao em vez de inventar resposta.
    """
    origem = 'simulacao_do_verilog'
    sincrono = True

    def __init__(self, gravacoes):
        self.gravacoes = list(gravacoes)
        self.atual = -1
        self._proxima()

    def _proxima(self):
        self.atual += 1
        self.posicao = 0
        self.entregues = 0
        self.recebido = bytearray()

    def enviar(self, dados):
        if self.atual < len(self.gravacoes) and self.posicao >= len(self.gravacoes[self.atual][0]):
            self._proxima()
        if self.atual >= len(self.gravacoes):
            raise DivergenciaDaSimulacao('o computador enviou mais do que foi simulado')
        entrada, saidas = self.gravacoes[self.atual]
        trecho = entrada[self.posicao:self.posicao + len(dados)]
        if bytes(trecho) != bytes(dados):
            raise DivergenciaDaSimulacao('conversa %d, byte %d: o computador enviou algo que nao '
                                         'foi simulado' % (self.atual, self.posicao))
        self.posicao += len(dados)
        while self.entregues < len(saidas) and saidas[self.entregues][1] <= self.posicao:
            self.recebido.append(saidas[self.entregues][0])
            self.entregues += 1

    def receber(self, tempo_limite_s):
        dados, self.recebido = bytes(self.recebido), bytearray()
        return dados

    def tudo_consumido(self):
        """Todas as conversas simuladas foram enviadas e todas as respostas entregues."""
        if not self.gravacoes:
            return True
        entrada, saidas = self.gravacoes[-1]
        return (self.atual == len(self.gravacoes) - 1 and self.posicao == len(entrada)
                and self.entregues == len(saidas))

    def fechar(self):
        pass

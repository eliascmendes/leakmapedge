"""LEAKMAP - meios de transporte entre o computador e a placa.

TransporteMemoria  liga o computador ao modelo de referencia da placa, no
                   mesmo processo. E o que roda nos testes e no GitHub. Pode
                   corromper bytes de proposito, para testar B-06.
TransporteSerial   liga o computador a FPGA de verdade pela porta serial.
                   Precisa do pacote pyserial, carregado so quando usado.
"""
import time


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
    origem = 'fpga'

    def __init__(self, porta, baud=115200):
        try:
            import serial  # pyserial
        except ImportError as e:
            raise RuntimeError('a porta serial precisa do pacote pyserial: '
                               'pip install pyserial') from e
        self.porta = serial.Serial(porta, baudrate=baud, timeout=0.05)
        self.porta.reset_input_buffer()

    def enviar(self, dados):
        self.porta.write(dados)
        self.porta.flush()

    def receber(self, tempo_limite_s):
        """Le o que chegar ate o tempo limite ou ate a linha ficar em silencio."""
        fim = time.monotonic() + tempo_limite_s
        dados = bytearray()
        while time.monotonic() < fim:
            parte = self.porta.read(4096)
            if parte:
                dados += parte
                fim = min(fim, time.monotonic() + 0.1)
            elif dados:
                break
        return bytes(dados)

    def fechar(self):
        self.porta.close()

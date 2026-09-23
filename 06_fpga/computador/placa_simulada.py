"""LEAKMAP - placa simulada: um programa que fala o protocolo serial da FPGA.

Fica do outro lado do fio no lugar da placa. O computador do cenario B
conversa com ela pelo mesmo TransporteSerial e pelo mesmo protocolo que vai
usar com a FPGA; so o endereco muda. Assim o receptor, o calculo de posicao e
o avaliador sao testados de ponta a ponta sem hardware, e a tela do modo FPGA
(B-12) sera testada do mesmo jeito. No dia basta trocar o endereco da placa
simulada pela porta da placa real.

Dois motores respondem as mensagens:
  referencia  o modelo Python da placa (placa_referencia.py), sem nada alem
              do Python;
  verilog     o proprio Verilog da placa (06_fpga/rtl) rodando no Icarus
              Verilog, ciclo a ciclo, atras da porta. Precisa do Icarus.

E o enlace pode ser piorado de proposito, para exercitar o receptor: bits
trocados nos dois sentidos, resultados perdidos, e o tempo de fio da serial.

A placa simulada responde a IDENTIFICAR (a FPGA nao responde), entao o
computador grava os resultados com a origem `placa_simulada` e nunca como
resultado de FPGA.

Uso, num terminal:
  python placa_simulada.py                       escuta em 127.0.0.1:5555
  python placa_simulada.py --motor verilog       responde o Verilog da placa
  python placa_simulada.py --ruido 1e-4 --perder-resultado 0.1 --semente 7
  python placa_simulada.py --serial COM7         num par de portas virtuais

E no outro:
  python executar_cenario_b.py --serial socket://127.0.0.1:5555
No dia da placa:
  python executar_cenario_b.py --serial COM5
"""
import argparse
import os
import queue
import random
import socket
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
FPGA = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import placa_referencia as PLACA  # noqa: E402
import protocolo as PR  # noqa: E402

ENDERECO_PADRAO = ('127.0.0.1', 5555)
RELOGIO_PADRAO_HZ = 100_000_000


# --- motores ---------------------------------------------------------------------------------

class MotorReferencia:
    descricao = 'modelo Python da placa (placa_referencia.py)'

    def __init__(self, capacidade_de_amostras=4096):
        self.placa = PLACA.PlacaReferencia(capacidade_de_amostras=capacidade_de_amostras)

    def receber(self, dados):
        """Bytes da resposta e ciclos de relogio gastos (None: o modelo nao conta ciclos)."""
        return self.placa.receber(dados), None

    def fechar(self):
        pass


class MotorVerilog:
    """O nucleo em Verilog rodando no Icarus, conversando por 06_fpga/sim/tb_interativo.v."""
    descricao = 'Verilog da placa (06_fpga/rtl) no Icarus Verilog'
    FONTES = ['rtl/leakmap_multiplicador.v', 'rtl/leakmap_detector.v', 'rtl/leakmap_nucleo.v',
              'sim/tb_interativo.v']

    def __init__(self, tempo_limite_s=30.0):
        sys.path.insert(0, os.path.join(FPGA, 'sim'))
        import rodar_simulacao as RS
        iverilog, vvp = RS.achar('iverilog'), RS.achar('vvp')
        if not iverilog or not vvp:
            raise RuntimeError('o motor verilog precisa do Icarus Verilog (iverilog e vvp)')
        RS.compilar(iverilog, self.FONTES[:-1], self.FONTES[-1], 'sim/tb_interativo.vvp')
        self.tempo_limite_s = tempo_limite_s
        self.processo = subprocess.Popen([vvp, '-n', 'sim/tb_interativo.vvp'], cwd=FPGA,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.linhas = queue.Queue()
        self.leitura = threading.Thread(target=self._ler, daemon=True)
        self.leitura.start()
        self.ciclo_livre = self._ate_pronto(1)[1]

    def _ler(self):
        for linha in iter(self.processo.stdout.readline, b''):
            self.linhas.put(linha.decode('ascii', errors='replace').strip())
        self.linhas.put(None)

    def _ate_pronto(self, n):
        """Le a saida do simulador ate o nucleo pedir o n-esimo byte novo."""
        saida, vistos, ciclo = bytearray(), 0, None
        while vistos < n:
            try:
                linha = self.linhas.get(timeout=self.tempo_limite_s)
            except queue.Empty:
                raise RuntimeError('o simulador do Verilog parou de responder')
            if linha is None:
                raise RuntimeError('o simulador do Verilog terminou')
            partes = linha.split()
            if partes and partes[0] == 'PRONTO':
                vistos += 1
                ciclo = int(partes[1])
            elif partes and partes[0] == 'BYTE':
                saida.append(int(partes[1], 16))
        return bytes(saida), ciclo

    def receber(self, dados):
        if not dados:
            return b'', 0
        self.processo.stdin.write(''.join('%02x\n' % b for b in dados).encode('ascii'))
        self.processo.stdin.flush()
        resposta, ciclo = self._ate_pronto(len(dados))
        # ciclos que o nucleo ficou ocupado alem de receber os bytes, um por ciclo
        gastos = max(0, ciclo - self.ciclo_livre - len(dados))
        self.ciclo_livre = ciclo
        return resposta, gastos

    def fechar(self):
        if self.processo.poll() is None:
            self.processo.stdin.close()
            try:
                self.processo.wait(5)
            except subprocess.TimeoutExpired:
                self.processo.kill()
                self.processo.wait()
        self.leitura.join(2)
        self.processo.stdout.close()


def criar_motor(nome, capacidade_de_amostras=4096):
    if nome == 'verilog':
        return MotorVerilog()
    return MotorReferencia(capacidade_de_amostras)


# --- a placa do outro lado do fio --------------------------------------------------------------

def quadros_de(dados):
    """Fatia uma resposta do motor, que sempre vem em quadros inteiros."""
    i, fatias = 0, []
    while i + 5 <= len(dados):
        total = 7 + int.from_bytes(dados[i + 3:i + 5], 'little')
        fatias.append((dados[i + 2], dados[i:i + total]))
        i += total
    return fatias


class PlacaSimulada:
    """Motor + enlace: identidade, ruido, perda de resultado e tempo de fio.

    `baud` > 0 atrasa cada envio e cada resposta pelo tempo que os bytes
    levariam no fio (10 bits por byte). `ruido` e a probabilidade de trocar um
    bit em cada byte, nos dois sentidos. `perder_resultado` e a probabilidade
    de uma mensagem RESULTADO nao chegar ao computador.
    """

    def __init__(self, motor, baud=0, ruido=0.0, perder_resultado=0.0, semente=None,
                 relogio_hz=RELOGIO_PADRAO_HZ, mostrar=None):
        self.motor = motor
        self.baud = baud
        self.ruido = ruido
        self.perder_resultado = perder_resultado
        self.relogio_hz = relogio_hz
        self.sorteio = random.Random(semente)
        self.mostrar = mostrar
        self.monitor = PR.LeitorDeQuadros()
        self.identidade = 'placa simulada LEAKMAP; motor: %s' % motor.descricao
        self.contagem = {'mensagens_recebidas': 0, 'quadros_com_crc_invalido_recebidos': 0,
                         'bits_trocados_na_ida': 0, 'bits_trocados_na_volta': 0,
                         'resultados_perdidos': 0, 'identificacoes': 0, 'ciclos_de_processamento': 0}

    def _trocar_bits(self, dados, chave):
        if not self.ruido:
            return dados
        dados = bytearray(dados)
        for k in range(len(dados)):
            if self.sorteio.random() < self.ruido:
                dados[k] ^= 1 << self.sorteio.randrange(8)
                self.contagem[chave] += 1
        return bytes(dados)

    def _fio(self, n_bytes):
        if self.baud:
            time.sleep(n_bytes * 10.0 / self.baud)

    def receber(self, dados):
        """Bytes que chegaram pelo fio; devolve os bytes que a placa manda de volta."""
        self._fio(len(dados))
        dados = self._trocar_bits(dados, 'bits_trocados_na_ida')

        identificar = 0
        for situacao, tipo, carga in self.monitor.alimentar(dados):
            if situacao != 'ok':
                self.contagem['quadros_com_crc_invalido_recebidos'] += 1
                self._registrar('<- quadro com CRC invalido (tipo lido 0x%02x)' % tipo)
                continue
            self.contagem['mensagens_recebidas'] += 1
            self._registrar('<- %s %s' % (PR.NOMES.get(tipo, '0x%02x' % tipo), self._resumo(tipo, carga)))
            if tipo == PR.IDENTIFICAR:
                identificar += 1

        # o motor recebe tudo, como a FPGA; IDENTIFICAR ele ignora, como tipo desconhecido
        resposta, ciclos = self.motor.receber(dados)
        if ciclos:
            self.contagem['ciclos_de_processamento'] += ciclos
            time.sleep(ciclos / self.relogio_hz)

        saida = bytearray()
        for tipo, quadro in quadros_de(resposta):
            if tipo == PR.RESULTADO and self.sorteio.random() < self.perder_resultado:
                self.contagem['resultados_perdidos'] += 1
                self._registrar('-> RESULTADO perdido no enlace, de proposito')
                continue
            self._registrar('-> %s %s' % (PR.NOMES.get(tipo, '0x%02x' % tipo), self._resumo(tipo, quadro[5:-2])))
            saida += quadro
        for _ in range(identificar):
            self.contagem['identificacoes'] += 1
            saida += PR.montar_quadro(PR.IDENTIDADE, PR.carga_identidade(self.identidade))
            self._registrar('-> IDENTIDADE %s' % self.identidade)

        saida = self._trocar_bits(bytes(saida), 'bits_trocados_na_volta')
        self._fio(len(saida))
        return saida

    @staticmethod
    def _resumo(tipo, carga):
        try:
            if tipo == PR.AMOSTRAS:
                ident, seq, inicio, pares = PR.ler_amostras(carga)
                return '%s bloco %d (%d pares)' % (ident, seq, len(pares))
            if tipo == PR.BLOCO_RECEBIDO:
                ident, seq, situacao = PR.ler_bloco_recebido(carga)
                return '%s bloco %d situacao %d' % (ident, seq, situacao)
            if tipo == PR.RESULTADO:
                r = PR.ler_resultado(carga)
                return '%s situacao %d, chegadas A %d e B %d' % (
                    r['id'], r['situacao'], r['canal_A']['indice_de_chegada'], r['canal_B']['indice_de_chegada'])
            if tipo in (PR.CONFIGURAR, PR.CONFIGURACAO_LIDA, PR.EXECUTAR, PR.PEDIR_RESULTADO,
                        PR.CONFIRMAR_RESULTADO):
                return PR.decodificar_id(carga[:PR.TAMANHO_DO_ID])
        except (PR.QuadroInvalido, ValueError, KeyError, IndexError):
            pass
        return '(%d bytes)' % len(carga)

    def _registrar(self, texto):
        if self.mostrar:
            self.mostrar(texto)

    def fechar(self):
        self.motor.fechar()


# --- o fio: TCP ou porta serial ----------------------------------------------------------------

class ServidorTCP:
    """Escuta um endereco TCP e atende um computador por vez.

    O computador conecta com TransporteSerial('socket://HOST:PORTA'). O estado
    da placa sobrevive entre conexoes, como numa placa que continua ligada.
    """

    def __init__(self, placa, endereco=ENDERECO_PADRAO):
        self.placa = placa
        self.soquete = socket.create_server(endereco)
        self.soquete.settimeout(0.2)
        self.parar = threading.Event()
        self.fio = None

    @property
    def url(self):
        host, porta = self.soquete.getsockname()[:2]
        return 'socket://%s:%d' % (host, porta)

    def atender(self):
        while not self.parar.is_set():
            try:
                conexao, _ = self.soquete.accept()
            except socket.timeout:
                continue
            with conexao:
                conexao.settimeout(0.2)
                conexao.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                while not self.parar.is_set():
                    try:
                        dados = conexao.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not dados:
                        break
                    resposta = self.placa.receber(dados)
                    if resposta:
                        conexao.sendall(resposta)
        self.soquete.close()

    def em_segundo_plano(self):
        self.fio = threading.Thread(target=self.atender, daemon=True)
        self.fio.start()
        return self

    def fechar(self):
        self.parar.set()
        if self.fio:
            self.fio.join(2)
        else:
            self.soquete.close()

    def __enter__(self):
        return self.em_segundo_plano()

    def __exit__(self, *erro):
        self.fechar()


def atender_serial(placa, porta, baud):
    """Atende numa porta serial de verdade, por exemplo um par virtual com0com."""
    import serial  # pyserial
    with serial.Serial(porta, baudrate=baud, timeout=0.01) as fio:
        while True:
            dados = fio.read(max(1, fio.in_waiting))
            if dados:
                dados += fio.read(fio.in_waiting)
                resposta = placa.receber(dados)
                if resposta:
                    fio.write(resposta)
                    fio.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--endereco', default='%s:%d' % ENDERECO_PADRAO,
                    help='HOST:PORTA onde escutar (padrao %s:%d)' % ENDERECO_PADRAO)
    ap.add_argument('--serial', help='atende numa porta serial em vez de TCP (ex.: COM7 de um par virtual)')
    ap.add_argument('--motor', choices=('referencia', 'verilog'), default='referencia')
    ap.add_argument('--baud', type=int, default=115200,
                    help='tempo de fio da serial simulada; 0 desliga (padrao 115200)')
    ap.add_argument('--ruido', type=float, default=0.0, help='probabilidade de trocar um bit em cada byte')
    ap.add_argument('--perder-resultado', type=float, default=0.0,
                    help='probabilidade de uma mensagem RESULTADO se perder')
    ap.add_argument('--semente', type=int, help='semente do sorteio de ruido e perdas')
    ap.add_argument('--relogio-hz', type=float, default=RELOGIO_PADRAO_HZ,
                    help='relogio da placa, para o tempo de processamento do motor verilog')
    ap.add_argument('--silencioso', action='store_true', help='nao mostra cada mensagem')
    args = ap.parse_args()

    def mostrar(texto):
        print(texto, flush=True)

    motor = criar_motor(args.motor)
    placa = PlacaSimulada(motor, baud=0 if args.serial else args.baud, ruido=args.ruido,
                          perder_resultado=args.perder_resultado, semente=args.semente,
                          relogio_hz=args.relogio_hz, mostrar=None if args.silencioso else mostrar)
    mostrar(placa.identidade)
    try:
        if args.serial:
            mostrar('atendendo na porta serial %s' % args.serial)
            atender_serial(placa, args.serial, args.baud)
        else:
            host, porta = args.endereco.rsplit(':', 1)
            servidor = ServidorTCP(placa, (host, int(porta)))
            mostrar('escutando em %s' % servidor.url)
            mostrar('no outro terminal: python executar_cenario_b.py --serial %s' % servidor.url)
            servidor.atender()
    except KeyboardInterrupt:
        pass
    finally:
        placa.fechar()
        mostrar('contagem: %r' % placa.contagem)


if __name__ == '__main__':
    main()

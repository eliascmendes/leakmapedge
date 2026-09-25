"""LEAKMAP - meios de transporte entre o computador e a placa.

TransporteMemoria  liga o computador ao modelo de referencia da placa, no
                   mesmo processo. E o que roda nos testes e no GitHub. Pode
                   corromper bytes de proposito, para testar B-06.
TransporteSerial   liga o computador a placa pela porta serial: a FPGA
                   (COM5, /dev/ttyUSB0) ou a placa simulada
                   (socket://127.0.0.1:5555, ver placa_simulada.py). O codigo
                   e o mesmo nos dois casos; so muda o endereco. Precisa do
                   pacote pyserial, carregado so quando usado.
TransporteJtag     liga o computador a FPGA pelo proprio cabo de gravacao
                   (USB-Blaster), pelo JTAG virtual, sem adaptador serial e
                   sem fio nos pinos. Usa o quartus_stp do Quartus Prime.
TransporteSimulacaoDoVerilog
                   devolve ao computador os bytes que o Verilog da placa
                   respondeu no simulador (06_fpga/sim), conferindo que o
                   computador manda exatamente o que foi simulado.
"""
import glob
import os
import queue
import shutil
import socket
import subprocess
import threading
import time

import protocolo as PR

AQUI = os.path.dirname(os.path.abspath(__file__))


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


# --- JTAG virtual pelo cabo USB-Blaster ------------------------------------------------------

class FalhaNaConexao(RuntimeError):
    pass


def achar_quartus_stp():
    """quartus_stp do Quartus Prime: variavel QUARTUS_ROOTDIR, PATH ou as pastas de instalacao usuais."""
    raiz = os.environ.get('QUARTUS_ROOTDIR')
    candidatos = []
    if raiz:
        candidatos += [os.path.join(raiz, 'bin64', 'quartus_stp.exe'), os.path.join(raiz, 'bin64', 'quartus_stp'),
                       os.path.join(raiz, 'bin', 'quartus_stp')]
    no_path = shutil.which('quartus_stp')
    if no_path:
        candidatos.append(no_path)
    for disco in ('C:', 'D:', 'E:', 'F:'):
        for pasta in ('altera', 'altera_lite', 'intelFPGA', 'intelFPGA_lite'):
            candidatos += sorted(glob.glob('%s/%s/*/quartus/bin64/quartus_stp.exe' % (disco, pasta)), reverse=True)
    candidatos += sorted(glob.glob('/opt/*/*/quartus/bin/quartus_stp'), reverse=True)
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    return None


def inverter_bits(valor, comprimento):
    return int(format(valor, '0%db' % comprimento)[::-1], 2)


class TransporteJtag:
    """A FPGA pelo cabo USB-Blaster, conversando com leakmap_ponte_jtag.v.

    Um processo do quartus_stp roda 06_fpga/computador/ponte_jtag.tcl e fica
    aberto durante toda a execucao, esperando numa porta TCP local; este
    transporte conecta nela, manda comandos IR e DR e monta e desmonta os
    bytes. (TCP e nao a entrada e saida padrao, porque o quartus_stp so
    entrega o que escreve na saida quando termina.) As mensagens do protocolo
    sao as mesmas da serial: so o fio muda.

    Ao abrir, le o registro de estado da ponte e confere a marca "LK". Assim
    uma placa sem o projeto gravado, ou com outro projeto, para aqui com uma
    mensagem clara, em vez de travar na primeira mensagem. A mesma leitura
    descobre a ordem em que o cabo desloca os bits.

    `comando` troca o quartus_stp por outro programa que fale as mesmas
    linhas pela entrada e saida padrao; os testes usam o testbench
    06_fpga/sim/tb_ponte_jtag.v.
    """
    origem = 'fpga'
    sincrono = False
    IR_ESCREVER, IR_LER, IR_ESTADO = 1, 2, 3
    LER_MAX = 64            # igual ao parametro LER_MAX da ponte
    MARCA = 0x4C4B          # "LK"
    ESPERA_ENTRE_LEITURAS_S = 0.002

    def __init__(self, comando=None, pasta=None, cabo=None, dispositivo=None, instancia=0,
                 origem=None, tempo_limite_s=60.0, script=None):
        if origem:
            self.origem = origem
        self.tempo_limite_s = tempo_limite_s
        self.invertido = False
        self.ir_atual = None
        self.soquete = None
        self.linhas = queue.Queue()
        self.leitura = None
        if comando is None:
            stp = achar_quartus_stp()
            if not stp:
                raise FalhaNaConexao('quartus_stp nao encontrado: instale o Quartus Prime Lite')
            self._abrir_quartus(stp, script or os.path.join(AQUI, 'ponte_jtag.tcl'), cabo, dispositivo,
                                instancia, pasta)
        else:
            self.processo = subprocess.Popen(comando, cwd=pasta, stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.saida_do_processo = []
            self._comecar_leitura(self.processo.stdout)
        try:
            resposta = self._resposta()
            if not resposta.startswith('PRONTO'):
                raise FalhaNaConexao(resposta)
            self.descricao = resposta[len('PRONTO '):]
            self.estado = self._conferir()
        except FalhaNaConexao:
            self.fechar()
            raise

    # --- conversa com o quartus_stp ----------------------------------------------------------
    def _abrir_quartus(self, stp, script, cabo, dispositivo, instancia, pasta):
        with socket.socket() as livre:
            livre.bind(('127.0.0.1', 0))
            porta = livre.getsockname()[1]
        self.processo = subprocess.Popen(
            [stp, '-t', script, cabo or '', dispositivo or '', str(instancia), str(porta)],
            cwd=pasta, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # a saida do quartus_stp so chega quando ele termina; e guardada para a mensagem de erro
        self.saida_do_processo = []
        self.drenagem = threading.Thread(target=self._drenar, daemon=True)
        self.drenagem.start()
        fim = time.monotonic() + self.tempo_limite_s
        while True:
            if self.processo.poll() is not None:
                self.drenagem.join(5)
                erro = next((l[3:] for l in self.saida_do_processo if l.startswith('@@ ERRO')),
                            'o quartus_stp terminou sem abrir a conexao')
                raise FalhaNaConexao(erro)
            try:
                self.soquete = socket.create_connection(('127.0.0.1', porta), timeout=1.0)
                break
            except OSError:
                if time.monotonic() > fim:
                    self.processo.kill()
                    raise FalhaNaConexao('o quartus_stp nao abriu a conexao em %.0f s' % self.tempo_limite_s)
                time.sleep(0.2)
        self.soquete.settimeout(None)
        self._comecar_leitura(self.soquete.makefile('rb'))

    def _drenar(self):
        for linha in iter(self.processo.stdout.readline, b''):
            self.saida_do_processo.append(linha.decode('utf-8', errors='replace').strip())

    def _comecar_leitura(self, fonte):
        self.fonte = fonte
        self.leitura = threading.Thread(target=self._ler, daemon=True)
        self.leitura.start()

    def _ler(self):
        try:
            for linha in iter(self.fonte.readline, b''):
                self.linhas.put(linha.decode('utf-8', errors='replace').strip())
        except (OSError, ValueError):
            pass
        self.linhas.put(None)

    def _resposta(self):
        """Proxima linha comecada por "@@ "; o resto e mensagem do proprio quartus_stp."""
        fim = time.monotonic() + self.tempo_limite_s
        while True:
            try:
                linha = self.linhas.get(timeout=max(0.1, fim - time.monotonic()))
            except queue.Empty:
                raise FalhaNaConexao('o quartus_stp parou de responder')
            if linha is None:
                raise FalhaNaConexao('o quartus_stp terminou')
            if linha.startswith('@@ '):
                resposta = linha[3:]
                if resposta.startswith('ERRO'):
                    raise FalhaNaConexao(resposta)
                return resposta
            if time.monotonic() > fim:
                raise FalhaNaConexao('o quartus_stp parou de responder')

    def _mandar(self, texto):
        dados = (texto + '\n').encode('ascii')
        try:
            if self.soquete:
                self.soquete.sendall(dados)
            else:
                self.processo.stdin.write(dados)
                self.processo.stdin.flush()
        except OSError as e:
            raise FalhaNaConexao('a conexao com o quartus_stp caiu: %s' % e)
        return self._resposta()

    def _ir(self, valor):
        if self.ir_atual != valor:
            self._mandar('IR %d' % valor)
            self.ir_atual = valor

    def _dr(self, comprimento, valor):
        """Desloca `comprimento` bits; o bit 0 de `valor` sai primeiro. Devolve o que voltou."""
        if self.invertido:
            valor = inverter_bits(valor, comprimento)
        digitos = (comprimento + 3) // 4
        resposta = self._mandar('DR %d %0*x' % (comprimento, digitos, valor))
        texto = resposta.split()[-1] if resposta.startswith('DR ') else ''
        if len(texto) == comprimento and set(texto) <= {'0', '1'}:
            capturado = int(texto, 2)
        else:
            capturado = int(texto[-digitos:] or '0', 16) & ((1 << comprimento) - 1)
        if self.invertido:
            capturado = inverter_bits(capturado, comprimento)
        return capturado

    def _conferir(self):
        self._ir(self.IR_ESTADO)
        valor = self._dr(32, 0)
        if valor >> 16 == self.MARCA:
            pass
        elif inverter_bits(valor, 32) >> 16 == self.MARCA:
            self.invertido = True
            valor = inverter_bits(valor, 32)
        else:
            raise FalhaNaConexao('a FPGA respondeu 0x%08x em vez da marca do LEAKMAP: o projeto da ponte JTAG '
                                 'esta gravado na placa?' % valor)
        return {'versao': (valor >> 8) & 0xFF, 'fila_de_entrada_transbordou': bool(valor & 1)}

    # --- a interface dos transportes ------------------------------------------------------------
    def enviar(self, dados):
        self._ir(self.IR_ESCREVER)
        dados = bytes(dados)
        for k in range(0, len(dados), self.LER_MAX):
            pedaco = dados[k:k + self.LER_MAX]
            self._dr(8 * len(pedaco), int.from_bytes(pedaco, 'little'))

    def receber(self, tempo_limite_s):
        """Devolve assim que a placa tiver algum byte, ou vazio no tempo limite."""
        fim = time.monotonic() + max(0.0, tempo_limite_s)
        self._ir(self.IR_LER)
        while True:
            valor = self._dr(8 + 8 * self.LER_MAX, 0)
            n = valor & 0xFF
            if n:
                return (valor >> 8).to_bytes(self.LER_MAX, 'little')[:n]
            if time.monotonic() >= fim:
                return b''
            time.sleep(self.ESPERA_ENTRE_LEITURAS_S)

    def fechar(self):
        if self.processo.poll() is None:
            try:
                if self.soquete:
                    self.soquete.sendall(b'FIM\n')
                else:
                    self.processo.stdin.write(b'FIM\n')
                    self.processo.stdin.flush()
                    self.processo.stdin.close()
                self.processo.wait(15)
            except (OSError, subprocess.TimeoutExpired):
                self.processo.kill()
                self.processo.wait()
        if self.soquete:
            self.soquete.close()
            self.fonte.close()
        if self.leitura:
            self.leitura.join(2)
        if getattr(self, 'drenagem', None):
            self.drenagem.join(2)
        if self.processo.stdin:
            self.processo.stdin.close()
        self.processo.stdout.close()

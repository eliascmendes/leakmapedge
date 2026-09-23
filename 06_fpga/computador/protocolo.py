"""LEAKMAP B-04, B-06, B-07 e B-10 - protocolo entre computador e FPGA.

Este modulo e o contrato de bytes entre o computador e a placa. O mesmo
formato esta descrito em 06_fpga/ESPECIFICACAO.md, que e o que o Verilog
implementa. Tudo em little-endian.

QUADRO
------
    A5 5A | tipo (1) | tamanho (2) | carga util (tamanho) | CRC-16 (2)

O CRC-16/CCITT-FALSE (polinomio 0x1021, valor inicial 0xFFFF, sem reflexao,
sem xor final) cobre tipo, tamanho e carga util. E o CRC mais simples de
fazer em hardware, um deslocamento com xor por bit. Vetor de conferencia:
"123456789" da 0x29B1.

A identidade do ensaio viaja em todas as mensagens, em 8 bytes ASCII
completados com zero, para que nenhuma etapa processe um ensaio no lugar
de outro (B-01).
"""
import struct

SINCRONISMO = b'\xA5\x5A'

# computador -> placa
CONFIGURAR = 0x01
AMOSTRAS = 0x02
EXECUTAR = 0x03
CONFIRMAR_RESULTADO = 0x04
PEDIR_RESULTADO = 0x05

# placa -> computador
CONFIGURACAO_LIDA = 0x81
BLOCO_RECEBIDO = 0x82
RESULTADO = 0x83

NOMES = {
    CONFIGURAR: 'CONFIGURAR', AMOSTRAS: 'AMOSTRAS', EXECUTAR: 'EXECUTAR',
    CONFIRMAR_RESULTADO: 'CONFIRMAR_RESULTADO', PEDIR_RESULTADO: 'PEDIR_RESULTADO',
    CONFIGURACAO_LIDA: 'CONFIGURACAO_LIDA', BLOCO_RECEBIDO: 'BLOCO_RECEBIDO',
    RESULTADO: 'RESULTADO',
}

# situacao do bloco recebido
BLOCO_OK = 0
BLOCO_CRC_INVALIDO = 1
BLOCO_FORA_DE_SEQUENCIA = 2
BLOCO_DE_OUTRO_ENSAIO = 3
BLOCO_FORA_DA_MEMORIA = 4
BLOCO_MAL_FORMADO = 5

# situacao do resultado
RESULTADO_CONCLUIDO = 0
RESULTADO_RECUSADO_AMOSTRAS_FALTANDO = 1
RESULTADO_RECUSADO_SEM_CONFIGURACAO = 2
RESULTADO_RECUSADO_ESTOURO = 3

PARES_POR_BLOCO = 32
CANAIS_A_B_INTERCALADOS = 0x03
TAMANHO_DO_ID = 8
CONTAGEM_NAO_CONFIAVEL = 0xFFFF   # sequencia de um bloco com CRC invalido


class QuadroInvalido(ValueError):
    pass


# --- CRC ---------------------------------------------------------------------

def crc16(dados, crc=0xFFFF):
    """CRC-16/CCITT-FALSE, bit a bit, do mesmo jeito que o hardware faz."""
    for byte in dados:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


# --- quadro ------------------------------------------------------------------

def montar_quadro(tipo, carga):
    cabecalho = struct.pack('<BH', tipo, len(carga))
    return SINCRONISMO + cabecalho + carga + struct.pack('<H', crc16(cabecalho + carga))


class LeitorDeQuadros:
    """Recebe bytes em qualquer fatiamento e devolve quadros inteiros.

    Quadro com CRC errado vira o evento ('crc_invalido', tipo_lido) em vez de
    sumir, para quem recebe poder contar a falha (B-06). O leitor se
    ressincroniza procurando o proximo A5 5A.
    """

    TAMANHO_MAXIMO = 1024

    def __init__(self):
        self.buffer = bytearray()

    def alimentar(self, dados):
        self.buffer.extend(dados)
        eventos = []
        while True:
            inicio = self.buffer.find(SINCRONISMO)
            if inicio < 0:
                del self.buffer[:max(0, len(self.buffer) - 1)]
                return eventos
            del self.buffer[:inicio]
            if len(self.buffer) < 5:
                return eventos
            tipo, tamanho = struct.unpack_from('<BH', self.buffer, 2)
            if tamanho > self.TAMANHO_MAXIMO:
                del self.buffer[:2]
                eventos.append(('crc_invalido', tipo, b''))
                continue
            total = 2 + 3 + tamanho + 2
            if len(self.buffer) < total:
                return eventos
            corpo = bytes(self.buffer[2:5 + tamanho])
            (crc_lido,) = struct.unpack_from('<H', self.buffer, 5 + tamanho)
            del self.buffer[:total]
            carga = corpo[3:]
            if crc16(corpo) != crc_lido:
                eventos.append(('crc_invalido', tipo, carga))
            else:
                eventos.append(('ok', tipo, carga))


# --- identidade do ensaio ----------------------------------------------------

def codificar_id(identificador):
    dado = identificador.encode('ascii')
    if len(dado) > TAMANHO_DO_ID:
        raise ValueError('identificador maior que %d bytes: %r' % (TAMANHO_DO_ID, identificador))
    return dado.ljust(TAMANHO_DO_ID, b'\x00')


def decodificar_id(dado):
    return dado.rstrip(b'\x00').decode('ascii', errors='replace')


# --- B-07: configuracao --------------------------------------------------------

_CONFIG = struct.Struct('<8sIBBBBBHHIIH')
CAMPOS_DE_CONFIGURACAO = ('coeficiente_do_filtro', 'fracao', 'desloca_energia', 'n_curta',
                          'n_guarda', 'n_longa', 'limiar_de_razao', 'k2_faixa_de_ruido',
                          'piso_em_ye', 'piso_energia_por_amostra', 'n_amostras')


def carga_configurar(identificador, parametros, n_amostras):
    valores = dict(parametros, n_amostras=n_amostras)
    return _CONFIG.pack(codificar_id(identificador), *[int(valores[c]) for c in CAMPOS_DE_CONFIGURACAO])


def ler_configurar(carga):
    if len(carga) != _CONFIG.size:
        raise QuadroInvalido('CONFIGURAR com %d bytes, esperado %d' % (len(carga), _CONFIG.size))
    campos = _CONFIG.unpack(carga)
    return decodificar_id(campos[0]), dict(zip(CAMPOS_DE_CONFIGURACAO, campos[1:]))


_CONTADORES = struct.Struct('<HHHH')
CAMPOS_DE_CONTADORES = ('falhas_de_crc', 'descontinuidades_de_sequencia',
                        'eventos_de_buffer', 'blocos_recebidos')


def carga_configuracao_lida(identificador, parametros, n_amostras, contadores):
    return (carga_configurar(identificador, parametros, n_amostras)
            + _CONTADORES.pack(*[int(contadores[c]) for c in CAMPOS_DE_CONTADORES]))


def ler_configuracao_lida(carga):
    if len(carga) != _CONFIG.size + _CONTADORES.size:
        raise QuadroInvalido('CONFIGURACAO_LIDA com tamanho %d' % len(carga))
    identificador, parametros = ler_configurar(carga[:_CONFIG.size])
    contadores = dict(zip(CAMPOS_DE_CONTADORES, _CONTADORES.unpack(carga[_CONFIG.size:])))
    return identificador, parametros, contadores


# --- B-04: blocos de amostras ------------------------------------------------------

_BLOCO = struct.Struct('<8sHHBB')


def carga_amostras(identificador, sequencia, indice_inicial, pares):
    """Bloco com indice da primeira amostra, sequencia e canais explicitos.

    `pares` e uma lista de (codigo_A, codigo_B) da mesma amostra, A primeiro.
    A identidade do canal nao depende da ordem de chegada: esta no campo
    `canais` e na posicao dentro do par.
    """
    if not 0 < len(pares) <= PARES_POR_BLOCO:
        raise ValueError('bloco precisa ter de 1 a %d pares' % PARES_POR_BLOCO)
    corpo = b''.join(struct.pack('<HH', int(a), int(b)) for a, b in pares)
    return _BLOCO.pack(codificar_id(identificador), sequencia, indice_inicial,
                       len(pares), CANAIS_A_B_INTERCALADOS) + corpo


def ler_amostras(carga):
    if len(carga) < _BLOCO.size:
        raise QuadroInvalido('bloco de amostras curto demais')
    ident, seq, inicio, n, canais = _BLOCO.unpack_from(carga)
    if canais != CANAIS_A_B_INTERCALADOS:
        raise QuadroInvalido('campo de canais desconhecido: 0x%02x' % canais)
    if len(carga) != _BLOCO.size + 4 * n or not 0 < n <= PARES_POR_BLOCO:
        raise QuadroInvalido('bloco com %d pares e %d bytes' % (n, len(carga)))
    pares = [struct.unpack_from('<HH', carga, _BLOCO.size + 4 * k) for k in range(n)]
    return decodificar_id(ident), seq, inicio, pares


def blocos_do_ensaio(identificador, codigos_a, codigos_b):
    """Divide o ensaio em blocos numerados a partir de zero."""
    if len(codigos_a) != len(codigos_b):
        raise ValueError('canais com tamanhos diferentes')
    blocos = []
    for seq, inicio in enumerate(range(0, len(codigos_a), PARES_POR_BLOCO)):
        pares = list(zip(codigos_a[inicio:inicio + PARES_POR_BLOCO],
                         codigos_b[inicio:inicio + PARES_POR_BLOCO]))
        blocos.append(montar_quadro(AMOSTRAS, carga_amostras(identificador, seq, inicio, pares)))
    return blocos


_RECIBO = struct.Struct('<8sHB')


def carga_bloco_recebido(identificador, sequencia, situacao):
    return _RECIBO.pack(codificar_id(identificador), sequencia, situacao)


def ler_bloco_recebido(carga):
    ident, seq, situacao = _RECIBO.unpack(carga)
    return decodificar_id(ident), seq, situacao


# --- execucao ----------------------------------------------------------------------------

_EXECUTAR = struct.Struct('<8sHH')


def carga_executar(identificador, n_blocos, n_amostras):
    return _EXECUTAR.pack(codificar_id(identificador), n_blocos, n_amostras)


def ler_executar(carga):
    ident, n_blocos, n_amostras = _EXECUTAR.unpack(carga)
    return decodificar_id(ident), n_blocos, n_amostras


def carga_so_id(identificador):
    return codificar_id(identificador)


# --- B-10: resultado ---------------------------------------------------------------------

_RESULTADO = struct.Struct('<8sBHHHH')
_CANAL = struct.Struct('<BHHHQQI')
CAMPOS_DO_CANAL = ('bandeiras', 'indice_de_cruzamento', 'indice_de_chegada',
                   'n_oportunidades_de_decisao', 's_curta_no_cruzamento',
                   's_longa_no_cruzamento', 'maior_salto_q')
BANDEIRA_DETECTADO = 0x01
BANDEIRA_RETROCESSO_TRUNCADO = 0x02


def carga_resultado(identificador, situacao, n_reproduzidas, contadores, canal_a, canal_b):
    cab = _RESULTADO.pack(codificar_id(identificador), situacao, n_reproduzidas,
                          int(contadores['falhas_de_crc']),
                          int(contadores['descontinuidades_de_sequencia']),
                          int(contadores['eventos_de_buffer']))
    corpo = b''.join(_CANAL.pack(*[int(c[k]) for k in CAMPOS_DO_CANAL]) for c in (canal_a, canal_b))
    return cab + corpo


def ler_resultado(carga):
    if len(carga) != _RESULTADO.size + 2 * _CANAL.size:
        raise QuadroInvalido('RESULTADO com tamanho %d' % len(carga))
    ident, situacao, n_rep, crc, desc, buf = _RESULTADO.unpack_from(carga)
    canais = []
    for k in range(2):
        valores = _CANAL.unpack_from(carga, _RESULTADO.size + k * _CANAL.size)
        canal = dict(zip(CAMPOS_DO_CANAL, valores))
        canal['detectado'] = bool(canal['bandeiras'] & BANDEIRA_DETECTADO)
        canal['retrocesso_truncado'] = bool(canal['bandeiras'] & BANDEIRA_RETROCESSO_TRUNCADO)
        canais.append(canal)
    return {
        'id': decodificar_id(ident),
        'situacao': situacao,
        'n_amostras_reproduzidas': n_rep,
        'contadores': {'falhas_de_crc': crc, 'descontinuidades_de_sequencia': desc,
                       'eventos_de_buffer': buf},
        'canal_A': canais[0],
        'canal_B': canais[1],
    }

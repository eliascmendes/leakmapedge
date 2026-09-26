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
# so a placa simulada responde; a FPGA ignora, como todo tipo que nao conhece
IDENTIFICAR = 0x06
EXECUTAR_TEMPO_REAL = 0x07
PEDIR_TEMPOS = 0x08
PEDIR_SAUDE = 0x09

# placa -> computador
CONFIGURACAO_LIDA = 0x81
BLOCO_RECEBIDO = 0x82
RESULTADO = 0x83
IDENTIDADE = 0x86
TEMPOS = 0x87
SAUDE = 0x88

NOMES = {
    CONFIGURAR: 'CONFIGURAR', AMOSTRAS: 'AMOSTRAS', EXECUTAR: 'EXECUTAR',
    CONFIRMAR_RESULTADO: 'CONFIRMAR_RESULTADO', PEDIR_RESULTADO: 'PEDIR_RESULTADO',
    CONFIGURACAO_LIDA: 'CONFIGURACAO_LIDA', BLOCO_RECEBIDO: 'BLOCO_RECEBIDO',
    RESULTADO: 'RESULTADO', IDENTIFICAR: 'IDENTIFICAR', IDENTIDADE: 'IDENTIDADE',
    EXECUTAR_TEMPO_REAL: 'EXECUTAR_TEMPO_REAL', PEDIR_TEMPOS: 'PEDIR_TEMPOS', TEMPOS: 'TEMPOS',
    PEDIR_SAUDE: 'PEDIR_SAUDE', SAUDE: 'SAUDE',
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
                # descarta o cabecalho inteiro, como faz um circuito que ja o consumiu
                del self.buffer[:5]
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


# --- execucao em tempo real: a mesma execucao, uma amostra a cada `periodo` ciclos ---------
_EXECUTAR_TR = struct.Struct('<8sHHI')


def carga_executar_tempo_real(identificador, n_blocos, n_amostras, periodo_ciclos):
    return _EXECUTAR_TR.pack(codificar_id(identificador), n_blocos, n_amostras, periodo_ciclos)


def ler_executar_tempo_real(carga):
    ident, n_blocos, n_amostras, periodo = _EXECUTAR_TR.unpack(carga)
    return decodificar_id(ident), n_blocos, n_amostras, periodo


# --- autoteste dos canais: limites que o computador manda em PEDIR_SAUDE ------------------
#
# id (8), limite_congelado u16 (amostras seguidas com o mesmo codigo; 0 = nao
# confere), codigo_minimo u16 e codigo_maximo u16 (faixa aceita), limite_salto
# u16 (maior variacao aceita entre duas amostras, em codigos; 0 = nao confere).
_PEDIR_SAUDE = struct.Struct('<8sHHHH')
CAMPOS_DOS_LIMITES = ('limite_congelado', 'codigo_minimo', 'codigo_maximo', 'limite_salto')
LIMITES_ABERTOS = {'limite_congelado': 0, 'codigo_minimo': 0, 'codigo_maximo': 0xFFFF, 'limite_salto': 0}


def carga_pedir_saude(identificador, limites):
    return _PEDIR_SAUDE.pack(codificar_id(identificador), *[int(limites[c]) for c in CAMPOS_DOS_LIMITES])


def ler_pedir_saude(carga):
    ident, *valores = _PEDIR_SAUDE.unpack(carga)
    return decodificar_id(ident), dict(zip(CAMPOS_DOS_LIMITES, valores))


# tamanho exato da carga util de cada mensagem que a placa recebe;
# AMOSTRAS e conferida a parte, porque o tamanho depende de n_pares
TAMANHO_EXATO = {CONFIGURAR: _CONFIG.size, EXECUTAR: _EXECUTAR.size,
                 CONFIRMAR_RESULTADO: TAMANHO_DO_ID, PEDIR_RESULTADO: TAMANHO_DO_ID,
                 EXECUTAR_TEMPO_REAL: _EXECUTAR_TR.size, PEDIR_TEMPOS: TAMANHO_DO_ID,
                 PEDIR_SAUDE: _PEDIR_SAUDE.size}


# --- TEMPOS: ciclos de relogio da ultima execucao, contados pelo circuito ----------------
#
# id (8), situacao u8 (a do RESULTADO; 0xFF = nenhuma execucao ainda), modo u8
# (0 lote, 1 tempo real), frequencia_hz u32, periodo_ciclos u32, n_amostras u16,
# e a parte medida, que so o circuito sabe: contado u8 (1 = contado pelo
# circuito), ciclos_execucao u32, ciclos por amostra min u16 e max u16,
# amostras_atrasadas u16, e por canal (A, depois B) ciclo_declaracao u32 e
# latencia_declaracao u16 (0xFFFFFFFF / 0xFFFF = o canal nao declarou).
_TEMPOS = struct.Struct('<8sBBIIHBIHHHIHIH')
CAMPOS_MEDIDOS_DOS_TEMPOS = (20, _TEMPOS.size)   # bytes da carga que o modelo nao conhece
TEMPOS_SEM_EXECUCAO = 0xFF
NAO_DECLAROU = 0xFFFFFFFF
MODO_LOTE, MODO_TEMPO_REAL = 0, 1


def carga_tempos(identificador, situacao, modo, frequencia_hz, periodo_ciclos, n_amostras, medidos=None):
    """Carga de TEMPOS. `medidos` = None: o modelo nao tem relogio e zera a parte medida."""
    m = medidos or {}
    return _TEMPOS.pack(codificar_id(identificador), situacao, modo, frequencia_hz, periodo_ciclos,
                        n_amostras, 1 if medidos else 0, m.get('ciclos_execucao', 0),
                        m.get('ciclos_por_amostra_min', 0), m.get('ciclos_por_amostra_max', 0),
                        m.get('amostras_atrasadas', 0),
                        m.get('ciclo_declaracao_A', 0), m.get('latencia_declaracao_A', 0),
                        m.get('ciclo_declaracao_B', 0), m.get('latencia_declaracao_B', 0))


def ler_tempos(carga):
    if len(carga) != _TEMPOS.size:
        raise QuadroInvalido('TEMPOS com tamanho %d' % len(carga))
    (ident, situacao, modo, frequencia, periodo, n_amostras, contado, ciclos, amostra_min,
     amostra_max, atrasadas, decl_a, lat_a, decl_b, lat_b) = _TEMPOS.unpack(carga)
    tempos = {
        'id': decodificar_id(ident), 'situacao': situacao, 'modo': modo,
        'frequencia_hz': frequencia, 'periodo_ciclos': periodo, 'n_amostras': n_amostras,
        'contado_pelo_circuito': bool(contado), 'ciclos_execucao': ciclos,
        'ciclos_por_amostra_min': amostra_min, 'ciclos_por_amostra_max': amostra_max,
        'amostras_atrasadas': atrasadas,
    }
    for canal, decl, lat in (('A', decl_a, lat_a), ('B', decl_b, lat_b)):
        declarou = decl != NAO_DECLAROU
        tempos['ciclo_declaracao_' + canal] = decl if declarou else None
        tempos['latencia_declaracao_' + canal] = lat if declarou else None
    return tempos


# --- SAUDE: autoteste dos dois canais na ultima execucao -----------------------------------
#
# Enquanto executa, a placa acompanha cada canal amostra a amostra: menor e
# maior codigo, maior sequencia de codigos iguais, maior variacao entre duas
# amostras seguidas e amostras no extremo da palavra (0 ou 65 535). Ao receber
# PEDIR_SAUDE, compara com os limites pedidos e devolve:
#
# id (8, o da ultima execucao), situacao u8 (a do RESULTADO; 0xFF = nenhuma
# execucao), os quatro limites (u16, como vieram), e por canal (A, depois B):
# bandeiras u8, codigo_min u16, codigo_max u16, maior_sequencia u16,
# maior_variacao u16, amostras_no_extremo u16. Sem execucao concluida, os
# canais vem zerados.
_SAUDE = struct.Struct('<8sBHHHH')
_SAUDE_CANAL = struct.Struct('<BHHHHH')
CAMPOS_DA_SAUDE = ('bandeiras', 'codigo_min', 'codigo_max', 'maior_sequencia', 'maior_variacao',
                   'amostras_no_extremo')
SAUDE_CONGELADO = 0x01        # maior_sequencia >= limite_congelado (limite diferente de 0)
SAUDE_SATURADO = 0x02         # alguma amostra em 0 ou 65 535
SAUDE_FORA_DA_FAIXA = 0x04    # codigo_min < codigo_minimo ou codigo_max > codigo_maximo
SAUDE_SALTO = 0x08            # maior_variacao > limite_salto (limite diferente de 0)
NOMES_DA_SAUDE = ((SAUDE_CONGELADO, 'congelado'), (SAUDE_SATURADO, 'saturado'),
                  (SAUDE_FORA_DA_FAIXA, 'fora_da_faixa'), (SAUDE_SALTO, 'salto'))
SAUDE_SEM_EXECUCAO = 0xFF


def bandeiras_de_saude(canal, limites):
    """As bandeiras do canal, a partir das estatisticas e dos limites; igual ao Verilog."""
    b = 0
    if limites['limite_congelado'] and canal['maior_sequencia'] >= limites['limite_congelado']:
        b |= SAUDE_CONGELADO
    if canal['amostras_no_extremo']:
        b |= SAUDE_SATURADO
    if canal['codigo_min'] < limites['codigo_minimo'] or canal['codigo_max'] > limites['codigo_maximo']:
        b |= SAUDE_FORA_DA_FAIXA
    if limites['limite_salto'] and canal['maior_variacao'] > limites['limite_salto']:
        b |= SAUDE_SALTO
    return b


def carga_saude(identificador, situacao, limites, canal_a=None, canal_b=None):
    """Carga de SAUDE. `canal_a`/`canal_b` = estatisticas sem as bandeiras; None zera o canal."""
    corpo = b''
    for canal in (canal_a, canal_b):
        if canal is None:
            corpo += _SAUDE_CANAL.pack(0, 0, 0, 0, 0, 0)
        else:
            corpo += _SAUDE_CANAL.pack(bandeiras_de_saude(canal, limites),
                                       *[int(canal[c]) for c in CAMPOS_DA_SAUDE[1:]])
    return _SAUDE.pack(codificar_id(identificador), situacao,
                       *[int(limites[c]) for c in CAMPOS_DOS_LIMITES]) + corpo


def ler_saude(carga):
    if len(carga) != _SAUDE.size + 2 * _SAUDE_CANAL.size:
        raise QuadroInvalido('SAUDE com tamanho %d' % len(carga))
    ident, situacao, *limites = _SAUDE.unpack_from(carga)
    saude = {'id': decodificar_id(ident), 'situacao': situacao,
             'limites': dict(zip(CAMPOS_DOS_LIMITES, limites))}
    for k, nome in enumerate(('canal_A', 'canal_B')):
        canal = dict(zip(CAMPOS_DA_SAUDE, _SAUDE_CANAL.unpack_from(carga, _SAUDE.size + k * _SAUDE_CANAL.size)))
        canal['falhas'] = [n for bit, n in NOMES_DA_SAUDE if canal['bandeiras'] & bit]
        saude[nome] = canal
    return saude


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


# --- identificacao da placa simulada -------------------------------------------------------
#
# A FPGA nao responde a IDENTIFICAR: o Verilog ignora tipo que nao conhece. So
# a placa simulada responde, com IDENTIDADE e um texto curto. Assim o computador
# nunca grava resultado de placa simulada como resultado de FPGA.

TAMANHO_MAXIMO_DA_IDENTIDADE = 96


def carga_identidade(texto):
    return texto.encode('utf-8')[:TAMANHO_MAXIMO_DA_IDENTIDADE]


def ler_identidade(carga):
    return bytes(carga).decode('utf-8', errors='replace')

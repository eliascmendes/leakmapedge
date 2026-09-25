"""LEAKMAP - roteiro do testbench completo da placa pelo JTAG (06_fpga/sim/tb_leakmap_jtag.v).

Roda o computador do cenario B contra o modelo Python da placa e grava, mensagem
a mensagem, o que o computador mandou, o que a placa respondeu e se ficou um
resultado esperando confirmacao (o LED led_resultado). O testbench manda as
mesmas mensagens pelo JTAG ao Verilog e exige as mesmas respostas, byte a byte.

Todos os casos rodam numa placa so, na ordem, como no testbench (sem reinicio
entre eles):
  - ensaios da matriz: evento em cada nivel de transmissor, com c casada e
    desviada, e o ensaio mais longo, sem evento (500 amostras);
  - B-06: bloco corrompido no caminho, recusado pelo CRC e reenviado;
  - B-07: o mesmo ensaio duas vezes seguidas;
  - B-08: canal B igual ao A atrasado 40 amostras;
  - protocolo: IDENTIFICAR sem resposta (so a placa simulada responde) e
    resultado pedido de novo, antes e depois da confirmacao.

Formato (um byte hexadecimal por linha, para $readmemh):
  n_casos (2 bytes, little-endian)
  por caso:   tamanho do nome (1), nome em ASCII, n_mensagens (2)
  por mensagem: n_enviados (2), bytes enviados, n_respondidos (2), bytes
                respondidos, bandeiras (1; bit 0 = resultado esperando confirmacao)

O arquivo e completado com zeros ate TAMANHO bytes, o tamanho da memoria do
testbench, para o $readmemh nao reclamar de arquivo curto.

Grava 06_fpga/sim/questa/roteiro_jtag.hex, que vai para o git: o testbench roda
no Questa sem Python. Rodar de novo da o mesmo arquivo, byte a byte.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import hospedeiro as HO  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import protocolo as PR  # noqa: E402
import selo as SE  # noqa: E402
import transporte as TR  # noqa: E402

SAIDA = os.path.join(RAIZ, '06_fpga', 'sim', 'questa', 'roteiro_jtag.hex')
TAMANHO = 16384   # bytes; igual a TAM_ROTEIRO do testbench, que le o arquivo inteiro
ENSAIOS = ['MX-001', 'MX-013', 'MX-021', 'MX-030', 'MX-039']


class TransporteRoteiro(TR.TransporteMemoria):
    """Grava cada envio do computador com a resposta da placa."""

    def __init__(self, placa, corromper=None):
        super().__init__(placa, corromper)
        self.mensagens = []

    def enviar(self, dados):
        self.envios += 1
        if self.corromper:
            dados = self.corromper(bytes(dados), self.envios)
        resposta = self.placa.receber(dados)
        self.mensagens.append((bytes(dados), resposta, self.placa.resultado_pendente is not None))
        self.recebido += resposta


def main(saida=SAIDA):
    pacote = json.load(open(SE.PACOTE, encoding='utf-8'))
    selos = json.load(open(SE.SELOS, encoding='utf-8'))
    cal = D.calibracao_padrao()
    placa = PLACA.PlacaReferencia()
    casos = []

    def execucao(identificador):
        ensaio = SE.selecionar(identificador, pacote, selos)
        p = PP.preparar_ensaio(ensaio, pacote['escala'], cal)
        return (identificador, p['conversao']['canal_A']['codigos'],
                p['conversao']['canal_B']['codigos'], p['parametros'])

    def pelo_computador(nome, execucoes, corromper=None):
        transporte = TransporteRoteiro(placa, corromper)
        host = HO.Hospedeiro(transporte)
        for e in execucoes:
            rodada = host.rodar(*e)
            if rodada['resultado'] is None:
                raise SystemExit('o caso %s ficou sem resultado no modelo' % nome)
        casos.append((nome, transporte.mensagens))

    def quadros_soltos(nome, quadros):
        mensagens = []
        for q in quadros:
            mensagens.append((q, placa.receber(q), placa.resultado_pendente is not None))
        casos.append((nome, mensagens))

    for ident in ENSAIOS:
        pelo_computador(ident, [execucao(ident)])

    def corromper_terceiro(quadro, n):
        if n == 3:                           # o segundo bloco de amostras
            quadro = bytearray(quadro)
            quadro[20] ^= 0x01
        return bytes(quadro)
    pelo_computador('B-06 bloco corrompido e reenviado (MX-005)', [execucao('MX-005')], corromper_terceiro)

    pelo_computador('B-07 mesmo ensaio duas vezes (MX-005)', [execucao('MX-005'), execucao('MX-005')])

    base = execucao('MX-005')
    atrasado = [base[1][0]] * 40 + list(base[1][:-40])
    pelo_computador('B-08 canal B atrasado 40 amostras', [('ATRASO40', base[1], atrasado, base[3])])

    ident, ca, cb, par = execucao('MX-001')
    blocos = PR.blocos_do_ensaio(ident, ca, cb)
    pedir = PR.montar_quadro(PR.PEDIR_RESULTADO, PR.carga_so_id(ident))
    quadros_soltos('protocolo: IDENTIFICAR sem resposta e resultado pedido de novo', [
        PR.montar_quadro(PR.IDENTIFICAR, b''),
        PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(ident, par, len(ca))),
    ] + blocos + [
        PR.montar_quadro(PR.EXECUTAR, PR.carga_executar(ident, len(blocos), len(ca))),
        pedir, pedir,
        PR.montar_quadro(PR.CONFIRMAR_RESULTADO, PR.carga_so_id(ident)),
        pedir,
    ])

    dados = bytearray(len(casos).to_bytes(2, 'little'))
    total = 0
    for nome, mensagens in casos:
        rotulo = nome.encode('ascii')
        dados += bytes([len(rotulo)]) + rotulo + len(mensagens).to_bytes(2, 'little')
        for enviado, resposta, pendente in mensagens:
            dados += len(enviado).to_bytes(2, 'little') + enviado
            dados += len(resposta).to_bytes(2, 'little') + resposta
            dados += bytes([1 if pendente else 0])
            total += 1
    if len(dados) > TAMANHO:
        raise SystemExit('roteiro com %d bytes passa de %d: aumente TAMANHO aqui e TAM_ROTEIRO no testbench'
                         % (len(dados), TAMANHO))
    usados = len(dados)
    dados += bytes(TAMANHO - usados)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with open(saida, 'w', newline='\n') as f:
        f.write(''.join('%02x\n' % b for b in dados))
    print('roteiro: %d casos, %d mensagens, %d bytes em %s'
          % (len(casos), total, usados, os.path.relpath(saida, RAIZ)))


if __name__ == '__main__':
    main(*sys.argv[1:])

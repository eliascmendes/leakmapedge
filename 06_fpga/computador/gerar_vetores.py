"""LEAKMAP - vetores de teste do Verilog, gravados a partir do modelo da placa.

Para cada caso, grava o fluxo de bytes que o computador envia a placa e o
fluxo que o modelo de referencia (placa_referencia.py) devolve. O testbench
em 06_fpga/sim alimenta o Verilog com o primeiro e exige, byte a byte, o
segundo. E o criterio de aceitacao 2 de 06_fpga/ESPECIFICACAO.md.

Casos:
  - os 45 ensaios da matriz, com a conversa completa do hospedeiro;
  - sinais sinteticos que forcam retrocesso longo, retrocesso truncado e
    atraso conhecido entre canais;
  - casos de protocolo: bloco corrompido, lacuna de sequencia, mensagens mal
    formadas, execucao sem configuracao, ensaio acima da capacidade, pedido
    de resultado repetido, mensagem de tipo desconhecido, o mesmo ensaio duas
    vezes seguidas e tres ensaios seguidos na mesma placa.

casos.json guarda, para cada caso, os ensaios que ele roda na ordem, que e
o que 06_fpga/sim/prova_cenario_b.py usa para conferir os criterios.

Grava 06_fpga/vetores/ (gerado, fora do git) com um byte hexadecimal por linha.
"""
import json
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import detector_ponto_fixo as PF  # noqa: E402
import hospedeiro as HO  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import protocolo as PR  # noqa: E402
import selo as SE  # noqa: E402
import transporte as TR  # noqa: E402

SAIDA = os.path.join(RAIZ, '06_fpga', 'vetores')
CAPACIDADE = 4096


class TransporteGravado(TR.TransporteMemoria):
    """Grava tudo o que entra e sai da placa, depois da corrupcao do enlace."""

    def __init__(self, placa, corromper=None):
        super().__init__(placa, corromper)
        self.entrada = bytearray()
        self.saida = bytearray()

    def enviar(self, dados):
        self.envios += 1
        if self.corromper:
            dados = self.corromper(bytes(dados), self.envios)
        self.entrada += dados
        resposta = self.placa.receber(dados)
        self.saida += resposta
        self.recebido += resposta


def conversa(execucoes, corromper=None):
    """Roda uma ou mais execucoes do hospedeiro na mesma placa e grava os bytes."""
    placa = PLACA.PlacaReferencia(capacidade_de_amostras=CAPACIDADE)
    transporte = TransporteGravado(placa, corromper)
    host = HO.Hospedeiro(transporte)
    for identificador, codigos_a, codigos_b, parametros in execucoes:
        host.rodar(identificador, codigos_a, codigos_b, parametros)
    return bytes(transporte.entrada), bytes(transporte.saida)


def fluxo_bruto(quadros):
    """Envia quadros prontos, um a um, e grava as respostas."""
    placa = PLACA.PlacaReferencia(capacidade_de_amostras=CAPACIDADE)
    entrada, saida = bytearray(), bytearray()
    for q in quadros:
        entrada += q
        saida += placa.receber(q)
    return bytes(entrada), bytes(saida)


def gravar(nome, entrada, saida, descricao, indice, ensaios=()):
    os.makedirs(SAIDA, exist_ok=True)
    for sufixo, dados in (('entrada', entrada), ('saida', saida)):
        with open(os.path.join(SAIDA, '%s.%s.hex' % (nome, sufixo)), 'w') as f:
            f.write(''.join('%02x\n' % b for b in dados))
    indice[nome] = {'descricao': descricao, 'ensaios': list(ensaios),
                    'bytes_de_entrada': len(entrada), 'bytes_de_saida_esperados': len(saida)}


def main():
    pacote = json.load(open(SE.PACOTE, encoding='utf-8'))
    selos = json.load(open(SE.SELOS, encoding='utf-8'))
    escala = pacote['escala']
    cal = D.calibracao_padrao()
    indice = {}

    def execucao(identificador):
        ensaio = SE.selecionar(identificador, pacote, selos)
        p = PP.preparar_ensaio(ensaio, escala, cal)
        return (identificador, p['conversao']['canal_A']['codigos'],
                p['conversao']['canal_B']['codigos'], p['parametros'])

    # --- os 45 ensaios da matriz ---------------------------------------------------
    for ensaio in pacote['ensaios']:
        e, s = conversa([execucao(ensaio['id'])])
        gravar('ensaio_%s' % ensaio['id'], e, s, 'conversa completa do ensaio %s' % ensaio['id'], indice,
               [ensaio['id']])

    # --- sinais sinteticos --------------------------------------------------------------
    params = PF.parametros_inteiros(cal, 4.0130559895570352e-4, 1e-3, escala['resolucao_declarada_m'])
    rampa = np.concatenate([np.zeros(120), np.arange(1, 200), np.full(80, 199)])
    truncada = [int(v) for v in np.rint(58000 - 2.9 * rampa)]
    atrasada = [truncada[0]] * 5 + truncada[:-5]
    e, s = conversa([('RAMPA', truncada, atrasada, params)])
    gravar('sintetico_retrocesso_truncado', e, s, 'rampa limpa de passo 2,9: retrocesso truncado', indice,
           ['RAMPA'])

    for semente in (0, 3, 7):
        rng = np.random.default_rng(semente)
        frente = np.concatenate([np.zeros(150), np.linspace(0, -500, 40), np.full(120, -500)])
        a = [int(v) for v in np.rint(52000 + frente + rng.normal(0, 20, frente.size))]
        b = [int(v) for v in np.rint(52000 + np.roll(frente, 12) + rng.normal(0, 20, frente.size))]
        e, s = conversa([('RUIDO%d' % semente, a, b, params)])
        gravar('sintetico_frente_fraca_%d' % semente, e, s,
               'frente fraca com ruido, semente %d: retrocesso longo' % semente, indice,
               ['RUIDO%d' % semente])

    base = execucao('MX-005')
    atraso = [base[1][0]] * 40 + list(base[1][:-40])
    e, s = conversa([('ATRASO40', base[1], atraso, base[3])])
    gravar('sintetico_atraso_40', e, s, 'canal B igual ao A atrasado 40 amostras', indice, ['ATRASO40'])

    # --- protocolo -------------------------------------------------------------------------
    def corromper_terceiro(quadro, n):
        if n == 3:
            quadro = bytearray(quadro)
            quadro[20] ^= 0x01
        return bytes(quadro)
    e, s = conversa([execucao('MX-001')], corromper=corromper_terceiro)
    gravar('protocolo_bloco_corrompido', e, s, 'segundo bloco corrompido no enlace e reenviado', indice,
           ['MX-001'])

    e, s = conversa([execucao('MX-005'), execucao('MX-005')])
    gravar('protocolo_mesmo_ensaio_duas_vezes', e, s, 'MX-005 duas vezes seguidas na mesma placa', indice,
           ['MX-005', 'MX-005'])

    e, s = conversa([execucao('MX-021'), execucao('MX-001'), execucao('MX-021')])
    gravar('protocolo_tres_ensaios_seguidos', e, s, 'MX-021, MX-001 e MX-021 na mesma placa', indice,
           ['MX-021', 'MX-001', 'MX-021'])

    ident, ca, cb, par = execucao('MX-003')
    blocos = PR.blocos_do_ensaio(ident, ca, cb)
    configurar = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(ident, par, len(ca)))
    executar = PR.montar_quadro(PR.EXECUTAR, PR.carga_executar(ident, len(blocos), len(ca)))
    e, s = fluxo_bruto([configurar, blocos[0], blocos[2], blocos[1], executar])
    gravar('protocolo_lacuna_de_sequencia', e, s,
           'bloco 2 antes do 1: descontinuidade contada e execucao recusada', indice)

    pedir = PR.montar_quadro(PR.PEDIR_RESULTADO, PR.carga_so_id(ident))
    confirmar = PR.montar_quadro(PR.CONFIRMAR_RESULTADO, PR.carga_so_id(ident))
    e, s = fluxo_bruto([configurar] + blocos + [executar, pedir, pedir, confirmar, pedir])
    gravar('protocolo_pedido_de_resultado', e, s,
           'resultado repetido a pedido e descartado depois da confirmacao', indice)

    fora_de_lugar = PR.montar_quadro(PR.AMOSTRAS, PR.carga_amostras(ident, 0, 8, [(1, 2)] * 4))
    lixo = PR.SINCRONISMO + bytes([PR.EXECUTAR]) + (5000).to_bytes(2, 'little')
    desconhecido = PR.montar_quadro(0x7F, b'\x01\x02\x03')
    e, s = fluxo_bruto([
        PR.montar_quadro(PR.CONFIGURAR, b'\x00' * 30),
        PR.montar_quadro(PR.EXECUTAR, b'\x00' * 13),
        PR.montar_quadro(PR.AMOSTRAS, b'\x00' * 10),
        configurar, fora_de_lugar, lixo, desconhecido, blocos[0],
        PR.montar_quadro(PR.PEDIR_RESULTADO, b'\x00' * 9),
    ])
    gravar('protocolo_mal_formados', e, s,
           'tamanhos errados, bloco fora do lugar, cabecalho absurdo e tipo desconhecido', indice)

    outro = PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('OUTRO', 1, 10))
    amostra_solta = PR.montar_quadro(PR.AMOSTRAS, PR.carga_amostras(ident, 0, 0, [(1, 2)]))
    grande = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(ident, par, CAPACIDADE + 1))
    e, s = fluxo_bruto([outro, amostra_solta, grande, blocos[0], executar])
    gravar('protocolo_sem_configuracao_e_capacidade', e, s,
           'execucao e bloco sem configuracao; ensaio acima da capacidade', indice)

    with open(os.path.join(SAIDA, 'casos.json'), 'w', encoding='utf-8') as f:
        json.dump({'capacidade_de_amostras': CAPACIDADE, 'casos': indice}, f, ensure_ascii=False, indent=2)
    print('vetores: %d casos em %s' % (len(indice), os.path.relpath(SAIDA, RAIZ)))


if __name__ == '__main__':
    main()

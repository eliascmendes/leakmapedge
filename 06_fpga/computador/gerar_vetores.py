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

  - tempos: TEMPOS antes de qualquer execucao, depois de uma execucao em
    lote e em tempo real; tempo real com resultado igual ao do lote, com
    amostras atrasadas de proposito, mal formado e sem configuracao.

  - autoteste dos canais (SAUDE): todos os ensaios pedem o autoteste com os
    limites do transmissor; e canais doentes de proposito: congelado, cabo
    rompido (codigo 0), pico isolado, e o pedido antes de executar, depois
    de uma execucao recusada e mal formado.

casos.json guarda, para cada caso, os ensaios que ele roda na ordem, que e
o que 06_fpga/sim/prova_cenario_b.py usa para conferir os criterios.

Ao lado de cada saida vai uma mascara (<caso>.mascara.hex, 01 = comparar,
00 = nao comparar). So a parte de TEMPOS que o circuito mede (ciclos contados)
e o CRC dela ficam de fora; todo o resto e comparado byte a byte. Os ciclos
sao conferidos a parte, em prova_cenario_b.py, contra a contagem do proprio
simulador.

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


def conversa(execucoes, corromper=None, frequencia_hz=100_000_000):
    """Roda uma ou mais execucoes do hospedeiro na mesma placa e grava os bytes.

    `frequencia_hz` e a que a placa informa em TEMPOS: a do nucleo simulado.
    """
    placa = PLACA.PlacaReferencia(capacidade_de_amostras=CAPACIDADE, frequencia_hz=frequencia_hz)
    transporte = TransporteGravado(placa, corromper)
    host = HO.Hospedeiro(transporte)
    for identificador, codigos_a, codigos_b, parametros, *limites in execucoes:
        host.rodar(identificador, codigos_a, codigos_b, parametros,
                   limites_de_saude=limites[0] if limites else None)
    return bytes(transporte.entrada), bytes(transporte.saida)


def fluxo_bruto(quadros):
    """Envia quadros prontos, um a um, e grava as respostas."""
    placa = PLACA.PlacaReferencia(capacidade_de_amostras=CAPACIDADE)
    entrada, saida = bytearray(), bytearray()
    for q in quadros:
        entrada += q
        saida += placa.receber(q)
    return bytes(entrada), bytes(saida)


def mascara_da_saida(saida):
    """1 para cada byte comparado; 0 na parte medida de TEMPOS e no CRC dela."""
    mascara = bytearray([1]) * len(saida)
    i = 0
    while i + 5 <= len(saida):
        tamanho = int.from_bytes(saida[i + 3:i + 5], 'little')
        if saida[i + 2] == PR.TEMPOS:
            inicio, fim = PR.CAMPOS_MEDIDOS_DOS_TEMPOS
            for k in range(i + 5 + inicio, i + 5 + fim + 2):
                mascara[k] = 0
        i += 7 + tamanho
    return bytes(mascara)


def gravar(nome, entrada, saida, descricao, indice, ensaios=()):
    os.makedirs(SAIDA, exist_ok=True)
    mascara = mascara_da_saida(saida)
    for sufixo, dados in (('entrada', entrada), ('saida', saida), ('mascara', mascara)):
        with open(os.path.join(SAIDA, '%s.%s.hex' % (nome, sufixo)), 'w') as f:
            f.write(''.join('%02x\n' % b for b in dados))
    indice[nome] = {'descricao': descricao, 'ensaios': list(ensaios),
                    'bytes_de_entrada': len(entrada), 'bytes_de_saida_esperados': len(saida),
                    'bytes_nao_comparados': mascara.count(0)}


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
                p['conversao']['canal_B']['codigos'], p['parametros'], p['limites_de_saude'])

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
    e, s = conversa([('ATRASO40', base[1], atraso, base[3], base[4])])
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

    ident, ca, cb, par, _ = execucao('MX-003')
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
    identificar = PR.montar_quadro(PR.IDENTIFICAR, b'')   # so a placa simulada responde
    e, s = fluxo_bruto([
        PR.montar_quadro(PR.CONFIGURAR, b'\x00' * 30),
        PR.montar_quadro(PR.EXECUTAR, b'\x00' * 13),
        PR.montar_quadro(PR.AMOSTRAS, b'\x00' * 10),
        configurar, fora_de_lugar, lixo, desconhecido, identificar, blocos[0],
        PR.montar_quadro(PR.PEDIR_RESULTADO, b'\x00' * 9),
    ])
    gravar('protocolo_mal_formados', e, s,
           'tamanhos errados, bloco fora do lugar, cabecalho absurdo, tipo desconhecido '
           'e IDENTIFICAR, que a FPGA nao responde', indice)

    outro = PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('OUTRO', 1, 10))
    amostra_solta = PR.montar_quadro(PR.AMOSTRAS, PR.carga_amostras(ident, 0, 0, [(1, 2)]))
    grande = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(ident, par, CAPACIDADE + 1))
    e, s = fluxo_bruto([outro, amostra_solta, grande, blocos[0], executar])
    gravar('protocolo_sem_configuracao_e_capacidade', e, s,
           'execucao e bloco sem configuracao; ensaio acima da capacidade', indice)

    # o topo com a serial (tb_topo.v) roda o relogio a 1 MHz; so ele usa este vetor,
    # que por isso fica fora do indice dos casos do nucleo
    e, s = conversa([execucao('MX-005')], frequencia_hz=1_000_000)
    gravar('topo_serial_MX-005', e, s, 'MX-005 pelo topo com a serial, relogio de 1 MHz', {}, ['MX-005'])

    # --- tempos contados pelo circuito e execucao em tempo real ----------------------
    def quadros_do_ensaio(ident):
        _, ca, cb, par, _ = execucao(ident)
        blocos = PR.blocos_do_ensaio(ident, ca, cb)
        configurar = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(ident, par, len(ca)))
        return configurar, blocos, len(blocos), len(ca)

    def pedir_tempos(ident):
        return PR.montar_quadro(PR.PEDIR_TEMPOS, PR.carga_so_id(ident))

    def confirmar(ident):
        return PR.montar_quadro(PR.CONFIRMAR_RESULTADO, PR.carga_so_id(ident))

    e, s = fluxo_bruto([pedir_tempos('')])
    gravar('tempos_antes_de_executar', e, s, 'TEMPOS numa placa que ainda nao executou nada', indice)

    configurar, blocos, nb, na = quadros_do_ensaio('MX-013')
    e, s = fluxo_bruto([configurar] + blocos + [
        PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('MX-013', nb, na)),
        pedir_tempos('MX-013'), confirmar('MX-013')])
    gravar('tempos_lote_MX-013', e, s, 'execucao em lote e os ciclos que ela levou', indice, ['MX-013'])

    for ident, periodo in (('MX-001', 400), ('MX-039', 300)):
        configurar, blocos, nb, na = quadros_do_ensaio(ident)
        e, s = fluxo_bruto([configurar] + blocos + [
            PR.montar_quadro(PR.EXECUTAR_TEMPO_REAL, PR.carga_executar_tempo_real(ident, nb, na, periodo)),
            pedir_tempos(ident), confirmar(ident)])
        gravar('tempo_real_%s' % ident, e, s,
               'tempo real, uma amostra a cada %d ciclos: resultado igual ao do lote' % periodo,
               indice, [ident])

    configurar, blocos, nb, na = quadros_do_ensaio('MX-005')
    e, s = fluxo_bruto([configurar] + blocos + [
        PR.montar_quadro(PR.EXECUTAR_TEMPO_REAL, PR.carga_executar_tempo_real('MX-005', nb, na, 8)),
        pedir_tempos('MX-005'), confirmar('MX-005')])
    gravar('tempo_real_atrasado', e, s,
           'tempo real com periodo menor que o processamento: amostras atrasadas contadas', indice, ['MX-005'])

    e, s = fluxo_bruto([
        PR.montar_quadro(PR.EXECUTAR_TEMPO_REAL, PR.carga_executar_tempo_real('MX-005', nb, na, 400)),
        pedir_tempos('MX-005'),
        PR.montar_quadro(PR.EXECUTAR_TEMPO_REAL, PR.carga_executar_tempo_real('MX-005', nb, na, 0)),
        PR.montar_quadro(PR.EXECUTAR_TEMPO_REAL, PR.carga_executar('MX-005', nb, na)),
        PR.montar_quadro(PR.PEDIR_TEMPOS, b'\x00' * 9),
    ])
    gravar('tempo_real_mal_formado', e, s,
           'tempo real sem configuracao, com periodo zero e com tamanhos errados', indice)

    # --- autoteste dos canais: canais doentes de proposito ---------------------------------
    ident, ca, cb, par, limites = execucao('MX-013')
    congelado = list(cb[:60]) + [cb[60]] * (len(cb) - 60)
    configurar = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar('CONGELA', par, len(ca)))
    blocos = PR.blocos_do_ensaio('CONGELA', ca, congelado)
    e, s = fluxo_bruto([configurar] + blocos + [
        PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('CONGELA', len(blocos), len(ca))),
        PR.montar_quadro(PR.PEDIR_SAUDE, PR.carga_pedir_saude('CONGELA', limites)),
        PR.montar_quadro(PR.PEDIR_SAUDE, PR.carga_pedir_saude('CONGELA', PR.LIMITES_ABERTOS)),
        confirmar('CONGELA')])
    gravar('saude_canal_congelado', e, s,
           'canal B congelado a partir da amostra 60 (MX-013): acusado com os limites do '
           'transmissor, e nao acusado com os limites abertos', indice, ['CONGELA'])

    rompido = list(ca[:100]) + [0] * (len(ca) - 100)
    e, s = conversa([('ROMPIDO', rompido, cb, par, limites)])
    gravar('saude_cabo_rompido', e, s,
           'canal A cai a codigo 0 na amostra 100 (MX-013): congelado, saturado e fora da faixa',
           indice, ['ROMPIDO'])

    ident, ca, cb, par, limites = execucao('MX-021')
    pico = list(cb)
    pico[90] -= limites['limite_salto'] + 60
    e, s = conversa([('PICO', ca, pico, par, limites)])
    gravar('saude_pico_isolado', e, s,
           'uma amostra isolada do canal B cai mais que meia faixa (MX-021): salto', indice, ['PICO'])

    pedir_saude = PR.montar_quadro(PR.PEDIR_SAUDE, PR.carga_pedir_saude('', limites))
    e, s = fluxo_bruto([
        pedir_saude,
        PR.montar_quadro(PR.EXECUTAR, PR.carga_executar('NADA', 1, 10)),
        pedir_saude,
        PR.montar_quadro(PR.PEDIR_SAUDE, bytes(15)),
    ])
    gravar('saude_sem_execucao_e_mal_formado', e, s,
           'SAUDE antes de executar, depois de uma execucao recusada e com tamanho errado', indice)

    with open(os.path.join(SAIDA, 'casos.json'), 'w', encoding='utf-8') as f:
        json.dump({'capacidade_de_amostras': CAPACIDADE, 'casos': indice}, f, ensure_ascii=False, indent=2)
    print('vetores: %d casos em %s' % (len(indice), os.path.relpath(SAIDA, RAIZ)))


if __name__ == '__main__':
    main()

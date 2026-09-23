"""LEAKMAP B-05 - dimensionamento: memoria da placa ou transmissao com buffer.

A escolha entre via 1 (ensaio inteiro na memoria da placa) e via 2
(transmissao durante a execucao) sai de conta, nao de suposicao:

  memoria de amostras = amostras x canais x bits por amostra
  taxa necessaria     = frequencia x canais x bytes por amostra
  taxa da serial      = baud / 10   (8 bits de dado, 1 de partida, 1 de parada)

A memoria do algoritmo (janelas, somas e historico anterior ao disparo) e
somada a parte, com as larguras de palavra medidas pela referencia em ponto
fixo em 04_detector/resultados/leakmap_ponto_fixo_v1.json.

A placa ainda nao esta definida. A decisao e feita contra cada candidata,
com a capacidade de memoria em bloco da ficha tecnica do fabricante. Esses
valores precisam ser conferidos no modelo exato da placa emprestada: o
ensaio so e aceito no cenario B depois dessa conferencia.

Grava 06_fpga/resultados/leakmap_dimensionamento_v1.json.
"""
import json
import math
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocolo as PR  # noqa: E402
import representacao as RP  # noqa: E402

PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes', 'leakmap_pacote_matriz_v1.json')
PONTO_FIXO = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_ponto_fixo_v1.json')
SAIDA = os.path.join(RAIZ, '06_fpga', 'resultados', 'leakmap_dimensionamento_v1.json')

# Memoria em bloco total do chip, em kbit, segundo a ficha tecnica do fabricante.
PLACAS_CANDIDATAS = [
    {'placa': 'Spartan-7 XC7S6', 'memoria_em_bloco_kbit': 180},
    {'placa': 'Spartan-7 XC7S15', 'memoria_em_bloco_kbit': 360},
    {'placa': 'Spartan-7 XC7S25', 'memoria_em_bloco_kbit': 1620},
    {'placa': 'Spartan-7 XC7S50', 'memoria_em_bloco_kbit': 2700},
    {'placa': 'Cyclone V E 5CEBA2', 'memoria_em_bloco_kbit': 1760},
    {'placa': 'Cyclone V E 5CEBA4', 'memoria_em_bloco_kbit': 3080},
    {'placa': 'Cyclone V SE 5CSEMA5 (DE1-SoC)', 'memoria_em_bloco_kbit': 3970},
    {'placa': 'Gowin GW1NR-9 (Tang Nano 9K)', 'memoria_em_bloco_kbit': 468},
]

BAUD_PADRAO = 115200
BITS_POR_CARACTERE = 10


def memoria_de_amostras_bits(n_amostras, canais=2, bits=RP.BITS):
    return n_amostras * canais * bits


def memoria_por_duracao_bits(duracao_s, frequencia_hz, canais=2, bits=RP.BITS):
    return int(round(duracao_s * frequencia_hz)) * canais * bits


def capacidade_serial_bytes_s(baud=BAUD_PADRAO):
    return baud / BITS_POR_CARACTERE


def taxa_necessaria_bytes_s(frequencia_hz, canais=2, bytes_por_amostra=RP.BITS // 8):
    return frequencia_hz * canais * bytes_por_amostra


def eficiencia_do_bloco(pares=PR.PARES_POR_BLOCO):
    """Carga util de amostras sobre o total do quadro, com cabecalho e CRC."""
    util = 4 * pares
    total = len(PR.montar_quadro(PR.AMOSTRAS, PR.carga_amostras('X', 0, 0, [(0, 0)] * pares)))
    return util / total


def memoria_do_algoritmo_bits(n_curta, n_guarda, n_longa, larguras):
    """Por canal: quadrados da janela, historico antes do disparo e somas."""
    quadrados = (n_curta + n_guarda + n_longa + 1) * larguras['curta_quadrado']
    historico = (n_curta + n_guarda + 2) * (larguras['curta_deslocado'] + larguras['passa_altas_q16'])
    somas = larguras['curta_soma'] + larguras['longa_soma']
    por_canal = quadrados + historico + somas + larguras['passa_altas_q16']
    return 2 * por_canal


def decidir(n_amostras_max, larguras, cal, placas=PLACAS_CANDIDATAS):
    amostras = memoria_de_amostras_bits(n_amostras_max)
    algoritmo = memoria_do_algoritmo_bits(cal['n_curta'], cal['n_guarda'], cal['n_longa'], larguras)
    total = amostras + algoritmo
    decisoes = []
    for placa in placas:
        capacidade = placa['memoria_em_bloco_kbit'] * 1024
        via = 1 if total <= capacidade else 2
        decisoes.append(dict(placa, necessario_bits=total,
                             ocupacao=total / capacidade, via=via))
    return amostras, algoritmo, decisoes


def main():
    sys.path.insert(0, os.path.join(RAIZ, '04_detector'))
    import detector as D

    with open(PACOTE, encoding='utf-8') as f:
        pacote = json.load(f)
    with open(PONTO_FIXO, encoding='utf-8') as f:
        larguras = json.load(f)['larguras_de_palavra_observadas_bits']
    cal = D.calibracao_padrao()
    fs = float(pacote['amostragem']['frequencia_de_amostragem_hz'])
    n_max = max(e['n_pontos'] for e in pacote['ensaios'])

    amostras, algoritmo, decisoes = decidir(n_max, larguras, cal)
    serial = capacidade_serial_bytes_s()
    eficiencia = eficiencia_do_bloco()
    necessaria = taxa_necessaria_bytes_s(fs)
    necessaria_com_quadro = necessaria / eficiencia
    bytes_por_ensaio = sum(len(q) for q in PR.blocos_do_ensaio('X', [0] * n_max, [0] * n_max))

    todas_via_1 = all(d['via'] == 1 for d in decisoes)
    relatorio = {
        'descricao': 'Dimensionamento do cenario B (B-05): memoria da placa contra transmissao com buffer.',
        'exemplos_do_fluxograma': {
            '2 s, 10 kHz, 2 canais, 16 bits': {
                'bits': memoria_por_duracao_bits(2, 10000),
                'KiB': memoria_por_duracao_bits(2, 10000) / 8 / 1024},
            '10 s, 50 kHz, 2 canais, 16 bits': {
                'bits': memoria_por_duracao_bits(10, 50000),
                'MiB': memoria_por_duracao_bits(10, 50000) / 8 / 1024 / 1024},
            'serial 115200 bits/s': {
                'bytes_por_segundo': serial,
                'amostras_por_segundo_por_canal': serial / 4},
        },
        'ensaios_da_matriz': {
            'maior_ensaio_amostras_por_canal': n_max,
            'frequencia_de_amostragem_hz': fs,
            'memoria_de_amostras_bits': amostras,
            'memoria_do_algoritmo_bits': algoritmo,
            'memoria_total_bits': amostras + algoritmo,
            'larguras_usadas': 'medidas por 04_detector/detector_ponto_fixo.py',
        },
        'placas_candidatas': decisoes,
        'observacao_sobre_as_placas': ('capacidade de memoria em bloco da ficha tecnica do '
                                       'fabricante; conferir no modelo exato da placa usada'),
        'via_2_se_fosse_necessaria': {
            'taxa_de_amostras_bytes_s': necessaria,
            'eficiencia_do_bloco': eficiencia,
            'taxa_com_cabecalho_e_crc_bytes_s': necessaria_com_quadro,
            'capacidade_da_serial_a_115200_bytes_s': serial,
            'fecha': necessaria_com_quadro <= serial,
        },
        'via_1_carga_antes_da_execucao': {
            'bytes_do_maior_ensaio': bytes_por_ensaio,
            'tempo_de_carga_a_115200_s': bytes_por_ensaio / serial,
        },
        'decisao': {
            'via': 1 if todas_via_1 else 'depende da placa',
            'conta': ('%d amostras x 2 canais x 16 bits = %d bits de amostras, mais %d bits '
                      'de memoria do algoritmo: %d bits (%.1f kbit), contra %d kbit na menor '
                      'candidata. O ensaio cabe inteiro na memoria de todas as placas '
                      'candidatas, entao a temporizacao fica independente do enlace. A via 2 '
                      'a 115 200 bits/s precisaria de %.0f bytes/s com cabecalho e CRC, contra '
                      '%.0f disponiveis: %s.'
                      % (n_max, amostras, algoritmo, amostras + algoritmo,
                         (amostras + algoritmo) / 1024,
                         min(p['memoria_em_bloco_kbit'] for p in PLACAS_CANDIDATAS),
                         necessaria_com_quadro, serial,
                         'fecharia' if necessaria_com_quadro <= serial else 'nao fecharia')),
        },
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))
    print(relatorio['decisao']['conta'])


if __name__ == '__main__':
    main()

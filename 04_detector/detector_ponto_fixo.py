"""LEAKMAP - porte de referencia em ponto fixo das etapas A-11 e A-12.

BONUS. Prepara o terreno para o Cenario 1 (FPGA) sem depender da placa: a
mesma cadeia de `detector.py`, escrita so com inteiros, do tipo que se
sintetiza. Nao substitui o detector em ponto flutuante; serve para medir o
que a aritmetica inteira custa em exatidao antes de existir Verilog.

O que muda em relacao a versao em ponto flutuante
-------------------------------------------------
- a entrada e o codigo do conversor A/D, inteiro, e nao a carga em metros;
- o filtro passa-altas guarda o estado em Q`FRACAO` e trunca a cada amostra,
  como um deslocamento aritmetico a direita em hardware faz;
- nao ha divisao: a comparacao de razao de energia vira multiplicacao
  cruzada, `S_curta * N_longa >= limiar * S_longa * N_curta`;
- nao ha raiz quadrada: a faixa de ruido do retrocesso e comparada em
  energia, `Ye^2 * N_longa > k^2 * S_longa`.

Larguras de palavra
-------------------
Os acumuladores sao int64. `larguras_observadas` devolve o maior numero de
bits que cada estagio chegou a usar no ensaio, para dimensionar o registrador
no Verilog em vez de chutar. `conferir_larguras` para a execucao se algum
estagio passar de 63 bits.
"""
import numpy as np

import detector as D

FRACAO = 16      # bits de fracao do estado do filtro passa-altas
DESLOCA_ENERGIA = 8   # Y e deslocado antes de elevar ao quadrado
BITS_MAXIMOS = 63


class EstouroDeLargura(OverflowError):
    pass


def _bits(valor):
    v = int(abs(valor))
    return v.bit_length() + 1  # mais um bit para o sinal


def _conferir(nome, arranjo, larguras):
    if arranjo.size == 0:
        larguras[nome] = 0
        return arranjo
    maior = int(np.max(np.abs(arranjo)))
    larguras[nome] = _bits(maior)
    if larguras[nome] > BITS_MAXIMOS:
        raise EstouroDeLargura(
            'estagio %s precisou de %d bits, acima do limite de %d'
            % (nome, larguras[nome], BITS_MAXIMOS))
    return arranjo


def para_codigo(sinal_m, degrau_m, minimo_m=0.0):
    """Converte carga em metros para o codigo inteiro do conversor."""
    x = np.asarray(sinal_m, dtype=float)
    return np.rint((x - float(minimo_m)) / float(degrau_m)).astype(np.int64)


def coeficiente_do_filtro(corte_hz, ts):
    """Coeficiente do passa-altas em Q`FRACAO`: round(tau / (tau + Ts) * 2^FRACAO)."""
    tau = 1.0 / (2.0 * np.pi * float(corte_hz))
    a = tau / (tau + ts)
    return int(round(a * (1 << FRACAO)))


def piso_em_ye(piso_m, degrau_m):
    """Piso de amplitude levado para as unidades de Ye (codigo em Q(FRACAO-DESLOCA))."""
    return int(round(piso_m / float(degrau_m) * (1 << (FRACAO - DESLOCA_ENERGIA))))


def parametros_inteiros(cal, ts, degrau_m, resolucao_declarada_m=None):
    """Todos os numeros que a maquina inteira usa, e so eles.

    E o conjunto que o computador envia a FPGA no cenario B (etapa B-07).
    Com estes parametros e o codigo de entrada, o detector inteiro fica
    completamente determinado, sem nenhuma conta em ponto flutuante.
    """
    cal = dict(cal or D.calibracao_padrao())
    limiar = int(round(cal['limiar_de_razao']))
    if limiar != cal['limiar_de_razao']:
        raise ValueError('o porte em ponto fixo exige limiar de razao '
                         'inteiro; recebeu %r' % cal['limiar_de_razao'])
    piso_m = D.piso_de_amplitude(cal, resolucao_declarada_m)
    piso = piso_em_ye(piso_m, degrau_m)
    return {
        'fracao': FRACAO,
        'desloca_energia': DESLOCA_ENERGIA,
        'coeficiente_do_filtro': coeficiente_do_filtro(cal['corte_passa_altas_hz'], ts),
        'n_curta': int(cal['n_curta']),
        'n_guarda': int(cal['n_guarda']),
        'n_longa': int(cal['n_longa']),
        'limiar_de_razao': limiar,
        'k2_faixa_de_ruido': int(round(cal['k_faixa_de_ruido'] ** 2)),
        'piso_em_ye': piso,
        'piso_energia_por_amostra': (piso * piso) // 12,
    }


def passa_altas_inteiro(codigo, corte_hz, ts, larguras):
    """y[n] = (A * (y[n-1] + (x[n]-x[n-1]) << FRACAO)) >> FRACAO.

    `A` e o coeficiente do filtro em Q`FRACAO`. O deslocamento a direita e
    aritmetico e trunca para baixo, que e o comportamento de hardware; a
    versao em ponto flutuante arredonda. A diferenca entre as duas e
    justamente o que o teste de comparacao mede.
    """
    coeficiente = coeficiente_do_filtro(corte_hz, ts)
    larguras['coeficiente_do_filtro'] = _bits(coeficiente)

    x = np.asarray(codigo, dtype=np.int64)
    y = np.zeros(len(x), dtype=np.int64)
    estado = np.int64(0)
    for n in range(1, len(x)):
        diferenca = np.int64(x[n] - x[n - 1]) << FRACAO
        estado = (np.int64(coeficiente) * (estado + diferenca)) >> FRACAO
        y[n] = estado
    _conferir('passa_altas_q%d' % FRACAO, y, larguras)
    return y


def somas_de_energia(y, n_janela, larguras, nome):
    """Soma de y^2 em janela causal, sem divisao.

    Devolve int64 com NaN representado por -1 nas posicoes sem janela
    completa, para nao precisar de ponto flutuante.
    """
    ye = (np.asarray(y, dtype=np.int64) >> DESLOCA_ENERGIA)
    _conferir('%s_deslocado' % nome, ye, larguras)
    quadrados = ye * ye
    _conferir('%s_quadrado' % nome, quadrados, larguras)
    acumulado = np.concatenate([[np.int64(0)], np.cumsum(quadrados)])
    _conferir('%s_acumulado' % nome, acumulado, larguras)

    soma = np.full(len(ye), np.int64(-1), dtype=np.int64)
    n = np.arange(n_janela - 1, len(ye))
    soma[n] = acumulado[n + 1] - acumulado[n - n_janela + 1]
    _conferir('%s_soma' % nome, soma, larguras)
    return soma, ye


def detectar_canal_inteiro(sinal_m, ts, degrau_m, cal=None,
                           resolucao_declarada_m=None, minimo_m=0.0):
    """A-11 e A-12 em aritmetica inteira. Mesma estrutura de `detector.py`."""
    cal = dict(cal or D.calibracao_padrao())
    nc, ng, nl = cal['n_curta'], cal['n_guarda'], cal['n_longa']
    larguras = {}

    codigo = para_codigo(sinal_m, degrau_m, minimo_m)
    _conferir('codigo_de_entrada', codigo, larguras)
    y = passa_altas_inteiro(codigo, cal['corte_passa_altas_hz'], ts, larguras)

    s_curta, ye = somas_de_energia(y, nc, larguras, 'curta')
    s_longa_bruta, _ = somas_de_energia(y, nl, larguras, 'longa')

    recuo = nc + ng
    s_longa = np.full(len(y), np.int64(-1), dtype=np.int64)
    if recuo < len(y):
        s_longa[recuo:] = s_longa_bruta[:len(y) - recuo]

    # Piso de amplitude e de energia, levados para as unidades de Ye.
    piso_m = D.piso_de_amplitude(cal, resolucao_declarada_m)
    piso_ye = piso_em_ye(piso_m, degrau_m)
    larguras['piso_em_ye'] = _bits(piso_ye)
    piso_energia_por_amostra = (piso_ye * piso_ye) // 12

    valido = (s_curta >= 0) & (s_longa >= 0)
    s_longa_efetiva = np.where(
        s_longa > nl * piso_energia_por_amostra,
        s_longa, np.int64(nl * piso_energia_por_amostra))

    limiar = int(round(cal['limiar_de_razao']))
    if limiar != cal['limiar_de_razao']:
        raise ValueError('o porte em ponto fixo exige limiar de razao '
                         'inteiro; recebeu %r' % cal['limiar_de_razao'])

    esquerda = s_curta.astype(object) * nl
    direita = s_longa_efetiva.astype(object) * (limiar * nc)
    _conferir('comparacao_esquerda', np.asarray(
        [int(v) for v in esquerda[valido]] or [0], dtype=np.int64), larguras)
    _conferir('comparacao_direita', np.asarray(
        [int(v) for v in direita[valido]] or [0], dtype=np.int64), larguras)

    condicao_razao = np.zeros(len(y), dtype=bool)
    condicao_razao[valido] = np.asarray(
        [bool(e >= d) for e, d in zip(esquerda[valido], direita[valido])],
        dtype=bool)
    condicao_amplitude = valido & (s_curta >= nc * piso_ye * piso_ye)

    acima = valido & condicao_razao & condicao_amplitude
    indices = np.nonzero(acima)[0]

    det = {
        'detectado': bool(len(indices)),
        'n_oportunidades_de_decisao': int(np.count_nonzero(valido)),
        'indice_de_cruzamento': int(indices[0]) if len(indices) else None,
        'piso_de_amplitude_usado_m': float(piso_m),
        'piso_em_ye': piso_ye,
        'larguras_observadas': larguras,
    }
    if not len(indices):
        return det, y, ye, s_longa

    # --- A-12: retrocesso, tambem sem raiz quadrada -----------------------
    cruzamento = int(indices[0])
    limite = max(0, cruzamento - (nc + ng))
    k2 = int(round(cal['k_faixa_de_ruido'] ** 2))
    referencia = int(s_longa[cruzamento])

    def fora_da_faixa(i):
        return int(ye[i]) ** 2 * nl > k2 * referencia

    i = cruzamento
    while i > limite and fora_da_faixa(i - 1):
        i -= 1

    det['indice_de_chegada'] = int(i)
    det['amostras_retrocedidas'] = int(cruzamento - i)
    det['retrocesso_truncado'] = bool(i == limite and fora_da_faixa(i)
                                      and i > 0 and fora_da_faixa(i - 1))
    return det, y, ye, s_longa


def comparar_com_ponto_flutuante(sinal_m, ts, degrau_m, cal=None,
                                 resolucao_declarada_m=None, minimo_m=0.0):
    """Compara os dois portes sobre a MESMA entrada quantizada.

    A entrada e quantizada uma unica vez e usada pelos dois, para que a
    diferenca medida seja so a da aritmetica e nao a da quantizacao.
    """
    cal = dict(cal or D.calibracao_padrao())
    codigo = para_codigo(sinal_m, degrau_m, minimo_m)
    sinal_quantizado = float(minimo_m) + codigo.astype(float) * float(degrau_m)

    fixo, y_fixo, ye, _ = detectar_canal_inteiro(
        sinal_quantizado, ts, degrau_m, cal, resolucao_declarada_m, minimo_m)
    flutuante, y_flutuante, _, e_longa = D.detectar_canal(
        sinal_quantizado, ts, cal, resolucao_declarada_m)
    if flutuante['detectado']:
        tempo = np.arange(len(sinal_quantizado), dtype=float) * ts
        flutuante.update(D.marcar_chegada(
            y_flutuante, e_longa, flutuante['indice_de_cruzamento'],
            tempo, ts, cal))

    # O estado do filtro em ponto fixo esta em codigos Q`FRACAO`; converte
    # para metros para poder comparar com o de ponto flutuante.
    y_fixo_em_m = y_fixo.astype(float) / (1 << FRACAO) * float(degrau_m)
    erro = np.abs(y_fixo_em_m - y_flutuante)

    return {
        'ponto_fixo': fixo,
        'ponto_flutuante': flutuante,
        'mesma_deteccao': fixo['detectado'] == flutuante['detectado'],
        'mesmo_cruzamento': (fixo['indice_de_cruzamento']
                             == flutuante['indice_de_cruzamento']),
        'mesma_chegada': (fixo.get('indice_de_chegada')
                          == flutuante.get('indice_de_chegada')),
        'erro_maximo_do_passa_altas_m': float(erro.max()) if erro.size else 0.0,
        'erro_maximo_em_degraus_de_entrada': (
            float(erro.max() / float(degrau_m)) if erro.size else 0.0),
        'larguras_observadas': fixo['larguras_observadas'],
    }


DEGRAU_PADRAO_M = 1e-3
"""Degrau de entrada assumido quando o ensaio nao declara conversor.

A linha `sem_ruido` da matriz nao passa por conversor A/D, mas um porte de
hardware sempre recebe codigo inteiro. Para poder comparar os dois portes
nessa linha assume-se um degrau de 1 mm de carga, cerca de 0,1 mbar.
"""


def comparar_pacote(pacote, cal=None):
    """Compara os dois portes canal a canal em todos os ensaios do pacote."""
    ts = float(pacote['amostragem']['periodo_de_amostragem_s'])
    comparacoes, larguras = [], {}
    for ensaio in pacote['ensaios']:
        efeitos = ensaio.get('efeitos_de_sensor_aplicados') or {}
        resolucao = efeitos.get('resolucao_declarada_m')
        degrau = resolucao or DEGRAU_PADRAO_M
        for canal in ('canal_A_carga_m', 'canal_B_carga_m'):
            c = comparar_com_ponto_flutuante(
                ensaio[canal], ts, degrau, cal,
                resolucao_declarada_m=resolucao)
            for nome, bits in c['larguras_observadas'].items():
                larguras[nome] = max(larguras.get(nome, 0), bits)
            comparacoes.append({
                'id': ensaio['id'],
                'canal': 'A' if canal.startswith('canal_A') else 'B',
                'degrau_de_entrada_m': float(degrau),
                'mesma_deteccao': c['mesma_deteccao'],
                'mesmo_cruzamento': c['mesmo_cruzamento'],
                'mesma_chegada': c['mesma_chegada'],
                'indice_de_chegada_ponto_fixo':
                    c['ponto_fixo'].get('indice_de_chegada'),
                'indice_de_chegada_ponto_flutuante':
                    c['ponto_flutuante'].get('indice_de_chegada'),
                'erro_maximo_do_passa_altas_em_degraus':
                    c['erro_maximo_em_degraus_de_entrada'],
            })
    iguais = sum(1 for c in comparacoes
                 if c['mesma_deteccao'] and c['mesmo_cruzamento']
                 and c['mesma_chegada'])
    return {
        'n_comparacoes': len(comparacoes),
        'identicos': iguais,
        'divergentes': len(comparacoes) - iguais,
        'erro_maximo_do_passa_altas_em_degraus': max(
            (c['erro_maximo_do_passa_altas_em_degraus']
             for c in comparacoes), default=0.0),
        'larguras_de_palavra_observadas_bits': larguras,
        'comparacoes': comparacoes,
    }


def main():
    import json
    import os

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entrada = os.path.join(raiz, '03_ensaios', 'pacotes',
                           'leakmap_pacote_matriz_v1.json')
    saida = os.path.join(raiz, '04_detector', 'resultados',
                         'leakmap_ponto_fixo_v1.json')
    with open(entrada, encoding='utf-8') as f:
        pacote = json.load(f)

    relatorio = comparar_pacote(pacote)
    relatorio['descricao'] = (
        'Comparacao amostra a amostra entre o porte em ponto fixo das etapas '
        'A-11 e A-12 e a versao em ponto flutuante, sobre os mesmos ensaios '
        'da matriz. Os dois portes recebem a MESMA entrada ja quantizada, '
        'para que a diferenca medida seja so a da aritmetica.')
    relatorio['formato'] = {
        'bits_de_fracao_do_filtro': FRACAO,
        'deslocamento_antes_do_quadrado': DESLOCA_ENERGIA,
        'limite_de_largura_bits': BITS_MAXIMOS,
    }
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    print('escrito: %s' % os.path.relpath(saida, raiz))
    print('comparacoes: %d | identicas: %d | divergentes: %d'
          % (relatorio['n_comparacoes'], relatorio['identicos'],
             relatorio['divergentes']))
    print('erro maximo do passa-altas: %.3f degraus de entrada'
          % relatorio['erro_maximo_do_passa_altas_em_degraus'])
    print('maior largura de palavra observada: %d bits'
          % max(relatorio['larguras_de_palavra_observadas_bits'].values()))


if __name__ == '__main__':
    main()

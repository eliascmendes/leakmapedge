"""LEAKMAP - refino da diferenca de tempo por correlacao cruzada.

A posicao publicada sai das marcas de chegada de A-12, com resolucao de uma
amostra. Este refino compara a propria frente de onda dos dois canais: pega o
sinal passa-altas de A em volta da marca de A, procura em B, em volta da marca
de B, o deslocamento que melhor casa as duas frentes (correlacao normalizada)
e interpola o pico por uma parabola, o que da a diferenca de tempo em fracao
de amostra.

Fica ao lado da posicao principal, sem substitui-la: a posicao publicada, as
classes e a comparacao com a FPGA no cenario B continuam pelas marcas. O
avaliador mede os dois (05_avaliacao/avaliador.py).

O que se mediu com ele (05_avaliacao/LEIAME.md): ajuda quando a frente e limpa
e a marca erra por fracao de amostra; nao ajuda quando o erro vem de outra
coisa, como a saida em degraus de um transmissor lento.
"""
import numpy as np

import detector as D
import posicao as P

AMOSTRAS_ANTES = 3        # da janela da frente, antes da marca
AMOSTRAS_DEPOIS = 16      # e depois dela
BUSCA = 4                 # deslocamento procurado em volta da marca de B, em amostras


def refinar(ensaio, registro, cal=None):
    """Refino de um registro localizado. Devolve o dicionario do refino ou None."""
    if registro.get('classe') != D.CLASSE_LOCALIZADO:
        return None
    cal = cal or D.calibracao_padrao()
    t = np.asarray(ensaio['tempo_s'], dtype=float)
    ts = float(np.median(np.diff(t)))
    ya = D.passa_altas(np.asarray(ensaio['canal_A_carga_m'], dtype=float), cal['corte_passa_altas_hz'], ts)
    yb = D.passa_altas(np.asarray(ensaio['canal_B_carga_m'], dtype=float), cal['corte_passa_altas_hz'], ts)
    ia = registro['canal_A']['indice_de_chegada']
    ib = registro['canal_B']['indice_de_chegada']
    if (ia - AMOSTRAS_ANTES < 0 or ib - AMOSTRAS_ANTES - BUSCA < 0
            or ia + AMOSTRAS_DEPOIS > len(ya) or ib + AMOSTRAS_DEPOIS + BUSCA > len(yb)):
        return {'aplicado': False, 'motivo': 'frente perto da borda do registro'}

    frente_a = ya[ia - AMOSTRAS_ANTES: ia + AMOSTRAS_DEPOIS]
    energia_a = float(np.dot(frente_a, frente_a))
    correlacao = []
    for j in range(-BUSCA, BUSCA + 1):
        frente_b = yb[ib - AMOSTRAS_ANTES + j: ib + AMOSTRAS_DEPOIS + j]
        energia = energia_a * float(np.dot(frente_b, frente_b))
        correlacao.append(float(np.dot(frente_a, frente_b)) / np.sqrt(energia) if energia > 0 else 0.0)
    c = np.asarray(correlacao)
    k = int(np.argmax(c))
    if k == 0 or k == len(c) - 1:
        return {'aplicado': False, 'motivo': 'pico da correlacao na borda da busca'}
    curvatura = c[k - 1] - 2.0 * c[k] + c[k + 1]
    fracao = 0.5 * (c[k - 1] - c[k + 1]) / curvatura if curvatura != 0 else 0.0
    ajuste_de_b = (k - BUSCA) + fracao       # a frente de B esta aqui em relacao a marca de B

    delta_t = (ia - ib - ajuste_de_b) * ts
    par = ensaio['parametros_do_detector']
    loc = P.localizar(float(par['distancia_entre_sensores_L_m']), float(par['velocidade_de_onda_m_s']),
                      delta_t, float(par['posicao_sensor_A_m']))
    return {
        'aplicado': True,
        'delta_t_s': float(delta_t),
        'ajuste_em_relacao_as_marcas_amostras': float(ajuste_de_b),
        'correlacao_no_pico': float(c[k]),
        'posicao_estimada_m': loc['posicao_estimada_m'],
        'posicao_limitada_a_faixa': loc['posicao_limitada_a_faixa'],
        'janela_amostras': {'antes': AMOSTRAS_ANTES, 'depois': AMOSTRAS_DEPOIS, 'busca': BUSCA},
    }


def refinar_pacote(pacote, registros, cal=None):
    """Acrescenta `refino_por_correlacao` aos registros localizados, na ordem do pacote."""
    for ensaio, registro in zip(pacote['ensaios'], registros):
        refino = refinar(ensaio, registro, cal)
        if refino is not None:
            registro['refino_por_correlacao'] = refino
    return registros

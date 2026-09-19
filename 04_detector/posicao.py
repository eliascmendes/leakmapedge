"""LEAKMAP A-14 - calculo da posicao a partir da diferenca temporal.

A formula ja estava escrita em 04_detector/LEIAME.md e ja era usada pelo
baseline em 02_bancada/codigo/rodar_tudo.py. Aqui ela vira funcao isolada e
testavel, ligada as saidas de A-11 a A-13 em vez de reimplementada dentro do
laco de simulacao.

Hipoteses em que a formula vale, as mesmas declaradas em A-14: trecho
uniforme, evento entre os dois sensores e velocidade de propagacao
aproximadamente igual nos dois sentidos.

    x = (L + c * delta_t) / 2,  delta_t = tA - tB

`x` e medido a partir do sensor A; a posicao absoluta no trecho e
posicao_do_sensor_A + x.

Propagacao de erro, tambem de A-14: uma contribuicao de erro temporal
d(delta_t) produz aproximadamente dx = c * d(delta_t) / 2, mantidos os demais
parametros fixos. Como c tambem e incerto, entra o termo dx = delta_t * dc / 2.
Isso descreve a propagacao de um erro; nao e garantia da precisao total do
produto.
"""
import numpy as np


def limite_fisico_de_delta_t(l_m, c_m_s):
    """Maior |delta_t| fisicamente possivel: L / c.

    Corresponde ao evento exatamente sobre um dos dois sensores.
    """
    return float(l_m) / float(c_m_s)


def posicao_a_partir_do_sensor_A(l_m, c_m_s, delta_t_s):
    return (float(l_m) + float(c_m_s) * float(delta_t_s)) / 2.0


def incerteza_de_posicao_m(c_m_s, delta_t_s, incerteza_de_delta_t_s=0.0,
                           incerteza_de_c_m_s=0.0):
    """dx = sqrt( (c * d(delta_t) / 2)^2 + (delta_t * dc / 2)^2 )."""
    termo_tempo = float(c_m_s) * float(incerteza_de_delta_t_s) / 2.0
    termo_c = float(delta_t_s) * float(incerteza_de_c_m_s) / 2.0
    return float(np.hypot(termo_tempo, termo_c))


def localizar(l_m, c_m_s, delta_t_s, posicao_do_sensor_A_m,
              incerteza_de_delta_t_s=0.0, incerteza_de_c_m_s=0.0):
    """Posicao estimada, ja limitada ao trecho entre os sensores.

    A verificacao de faixa fisica de delta_t e responsabilidade de A-13 e
    acontece antes desta chamada. O limite aplicado aqui e a ultima barreira
    contra publicar uma posicao fora do trecho: delta_t pode ficar a meia
    amostra da borda por quantizacao temporal e ainda assim ser aceito por
    A-13. Quando isso acontece o registro marca `posicao_limitada_a_faixa`.

    Diferenca temporal igual a zero e um resultado valido, nao um caso
    inconclusivo: significa evento equidistante dos sensores.
    """
    l_m = float(l_m)
    bruto = posicao_a_partir_do_sensor_A(l_m, c_m_s, delta_t_s)
    limitado = min(max(bruto, 0.0), l_m)
    return {
        'posicao_estimada_rel_sensor_A_m': float(limitado),
        'posicao_estimada_m': float(posicao_do_sensor_A_m) + float(limitado),
        'posicao_sem_limite_rel_sensor_A_m': float(bruto),
        'posicao_limitada_a_faixa': bool(limitado != bruto),
        'incerteza_de_posicao_m': incerteza_de_posicao_m(
            c_m_s, delta_t_s, incerteza_de_delta_t_s, incerteza_de_c_m_s),
        'velocidade_de_onda_usada_m_s': float(c_m_s),
        'origem_da_velocidade_de_onda': (
            'parametros_do_detector do pacote do ensaio (A-10)'),
    }

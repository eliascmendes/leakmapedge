"""LEAKMAP - definicao da matriz de ensaios essencial.

Tres eixos, combinados de forma completa:

  posicao   as cinco posicoes ja simuladas em 02_bancada (60, 80, 100, 120,
            140 m), que chegam aqui como os ensaios EV-01..EV-05 de
            03_ensaios/amostras/leakmap_amostras_v1.json;
  ruido     tres configuracoes do modelo de sensor (A-09), incluindo a
            configuracao neutra, que serve de conferencia de regressao contra
            o resultado v1;
  velocidade  dois valores de velocidade de onda declarados ao detector.

Mais uma familia de ensaios sem evento, usada para medir a taxa de falso
alarme exigida pelo criterio de conclusao de A-11.

SOBRE O EIXO DE VELOCIDADE DE ONDA
----------------------------------
Este eixo varia a velocidade de onda que o detector assume, nao a velocidade
com que o solucionador gerou os sinais. A razao e pratica e esta registrada
aqui para nao ser confundida com outra coisa: refazer a simulacao com outro c
exige TSNet, que depende do wntr, que nao compila neste ambiente. O que o eixo
mede e o efeito de c assumido diferente de c real, que e justamente o modo de
erro que existe em campo, porque c nunca e conhecido exatamente. O que o eixo
nao cobre e a mudanca da forma de onda que um c diferente produziria no
escoamento; isso fica para quando a bancada com TSNet estiver disponivel.
"""
import numpy as np

import modelo_sensor as MS

# Faixa util do transmissor assumida em toda a matriz, em m de carga.
# 0 a 100 m de carga corresponde a cerca de 0 a 9,8 bar.
ESCALA_MIN_M = 0.0
ESCALA_MAX_M = 100.0

ENSAIOS_DE_ORIGEM = ('EV-01', 'EV-02', 'EV-03', 'EV-04', 'EV-05')

# Comprimento dos ensaios sem evento, na base do solucionador. Com decimacao
# por 4 sobram cerca de 500 amostras por canal, o que da uma contagem de
# oportunidades de decisao grande o bastante para a taxa de falso alarme
# significar alguma coisa.
N_PONTOS_SEM_EVENTO = 2000
SEMENTES_SEM_EVENTO = (101, 102, 103, 104, 105)


def _config(ruido_m, bits, corte_hz, atraso_comum_s, skew_s, jitter_s,
            offset_a, offset_b, semente):
    cfg = MS.config_neutra()
    cfg['banda'].update(ligado=True, corte_hz=corte_hz, ordem=2)
    cfg['atraso_comum'].update(ligado=True, atraso_s=atraso_comum_s)
    cfg['diferenca_de_atraso'].update(ligado=True, atraso_s=skew_s)
    cfg['erro_de_sincronizacao'].update(ligado=True, jitter_s=jitter_s,
                                        semente=semente)
    cfg['offset'].update(ligado=True, offset_A_m=offset_a, offset_B_m=offset_b)
    cfg['ruido'].update(ligado=True, desvio_padrao_m=ruido_m,
                        semente=semente + 1000)
    cfg['saturacao'].update(ligado=True, minimo_m=ESCALA_MIN_M,
                            maximo_m=ESCALA_MAX_M)
    cfg['quantizacao'].update(ligado=True, bits=bits,
                              fundo_de_escala_min_m=ESCALA_MIN_M,
                              fundo_de_escala_max_m=ESCALA_MAX_M)
    return cfg


def configuracoes_de_sensor(semente=0):
    """As tres configuracoes do eixo de ruido.

    `semente` desloca as sementes de ruido e de jitter, para que ensaios
    diferentes da mesma linha nao recebam a mesma realizacao de ruido.
    """
    return {
        # Conferencia de regressao: nenhum efeito ligado, saida identica a
        # entrada. O resultado tem de reproduzir o baseline v1.
        'sem_ruido': MS.config_neutra(),
        # Transmissor bom: 0,02 m de ruido (cerca de 2 mbar), 16 bits.
        'baixo': _config(ruido_m=0.02, bits=16, corte_hz=800.0,
                         atraso_comum_s=1.0e-3, skew_s=1.0e-4,
                         jitter_s=5.0e-6, offset_a=0.02, offset_b=-0.03,
                         semente=semente),
        # Transmissor modesto e mal casado: 0,20 m de ruido (cerca de
        # 20 mbar), 12 bits, banda estreita e 0,4 ms de diferenca de atraso
        # entre os canais.
        'alto': _config(ruido_m=0.20, bits=12, corte_hz=250.0,
                        atraso_comum_s=2.0e-3, skew_s=4.0e-4,
                        jitter_s=3.0e-5, offset_a=0.10, offset_b=-0.15,
                        semente=semente + 500),
    }


NIVEIS_DE_RUIDO = ('sem_ruido', 'baixo', 'alto')


def velocidades(c_efetiva_m_s):
    """Os dois valores de c declarados ao detector.

    `casada` e o proprio c efetivo do solucionador. `desviada` esta 2% acima,
    desvio compativel com a incerteza de modulo de elasticidade e de teor de
    gas dissolvido de uma linha real.
    """
    return {
        'casada': {'c_m_s': float(c_efetiva_m_s),
                   'incerteza_m_s': 0.0,
                   'desvio_relativo': 0.0},
        'desviada': {'c_m_s': float(c_efetiva_m_s) * 1.02,
                     'incerteza_m_s': float(c_efetiva_m_s) * 0.02,
                     'desvio_relativo': 0.02},
    }


def sinal_sem_evento(h0_a, h0_b, n_pontos, ts, t0=0.0):
    """Ensaio sem evento: regime permanente puro, antes do modelo de sensor.

    O que o detector ve depois disso e so o que a configuracao de sensor
    daquela linha acrescentar. Na linha `sem_ruido` o sinal fica exatamente
    constante, e a taxa de falso alarme e zero por construcao: nao existe
    fonte de variacao. As duas linhas com ruido sao as que produzem numero.
    """
    t = t0 + np.arange(n_pontos, dtype=float) * ts
    return t, np.full(n_pontos, float(h0_a)), np.full(n_pontos, float(h0_b))

"""LEAKMAP - fisica da linha: o que a mecanica dos fluidos tira do mesmo sinal.

A deteccao e a localizacao (detector.py, posicao.py) dizem SE houve um evento
e ONDE. Este modulo, ao lado delas e sem mudar a decisao nem a posicao
publicadas, usa os mesmos dois sinais de pressao para responder mais:
QUANTO esta vazando, por que furo, com que confianca na posicao, e com que
velocidade de onda a conta deveria ser feita. Tudo sai de principios de
mecanica dos fluidos e de propagacao de ondas em conduto forcado, com a
hipotese declarada em cada funcao.

1. Escoamento em regime (Darcy-Weisbach). A perda de carga medida entre os
   sensores, antes do evento, da a velocidade media do escoamento:

       h_f = f (L / D) V^2 / (2 g)

   com o fator de atrito f de Swamee-Jain (forma explicita de Colebrook), que
   depende de Re = V D / nu; por isso a solucao e iterativa. Vazao de regime
   Q0 = V A. Nao precisa de medidor de vazao.

2. Atenuacao da onda por atrito. Linearizando o termo de atrito das
   equacoes do transitorio (metodo das caracteristicas) em torno do regime, a
   amplitude de uma frente pequena decai com a distancia como

       dH(s) = dH(0) exp(-alpha s),   alpha = f V0 / (2 D c)

   O sensor mais longe do furo ve um degrau um pouco menor; a correcao devolve
   a amplitude no ponto do vazamento.

3. Degrau da onda em cada sensor. Nivel medio numa janela logo depois da
   chegada contra o nivel medio logo antes. A janela depois acaba antes da
   primeira reflexao: a onda que passa pelo sensor, bate no contorno mais
   proximo (reservatorio, tanque, fim da linha) e volta, em 2 d / c.

4. Vazao do vazamento (Joukowsky). Um furo que se abre de repente retira dQ;
   metade do deficit vai para cada lado, e cada frente leva

       dH = c (dQ / 2) / (g A)   =>   dQ = 2 g A dH / c

   dQ e a vazao que sai pelo furo com a pressao ja rebaixada.

5. Orificio equivalente (Torricelli). Com a carga de pressao no furo depois da
   queda, h = H(x) - dH (H(x) pela linha piezometrica de regime, linear entre
   os sensores):

       dQ = Cd A_o sqrt(2 g h)   =>   C_e = dQ / sqrt(h),  d = sqrt(4 A_o / pi)

   Cd = 0,61, orificio de borda viva. C_e e o coeficiente de emissor, o mesmo
   dos simuladores hidraulicos; com ele sai tambem a vazao que o furo teria na
   pressao de regime, C_e sqrt(H(x)).

6. Incerteza de posicao completa. x = (L + c dt) / 2, entao

       sigma_x^2 = (c sigma_dt / 2)^2 + (dt sigma_c / 2)^2

   e sigma_dt ganha, alem das marcas (detector.py), o periodo de atualizacao
   T do transmissor: cada canal marca a chegada na atualizacao seguinte, um
   erro uniforme em [0, T) e independente entre os canais, variancia T^2 / 12
   em cada um e T^2 / 6 na diferenca. Um transmissor HART comum (T de
   dezenas de ms) domina todo o resto.

7. Calibracao da velocidade da onda. Para uma fonte em posicao conhecida, a
   diferenca de tempo e linear na lentidao s = 1/c:

       dt = s * d,   d = 2 x - L (fonte no trecho),  d = -L ou +L (fonte alem
                                                        de A ou de B)

   Minimos quadrados ponderados em s, com varios eventos (manobras
   registradas, cuja posicao o cadastro da), dao c e a incerteza de c. Fontes
   fora do trecho sao as melhores: |d| = L, o maior braco possivel.

8. Menor vazamento detectavel. O detector declara quando a energia do
   passa-altas na janela curta passa de R vezes a de referencia (R = 12):
   para um degrau limpo, o pico do passa-altas e o proprio degrau, e o limiar
   fica em dH_min = sqrt(R / k) sigma, ou no piso de amplitude, o que for maior;
   k (cerca de 0,75) e a fracao da energia do degrau que o passa-altas de
   20 Hz, com constante de tempo de 8 ms, deixa na janela curta de 2,4 ms.
   Pela Joukowsky, dQ_min = 2 g A dH_min / c.

Nada aqui le a verdade do cenario: as entradas sao o sinal, o registro do
detector e a geometria da linha (a mesma do cadastro e do isometrico).
"""
import math

import numpy as np

import detector as D

G = 9.81
CD_ORIFICIO = 0.61                  # orificio de borda viva
ANTES_DA_CHEGADA_S = (0.030, 0.003)  # janela do nivel de antes: de 30 ms a 3 ms antes da chegada
INICIO_DEPOIS_S = 0.004             # a janela de depois comeca 4 ms depois da chegada (subida da frente)
DURACAO_DEPOIS_S = 0.020            # e dura ate 20 ms,
FOLGA_DA_REFLEXAO_S = 0.003         # acabando 3 ms antes da primeira reflexao
DURACAO_MINIMA_S = 0.004            # abaixo disso o canal nao mede degrau
ITERACOES = 50
# faixa de validade de Swamee-Jain (ajuste explicito de Colebrook): fora dela o fator de atrito nao merece confianca
RUGOSIDADE_RELATIVA_MAXIMA = 0.05
REYNOLDS_MINIMO_TURBULENTO = 4000.0
CORTES_DA_CALIBRACAO = 5            # rodadas de descarte de eventos discrepantes na calibracao de c
LIMITE_DO_CORTE = 3.0               # em desvios padrao


# --- 1. escoamento em regime ----------------------------------------------------------------

def fator_de_atrito(reynolds, rugosidade_relativa):
    """Darcy: 64/Re no laminar; Swamee-Jain (explicita de Colebrook) no turbulento."""
    re = abs(float(reynolds))
    if re <= 0.0:
        return float('nan')
    if re < 2000.0:
        return 64.0 / re
    return 0.25 / math.log10(rugosidade_relativa / 3.7 + 5.74 / re ** 0.9) ** 2


def escoamento_de_regime(carga_a_m, carga_b_m, l_m, diametro_m, rugosidade_m, viscosidade_m2_s,
                         cota_a_m=0.0, cota_b_m=0.0):
    """Velocidade e vazao de regime pela perda de carga entre os sensores (Darcy-Weisbach).

    `carga_*` e carga piezometrica (m de coluna do produto); a perda de carga e a diferenca das cargas
    totais, com as cotas. Sentido positivo de A para B.
    """
    h_f = (float(carga_a_m) + float(cota_a_m)) - (float(carga_b_m) + float(cota_b_m))
    sentido = 1.0 if h_f >= 0 else -1.0
    h_f = abs(h_f)
    area = math.pi * diametro_m ** 2 / 4.0
    rel = rugosidade_m / diametro_m
    f = 0.02
    v = 0.0
    for _ in range(ITERACOES):
        v = math.sqrt(2.0 * G * diametro_m * h_f / (f * l_m)) if h_f > 0 else 0.0
        if v == 0.0:
            break
        f_novo = fator_de_atrito(v * diametro_m / viscosidade_m2_s, rel)
        if abs(f_novo - f) < 1e-10:
            f = f_novo
            break
        f = f_novo
    re = v * diametro_m / viscosidade_m2_s
    valido = rel <= RUGOSIDADE_RELATIVA_MAXIMA and (re >= REYNOLDS_MINIMO_TURBULENTO or re < 2000.0)
    return {'perda_de_carga_m': float(h_f), 'velocidade_m_s': float(sentido * v),
            'vazao_m3_s': float(sentido * v * area), 'fator_de_atrito': float(f),
            'reynolds': float(re), 'area_m2': float(area), 'rugosidade_relativa': float(rel),
            'dentro_da_faixa_de_validade': bool(valido)}


# --- 2. atenuacao da onda por atrito ------------------------------------------------------------

def atenuacao_por_atrito(fator_de_atrito_f, velocidade_m_s, diametro_m, c_m_s):
    """alpha (1/m) do decaimento exp(-alpha s) de uma frente pequena, pelo atrito linearizado."""
    return abs(float(fator_de_atrito_f) * float(velocidade_m_s) / (2.0 * float(diametro_m) * float(c_m_s)))


def atenuacao_medida(degrau_a_m, degrau_b_m, distancia_a_m, distancia_b_m, l_m):
    """alpha pela razao das amplitudes: dH_A / dH_B = exp(-alpha (d_A - d_B)).

    Dois sensores, duas incognitas (a amplitude no furo e alpha): o atrito sai medido, sem depender de rugosidade
    nem de fator de atrito. So vale com o furo longe do meio do trecho (|d_B - d_A| >= L/4); perto do meio a razao
    nao informa nada. Um alpha negativo e ruido e vira zero.
    """
    braco = float(distancia_b_m) - float(distancia_a_m)
    if abs(braco) < float(l_m) / 4.0 or degrau_a_m <= 0 or degrau_b_m <= 0:
        return None
    return max(0.0, math.log(float(degrau_a_m) / float(degrau_b_m)) / braco)


# --- 3. degrau da onda em cada sensor -----------------------------------------------------------

def janela_depois(distancia_ao_contorno_m, c_m_s, periodo_de_atualizacao_s=0.0):
    """(inicio, fim) da janela de depois, em segundos a partir da chegada, ou None se nao cabe.

    O inicio espera a subida da frente e a atualizacao seguinte do transmissor; o fim para antes da primeira
    reflexao no contorno mais proximo alem do sensor (2 d / c).
    """
    inicio = INICIO_DEPOIS_S + float(periodo_de_atualizacao_s)
    fim = inicio + DURACAO_DEPOIS_S
    if distancia_ao_contorno_m is not None:
        fim = min(fim, 2.0 * float(distancia_ao_contorno_m) / float(c_m_s) - FOLGA_DA_REFLEXAO_S)
    return (inicio, fim) if fim - inicio >= DURACAO_MINIMA_S else None


def nivel_antes_da_chegada(sinal, tempo_s, indice_de_chegada):
    """Nivel de regime (media) e ruido (desvio) logo antes da chegada; None se o registro comeca em cima dela."""
    x = np.asarray(sinal, dtype=float)
    t = np.asarray(tempo_s, dtype=float)
    t0 = t[int(indice_de_chegada)]
    antes = x[(t >= t0 - ANTES_DA_CHEGADA_S[0]) & (t <= t0 - ANTES_DA_CHEGADA_S[1])]
    if len(antes) < 3:
        return None
    return {'nivel_m': float(np.mean(antes)), 'ruido_m': float(np.std(antes, ddof=1)), 'n': int(len(antes))}


def degrau_no_sensor(sinal, tempo_s, indice_de_chegada, janela):
    """Nivel medio depois menos o de antes, com a incerteza do ruido; None se a janela sai do registro."""
    antes = nivel_antes_da_chegada(sinal, tempo_s, indice_de_chegada)
    x = np.asarray(sinal, dtype=float)
    t = np.asarray(tempo_s, dtype=float)
    t0 = t[int(indice_de_chegada)]
    depois = x[(t >= t0 + janela[0]) & (t <= t0 + janela[1])]
    if antes is None or len(depois) < 3:
        return None
    sigma = antes['ruido_m'] * math.sqrt(1.0 / antes['n'] + 1.0 / len(depois))
    return {'degrau_m': float(np.mean(depois) - antes['nivel_m']), 'incerteza_m': float(sigma),
            'nivel_antes_m': antes['nivel_m'], 'ruido_m': antes['ruido_m'],
            'janela_depois_s': [float(janela[0]), float(janela[1])]}


# --- 4 e 5. vazao do vazamento e orificio equivalente ----------------------------------------------

def vazao_por_joukowsky(degrau_no_furo_m, c_m_s, area_m2):
    """dQ = 2 g A dH / c: metade do deficit de vazao em cada frente."""
    return 2.0 * G * float(area_m2) * abs(float(degrau_no_furo_m)) / float(c_m_s)


def orificio_equivalente(vazao_m3_s, carga_de_pressao_m, cd=CD_ORIFICIO):
    """Coeficiente de emissor C_e = Q / sqrt(h) e diametro do orificio de borda viva que da a mesma vazao."""
    h = float(carga_de_pressao_m)
    if h <= 0:
        return None
    c_e = float(vazao_m3_s) / math.sqrt(h)
    area = c_e / (cd * math.sqrt(2.0 * G))
    return {'coeficiente_de_emissor_m2_5_s': c_e, 'diametro_equivalente_m': math.sqrt(4.0 * area / math.pi),
            'area_equivalente_m2': area, 'cd': cd}


def caracterizar_vazamento(ensaio, registro, geometria, periodo_de_atualizacao_s=0.0):
    """Regime, degraus, vazao do vazamento e furo equivalente de um registro localizado como vazamento.

    `geometria`: diametro_interno_m, rugosidade_m, viscosidade_m2_s e, opcionais, cota_a_m, cota_b_m,
    contorno_antes_de_a_m e contorno_depois_de_b_m (distancias dos sensores aos contornos que refletem a onda).
    Devolve None para o que nao e vazamento localizado.
    """
    if registro.get('classe') != D.CLASSE_LOCALIZADO:
        return None
    par = ensaio['parametros_do_detector']
    l_m, c = float(par['distancia_entre_sensores_L_m']), float(par['velocidade_de_onda_m_s'])
    diametro = float(geometria['diametro_interno_m'])
    t = np.asarray(ensaio['tempo_s'], dtype=float)
    canais = {s: (np.asarray(ensaio['canal_%s_carga_m' % s], dtype=float), registro['canal_%s' % s])
              for s in 'AB'}
    x = float(registro['posicao_estimada_rel_sensor_A_m'])
    distancia = {'A': x, 'B': l_m - x}
    contorno = {'A': geometria.get('contorno_antes_de_a_m'), 'B': geometria.get('contorno_depois_de_b_m')}

    niveis, degraus = {}, {}
    for s, (sinal, det) in canais.items():
        niveis[s] = nivel_antes_da_chegada(sinal, t, det['indice_de_chegada'])
        janela = janela_depois(contorno[s], c, periodo_de_atualizacao_s)
        degraus[s] = None if janela is None else degrau_no_sensor(sinal, t, det['indice_de_chegada'], janela)
    if niveis['A'] is None or niveis['B'] is None:
        return {'aplicado': False, 'motivo': 'registro sem nivel de regime antes da chegada'}
    usados = [s for s in 'AB' if degraus[s] is not None]
    if not usados:
        # transmissor lento demais para a janela antes da primeira reflexao, nos dois canais
        return {'aplicado': False, 'motivo': 'sem janela limpa antes da reflexao em nenhum canal'}

    regime = escoamento_de_regime(niveis['A']['nivel_m'], niveis['B']['nivel_m'], l_m, diametro,
                                  geometria['rugosidade_m'], geometria['viscosidade_m2_s'],
                                  geometria.get('cota_a_m', 0.0), geometria.get('cota_b_m', 0.0))
    alpha_teorico = atenuacao_por_atrito(regime['fator_de_atrito'], regime['velocidade_m_s'], diametro, c)
    alpha, origem_alpha = alpha_teorico, 'teorica (f V / 2 D c)'
    if not regime['dentro_da_faixa_de_validade']:
        # atrito teorico fora da faixa de Colebrook/Swamee-Jain: melhor nao corrigir do que corrigir errado
        alpha, origem_alpha = 0.0, 'sem correcao: atrito teorico fora da faixa de validade'
    if len(usados) == 2:
        medido = atenuacao_medida(-degraus['A']['degrau_m'], -degraus['B']['degrau_m'], distancia['A'],
                                  distancia['B'], l_m)
        if medido is not None:
            alpha, origem_alpha = medido, 'medida pela razao das amplitudes nos dois sensores'

    # degrau no ponto do furo, visto de cada sensor, com o atrito descontado
    no_furo, pesos = {}, {}
    for s in usados:
        dh = -degraus[s]['degrau_m']                     # queda: degrau negativo
        no_furo[s] = dh * math.exp(alpha * distancia[s])
        pesos[s] = 1.0 / max(degraus[s]['incerteza_m'], 1e-6) ** 2
    dh_furo = sum(no_furo[s] * pesos[s] for s in usados) / sum(pesos.values())
    if dh_furo <= 0:
        return {'aplicado': False, 'motivo': 'degrau medido nao e queda'}
    sigma_ruido = 1.0 / math.sqrt(sum(pesos.values()))
    discordancia = abs(no_furo['A'] - no_furo['B']) / 2.0 if len(usados) == 2 else 0.0
    sigma_dh = math.hypot(sigma_ruido, discordancia)

    q = vazao_por_joukowsky(dh_furo, c, regime['area_m2'])
    sigma_c = float(par.get('incerteza_de_velocidade_de_onda_m_s', 0.0))
    sigma_q_rel = math.hypot(sigma_dh / dh_furo, sigma_c / c)

    # linha piezometrica de regime (linear entre os sensores) e carga de pressao no furo depois da queda
    h_a, h_b = niveis['A']['nivel_m'], niveis['B']['nivel_m']
    cota = geometria.get('cota_a_m', 0.0) + (geometria.get('cota_b_m', 0.0) - geometria.get('cota_a_m', 0.0)) * x / l_m
    carga_regime_no_furo = h_a + (h_b - h_a) * x / l_m
    pressao_depois = carga_regime_no_furo - dh_furo - cota
    orificio = orificio_equivalente(q, pressao_depois)

    saida = {
        'aplicado': True,
        'escoamento_de_regime': dict(regime, vazao_m3_h=regime['vazao_m3_s'] * 3600.0),
        'onda': {'velocidade_m_s': c, 'atenuacao_por_atrito_1_m': alpha, 'origem_da_atenuacao': origem_alpha,
                 'atenuacao_teorica_1_m': alpha_teorico,
                 'canais_usados': usados,
                 'degrau_medido_m': {s: degraus[s]['degrau_m'] for s in usados},
                 'degrau_no_furo_visto_de_m': no_furo, 'degrau_no_furo_m': dh_furo,
                 'incerteza_do_degrau_m': sigma_dh, 'janelas_depois_s': {s: degraus[s]['janela_depois_s'] for s in usados}},
        'vazamento': {'vazao_m3_s': q, 'vazao_l_min': q * 60000.0, 'incerteza_relativa': sigma_q_rel,
                      'fracao_da_vazao_de_regime': (q / abs(regime['vazao_m3_s'])) if regime['vazao_m3_s'] else None,
                      'carga_de_regime_no_furo_m': carga_regime_no_furo, 'carga_de_pressao_depois_m': pressao_depois},
    }
    if orificio:
        saida['vazamento'].update(orificio)
        saida['vazamento']['vazao_na_pressao_de_regime_m3_s'] = (
            orificio['coeficiente_de_emissor_m2_5_s'] * math.sqrt(carga_regime_no_furo - cota))
    return saida


# --- 6. incerteza de posicao completa ------------------------------------------------------------

def incerteza_de_posicao(registro, periodo_de_atualizacao_s=0.0, incerteza_de_c_m_s=None):
    """sigma_x com as marcas, o periodo de atualizacao do transmissor e a velocidade da onda."""
    if registro.get('delta_t_s') is None:
        return None
    par = registro['parametros_do_detector']
    c = float(par['velocidade_de_onda_m_s'])
    sigma_c = float(par.get('incerteza_de_velocidade_de_onda_m_s', 0.0)
                    if incerteza_de_c_m_s is None else incerteza_de_c_m_s)
    dt = float(registro['delta_t_s'])
    marcas = float(registro.get('incerteza_de_delta_t_s') or 0.0)
    atualizacao = float(periodo_de_atualizacao_s) / math.sqrt(6.0)
    sigma_dt = math.hypot(marcas, atualizacao)
    termos = {'marcas_m': c * marcas / 2.0, 'atualizacao_do_transmissor_m': c * atualizacao / 2.0,
              'velocidade_da_onda_m': abs(dt) * sigma_c / 2.0}
    return {'incerteza_m': math.sqrt(sum(v ** 2 for v in termos.values())), 'componentes_m': termos,
            'incerteza_de_delta_t_s': sigma_dt}


# --- 7. calibracao da velocidade da onda ------------------------------------------------------------

def diferenca_de_percurso(posicao_rel_sensor_a_m, l_m):
    """d = 2x - L no trecho; -L antes de A e +L depois de B (a onda passa por um sensor e percorre L ate o outro).

    Com dt = tA - tB: fonte perto de A chega antes em A, dt < 0.
    """
    x = float(posicao_rel_sensor_a_m)
    return max(-float(l_m), min(float(l_m), 2.0 * x - float(l_m)))


def calibrar_velocidade(eventos):
    """c e sigma_c por minimos quadrados ponderados na lentidao s = 1/c: dt_i = s d_i.

    `eventos`: lista de {'delta_t_s', 'incerteza_de_delta_t_s', 'diferenca_de_percurso_m'}. Eventos com d = 0 (no
    meio do trecho) nao informam nada sobre c e sao ignorados.
    """
    uteis = [e for e in eventos if abs(e['diferenca_de_percurso_m']) > 1e-9 and e.get('delta_t_s') is not None]
    if not uteis:
        return None
    w = np.array([1.0 / max(float(e.get('incerteza_de_delta_t_s') or 0.0), 1e-7) ** 2 for e in uteis])
    d = np.array([float(e['diferenca_de_percurso_m']) for e in uteis])
    dt = np.array([float(e['delta_t_s']) for e in uteis])
    usar = np.ones(len(uteis), dtype=bool)
    for _ in range(CORTES_DA_CALIBRACAO):
        s = float(np.sum(w[usar] * d[usar] * dt[usar]) / np.sum(w[usar] * d[usar] ** 2))
        residuos = dt - s * d
        # evento mal marcado (transmissor lento, frente perdida) puxa a reta: sai o que passa de 3 sigma, com a
        # escala medida pelo desvio absoluto mediano (1,4826 MAD), que o proprio evento ruim nao consegue inflar
        normalizados = np.abs(residuos) * np.sqrt(w)
        escala = max(1.0, 1.4826 * float(np.median(normalizados[usar])))
        novo = normalizados <= LIMITE_DO_CORTE * escala
        if usar.sum() - novo.sum() <= 0 or novo.sum() < 2 or np.array_equal(novo, usar):
            break
        usar = novo
    s = float(np.sum(w[usar] * d[usar] * dt[usar]) / np.sum(w[usar] * d[usar] ** 2))
    residuos = dt - s * d
    sigma_s = float(1.0 / math.sqrt(np.sum(w[usar] * d[usar] ** 2)))
    if usar.sum() > 1:
        # espalhamento observado: se os residuos forem maiores que as incertezas declaradas, a incerteza cresce
        sigma_s *= math.sqrt(max(_espalhamento(w, residuos, usar) ** 2, 1.0))
    c = 1.0 / s
    return {'velocidade_m_s': c, 'incerteza_m_s': sigma_s / s ** 2, 'n_eventos': int(usar.sum()),
            'n_descartados': int(len(uteis) - usar.sum()), 'residuos_s': [float(r) for r in residuos]}


def _espalhamento(w, residuos, usar):
    """Raiz do chi-quadrado reduzido dos residuos usados."""
    n = int(usar.sum())
    return math.sqrt(float(np.sum(w[usar] * residuos[usar] ** 2)) / max(n - 1, 1))


def relocalizar(registro, velocidade_m_s, incerteza_m_s=0.0):
    """Posicao e incerteza refeitas com uma velocidade de onda calibrada (mesmo delta_t das marcas)."""
    if registro.get('delta_t_s') is None:
        return None
    par = registro['parametros_do_detector']
    l_m = float(par['distancia_entre_sensores_L_m'])
    dt = float(registro['delta_t_s'])
    x = min(max((l_m + float(velocidade_m_s) * dt) / 2.0, 0.0), l_m)
    sigma_dt = float(registro.get('incerteza_de_delta_t_s') or 0.0)
    return {'posicao_estimada_rel_sensor_A_m': x, 'posicao_estimada_m': float(par['posicao_sensor_A_m']) + x,
            'velocidade_de_onda_usada_m_s': float(velocidade_m_s),
            'incerteza_m': math.hypot(velocidade_m_s * sigma_dt / 2.0, dt * incerteza_m_s / 2.0)}


def posicao_com_adveccao(l_m, c_m_s, velocidade_do_escoamento_m_s, delta_t_s):
    """x a partir de A com as caracteristicas V +- c: a onda sobe contra o escoamento a c - V e desce a c + V.

    Com o escoamento de A para B (V > 0): tA = x / (c - V), tB = (L - x) / (c + V), e

        x = [dt (c^2 - V^2) + L (c - V)] / (2 c)

    Para V = 0 volta a x = (L + c dt) / 2. A diferenca, cerca de -L V / (2 c), e um vies sistematico: 0,42 m numa
    linha de 700 m a 1,46 m/s. A teoria classica do golpe de ariete (e o TSNet) despreza V diante de c; esta
    correcao vale para o campo, nao para comparar com essas simulacoes.
    """
    c, v, dt, l = float(c_m_s), float(velocidade_do_escoamento_m_s), float(delta_t_s), float(l_m)
    return (dt * (c * c - v * v) + l * (c - v)) / (2.0 * c)


# --- 8. menor vazamento detectavel ----------------------------------------------------------------

def fator_da_janela_curta(cal, periodo_de_amostragem_s):
    """Fracao da energia de um degrau que o passa-altas deixa na janela curta.

    O passa-altas de primeira ordem responde ao degrau h com h exp(-t / tau), tau = 1 / (2 pi f_c); a energia media
    numa janela de duracao T depois da frente e h^2 (1 - exp(-2T/tau)) / (2T/tau).
    """
    tau = 1.0 / (2.0 * math.pi * float(cal['corte_passa_altas_hz']))
    razao = 2.0 * cal['n_curta'] * float(periodo_de_amostragem_s) / tau
    return (1.0 - math.exp(-razao)) / razao


def menor_vazamento_detectavel(sigma_ruido_m, c_m_s, area_m2, cal=None, resolucao_declarada_m=None,
                               periodo_de_amostragem_s=None):
    """Limiar do detector em carga e a vazao correspondente pela Joukowsky.

    A razao de energia R compara a janela curta com a de referencia (ruido, sigma^2): o degrau h passa quando
    h^2 k >= R sigma^2, com k a fracao de energia que o passa-altas deixa na janela curta (fator_da_janela_curta).
    """
    cal = cal or D.calibracao_padrao()
    k = fator_da_janela_curta(cal, periodo_de_amostragem_s) if periodo_de_amostragem_s else 1.0
    dh_ruido = math.sqrt(cal['limiar_de_razao'] / k) * float(sigma_ruido_m)
    dh_piso = D.piso_de_amplitude(cal, resolucao_declarada_m)
    dh = max(dh_ruido, dh_piso)
    return {'degrau_minimo_m': dh, 'limitado_por': 'ruido' if dh_ruido >= dh_piso else 'piso de amplitude',
            'fracao_de_energia_na_janela_curta': k, 'vazao_minima_m3_s': vazao_por_joukowsky(dh, c_m_s, area_m2)}


def periodo_de_atualizacao_do_ensaio(ensaio):
    """Periodo de atualizacao da saida do transmissor, lido dos efeitos de sensor do ensaio (0 se continua).

    Na planta, o valor vem da folha de dados do transmissor instalado.
    """
    efeitos = (ensaio.get('efeitos_de_sensor_aplicados') or {}).get('efeitos') or []
    for e in efeitos:
        if e.get('efeito') == 'atualizacao':
            return float(e['parametros'].get('periodo_s', 0.0))
    return 0.0


def caracterizar_pacote(pacote, registros, geometria, periodo_de_atualizacao_por_id=None):
    """Acrescenta `fisica` aos registros (vazamento localizado) e `incerteza_fisica` a todo registro com delta_t."""
    periodos = periodo_de_atualizacao_por_id or {}
    for ensaio, registro in zip(pacote['ensaios'], registros):
        periodo = float(periodos.get(ensaio['id'], periodo_de_atualizacao_do_ensaio(ensaio)))
        inc = incerteza_de_posicao(registro, periodo)
        if inc is not None:
            registro['incerteza_fisica'] = dict(inc, periodo_de_atualizacao_s=periodo)
        fis = caracterizar_vazamento(ensaio, registro, geometria, periodo)
        if fis is not None:
            registro['fisica'] = fis
    return registros

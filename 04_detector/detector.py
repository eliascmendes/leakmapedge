"""LEAKMAP - detector do produto. Etapas A-11 a A-15.

A-11  pre-processamento e deteccao por razao de energia curta/longa
A-12  marcacao dos tempos de chegada com retrocesso ate a faixa de ruido
A-13  decisao de evidencia suficiente antes de localizar
A-14  calculo da posicao
A-15  montagem do registro de resultado, um por ensaio

Este modulo le apenas `parametros` e `amostras` (pacote da etapa A-10).
Nunca le `03_ensaios/verdade_do_cenario`: a posicao real do vazamento e de
uso exclusivo do avaliador (A-17), que roda como processo separado.

Nao ha CUSUM aqui. O CUSUM interno do TSNet foi o substituto provisorio do
baseline v1, para fechar a cadeia A-01..A-08 antes de existir detector; a
cadeia abaixo e a especificada em A-11.
"""
import numpy as np

import posicao as P

# --- calibracao padrao (A-11) ----------------------------------------------
# Janelas em amostras da base decimada. A janela longa precede a curta com uma
# guarda entre as duas, para que a frente de onda nao contamine a referencia
# de ruido contra a qual ela esta sendo comparada.
N_CURTA = 6
N_GUARDA = 3
N_LONGA = 30

CORTE_PASSA_ALTAS_HZ = 20.0   # remove deriva, preserva a frente de ~1 ms
LIMIAR_DE_RAZAO = 12.0        # energia curta / energia longa

# Limiar minimo absoluto, em m de carga. E o parametro que impede o detector
# de disparar sobre ruido numerico do simulador: na verificacao do documento o
# desvio-padrao da carga antes do evento ficou na ordem de 1e-7 m, valor sem
# significado fisico. Este piso vale ~1 mbar e fica sempre acima da resolucao
# declarada do instrumento (ver `piso_de_amplitude`).
PISO_DE_AMPLITUDE_M = 0.01
FATOR_SOBRE_A_RESOLUCAO = 1.0

K_FAIXA_DE_RUIDO = 3.0        # A-12: largura da faixa de ruido, em sigma

CLASSE_LOCALIZADO = 'localizado'
CLASSE_SEM_LOCALIZACAO = 'detectado_sem_localizacao'
CLASSE_SEM_DETECCAO = 'sem_deteccao'
CLASSE_FALHA = 'falha_execucao'


def calibracao_padrao():
    return {
        'n_curta': N_CURTA,
        'n_guarda': N_GUARDA,
        'n_longa': N_LONGA,
        'corte_passa_altas_hz': CORTE_PASSA_ALTAS_HZ,
        'limiar_de_razao': LIMIAR_DE_RAZAO,
        'piso_de_amplitude_m': PISO_DE_AMPLITUDE_M,
        'fator_sobre_a_resolucao': FATOR_SOBRE_A_RESOLUCAO,
        'k_faixa_de_ruido': K_FAIXA_DE_RUIDO,
    }


def piso_de_amplitude(cal, resolucao_declarada_m):
    """Limiar minimo de amplitude efetivamente usado, em m de carga.

    E o maior entre o piso absoluto declarado na calibracao e a resolucao do
    instrumento multiplicada por `fator_sobre_a_resolucao`. Assim o limiar
    nunca fica abaixo da resolucao declarada do sensor, que e o tratamento
    previsto em A-11 para a falha "limiar abaixo do ruido numerico".
    """
    piso = float(cal['piso_de_amplitude_m'])
    if resolucao_declarada_m:
        piso = max(piso, float(cal['fator_sobre_a_resolucao'])
                   * float(resolucao_declarada_m))
    return piso


def piso_de_energia(cal, resolucao_declarada_m):
    """Energia minima que se pode atribuir a janela de referencia, em m^2.

    Uma janela de referencia nunca e de fato mais silenciosa que o proprio
    ruido de quantizacao do conversor: se ela le exatamente constante, e
    porque a variacao ficou abaixo de um degrau, nao porque nao exista. O
    piso e a variancia do ruido de quantizacao uniforme, (degrau^2)/12,
    calculada sobre o mesmo piso de amplitude de `piso_de_amplitude`.

    Sem esse piso a razao de energia divide por zero em qualquer trecho
    perfeitamente constante, que e exatamente o caso dos ensaios sem ruido.
    O piso nao torna o detector menos sensivel: exigir razao acima do limiar
    contra este piso equivale a exigir amplitude acima do piso de amplitude,
    que a condicao absoluta ja exige.
    """
    return piso_de_amplitude(cal, resolucao_declarada_m) ** 2 / 12.0


# --- A-11: pre-processamento e deteccao ------------------------------------

def passa_altas(x, corte_hz, ts):
    """Passa-altas de primeira ordem, em NumPy puro.

    y[n] = a * (y[n-1] + x[n] - x[n-1]), com a = tau / (tau + Ts).
    Remove o nivel de regime e a deriva lenta; y[0] = 0.
    """
    x = np.asarray(x, dtype=float)
    tau = 1.0 / (2.0 * np.pi * float(corte_hz))
    a = tau / (tau + ts)
    y = np.empty_like(x)
    y[0] = 0.0
    for n in range(1, len(x)):
        y[n] = a * (y[n - 1] + x[n] - x[n - 1])
    return y


def energia_em_janela(y, n_janela):
    """Energia media por amostra em uma janela causal de `n_janela` amostras.

    Posicao n devolve a media de y[n-n_janela+1 .. n]^2. As primeiras
    n_janela-1 posicoes ficam NaN: nao ha janela completa.
    """
    y2 = np.asarray(y, dtype=float) ** 2
    acumulado = np.concatenate([[0.0], np.cumsum(y2)])
    saida = np.full(len(y2), np.nan)
    n = np.arange(n_janela - 1, len(y2))
    saida[n] = (acumulado[n + 1] - acumulado[n - n_janela + 1]) / n_janela
    return saida


def razao_de_energia(y, cal, piso_de_energia_m2):
    """Razao entre a energia da janela curta e a da janela longa anterior.

    Devolve (razao, energia_curta, energia_longa). A janela longa termina
    `n_curta + n_guarda` amostras antes do fim da janela curta, de modo que a
    referencia de ruido e sempre anterior ao trecho sob teste. O denominador
    e limitado por baixo pelo piso de energia, para que a razao continue
    finita quando a referencia le exatamente constante.
    """
    nc, ng, nl = cal['n_curta'], cal['n_guarda'], cal['n_longa']
    e_curta = energia_em_janela(y, nc)
    e_longa_bruta = energia_em_janela(y, nl)

    recuo = nc + ng
    e_longa = np.full(len(y), np.nan)
    if recuo < len(y):
        e_longa[recuo:] = e_longa_bruta[:len(y) - recuo]

    with np.errstate(invalid='ignore'):
        razao = e_curta / np.maximum(e_longa, float(piso_de_energia_m2))
    return razao, e_curta, e_longa


def detectar_canal(sinal, ts, cal, resolucao_declarada_m):
    """A-11 em um canal. Devolve o dicionario de deteccao do canal."""
    y = passa_altas(sinal, cal['corte_passa_altas_hz'], ts)
    piso = piso_de_amplitude(cal, resolucao_declarada_m)
    piso_energia = piso_de_energia(cal, resolucao_declarada_m)
    razao, e_curta, e_longa = razao_de_energia(y, cal, piso_energia)

    rms_curta = np.sqrt(e_curta)

    valido = np.isfinite(razao) & np.isfinite(rms_curta)
    # Condicao 1: teste relativo contra o ruido da janela anterior.
    # Condicao 2: teste absoluto acima da resolucao do instrumento. E a
    # condicao 2 que impede disparo sobre variacao sem significado fisico.
    acima = valido & (razao >= cal['limiar_de_razao']) & (rms_curta >= piso)
    indices = np.nonzero(acima)[0]

    det = {
        'detectado': bool(len(indices)),
        'piso_de_amplitude_usado_m': float(piso),
        'piso_de_energia_usado_m2': float(piso_energia),
        'n_oportunidades_de_decisao': int(np.count_nonzero(valido)),
        'indice_de_cruzamento': int(indices[0]) if len(indices) else None,
        'razao_no_cruzamento': (float(razao[indices[0]]) if len(indices)
                                else None),
        'razao_maxima': (float(np.nanmax(razao[valido])) if valido.any()
                         else None),
        'rms_curta_no_cruzamento': (float(rms_curta[indices[0]])
                                    if len(indices) else None),
    }
    return det, y, razao, e_longa


# --- A-12: marcacao do tempo de chegada ------------------------------------

def marcar_chegada(y, e_longa, indice_de_cruzamento, tempo_s, ts, cal):
    """Retrocede do cruzamento ate o ponto em que o sinal sai da faixa de ruido.

    O cruzamento do limiar acontece depois da chegada real, porque a janela de
    energia curta precisa se encher. O retrocesso desfaz esse atraso: anda para
    tras enquanto o sinal estiver fora da faixa de ruido e marca a primeira
    amostra que ja estava fora dela.

    O retrocesso e limitado a `n_curta + n_guarda` amostras, que e o atraso
    maximo que a janela de energia pode ter introduzido. Alem disso nao ha
    justificativa para continuar andando para tras.
    """
    nc, ng = cal['n_curta'], cal['n_guarda']
    limite = max(0, indice_de_cruzamento - (nc + ng))

    sigma_ref = float(np.sqrt(e_longa[indice_de_cruzamento]))
    faixa = cal['k_faixa_de_ruido'] * sigma_ref

    i = indice_de_cruzamento
    while i > limite and abs(y[i - 1]) > faixa:
        i -= 1
    truncado = bool(i == limite and abs(y[i]) > faixa and i > 0
                    and abs(y[i - 1]) > faixa)

    # Inclinacao no ponto de chegada, para converter ruido em incerteza de
    # tempo. Usa o maior salto entre a marca e o cruzamento.
    trecho = y[i:indice_de_cruzamento + 1]
    inclinacao = (float(np.max(np.abs(np.diff(trecho)))) / ts
                  if len(trecho) > 1 else 0.0)

    u_quantizacao = ts / np.sqrt(12.0)
    u_ruido = (sigma_ref / inclinacao) if inclinacao > 0.0 else ts
    u_retrocesso = ts  # ambiguidade de mais ou menos uma amostra na marca
    if truncado:
        u_retrocesso = (nc + ng) * ts

    incerteza = float(np.sqrt(u_quantizacao ** 2 + u_ruido ** 2
                              + u_retrocesso ** 2))
    return {
        'indice_de_chegada': int(i),
        'tempo_de_chegada_s': float(tempo_s[i]),
        'amostras_retrocedidas': int(indice_de_cruzamento - i),
        'retrocesso_truncado': truncado,
        'sigma_de_referencia_m': sigma_ref,
        'faixa_de_ruido_m': float(faixa),
        'inclinacao_m_por_s': inclinacao,
        'incerteza_s': incerteza,
        'componentes_da_incerteza_s': {
            'quantizacao_temporal': float(u_quantizacao),
            'ruido_sobre_inclinacao': float(u_ruido),
            'ambiguidade_do_retrocesso': float(u_retrocesso),
        },
    }


# --- A-13: evidencia suficiente --------------------------------------------

def canal_saturado(sinal, escala):
    """Indicador de qualidade: o canal encostou no fundo de escala."""
    if not escala:
        return False
    x = np.asarray(sinal, dtype=float)
    minimo = escala.get('minimo_m')
    maximo = escala.get('maximo_m')
    passo = escala.get('resolucao_declarada_m') or 0.0
    eps = max(passo, 1e-12)
    tocou = False
    if minimo is not None:
        tocou = tocou or bool(np.any(x <= float(minimo) + eps))
    if maximo is not None:
        tocou = tocou or bool(np.any(x >= float(maximo) - eps))
    return tocou


def decidir_evidencia(det_a, det_b, sat_a, sat_b, delta_t, l_m, c_m_s, ts, cal):
    """Regras de A-13. Devolve (pode_localizar, motivo)."""
    if not det_a['detectado'] and not det_b['detectado']:
        return False, 'nenhum canal declarou evento'
    if not det_a['detectado']:
        return False, 'canal A nao declarou evento'
    if not det_b['detectado']:
        return False, 'canal B nao declarou evento'
    if sat_a and sat_b:
        return False, 'os dois canais encostaram no fundo de escala'
    if sat_a:
        return False, 'canal A encostou no fundo de escala'
    if sat_b:
        return False, 'canal B encostou no fundo de escala'

    limiar = cal['limiar_de_razao']
    if det_a['razao_no_cruzamento'] < limiar:
        return False, 'razao de energia do canal A abaixo do limiar'
    if det_b['razao_no_cruzamento'] < limiar:
        return False, 'razao de energia do canal B abaixo do limiar'

    limite = P.limite_fisico_de_delta_t(l_m, c_m_s)
    tolerancia = ts / 2.0
    if abs(delta_t) > limite + tolerancia:
        return False, ('diferenca temporal fora da faixa fisica: |%.6e| s > '
                       'L/c = %.6e s' % (delta_t, limite))
    return True, 'evidencia suficiente'


# --- A-15: registro de resultado -------------------------------------------

def processar_ensaio(ensaio, escala, cal=None):
    """Roda A-11 a A-15 sobre um ensaio do pacote e devolve um unico registro.

    `ensaio` e um item de `pacote['ensaios']`. `escala` vem do cabecalho do
    pacote. A funcao nunca levanta excecao por causa do sinal: qualquer falha
    de execucao vira um registro de classe `falha_execucao`, para que nenhum
    ensaio desapareca da metrica (criterio de conclusao de A-15).
    """
    cal = dict(cal or calibracao_padrao())
    registro = {'id': ensaio['id'], 'calibracao': cal}
    try:
        par = ensaio['parametros_do_detector']
        l_m = float(par['distancia_entre_sensores_L_m'])
        c_m_s = float(par['velocidade_de_onda_m_s'])
        u_c = float(par.get('incerteza_de_velocidade_de_onda_m_s', 0.0))
        pos_a = float(par['posicao_sensor_A_m'])
        registro['parametros_do_detector'] = par

        t = np.asarray(ensaio['tempo_s'], dtype=float)
        ts = float(np.median(np.diff(t)))
        sa = np.asarray(ensaio['canal_A_carga_m'], dtype=float)
        sb = np.asarray(ensaio['canal_B_carga_m'], dtype=float)
        resolucao = (escala or {}).get('resolucao_declarada_m')

        det_a, ya, _, ela = detectar_canal(sa, ts, cal, resolucao)
        det_b, yb, _, elb = detectar_canal(sb, ts, cal, resolucao)
        sat_a = canal_saturado(sa, escala)
        sat_b = canal_saturado(sb, escala)
        det_a['saturado'] = sat_a
        det_b['saturado'] = sat_b

        marca_a = marca_b = None
        if det_a['detectado']:
            marca_a = marcar_chegada(ya, ela, det_a['indice_de_cruzamento'],
                                     t, ts, cal)
            det_a.update(marca_a)
        if det_b['detectado']:
            marca_b = marcar_chegada(yb, elb, det_b['indice_de_cruzamento'],
                                     t, ts, cal)
            det_b.update(marca_b)

        registro['canal_A'] = det_a
        registro['canal_B'] = det_b
        registro['periodo_de_amostragem_s'] = ts

        # Tempo de deteccao: primeiro instante em que o produto declarou o
        # evento, ou seja o cruzamento mais cedo entre os canais que
        # declararam. Existe mesmo quando so um canal detectou.
        cruzamentos = [t[d['indice_de_cruzamento']] for d in (det_a, det_b)
                       if d['detectado']]
        registro['tempo_de_declaracao_s'] = (float(min(cruzamentos))
                                             if cruzamentos else None)

        if marca_a is not None and marca_b is not None:
            delta_t = marca_a['tempo_de_chegada_s'] - marca_b['tempo_de_chegada_s']
            u_delta_t = float(np.hypot(marca_a['incerteza_s'],
                                       marca_b['incerteza_s']))
            registro['delta_t_s'] = float(delta_t)
            registro['incerteza_de_delta_t_s'] = u_delta_t
            registro['delta_t_amostras'] = int(
                marca_a['indice_de_chegada'] - marca_b['indice_de_chegada'])
        else:
            delta_t = None
            u_delta_t = None

        pode, motivo = decidir_evidencia(det_a, det_b, sat_a, sat_b,
                                         delta_t if delta_t is not None else 0.0,
                                         l_m, c_m_s, ts, cal)
        registro['motivo'] = motivo

        if not pode:
            registro['classe'] = (CLASSE_SEM_DETECCAO
                                  if not det_a['detectado'] and not det_b['detectado']
                                  else CLASSE_SEM_LOCALIZACAO)
            return registro

        loc = P.localizar(l_m, c_m_s, delta_t, pos_a,
                          incerteza_de_delta_t_s=u_delta_t,
                          incerteza_de_c_m_s=u_c)
        registro['classe'] = CLASSE_LOCALIZADO
        registro.update(loc)
        return registro

    except Exception as e:  # nenhum ensaio pode sair sem registro (A-15)
        registro['classe'] = CLASSE_FALHA
        registro['motivo'] = '%s: %s' % (type(e).__name__, e)
        return registro


def processar_pacote(pacote, cal=None):
    """Um registro por ensaio do pacote, na mesma ordem."""
    escala = pacote.get('escala') or {}
    return [processar_ensaio(e, escala, cal) for e in pacote['ensaios']]

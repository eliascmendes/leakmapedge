"""LEAKMAP B-11 - registro do resultado do cenario B no computador.

A placa devolve indices de chegada e somas inteiras. O computador calcula
o resto, com as mesmas regras do cenario A:

  - diferenca temporal = diferenca entre os indices x periodo de amostragem;
  - decisao de evidencia (A-13) e posicao (A-14), com as funcoes de
    04_detector/detector.py e 04_detector/posicao.py, sem reimplementar;
  - incerteza de cada marca com os mesmos tres termos do cenario A, a partir
    das somas e do maior salto que a placa mediu.

O registro tem a mesma estrutura dos registros do cenario A, entao o
avaliador independente (05_avaliacao/avaliador.py) le os dois do mesmo jeito.
O campo `origem` e obrigatorio e diz de onde saiu o processamento: `fpga`
ou `referencia_python_da_placa`. Nunca se misturam no mesmo arquivo.
"""
import math
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import posicao as P  # noqa: E402
import protocolo as PR  # noqa: E402
import representacao as RP  # noqa: E402

MOTIVOS_DA_PLACA = {
    PR.RESULTADO_RECUSADO_AMOSTRAS_FALTANDO: 'a placa recusou a execucao: amostras faltando na memoria',
    PR.RESULTADO_RECUSADO_SEM_CONFIGURACAO: 'a placa recusou a execucao: ensaio nao configurado',
    PR.RESULTADO_RECUSADO_ESTOURO: 'a placa recusou o resultado: estouro de largura de palavra',
}


def periodo(ensaio):
    """Mesmo periodo que o cenario A usa: mediana dos passos da base de tempo."""
    return float(np.median(np.diff(np.asarray(ensaio['tempo_s'], dtype=float))))


def _canal(bruto, conv, preparo, escala, ts, tempo, cal):
    p = preparo['parametros']
    espec = preparo['representacao']
    nc, nl = p['n_curta'], p['n_longa']
    escala_q = float(1 << p['fracao'])
    escala_ye = float(1 << (p['fracao'] - p['desloca_energia']))
    reconstruido = RP.desconverter(conv['codigos'], espec)
    det = {
        'detectado': bruto['detectado'],
        'n_oportunidades_de_decisao': bruto['n_oportunidades_de_decisao'],
        'amostras_saturadas_na_conversao': conv['abaixo'] + conv['acima'],
        'indice_de_cruzamento': None,
        'razao_no_cruzamento': None,
    }
    det['saturado'] = bool(det['amostras_saturadas_na_conversao']
                           or D.canal_saturado(reconstruido, escala))
    if not bruto['detectado']:
        return det, None

    s_longa_efetiva = max(bruto['s_longa_no_cruzamento'], nl * p['piso_energia_por_amostra'])
    razao = (bruto['s_curta_no_cruzamento'] / nc) / (s_longa_efetiva / nl)
    i = bruto['indice_de_chegada']
    sigma_ref = math.sqrt(bruto['s_longa_no_cruzamento'] / nl) / escala_ye * espec['degrau_m']
    inclinacao = bruto['maior_salto_q'] / escala_q * espec['degrau_m'] / ts
    u_q = ts / math.sqrt(12.0)
    u_r = sigma_ref / inclinacao if inclinacao > 0 else ts
    u_ret = (p['n_curta'] + p['n_guarda']) * ts if bruto['retrocesso_truncado'] else ts
    det.update({
        'indice_de_cruzamento': bruto['indice_de_cruzamento'],
        'razao_no_cruzamento': razao,
        'indice_de_chegada': i,
        'tempo_de_chegada_s': float(tempo[i]),
        'amostras_retrocedidas': bruto['indice_de_cruzamento'] - i,
        'retrocesso_truncado': bruto['retrocesso_truncado'],
        'sigma_de_referencia_m': sigma_ref,
        'faixa_de_ruido_m': cal['k_faixa_de_ruido'] * sigma_ref,
        'inclinacao_m_por_s': inclinacao,
        'incerteza_s': math.sqrt(u_q ** 2 + u_r ** 2 + u_ret ** 2),
        'componentes_da_incerteza_s': {'quantizacao_temporal': u_q,
                                       'ruido_sobre_inclinacao': u_r,
                                       'ambiguidade_do_retrocesso': u_ret},
        'somas_inteiras_no_cruzamento': {'s_curta': bruto['s_curta_no_cruzamento'],
                                         's_longa': bruto['s_longa_no_cruzamento']},
        'maior_salto_q': bruto['maior_salto_q'],
    })
    return det, i


def montar_registro(ensaio, preparo, rodada, escala, cal, origem):
    """Um registro por ensaio, inclusive quando nao houve resultado (A-15)."""
    registro = {
        'id': ensaio['id'],
        'origem': origem,
        'calibracao': dict(cal),
        'parametros_do_detector': ensaio['parametros_do_detector'],
        'representacao': preparo['representacao'],
        'parametros_inteiros': preparo['parametros'],
        'conversao': {c: {'saturadas_abaixo': preparo['conversao'][c]['abaixo'],
                          'saturadas_acima': preparo['conversao'][c]['acima']}
                      for c in ('canal_A', 'canal_B')},
    }
    if rodada is not None:
        registro['comunicacao'] = {k: rodada[k] for k in ('n_blocos', 'bytes_de_amostras_enviados',
                                                         'eventos_de_comunicacao',
                                                         'tempos_de_comunicacao')}
    resultado = rodada and rodada['resultado']
    if not resultado:
        registro['classe'] = D.CLASSE_FALHA
        registro['motivo'] = preparo.get('motivo_de_falha') or 'sem resultado da placa depois das tentativas'
        return registro

    registro['contadores_da_placa'] = resultado['contadores']
    registro['n_amostras_reproduzidas'] = resultado['n_amostras_reproduzidas']
    if resultado['situacao'] != PR.RESULTADO_CONCLUIDO:
        registro['classe'] = D.CLASSE_FALHA
        registro['motivo'] = MOTIVOS_DA_PLACA.get(resultado['situacao'], 'situacao desconhecida da placa')
        return registro
    if resultado['n_amostras_reproduzidas'] != ensaio['n_pontos']:
        registro['classe'] = D.CLASSE_FALHA
        registro['motivo'] = ('a placa reproduziu %d amostras de %d'
                              % (resultado['n_amostras_reproduzidas'], ensaio['n_pontos']))
        return registro

    par = ensaio['parametros_do_detector']
    l_m = float(par['distancia_entre_sensores_L_m'])
    c_m_s = float(par['velocidade_de_onda_m_s'])
    u_c = float(par.get('incerteza_de_velocidade_de_onda_m_s', 0.0))
    ts = periodo(ensaio)
    tempo = ensaio['tempo_s']
    registro['periodo_de_amostragem_s'] = ts

    det_a, ia = _canal(resultado['canal_A'], preparo['conversao']['canal_A'], preparo, escala, ts, tempo, cal)
    det_b, ib = _canal(resultado['canal_B'], preparo['conversao']['canal_B'], preparo, escala, ts, tempo, cal)
    registro['canal_A'], registro['canal_B'] = det_a, det_b

    cruzamentos = [tempo[d['indice_de_cruzamento']] for d in (det_a, det_b) if d['detectado']]
    registro['tempo_de_declaracao_s'] = float(min(cruzamentos)) if cruzamentos else None

    delta_t = u_delta_t = None
    if ia is not None and ib is not None:
        delta_t = (ia - ib) * ts
        u_delta_t = math.hypot(det_a['incerteza_s'], det_b['incerteza_s'])
        registro.update({'delta_t_s': delta_t, 'incerteza_de_delta_t_s': u_delta_t,
                         'delta_t_amostras': ia - ib})

    pode, motivo = D.decidir_evidencia(det_a, det_b, det_a['saturado'], det_b['saturado'],
                                       delta_t if delta_t is not None else 0.0, l_m, c_m_s, ts, cal)
    registro['motivo'] = motivo
    if not pode:
        registro['classe'] = (D.CLASSE_SEM_DETECCAO if not det_a['detectado'] and not det_b['detectado']
                              else D.CLASSE_SEM_LOCALIZACAO)
        return registro
    registro['classe'] = D.CLASSE_LOCALIZADO
    registro.update(P.localizar(l_m, c_m_s, delta_t, float(par['posicao_sensor_A_m']),
                                incerteza_de_delta_t_s=u_delta_t, incerteza_de_c_m_s=u_c))
    return registro

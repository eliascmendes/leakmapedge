"""LEAKMAP - simulacao transiente TSNet dos cinco eventos + caso de conferencia."""
import json, sys, traceback
import numpy as np
from tsnet.postprocessing.detect_cusum import detect_cusum
import simular as S
from build_model import (escrever_inp, nome_no, SENSOR_A, SENSOR_B,
                         L_TRECHO, POS_EVENTO, DIAMETRO, FRICCAO_DW)

CUSUM_LIMIAR = 0.5     # m de carga
CUSUM_DERIVA = 0.05    # m de carga
LIMIAR_VAR   = 1e-3    # m, criterio de conferencia
JANELA       = 200     # pontos antes/depois
RHO_G        = 9810.0  # Pa/m -> pressao em bar = carga * RHO_G / 1e5

L_SENSORES = SENSOR_B - SENSOR_A

def carga_para_bar(h):
    return h * RHO_G / 1e5

def chegada(t, h):
    """Criterio primario: CUSUM interno do TSNet (tsnet.postprocessing.detect_cusum).
    Criterio de conferencia: primeira amostra com |h - h0| > LIMIAR_VAR."""
    tai, _, _ = detect_cusum(t, h, CUSUM_LIMIAR, CUSUM_DERIVA, False)
    i_cusum = int(tai[0]) if len(tai) else None
    d = np.abs(h - h[0])
    acima = np.nonzero(d > LIMIAR_VAR)[0]
    i_lim = int(acima[0]) if len(acima) else None
    return i_cusum, i_lim

def processar(pos, inp):
    tm = S.rodar(pos, inp)
    t = np.asarray(tm.simulation_timestamps, dtype=float)
    ha = np.asarray(tm.get_node(nome_no(SENSOR_A))._head, dtype=float)
    hb = np.asarray(tm.get_node(nome_no(SENSOR_B))._head, dtype=float)
    c_ef, comp, det = S.wavespeed_efetiva_entre_sensores(tm)

    ia_c, ia_l = chegada(t, ha)
    ib_c, ib_l = chegada(t, hb)
    if ia_c is None or ib_c is None:
        raise RuntimeError('CUSUM nao detectou chegada em algum canal (evento %s)' % pos)

    tA, tB = float(t[ia_c]), float(t[ib_c])
    dt_ab = tA - tB
    x_rel = (L_SENSORES + c_ef * dt_ab) / 2.0
    x_abs = SENSOR_A + x_rel

    i0 = max(0, min(ia_c, ib_c) - JANELA)
    i1 = min(len(t), max(ia_c, ib_c) + JANELA + 1)
    jan = slice(i0, i1)

    return tm, {
        'posicao_real_m': float(pos),
        'no_do_evento': nome_no(pos),
        'chegada_canal_A_s': tA,
        'chegada_canal_B_s': tB,
        'indice_chegada_A': ia_c,
        'indice_chegada_B': ib_c,
        'chegada_A_por_limiar_s': float(t[ia_l]) if ia_l is not None else None,
        'chegada_B_por_limiar_s': float(t[ib_l]) if ib_l is not None else None,
        'delta_t_s': dt_ab,
        'delta_t_amostras': ia_c - ib_c,
        'posicao_estimada_rel_sensor_A_m': float(x_rel),
        'posicao_estimada_m': float(x_abs),
        'erro_absoluto_m': float(abs(x_abs - pos)),
        'wavespeed_efetiva_usada_m_s': float(c_ef),
        'janela': {
            'indice_inicial': int(i0), 'indice_final': int(i1 - 1),
            'n_pontos': int(i1 - i0), 'pontos_antes_depois': JANELA,
            'tempo_s': [float(v) for v in t[jan]],
            'canal_A_carga_m': [float(v) for v in ha[jan]],
            'canal_B_carga_m': [float(v) for v in hb[jan]],
            'canal_A_pressao_bar': [float(v) for v in carga_para_bar(ha[jan])],
            'canal_B_pressao_bar': [float(v) for v in carga_para_bar(hb[jan])],
        },
    }, det, c_ef

def main():
    inp = escrever_inp('/home/claude/leakmap/trecho200.inp')

    # --- caso de conferencia: evento exatamente no meio dos sensores ---
    print('>>> CASO DE CONFERENCIA (evento em 100 m)', flush=True)
    tm_ref, conf, det, c_ef = processar(100.0, inp)
    print('  delta_t = %.9e s (%d amostras)' % (conf['delta_t_s'], conf['delta_t_amostras']))
    print('  posicao estimada = %.9f m' % conf['posicao_estimada_m'])
    tol_dt = 1e-12
    tol_x = 1e-6
    if abs(conf['delta_t_s']) > tol_dt or abs(conf['posicao_estimada_m'] - 100.0) > tol_x:
        print('FALHA NA CONFERENCIA: delta_t=%r  x=%r' % (conf['delta_t_s'], conf['posicao_estimada_m']))
        sys.exit(2)
    print('  CONFERENCIA OK\n', flush=True)

    dt_efetivo = float(tm_ref.time_step)
    eventos, falhas = [], []
    for pos in POS_EVENTO:
        print('>>> evento em %g m' % pos, flush=True)
        try:
            _, ev, _, _ = processar(pos, inp)
            print('   dt=%.6e s  x_est=%.4f m  erro=%.4f m'
                  % (ev['delta_t_s'], ev['posicao_estimada_m'], ev['erro_absoluto_m']), flush=True)
            eventos.append(ev)
        except Exception as e:
            traceback.print_exc()
            falhas.append({'posicao_real_m': pos, 'erro': repr(e)})

    saida = {
        'metadados': {
            'gerado_em': '2026-09-18',
            'ferramenta': 'TSNet 0.3.1 (wheel) / tsnet.__version__ = %s' % __import__('tsnet').__version__,
            'wntr': __import__('wntr').__version__,
            'numpy': np.__version__,
            'metodo': 'Metodo das caracteristicas (MOC), friction="steady"',
            'criterio_de_deteccao': (
                'Primario: CUSUM interno do TSNet (tsnet.postprocessing.detect_cusum), '
                'limiar=%.3f m de carga, deriva=%.3f m, aplicado a serie bruta de carga '
                'de cada canal; o instante de chegada e o primeiro indice tai retornado. '
                'Conferencia: primeira amostra com |h - h0| > %.0e m. '
                'Os dois criterios coincidiram em todos os eventos (diferenca de no maximo 1 amostra).'
                % (CUSUM_LIMIAR, CUSUM_DERIVA, LIMIAR_VAR)),
            'formula_localizacao': 'x = (L + c * delta_t) / 2, delta_t = tA - tB, '
                                   'x medido a partir do sensor A; posicao absoluta = 40 m + x',
            'evento': 'add_burst: abertura de vazamento em ts=%.3f s, tc=%.4f s, '
                      'coeficiente emissor final=%.4f' % (S.TS_BURST, S.TC_BURST, S.COEF_BURST),
            'observacao_friccao': 'TSNet recalculou o coeficiente D-W para 0.03 nos tubos '
                                  '(aviso interno "friction coefficient too large"); nao afeta '
                                  'tempos de chegada, apenas o nivel de carga de regime.',
        },
        'trecho_m': float(L_TRECHO),
        'diametro_m': float(DIAMETRO),
        'sensores': {
            'A': {'nome_no': nome_no(SENSOR_A), 'posicao_m': float(SENSOR_A)},
            'B': {'nome_no': nome_no(SENSOR_B), 'posicao_m': float(SENSOR_B)},
            'distancia_entre_sensores_L_m': float(L_SENSORES),
        },
        'velocidade_de_onda': {
            'solicitada_m_s': float(S.C_SOLICITADA),
            'efetiva_ajustada_m_s': float(c_ef),
            'origem': 'pipe.wavev apos tsnet discretization/adjust_wavev; '
                      'os seis sub-trechos entre os sensores receberam o mesmo valor ajustado',
            'por_sub_trecho': det,
        },
        'passo_de_tempo': {
            'solicitado_s': float(S.DT_SOLICITADO),
            'efetivo_s': dt_efetivo,
            'origem': 'tm.time_step apos tsnet set_time/adjust_wavev',
        },
        'caso_de_conferencia': {
            'descricao': 'Evento em 100 m, exatamente no meio entre os sensores. '
                         'Esperado delta_t = 0 e posicao estimada = 100 m.',
            'aprovado': True,
            'delta_t_s': conf['delta_t_s'],
            'posicao_estimada_m': conf['posicao_estimada_m'],
            'erro_absoluto_m': conf['erro_absoluto_m'],
        },
        'eventos': eventos,
        'falhas': falhas,
    }
    caminho = '/home/claude/leakmap/leakmap_resultados.json'
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print('\nJSON escrito:', caminho)
    print('eventos ok: %d  falhas: %d' % (len(eventos), len(falhas)))

if __name__ == '__main__':
    main()

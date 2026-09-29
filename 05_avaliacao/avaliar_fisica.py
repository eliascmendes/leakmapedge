"""LEAKMAP - avaliacao da fisica da linha (04_detector/fisica.py) contra a verdade do cenario.

O detector e o modulo de fisica nunca leem a verdade; este avaliador le. Mede:

  A. Quantificacao do vazamento (Joukowsky + Torricelli + atrito): coeficiente
     de emissor e diametro do furo equivalente contra os da simulacao, na linha
     do cais (seis transmissores) e na matriz do trecho de 200 m; e a vazao de
     regime pela perda de carga (Darcy-Weisbach) contra a da simulacao.
  B. Incerteza de posicao: fracao dos vazamentos localizados cujo erro fica
     dentro de 2 sigma, com a incerteza de hoje (so as marcas) e com a completa
     (marcas, periodo de atualizacao do transmissor, velocidade da onda).
  C. Calibracao da velocidade da onda por eventos de posicao conhecida
     (manobras do cadastro e vazamento fora do trecho), contra a velocidade
     efetiva da simulacao; e a relocalizacao da matriz com a velocidade
     calibrada, em validacao cruzada (cada evento fica de fora da propria
     calibracao), contra a velocidade declarada.
  D. Menor vazamento detectavel: o degrau minimo previsto (raiz(R) sigma)
     contra o degrau em que o detector passa a localizar, com vazamentos
     sinteticos cada vez menores (a onda de um vazamento simulado escalada,
     somada ao regime e passada pelo modelo de transmissor).
  E. Advecao: o vies de posicao de desprezar V diante de c (L V / 2 c).

Grava 05_avaliacao/leakmap_avaliacao_fisica_v1.json.

Uso: python 05_avaliacao/avaliar_fisica.py
"""
import collections
import json
import math
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))
import amostragem as AM  # noqa: E402
import detector as D  # noqa: E402
import fisica as F  # noqa: E402
import linha_cais as LQ  # noqa: E402
import modelo_sensor as MS  # noqa: E402

SAIDA = os.path.join(AQUI, 'leakmap_avaliacao_fisica_v1.json')
PAC = os.path.join(RAIZ, '03_ensaios', 'pacotes')
VER = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario')
RES = os.path.join(RAIZ, '04_detector', 'resultados')
CD = F.CD_ORIFICIO

ESCALAS = [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.1]
SEMENTES_DETECTABILIDADE = range(6)
ENSAIO_BASE_DETECTABILIDADE = 'LC-12'      # vazamento pequeno em 350 m, no meio do trecho


def ler(pasta, nome):
    with open(os.path.join(pasta, nome), encoding='utf-8') as f:
        return json.load(f)


def diametro_de_c(c_e):
    return math.sqrt(4.0 * c_e / (CD * math.sqrt(2.0 * F.G)) / math.pi)


def resumo(valores):
    v = np.asarray(valores, dtype=float)
    return {'n': int(len(v)), 'mediana': float(np.median(v)), 'minimo': float(v.min()), 'maximo': float(v.max())}


def linha_do_cais():
    pacote = ler(PAC, 'leakmap_pacote_linha_cais_v1.json')
    res = ler(RES, 'leakmap_resultado_linha_cais_v1.json')['resultados']
    plano = {e['id']: e for e in ler(os.path.join(RAIZ, '03_ensaios', 'matriz'), 'leakmap_plano_linha_cais_v1.json')['ensaios']}
    verdade_lc = ler(VER, 'leakmap_verdade_linha_cais_v1.json')
    ver = {v['id']: v for v in verdade_lc['ensaios']}
    ver.update({v['id']: v for v in ler(VER, 'leakmap_verdade_manobras_cais_v1.json')['ensaios']})
    c_real = float(verdade_lc['velocidade_de_onda_efetiva_m_s'])
    l_m = 700.0

    quant, regime, cobertura, eventos = (collections.defaultdict(list) for _ in range(4))
    for ensaio, r in zip(pacote['ensaios'], res):
        p = plano[ensaio['id']]
        cfg = p['configuracao']
        v = ver.get(p.get('ensaio_de_origem'))
        if not v:
            continue
        periodo = F.periodo_de_atualizacao_do_ensaio(ensaio)
        fis = r.get('fisica')
        if fis and fis.get('aplicado') and v.get('coeficiente_emissor'):
            c_e = fis['vazamento']['coeficiente_de_emissor_m2_5_s']
            quant[cfg].append({'erro_c': c_e / v['coeficiente_emissor'] - 1.0,
                               'd_mm': fis['vazamento']['diametro_equivalente_m'] * 1000.0,
                               'd_real_mm': diametro_de_c(v['coeficiente_emissor']) * 1000.0,
                               'canais': len(fis['onda']['canais_usados'])})
            regime[cfg].append(fis['escoamento_de_regime']['vazao_m3_s'])
        pos = v.get('posicao_real_m', v.get('posicao_da_manobra_m'))
        if r.get('delta_t_s') is not None and pos is not None:
            inc = F.incerteza_de_posicao(r, periodo)
            eventos[cfg].append({'delta_t_s': r['delta_t_s'], 'incerteza_de_delta_t_s': inc['incerteza_de_delta_t_s'],
                                 'diferenca_de_percurso_m': F.diferenca_de_percurso(pos, l_m)})
            if r['classe'] == D.CLASSE_LOCALIZADO and 0.0 <= pos <= l_m:
                erro = abs(r['posicao_estimada_m'] - pos)
                cobertura[cfg].append((erro <= 2.0 * r['incerteza_de_posicao_m'], erro <= 2.0 * inc['incerteza_m'],
                                       erro, inc['incerteza_m']))

    saida = {'velocidade_real_m_s': c_real, 'vazao_de_regime_real_m3_s': float(verdade_lc['vazao_de_regime_m3_s']),
             'por_transmissor': {}}
    for cfg in plano_cfgs(plano):
        q = quant.get(cfg, [])
        cob = cobertura.get(cfg, [])
        cal = F.calibrar_velocidade(eventos.get(cfg, []))
        saida['por_transmissor'][cfg] = {
            'quantificacao': {
                'erro_do_coeficiente_de_emissor': resumo([x['erro_c'] for x in q]) if q else None,
                'diametro_equivalente_mm': resumo([x['d_mm'] for x in q]) if q else None,
                'diametros_reais_mm': sorted(set(round(x['d_real_mm'], 2) for x in q)),
                'com_os_dois_canais': sum(1 for x in q if x['canais'] == 2)},
            'vazao_de_regime_estimada_m3_s': resumo(regime[cfg]) if regime.get(cfg) else None,
            'cobertura_2_sigma': {'n': len(cob),
                                  'incerteza_de_hoje': (sum(a for a, _, _, _ in cob) / len(cob)) if cob else None,
                                  'incerteza_completa': (sum(b for _, b, _, _ in cob) / len(cob)) if cob else None,
                                  'erro_mediano_m': float(np.median([e for _, _, e, _ in cob])) if cob else None,
                                  'incerteza_completa_mediana_m': float(np.median([s for _, _, _, s in cob])) if cob else None},
            'calibracao_da_velocidade': (dict(cal, erro_relativo=cal['velocidade_m_s'] / c_real - 1.0)
                                         if cal else None),
        }
    return saida


def plano_cfgs(plano):
    vistos = []
    for e in plano.values():
        if e['configuracao'] not in vistos:
            vistos.append(e['configuracao'])
    return vistos


def matriz():
    pacote = ler(PAC, 'leakmap_pacote_matriz_v1.json')
    res = ler(RES, 'leakmap_resultado_matriz_v1.json')['resultados']
    ver = {v['id']: v for v in ler(VER, 'leakmap_verdade_matriz_v1.json')['ensaios']}
    c_emissor = 0.01          # 02_bancada/codigo/simular.py, COEF_BURST
    grupos = collections.defaultdict(list)
    for ensaio, r in zip(pacote['ensaios'], res):
        v = ver[ensaio['id']]
        if v['tem_evento'] and r['classe'] == D.CLASSE_LOCALIZADO:
            grupos[v['linha_da_matriz']].append((ensaio, r, v))
    saida = {}
    for linha, itens in grupos.items():
        erros_c = [r['fisica']['vazamento']['coeficiente_de_emissor_m2_5_s'] / c_emissor - 1.0
                   for _, r, _ in itens if r.get('fisica', {}).get('aplicado')]
        antes, depois, cs = [], [], []
        for k, (ensaio, r, v) in enumerate(itens):
            par = ensaio['parametros_do_detector']
            outros = [{'delta_t_s': r2['delta_t_s'], 'incerteza_de_delta_t_s': r2['incerteza_de_delta_t_s'],
                       'diferenca_de_percurso_m': F.diferenca_de_percurso(
                           v2['posicao_real_m'] - par['posicao_sensor_A_m'], par['distancia_entre_sensores_L_m'])}
                      for j, (_, r2, v2) in enumerate(itens) if j != k]
            cal = F.calibrar_velocidade(outros)
            novo = F.relocalizar(r, cal['velocidade_m_s'], cal['incerteza_m_s'])
            antes.append(abs(r['posicao_estimada_m'] - v['posicao_real_m']))
            depois.append(abs(novo['posicao_estimada_m'] - v['posicao_real_m']))
            cs.append(cal['velocidade_m_s'])
        v0 = itens[0][2]
        saida[linha] = {
            'erro_do_coeficiente_de_emissor': resumo(erros_c) if erros_c else None,
            'velocidade_declarada_m_s': v0['velocidade_declarada_ao_detector_m_s'],
            'velocidade_real_m_s': v0['velocidade_de_onda_real_m_s'],
            'velocidade_calibrada_m_s': resumo(cs),
            'erro_de_posicao_com_a_velocidade_declarada_m': {'medio': float(np.mean(antes)), 'maximo': float(max(antes))},
            'erro_de_posicao_com_a_velocidade_calibrada_m': {'medio': float(np.mean(depois)), 'maximo': float(max(depois))},
        }
    return saida


def detectabilidade():
    """Degrau minimo previsto contra o degrau a partir do qual o detector localiza, com vazamentos escalados."""
    amostras = ler(os.path.join(RAIZ, '03_ensaios', 'amostras'), 'leakmap_amostras_linha_cais_v1.json')
    regime = next(e for e in amostras['ensaios'] if e['id'] == 'LC-REGIME')
    base = next(e for e in amostras['ensaios'] if e['id'] == ENSAIO_BASE_DETECTABILIDADE)
    ts = float(amostras['base_de_tempo_s'])
    c = float(amostras['velocidade_de_onda_efetiva_m_s'])
    faixa = LQ.faixa_em_carga_m(amostras)
    escolha = AM.escolher_frequencia(c, ts)
    area = math.pi * float(amostras['premissas']['diametro_interno_m']) ** 2 / 4.0
    par = {'posicao_sensor_A_m': 0.0, 'posicao_sensor_B_m': 700.0, 'distancia_entre_sensores_L_m': 700.0,
           'velocidade_de_onda_m_s': c, 'incerteza_de_velocidade_de_onda_m_s': 0.0}
    escala = {'resolucao_declarada_m': MS.degrau_de_quantizacao(16, 0.0, faixa)}
    ra = {k: np.asarray(regime['canal_%s_carga_m' % k], dtype=float) for k in 'AB'}
    onda = {k: np.asarray(base['canal_%s_carga_m' % k], dtype=float) - ra[k] for k in 'AB'}
    # amplitude da onda base no sensor A: patamar de 5 a 25 ms depois da chegada (evento em 0,1 s + percurso)
    verdade = {v['id']: v for v in ler(VER, 'leakmap_verdade_linha_cais_v1.json')['ensaios']}[ENSAIO_BASE_DETECTABILIDADE]
    t = np.asarray(base['tempo_s'], dtype=float)
    chegada = float(verdade['instante_do_evento_s']) + float(verdade['posicao_real_m']) / c
    patamar = (t >= chegada + 0.005) & (t <= chegada + 0.025)
    degrau_base = float(-np.mean(onda['A'][patamar]))
    saida = {}
    for cfg_nome in ('rapido', 'inteligente_10ms'):
        taxas, sigmas = [], []
        for k in ESCALAS:
            localizou = 0
            for semente in SEMENTES_DETECTABILIDADE:
                cfg = LQ.configuracoes(faixa, 1000 + semente)[cfg_nome]
                a, b, reg = MS.aplicar(ra['A'] + k * onda['A'], ra['B'] + k * onda['B'], ts, cfg)
                ensaio = AM.montar_ensaio('DT', base['tempo_s'], a, b, par, {'efeitos': reg}, escolha)
                r = D.processar_ensaio(ensaio, escala)
                localizou += r['classe'] == D.CLASSE_LOCALIZADO
                x = np.asarray(ensaio['canal_A_carga_m'], dtype=float)
                sigmas.append(float(np.std(x[:int(0.08 / ensaio['tempo_s'][1])], ddof=1)))
            taxas.append(localizou / len(SEMENTES_DETECTABILIDADE))
        sigma = float(np.median(sigmas))
        teoria = F.menor_vazamento_detectavel(sigma, c, area, resolucao_declarada_m=escala['resolucao_declarada_m'],
                                              periodo_de_amostragem_s=escolha['periodo_de_amostragem_s'])
        # menor escala com metade ou mais dos ensaios localizados
        k50 = next((k for k, tx in zip(ESCALAS, taxas) if tx >= 0.5), None)
        dh50 = None if k50 is None else k50 * degrau_base
        saida[cfg_nome] = {
            'ruido_do_canal_m': sigma,
            'teoria': dict(teoria, vazao_minima_l_min=teoria['vazao_minima_m3_s'] * 60000.0),
            'simulacao': {'escalas': ESCALAS, 'taxa_de_localizacao': taxas, 'degrau_da_onda_base_m': degrau_base,
                          'degrau_com_metade_localizada_m': dh50,
                          'vazao_com_metade_localizada_l_min': (None if dh50 is None else
                                                                F.vazao_por_joukowsky(dh50, c, area) * 60000.0)},
        }
    return saida


def adveccao():
    v = ler(VER, 'leakmap_verdade_linha_cais_v1.json')
    c, vel, l_m = float(v['velocidade_de_onda_efetiva_m_s']), float(v['velocidade_do_escoamento_m_s']), 700.0
    x0 = l_m / 2.0
    dt_real = x0 / (c - vel) - (l_m - x0) / (c + vel)
    return {'velocidade_do_escoamento_m_s': vel, 'vies_previsto_m': -l_m * vel / (2.0 * c),
            'exemplo_meio_do_trecho': {'delta_t_s': dt_real,
                                       'posicao_sem_adveccao_m': (l_m + c * dt_real) / 2.0,
                                       'posicao_com_adveccao_m': F.posicao_com_adveccao(l_m, c, vel, dt_real)},
            'observacao': 'o TSNet, como a teoria classica do golpe de ariete, despreza V diante de c; a correcao e '
                          'para o campo e nao entra na comparacao com as simulacoes'}


def main():
    resultado = {'descricao': __doc__.split('\n')[0], 'linha_do_cais': linha_do_cais(), 'matriz': matriz(),
                 'detectabilidade': detectabilidade(), 'adveccao': adveccao()}
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)

    lc = resultado['linha_do_cais']
    print('A/B/C. Linha do cais (velocidade real %.1f m/s, vazao de regime %.4f m3/s)'
          % (lc['velocidade_real_m_s'], lc['vazao_de_regime_real_m3_s']))
    for cfg, x in lc['por_transmissor'].items():
        q, cob, cal = x['quantificacao'], x['cobertura_2_sigma'], x['calibracao_da_velocidade']
        e = q['erro_do_coeficiente_de_emissor']
        print('  %-18s furo: erro de C %s | Q0 %s | 2 sigma: hoje %s, completa %s | c calibrada %s' % (
            cfg, ('%+.1f%% (%+.1f a %+.1f)' % (100 * e['mediana'], 100 * e['minimo'], 100 * e['maximo'])) if e else '-',
            ('%.4f' % x['vazao_de_regime_estimada_m3_s']['mediana']) if x['vazao_de_regime_estimada_m3_s'] else '-',
            '%.0f%%' % (100 * cob['incerteza_de_hoje']) if cob['n'] else '-',
            '%.0f%%' % (100 * cob['incerteza_completa']) if cob['n'] else '-',
            ('%.1f +- %.1f (%+.2f%%)' % (cal['velocidade_m_s'], cal['incerteza_m_s'], 100 * cal['erro_relativo'])) if cal else '-'))
    print('A/C. Matriz do trecho de 200 m')
    for linha, x in resultado['matriz'].items():
        e = x['erro_do_coeficiente_de_emissor']
        print('  %-26s erro de C %+.1f%% (%+.1f a %+.1f) | posicao: declarada %.3f m (max %.3f) -> calibrada %.3f m (max %.3f)' % (
            linha, 100 * e['mediana'], 100 * e['minimo'], 100 * e['maximo'],
            x['erro_de_posicao_com_a_velocidade_declarada_m']['medio'], x['erro_de_posicao_com_a_velocidade_declarada_m']['maximo'],
            x['erro_de_posicao_com_a_velocidade_calibrada_m']['medio'], x['erro_de_posicao_com_a_velocidade_calibrada_m']['maximo']))
    print('D. Menor vazamento detectavel')
    for cfg, x in resultado['detectabilidade'].items():
        t, s = x['teoria'], x['simulacao']
        print('  %-18s ruido %.4f m | teoria: degrau %.3f m, %.1f L/min | simulacao: degrau %s m, %s L/min | taxas %s' % (
            cfg, x['ruido_do_canal_m'], t['degrau_minimo_m'], t['vazao_minima_l_min'],
            '%.3f' % s['degrau_com_metade_localizada_m'] if s['degrau_com_metade_localizada_m'] else '-',
            '%.1f' % s['vazao_com_metade_localizada_l_min'] if s['vazao_com_metade_localizada_l_min'] else '-',
            ' '.join('%.0f' % (100 * y) for y in s['taxa_de_localizacao'])))
    a = resultado['adveccao']
    print('E. Advecao: vies previsto %.3f m (V = %.2f m/s)' % (a['vies_previsto_m'], a['velocidade_do_escoamento_m_s']))
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))


if __name__ == '__main__':
    main()

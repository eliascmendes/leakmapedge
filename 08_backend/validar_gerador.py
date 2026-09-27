"""LEAKMAP - conferencia do gerador da bancada contra o TSNet.

Para cada ponto simulado pelo TSNet, tira aquela simulacao dos moldes e gera o
mesmo ponto a partir das vizinhas (deixa um de fora). Compara com o sinal
verdadeiro do TSNet naquele ponto:

  - chegada: instante em que a variacao passa de metade da amplitude da frente,
    em cada sensor, no sinal gerado e no do TSNet;
  - amplitude da frente em cada sensor;
  - o detector: os dois sinais passam pelo mesmo transmissor (rapido dedicado,
    mesmas sementes) e pelo mesmo detector, e comparam-se os erros de posicao.

Os pontos das pontas (sem vizinha dos dois lados) sao gerados por extrapolacao
a partir de uma vizinha so; entram na conta e vem marcados.

Grava 08_backend/resultados/leakmap_validacao_do_gerador_v1.json.
Uso: python 08_backend/validar_gerador.py
"""
import json
import os

import numpy as np

import gerador as GE
import linhas as LN
import projeto as P

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, 'resultados', 'leakmap_validacao_do_gerador_v1.json')
TS = 1.0 / 2500.0


def chegada_a_meia_amplitude(t, delta, amplitude):
    acima = np.nonzero(np.abs(delta) >= 0.5 * abs(amplitude))[0]
    return float(t[acima[0]]) if len(acima) and amplitude else None


def detectar(linha, sinais, t):
    """Transmissor rapido e detector, como na bancada; devolve (trecho, posicao) ou a classe."""
    tg = np.arange(t[0], t[-1], TS)
    limpo = {s: np.interp(tg, t, x) for s, x in sinais.items()}
    nomes = list(linha.sensores)
    saida = {}
    for k in range(0, len(nomes), 2):
        par = nomes[k:k + 2]
        cfg = P.TX.configuracoes(linha.faixa_m, 11 + k)['rapido']
        a, b, _ = P.MS.aplicar(limpo[par[0]], limpo[par[1]], TS, cfg)
        saida[par[0]], saida[par[1]] = a, b
    faixa = linha.faixa_m
    escala = {'minimo_m': 0.0, 'maximo_m': faixa, 'resolucao_declarada_m': P.MS.degrau_de_quantizacao(16, 0.0, faixa)}
    if linha.topo is not None:
        r = P.RD.processar_ensaio_rede({'id': 'V', 'tempo_s': tg, 'canais_carga_m': saida}, escala, linha.topo)
        return (r.get('trecho_estimado'), r.get('s_estimado_m')) if r['classe'] == 'localizado' else r['classe']
    sa, sb = linha.sensores['A']['s_m'], linha.sensores['B']['s_m']
    r = P.D.processar_ensaio({'id': 'V', 'tempo_s': tg, 'canal_A_carga_m': saida['A'], 'canal_B_carga_m': saida['B'],
                              'parametros_do_detector': {'posicao_sensor_A_m': sa, 'posicao_sensor_B_m': sb,
                                                         'distancia_entre_sensores_L_m': sb - sa,
                                                         'velocidade_de_onda_m_s': linha.c,
                                                         'incerteza_de_velocidade_de_onda_m_s': 0.0}}, escala)
    return ('principal', r['posicao_estimada_m']) if r['classe'] == 'localizado' else r['classe']


def erro(linha, estimado, trecho, s_m):
    if not isinstance(estimado, tuple):
        return None
    if linha.topo is not None:
        return float(P.RD.distancia_entre_pontos(linha.topo, estimado, (trecho, s_m)))
    return abs(estimado[1] - s_m)


def conferir(linha):
    itens = []
    todos = list(linha.moldes_de_vazamento)
    for alvo in todos:
        linha.moldes_de_vazamento = [m for m in todos if m is not alvo]
        try:
            ev = GE.vazamento(linha, alvo.trecho, alvo.s_m, alvo.tamanho, 0.0)
        except ValueError:
            continue
        vizinhos = sorted(m.s_m for m in linha.moldes_de_vazamento
                          if m.trecho == alvo.trecho and m.tamanho == alvo.tamanho)
        t = alvo.t_rel
        gerado = {s: linha.regime[s] + GE.variacao(linha, ev, s, t) for s in linha.sensores}
        tsnet = {s: linha.regime[s] + alvo.delta[s] for s in linha.sensores}
        sensores = {}
        for s in linha.sensores:
            c_ts = chegada_a_meia_amplitude(t, alvo.delta[s], alvo.amplitude[s])
            c_ge = chegada_a_meia_amplitude(t, gerado[s] - linha.regime[s], alvo.amplitude[s])
            amp_ge = float(np.interp(alvo.chegada[s] + LN.APOS_A_CHEGADA_S, t, gerado[s] - linha.regime[s]))
            sensores[s] = {'chegada_tsnet_s': c_ts, 'chegada_gerador_s': c_ge,
                           'diferenca_de_chegada_ms': None if c_ts is None or c_ge is None else 1e3 * (c_ge - c_ts),
                           'amplitude_tsnet_m': alvo.amplitude[s], 'amplitude_gerador_m': amp_ge}
        det_ts, det_ge = detectar(linha, tsnet, t), detectar(linha, gerado, t)
        itens.append({'linha': linha.id, 'simulacao': alvo.id, 'trecho': alvo.trecho, 's_m': alvo.s_m,
                      'tamanho': alvo.tamanho, 'gerado_a_partir_de': ev['molde'].id,
                      'extrapolado': not (vizinhos and vizinhos[0] < alvo.s_m < vizinhos[-1]),
                      'sensores': sensores,
                      'erro_do_detector_no_tsnet_m': erro(linha, det_ts, alvo.trecho, alvo.s_m),
                      'erro_do_detector_no_gerador_m': erro(linha, det_ge, alvo.trecho, alvo.s_m),
                      'classe_tsnet': det_ts if isinstance(det_ts, str) else 'localizado',
                      'classe_gerador': det_ge if isinstance(det_ge, str) else 'localizado'})
    linha.moldes_de_vazamento = todos
    return itens


def main():
    itens = []
    for linha in LN.todas().values():
        itens += conferir(linha)
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Conferencia do gerador da bancada contra o TSNet: cada ponto simulado gerado a partir '
                                 'das simulacoes vizinhas, sem a propria.'), 'itens': itens}, f, ensure_ascii=False,
                  indent=1)
    print('%-10s %-9s %7s %-7s %-6s %-5s %22s %22s %9s %9s' % (
        'linha', 'trecho', 's_m', 'tamanho', 'molde', 'extr', 'dif. chegada (ms)', 'amplitude ger/tsnet',
        'erro ts', 'erro ger'))
    for i in itens:
        difs = [v['diferenca_de_chegada_ms'] for v in i['sensores'].values() if v['diferenca_de_chegada_ms'] is not None]
        razoes = [v['amplitude_gerador_m'] / v['amplitude_tsnet_m'] for v in i['sensores'].values()
                  if v['amplitude_tsnet_m']]
        fmt = lambda e: '-' if e is None else '%.2f m' % e  # noqa: E731
        print('%-10s %-9s %7.1f %-7s %-6s %-5s %22s %22s %9s %9s' % (
            i['linha'], i['trecho'], i['s_m'], i['tamanho'], i['gerado_a_partir_de'], 'sim' if i['extrapolado'] else '',
            '%+.2f a %+.2f' % (min(difs), max(difs)) if difs else '-',
            '%.2f a %.2f' % (min(razoes), max(razoes)) if razoes else '-',
            fmt(i['erro_do_detector_no_tsnet_m']) if i['classe_tsnet'] == 'localizado' else i['classe_tsnet'][:9],
            fmt(i['erro_do_detector_no_gerador_m']) if i['classe_gerador'] == 'localizado' else i['classe_gerador'][:9]))
    print('escrito: %s' % os.path.relpath(SAIDA, P.RAIZ))


if __name__ == '__main__':
    main()

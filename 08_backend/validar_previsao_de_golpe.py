"""LEAKMAP - conferencia da previsao do golpe contra o TSNet.

Para cada simulacao de 02_bancada/codigo/golpe_por_tempo_de_manobra.py, a
previsao (07_servico/previsao_de_golpe.py) calcula a subida de pressao no
equipamento com os dados hidraulicos da bancada (linhas.py) e a carga de
regime da propria simulacao, e compara com a subida simulada:

  grade         os tempos e fracoes de onde sai o estudo de transitorios;
                aqui o erro mede a parte fisica (Joukowsky com a valvula
                como orificio) e a interpolacao
  conferencia   fracoes e tempos que o estudo nao usa (30% e 75% da vazao,
                tempos no meio e alem da tabela): o erro fora do ajuste

Para comparar, a mesma conta so com a formula de Michaud, sem estudo.

Grava resultados/leakmap_validacao_da_previsao_de_golpe_v1.json.

Uso: python 08_backend/validar_previsao_de_golpe.py
"""
import json
import os

import linhas as LN
import projeto as P

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resultados',
                     'leakmap_validacao_da_previsao_de_golpe_v1.json')


def subida_prevista_m(linha, hid, fracao, tempo_s, carga_m, com_estudo=True):
    tubo = linha.tubo_da_previsao
    c = tubo['velocidade_de_onda_m_s']
    maximo = P.PG.subida_m(c, tubo['area_m2'], hid['vazao_m3_s'], fracao, carga_m, hid['ligacoes'])
    alivio = 2.0 * hid['distancia_de_alivio_m'] / c
    fator, _ = P.PG.fator_do_tempo(tempo_s, hid['estudo'] if com_estudo else None, alivio)
    return maximo * fator


def main():
    linhas = LN.todas()
    resultados = LN._estudos_de_golpe()
    if not resultados:
        raise SystemExit('faltam as simulacoes: rode 02_bancada/codigo/golpe_por_tempo_de_manobra.py')
    casos, erros = [], {'grade': [], 'conferencia': [], 'michaud': []}
    for r in resultados:
        linha = linhas[r['linha']]
        hid = linha.hidraulica[r['equipamento']]
        carga = r['carga_de_regime_no_equipamento_m']
        simulado = r['maior_subida_no_equipamento_m']
        previsto = subida_prevista_m(linha, hid, r['fracao_da_vazao_cortada'], r['tempo_de_manobra_s'], carga)
        michaud = subida_prevista_m(linha, hid, r['fracao_da_vazao_cortada'], r['tempo_de_manobra_s'], carga, False)
        erro, erro_m = (previsto - simulado) / simulado, (michaud - simulado) / simulado
        papel = r.get('papel', 'grade')
        erros[papel].append(erro)
        erros['michaud'].append(erro_m)
        bpm = linha.tubo_da_previsao['bar_por_metro']
        casos.append({'caso': r['caso'], 'papel': papel, 'fracao_da_vazao_cortada': r['fracao_da_vazao_cortada'],
                      'tempo_de_manobra_s': r['tempo_de_manobra_s'],
                      'subida_simulada_bar': round(simulado * bpm, 3), 'subida_prevista_bar': round(previsto * bpm, 3),
                      'erro_relativo': round(erro, 4), 'subida_so_com_michaud_bar': round(michaud * bpm, 3),
                      'erro_relativo_so_com_michaud': round(erro_m, 4)})
        print('%-17s %-11s %4.0f%% em %4.2f s: TSNet %5.2f bar, previsto %5.2f (%+5.1f%%), so Michaud %5.2f (%+6.1f%%)'
              % (r['caso'], papel, 100 * r['fracao_da_vazao_cortada'], r['tempo_de_manobra_s'], simulado * bpm,
                 previsto * bpm, 100 * erro, michaud * bpm, 100 * erro_m))
    resumo = {k: {'n': len(v), 'menor_erro': round(min(v), 4), 'maior_erro': round(max(v), 4),
                  'maior_erro_absoluto': round(max(abs(x) for x in v), 4)} for k, v in erros.items() if v}
    print('\nresumo (erro relativo da subida prevista):')
    for k, v in resumo.items():
        print('  %-12s %2d casos: de %+.1f%% a %+.1f%%' % (k, v['n'], 100 * v['menor_erro'], 100 * v['maior_erro']))
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump({'descricao': __doc__.split('\n')[0], 'margem_publicada': P.PG.MARGEM, 'resumo': resumo,
                   'casos': casos}, f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA, P.RAIZ))


if __name__ == '__main__':
    main()

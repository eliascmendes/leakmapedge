"""LEAKMAP - avaliacao independente da rede do cais com manifold e ramais.

Processo separado, como o avaliador da matriz: le o resultado gravado pelo
detector (04_detector/rede_cais.py), o plano dos ensaios e a verdade da
simulacao (02_bancada/codigo/rede_cais.py), e nao importa nenhum modulo de
04_detector. A distancia entre a posicao estimada e a real e medida pela
tubulacao, com a topologia gravada na verdade.

Grupos: <configuracao>/<tamanho>/dentro, <configuracao>/<tamanho>/fora
(vazamento antes do sensor A: a resposta certa e "fora do trecho, lado A") e
sem_evento/<configuracao>.

Grava 05_avaliacao/leakmap_avaliacao_rede_cais_v1.json.
"""
import json
import os

import avaliador as AV

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
RESULTADO = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_rede_cais_v1.json')
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_rede_cais_v1.json')
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_rede_cais_v1.json')
SAIDA = os.path.join(AQUI, 'leakmap_avaliacao_rede_cais_v1.json')


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def distancia_pela_tubulacao(topo, p, q):
    """Distancia entre (trecho, s) e (trecho, s) numa arvore com um so no de juncao."""
    if p[0] == q[0]:
        return abs(p[1] - q[1])
    j = lambda trecho: float(topo['trechos'][trecho]['juncao_em_s_m'])  # noqa: E731
    return abs(p[1] - j(p[0])) + abs(q[1] - j(q[0]))


def main():
    AV.conferir_independencia()
    resultado, plano, verdade = ler(RESULTADO), ler(PLANO), ler(VERDADE)
    topo = verdade['topologia']
    v_por_id = {e['id']: e for e in verdade['ensaios']}
    p_por_id = {p['id']: p for p in plano['ensaios']}

    grupos, itens = {}, []
    for r in resultado['resultados']:
        p = p_por_id[r['id']]
        v = v_por_id[p['ensaio_de_origem']]
        if not v['tem_evento']:
            grupo = 'sem_evento/%s' % p['configuracao']
        else:
            grupo = '%s/%s/%s' % (p['configuracao'], v['tamanho_do_vazamento'],
                                  'dentro' if v['dentro_da_rede_monitorada'] else 'fora')
        item = {'id': r['id'], 'grupo': grupo, 'classe': r['classe'], 'motivo': r.get('motivo'),
                'trecho_real': v.get('trecho_real'), 's_real_m': v.get('s_real_m'),
                'trecho_estimado': r.get('trecho_estimado'), 's_estimado_m': r.get('s_estimado_m'),
                'lado_da_origem': r.get('lado_da_origem')}
        if r['classe'] == 'localizado' and v['tem_evento']:
            item['trecho_certo'] = r['trecho_estimado'] == v['trecho_real']
            item['erro_pela_tubulacao_m'] = distancia_pela_tubulacao(
                topo, (r['trecho_estimado'], r['s_estimado_m']), (v['trecho_real'], v['s_real_m']))
        itens.append(item)
        grupos.setdefault(grupo, []).append(item)

    detectou = ('localizado', 'detectado_sem_localizacao', 'fora_do_trecho', 'manobra')
    tabela = []
    for grupo in sorted(grupos):
        g = grupos[grupo]
        erros = [i['erro_pela_tubulacao_m'] for i in g if 'erro_pela_tubulacao_m' in i]
        tabela.append({
            'grupo': grupo, 'n': len(g),
            'detectados': sum(i['classe'] in detectou for i in g),
            'localizados': sum(i['classe'] == 'localizado' for i in g),
            'trecho_certo': sum(bool(i.get('trecho_certo')) for i in g),
            'fora_do_trecho_lado_A': sum(i['classe'] == 'fora_do_trecho' and i['lado_da_origem'] == 'A' for i in g),
            'erro_pela_tubulacao': AV._resumo(erros),
        })
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Avaliacao independente da rede do cais com manifold e tres ramais (simulacao com '
                                 'premissas), por configuracao de transmissor. Erro medido pela tubulacao.'),
                   'premissas_da_simulacao': verdade.get('premissas'), 'topologia': topo,
                   'resultado_de_origem': os.path.basename(RESULTADO), 'verdade_de_origem': os.path.basename(VERDADE),
                   'por_grupo': tabela, 'ensaios': itens}, f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))
    print('\n%-30s %3s %4s %4s %6s %6s %9s %9s' % ('grupo', 'n', 'det', 'loc', 'trecho', 'fora A', 'erro med', 'erro max'))
    for t in tabela:
        e = t['erro_pela_tubulacao']
        print('%-30s %3d %4d %4d %6d %6d %9s %9s' % (t['grupo'], t['n'], t['detectados'], t['localizados'],
                                                  t['trecho_certo'], t['fora_do_trecho_lado_A'],
                                                  ('%.2f m' % e['mediano_m']) if e else '-',
                                                  ('%.2f m' % e['maximo_m']) if e else '-'))
    erradas = [i for i in itens if i.get('trecho_certo') is False]
    for i in erradas:
        print('trecho errado: %s %s real %s %.0f m, estimado %s %.1f m' % (
            i['id'], i['grupo'], i['trecho_real'], i['s_real_m'], i['trecho_estimado'], i['s_estimado_m']))


if __name__ == '__main__':
    main()

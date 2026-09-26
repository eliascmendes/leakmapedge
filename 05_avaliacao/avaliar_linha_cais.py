"""LEAKMAP - avaliacao independente da linha de produto do cais.

Processo separado, como o avaliador da matriz (avaliador.py): le o resultado
gravado pelo detector, o plano dos ensaios e a verdade das simulacoes, monta a
verdade de cada ensaio e aplica as mesmas metricas de avaliador.avaliar. Nao
importa nenhum modulo de 04_detector.

Grupos (linha_da_matriz):
  <configuracao>/<tamanho>/dentro   vazamento entre os sensores
  <configuracao>/<tamanho>/fora     vazamento antes do sensor A: a resposta
                                    certa e "fora do trecho, lado do sensor A"
  sem_evento/<configuracao>         regime permanente, para falso alarme
  manobra/<manobra>/<configuracao>  manobra operacional: a resposta certa e
                                    nao alarmar vazamento

Avalia o detector com a classificacao por polaridade e origem e sem ela.

Grava 05_avaliacao/leakmap_avaliacao_linha_cais_v1.json.
"""
import json
import os

import avaliador as AV

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
RESULTADOS = {
    'com_classificacao': os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_linha_cais_v1.json'),
    'sem_classificacao': os.path.join(RAIZ, '04_detector', 'resultados',
                                      'leakmap_resultado_linha_cais_sem_classificacao_v1.json'),
}
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_linha_cais_v1.json')
VERDADES = [os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_linha_cais_v1.json'),
            os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_manobras_cais_v1.json')]
SAIDA = os.path.join(AQUI, 'leakmap_avaliacao_linha_cais_v1.json')


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def verdade_por_ensaio(plano, por_origem):
    ensaios = []
    for p in plano['ensaios']:
        v = por_origem[p['ensaio_de_origem']]
        if 'manobra' in v:
            linha = 'manobra/%s/%s' % (v['manobra'], p['configuracao'])
        elif v['tem_evento']:
            lado = 'dentro' if v['dentro_do_trecho_entre_sensores'] else 'fora'
            linha = '%s/%s/%s' % (p['configuracao'], v['tamanho_do_vazamento'], lado)
        else:
            linha = 'sem_evento/%s' % p['configuracao']
        ensaios.append({'id': p['id'], 'tem_evento': v['tem_evento'], 'linha_da_matriz': linha,
                        'posicao_real_m': v.get('posicao_real_m'),
                        'instante_do_evento_s': v.get('instante_do_evento_s'),
                        'configuracao': p['configuracao'], 'ensaio_de_origem': p['ensaio_de_origem']})
    return {'ensaios': ensaios}


def resumo_fora_e_manobras(relatorio, resultado):
    por_id = {r['id']: r for r in resultado['resultados']}
    saida = []
    for d in relatorio['ensaios']:
        linha = d['linha_da_matriz']
        if linha.endswith('/fora') or linha.startswith('manobra/'):
            r = por_id[d['id']]
            saida.append({'id': d['id'], 'linha_da_matriz': linha, 'classe': r.get('classe'),
                          'desfecho': d['desfecho'], 'lado_da_origem': r.get('lado_da_origem'),
                          'posicao_estimada_m': r.get('posicao_estimada_m'),
                          'posicao_da_origem_m': r.get('posicao_da_origem_m'),
                          'motivo': r.get('motivo')})
    return saida


def main():
    AV.conferir_independencia()
    plano = ler(PLANO)
    por_origem, premissas = {}, None
    for caminho in VERDADES:
        if os.path.exists(caminho):
            v = ler(caminho)
            premissas = premissas or v.get('premissas')
            por_origem.update({e['id']: e for e in v['ensaios']})
    verdade = verdade_por_ensaio(plano, por_origem)

    saida = {'descricao': ('Avaliacao independente da linha de produto do cais (simulacao com premissas), '
                           'por configuracao de transmissor, com e sem a classificacao por polaridade e origem.'),
             'premissas_da_simulacao': premissas}
    for modo, caminho in RESULTADOS.items():
        resultado = ler(caminho)
        relatorio = AV.avaliar(resultado, verdade)
        relatorio['resultado_de_origem'] = os.path.basename(caminho)
        relatorio['verdade_de_origem'] = [os.path.basename(v) for v in VERDADES]
        relatorio['vazamentos_fora_do_trecho_e_manobras'] = resumo_fora_e_manobras(relatorio, resultado)
        saida[modo] = relatorio

    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))

    rel = saida['com_classificacao']
    print('\n%-34s %3s %4s %9s %9s %7s' % ('grupo (com classificacao)', 'n', 'det', 'erro med', 'erro max', 'falsos'))
    for linha in rel['por_linha_da_matriz']:
        nome = linha['linha_da_matriz']
        if nome.startswith('manobra/') or nome.endswith('/fora'):
            continue
        e, c = linha['erro_de_localizacao'], linha['contagens']
        print('%-34s %3d %4d %9s %9s %7d' % (nome, linha['n_ensaios'], c['deteccao'],
                                             ('%.2f m' % e['mediano_m']) if e else '-',
                                             ('%.2f m' % e['maximo_m']) if e else '-', c['falso_alarme']))
    for modo in ('sem_classificacao', 'com_classificacao'):
        itens = saida[modo]['vazamentos_fora_do_trecho_e_manobras']
        manobras = [i for i in itens if i['linha_da_matriz'].startswith('manobra/')]
        fora = [i for i in itens if i['linha_da_matriz'].endswith('/fora')]
        alarmes = sum(1 for i in manobras if i['desfecho'] == 'falso_alarme')
        print('\n%s: manobras que viraram alarme de vazamento: %d de %d' % (modo, alarmes, len(manobras)))
        for i in manobras:
            print('  %-40s %-26s %s' % (i['linha_da_matriz'], i['classe'], i['motivo'] or ''))
        print('%s: vazamentos fora do trecho (real -150 m):' % modo)
        for i in fora:
            print('  %-40s %-26s lado %s, posicao %s' % (
                i['linha_da_matriz'], i['classe'], i['lado_da_origem'] or '-',
                '-' if i['posicao_estimada_m'] is None else '%.1f m' % i['posicao_estimada_m']))


if __name__ == '__main__':
    main()

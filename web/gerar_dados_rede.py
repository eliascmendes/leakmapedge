"""LEAKMAP - dados da tela da rede do cais (manifold e tres ramais) no painel.

Junta o plano dos ensaios, os registros do detector (04_detector/rede_cais.py)
e a avaliacao independente (05_avaliacao/avaliar_rede_cais.py) num resumo
leve, sem os sinais:

  web/leakmap_dados_rede.js

A verdade entra pela avaliacao, porque o painel e a tela de avaliacao: mostra
onde o vazamento estava e onde o detector disse que estava. O detector nunca a
viu. O nivel da escala de alerta sai do proprio 07_servico/alerta.py.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, '07_servico'))
import alerta as AL  # noqa: E402

PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_rede_cais_v1.json')
RESULTADO = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_rede_cais_v1.json')
AVALIACAO = os.path.join(RAIZ, '05_avaliacao', 'leakmap_avaliacao_rede_cais_v1.json')
SAIDA = os.path.join(RAIZ, 'web', 'leakmap_dados_rede.js')

CONFIGURACOES = [
    ('rapido', 'Rápido dedicado', 'saída contínua, banda de 800 Hz'),
    ('inteligente_1ms', 'Inteligente · 1 ms', 'saída atualizada a cada 1 ms'),
    ('inteligente_10ms', 'Inteligente · 10 ms', 'a cada 10 ms'),
    ('inteligente_50ms', 'Inteligente · 50 ms', 'a cada 50 ms'),
    ('inteligente_100ms', 'Inteligente · 100 ms', 'a cada 100 ms'),
    ('ideal', 'Ideal', 'hidráulica pura, sem transmissor'),
]


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def rel(caminho):
    return os.path.relpath(caminho, RAIZ).replace(os.sep, '/')


def main():
    plano, resultado, av = ler(PLANO), ler(RESULTADO), ler(AVALIACAO)
    registros = {r['id']: r for r in resultado['resultados']}
    itens = {i['id']: i for i in av['ensaios']}

    eventos, casos = {}, {}
    for p in plano['ensaios']:
        origem, i = p['ensaio_de_origem'], itens[p['id']]
        if origem == 'RC-REGIME':
            continue
        if origem not in eventos:
            tamanho = i['grupo'].split('/')[1]
            eventos[origem] = {'id': origem, 'tamanho': tamanho, 'trecho': i['trecho_real'], 's_m': i['s_real_m'],
                               'dentro': i['grupo'].endswith('/dentro')}
        r = registros[p['id']]
        casos['%s/%s' % (origem, p['configuracao'])] = {
            'classe': r['classe'], 'nivel': AL.nivel_do_evento(r), 'motivo': r.get('motivo'),
            'trecho': r.get('trecho_estimado'), 's_m': r.get('s_estimado_m'), 'lado': r.get('lado_da_origem'),
            'erro_m': i.get('erro_pela_tubulacao_m'), 'trecho_certo': i.get('trecho_certo'),
            'sensores': sorted(n for n, d in (r.get('canais') or {}).items() if d.get('detectado')),
        }

    por_grupo = {g['grupo']: g for g in av['por_grupo']}
    resumo = []
    for chave, nome, sub in CONFIGURACOES:
        dentro = [por_grupo['%s/%s/dentro' % (chave, t)] for t in ('grande', 'pequeno')]
        erros = [g['erro_pela_tubulacao'] for g in dentro if g['erro_pela_tubulacao']]
        fora = [por_grupo['%s/%s/fora' % (chave, t)] for t in ('grande', 'pequeno')]
        sem = por_grupo['sem_evento/%s' % chave]
        resumo.append({'configuracao': chave, 'nome': nome, 'sub': sub,
                       'vazamentos': sum(g['n'] for g in dentro),
                       'localizados': sum(g['localizados'] for g in dentro),
                       'trecho_certo': sum(g['trecho_certo'] for g in dentro),
                       'erro_mediano_m': [e['mediano_m'] for e in erros],
                       'erro_maximo_m': max(e['maximo_m'] for e in erros) if erros else None,
                       'fora_lado_A': sum(g['fora_do_trecho_lado_A'] for g in fora),
                       'fora': sum(g['n'] for g in fora),
                       'falsos_alarmes': sem['detectados'], 'ensaios_sem_evento': sem['n']})

    topo = av['topologia']
    ordem = sorted(eventos.values(), key=lambda e: (e['tamanho'] != 'grande', not e['dentro'], e['trecho'], e['s_m']))
    dados = {
        'topologia': topo,
        'premissas': {k: av['premissas_da_simulacao'][k] for k in ('produto', 'tubo', 'rede', 'observacao')},
        'configuracoes': [{'configuracao': k, 'nome': n, 'sub': s} for k, n, s in CONFIGURACOES],
        'eventos': ordem, 'casos': casos, 'resumo': resumo,
        'fontes': [rel(PLANO), rel(RESULTADO), rel(AVALIACAO)],
    }
    with open(SAIDA, 'w', encoding='utf-8') as f:
        f.write('/* Gerado por web/gerar_dados_rede.py. Nao editar a mao. */\n')
        f.write('var LEAKMAP_REDE = ' + json.dumps(dados, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('escrito: %s (%.0f kB), %d eventos, %d casos' % (rel(SAIDA), os.path.getsize(SAIDA) / 1024,
                                                           len(ordem), len(casos)))


if __name__ == '__main__':
    main()

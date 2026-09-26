"""LEAKMAP - dados da tela da linha do cais no painel.

Junta o plano dos ensaios, os registros do detector (com a classificacao por
polaridade e origem e a conferencia com o cadastro de equipamentos, de
07_servico/cadastro_linha_cais.py) e a verdade da simulacao da linha do cais num resumo
leve, sem os sinais, para o mapa do painel:

  web/leakmap_dados_cais.js

A verdade entra aqui porque o painel e a tela de avaliacao: mostra onde o
vazamento estava e onde o detector disse que estava. O detector nunca a viu.
O nivel da escala de alerta sai do proprio 07_servico/alerta.py.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, '07_servico'))
import alerta as AL  # noqa: E402

PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_linha_cais_v1.json')
RESULTADO = os.path.join(RAIZ, '07_servico', 'resultados', 'leakmap_resultado_linha_cais_com_cadastro_v1.json')
CADASTRO = os.path.join(RAIZ, '07_servico', 'cadastro.exemplo.json')
# o mesmo detector sem a conferencia com o cadastro: o que o painel mostra sem o registro de operacao
RESULTADO_SEM_CADASTRO = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_linha_cais_v1.json')
AVALIACAO = os.path.join(RAIZ, '05_avaliacao', 'leakmap_avaliacao_linha_cais_v1.json')
VERDADES = [os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_linha_cais_v1.json'),
            os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_manobras_cais_v1.json')]
SAIDA = os.path.join(RAIZ, 'web', 'leakmap_dados_cais.js')

CONFIGURACOES = [
    ('rapido', 'Rápido dedicado', 'saída contínua, banda de 800 Hz'),
    ('inteligente_1ms', 'Inteligente · 1 ms', 'saída atualizada a cada 1 ms'),
    ('inteligente_10ms', 'Inteligente · 10 ms', 'a cada 10 ms'),
    ('inteligente_50ms', 'Inteligente · 50 ms', 'a cada 50 ms'),
    ('inteligente_100ms', 'Inteligente · 100 ms', 'a cada 100 ms'),
    ('ideal', 'Ideal', 'hidráulica pura, sem transmissor'),
]
NOMES_DAS_MANOBRAS = {'fechamento_navio': 'Fim de carregamento no navio (108)',
                      'fechamento_106': 'Fechamento no ramal do berço 106',
                      'abertura_106': 'Abertura no ramal do berço 106',
                      'parada_bomba': 'Parada da bomba'}


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def rel(caminho):
    return os.path.relpath(caminho, RAIZ).replace(os.sep, '/')


def main():
    plano, resultado = ler(PLANO), ler(RESULTADO)
    verdade, premissas = {}, None
    for caminho in VERDADES:
        v = ler(caminho)
        premissas = premissas or v['premissas']
        verdade.update({e['id']: e for e in v['ensaios']})
    registros = {r['id']: r for r in resultado['resultados']}
    sem_cadastro = {r['id']: r for r in ler(RESULTADO_SEM_CADASTRO)['resultados']}

    eventos, casos = {}, {}
    for p in plano['ensaios']:
        origem = p['ensaio_de_origem']
        v = verdade[origem]
        if origem == 'LC-REGIME':
            continue                                    # ensaios sem evento: so no resumo
        if origem not in eventos:
            if 'manobra' in v:
                eventos[origem] = {'id': origem, 'tipo': 'manobra', 'nome': NOMES_DAS_MANOBRAS[v['manobra']],
                                   'posicao_real_m': v['posicao_da_manobra_m'],
                                   'dentro_do_trecho': v['dentro_do_trecho_entre_sensores']}
            else:
                eventos[origem] = {'id': origem, 'tipo': 'vazamento', 'tamanho': v['tamanho_do_vazamento'],
                                   'posicao_real_m': v['posicao_real_m'],
                                   'dentro_do_trecho': v['dentro_do_trecho_entre_sensores']}
        r = registros[p['id']]
        real = eventos[origem]['posicao_real_m']
        estimada = r.get('posicao_estimada_m')
        s = sem_cadastro[p['id']]
        diferenca = None
        if s['classe'] != r['classe']:
            e = s.get('posicao_estimada_m')
            diferenca = {'classe': s['classe'], 'nivel': AL.nivel_do_evento(s), 'motivo': s.get('motivo'),
                         'posicao_estimada_m': e, 'posicao_da_origem_m': s.get('posicao_da_origem_m'),
                         'incerteza_m': s.get('incerteza_de_posicao_m'), 'lado': s.get('lado_da_origem'),
                         'erro_m': None, 'cadastro': None}
        casos['%s/%s' % (origem, p['configuracao'])] = {
            'sem_cadastro': diferenca,
            'classe': r['classe'],
            'nivel': AL.nivel_do_evento(r),
            'motivo': r.get('motivo'),
            'cadastro': (dict({k: r['cadastro'][k] for k in ('decisao', 'equipamento', 'texto')},
                              acao=(r['cadastro'].get('operacao') or {}).get('acao'),
                              reclassificado='classe_antes_do_cadastro' in r)
                         if r.get('cadastro') else None),
            'posicao_estimada_m': estimada,
            'posicao_da_origem_m': r.get('posicao_da_origem_m'),
            'incerteza_m': r.get('incerteza_de_posicao_m'),
            'lado': r.get('lado_da_origem'),
            'erro_m': abs(estimada - real) if estimada is not None and eventos[origem]['tipo'] == 'vazamento' else None,
            'polaridade': [(r.get(c) or {}).get('polaridade') for c in ('canal_A', 'canal_B')],
        }

    av = ler(AVALIACAO)['com_cadastro']
    por_linha = {l['linha_da_matriz']: l for l in av['por_linha_da_matriz']}
    resumo = []
    for chave, nome, sub in CONFIGURACOES:
        erros = [por_linha['%s/%s/dentro' % (chave, t)]['erro_de_localizacao'] for t in ('grande', 'pequeno')]
        dentro = [por_linha['%s/%s/dentro' % (chave, t)] for t in ('grande', 'pequeno')]
        resumo.append({'configuracao': chave, 'nome': nome, 'sub': sub,
                       'localizados': sum(l['contagens']['localizado'] for l in dentro),
                       'vazamentos': sum(l['n_ensaios'] for l in dentro),
                       'erro_mediano_m': [e['mediano_m'] for e in erros],
                       'erro_maximo_m': max(e['maximo_m'] for e in erros),
                       'falsos_alarmes': por_linha['sem_evento/%s' % chave]['contagens']['falso_alarme'],
                       'ensaios_sem_evento': por_linha['sem_evento/%s' % chave]['n_ensaios']})

    ordem = sorted(eventos.values(), key=lambda e: (e['tipo'] != 'vazamento', e.get('tamanho') != 'grande',
                                                     e['posicao_real_m']))
    dados = {
        'premissas': {
            'produto': premissas['produto'], 'tubo': premissas['tubo'],
            'velocidade_de_onda_m_s': premissas['velocidade_de_onda_korteweg_m_s'],
            'posicoes_m': premissas['posicoes_m'],
            'observacao': premissas['observacao'],
        },
        'configuracoes': [{'configuracao': k, 'nome': n, 'sub': s} for k, n, s in CONFIGURACOES],
        'equipamentos': ler(CADASTRO)['equipamentos'],
        'eventos': ordem,
        'casos': casos,
        'resumo': resumo,
        'fontes': [rel(PLANO), rel(RESULTADO), rel(RESULTADO_SEM_CADASTRO), rel(CADASTRO), rel(AVALIACAO)] + [rel(v) for v in VERDADES],
    }
    with open(SAIDA, 'w', encoding='utf-8') as f:
        f.write('/* Gerado por web/gerar_dados_cais.py. Nao editar a mao. */\n')
        f.write('var LEAKMAP_CAIS = ' + json.dumps(dados, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print('escrito: %s (%.0f kB), %d eventos, %d casos'
          % (rel(SAIDA), os.path.getsize(SAIDA) / 1024, len(ordem), len(casos)))


if __name__ == '__main__':
    main()

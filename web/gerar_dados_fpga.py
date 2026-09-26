"""LEAKMAP - dados da tela do modo FPGA do painel (B-12).

Grava web/leakmap_dados_fpga.js com, para cada ensaio da matriz:

  serie     os codigos inteiros que a placa recebeu nos dois canais, com o
            degrau da conversao, para a tela desenhar o que a placa viu;
  software  o resultado do cenario A (04_detector): classe, marcas de
            chegada, diferenca temporal e posicao;
  placa     o resultado do cenario B, uma entrada por origem de
            processamento que tiver arquivo gravado em 06_fpga/resultados;
  verdade   a posicao real do evento, que so a tela usa, para mostrar o erro.

Origens, na ordem em que a tela prefere mostrar:
  fpga        leakmap_cenario_b_*_fpga_v1.json, da placa de verdade;
  simulacao   leakmap_cenario_b_*_simulacao_v1.json, do Verilog da placa
              rodando ciclo a ciclo no simulador.
A referencia Python da placa e as rodadas contra a placa simulada nao entram
na tela. Cada origem leva o proprio rotulo, e a tela sempre mostra o rotulo
de quem processou: um observador externo sabe, olhando a tela, se o
resultado veio do software, do Verilog simulado ou da FPGA.

Quando a placa gravar os arquivos com origem fpga, basta rodar este script de
novo: a tela passa a abrir no resultado da FPGA, sem mudar codigo.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))
sys.path.insert(0, os.path.join(RAIZ, '06_fpga', 'computador'))

import detector as D  # noqa: E402
import preparo as PP  # noqa: E402

PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes', 'leakmap_pacote_matriz_v1.json')
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_matriz_v1.json')
RESULTADO_A = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_matriz_v1.json')
AVALIACAO_A = os.path.join(RAIZ, '05_avaliacao', 'leakmap_avaliacao_matriz_v1.json')
RESULTADOS_B = os.path.join(RAIZ, '06_fpga', 'resultados')
PROVA = os.path.join(RESULTADOS_B, 'leakmap_cenario_b_prova_simulacao_v1.json')
LATENCIA = os.path.join(RESULTADOS_B, 'leakmap_latencia_fpga_e_cpu_v1.json')
SAIDA = os.path.join(RAIZ, 'web', 'leakmap_dados_fpga.js')

NOME_DO_CENARIO = 'reprodução de sinais digitais em FPGA física'
ORIGENS = [
    ('fpga', {
        'rotulo': 'Processado na FPGA · reprodução de sinais digitais',
        'curto': 'FPGA',
        'onde': 'na placa FPGA',
    }),
    ('simulacao', {
        'rotulo': 'Processado no Verilog da placa, simulado ciclo a ciclo · reprodução de sinais digitais',
        'curto': 'Verilog da placa',
        'onde': 'no Verilog da placa, simulado ciclo a ciclo',
    }),
]
ROTULO_SOFTWARE = 'Processado em software · cenário A'
# o que a tela diz sobre a entrada, fixo em todas as origens (B-12)
ENTRADA = ('Hidráulica e transmissores simulados; a placa recebe as amostras em forma digital, '
           'as mesmas do cenário A.')


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def rel(caminho):
    return os.path.relpath(caminho, RAIZ).replace(os.sep, '/')


def arquivo_b(nome, sufixo):
    return os.path.join(RESULTADOS_B, 'leakmap_cenario_b_%s_%s_v1.json' % (nome, sufixo))


def resumo_do_registro(r):
    """O que a tela mostra de um registro, igual para o cenario A e o B."""
    canais = {}
    for c in ('A', 'B'):
        d = r.get('canal_' + c) or {}
        canais[c] = {
            'detectado': bool(d.get('detectado')),
            'chegada': d.get('indice_de_chegada') if d.get('detectado') else None,
            'cruzamento': d.get('indice_de_cruzamento') if d.get('detectado') else None,
        }
    return {
        'classe': r['classe'],
        'motivo': r.get('motivo'),
        'canal_A': canais['A'],
        'canal_B': canais['B'],
        'delta_t_amostras': r.get('delta_t_amostras'),
        'delta_t_s': r.get('delta_t_s'),
        'posicao_m': r.get('posicao_estimada_m'),
        'incerteza_m': r.get('incerteza_de_posicao_m'),
    }


def conferir(a, b):
    """Canais com a mesma decisao e a mesma chegada, e se a posicao e a mesma."""
    canais = sum(1 for c in ('canal_A', 'canal_B')
                 if a[c]['detectado'] == b[c]['detectado'] and a[c]['chegada'] == b[c]['chegada'])
    if a['posicao_m'] is None or b['posicao_m'] is None:
        mesma_posicao = a['posicao_m'] is None and b['posicao_m'] is None
    else:
        mesma_posicao = abs(a['posicao_m'] - b['posicao_m']) < 1e-9
    return canais, mesma_posicao and a['classe'] == b['classe']


def latencia_fpga_e_notebook():
    """FPGA x notebook, de 06_fpga/computador/comparar_latencia.py; so com medicao na placa."""
    if not os.path.exists(LATENCIA):
        return None
    m = ler(LATENCIA)
    f, c = m.get('fpga'), m['notebook']
    if not f:
        return None
    return {
        'arquivo': rel(LATENCIA),
        'ensaios': len(m['ensaios']),
        'repeticoes': m['repeticoes'],
        'frequencia_hz': f['frequencia_hz'],
        'fpga': {
            'mediana_us': f['latencia_de_declaracao_us']['mediana'],
            'min_us': f['latencia_de_declaracao_us']['min'],
            'max_us': f['latencia_de_declaracao_us']['max'],
            'ensaios_sem_variacao': f['ensaios_com_o_mesmo_numero_de_ciclos_em_todas_as_repeticoes'],
            'amostras_atrasadas': f['amostras_atrasadas'],
        },
        'notebook': {
            'mediana_us': c['latencia_de_declaracao_us']['mediana'],
            'p99_us': c['latencia_de_declaracao_us']['p99'],
            'max_us': c['latencia_de_declaracao_us']['max'],
            'desvio_us': c['latencia_de_declaracao_us']['desvio_padrao'],
            'maior_atraso_de_entrega_us': c['atraso_da_entrega_us']['max'],
            'amostras': c['atraso_da_entrega_us']['n'],
        },
    }


def main():
    pacote, verdade = ler(PACOTE), ler(VERDADE)
    escala = pacote['escala']
    cal = D.calibracao_padrao()
    software = {r['id']: resumo_do_registro(r) for r in ler(RESULTADO_A)['resultados']}
    real = {v['id']: v for v in verdade['ensaios']}

    origens, placa, fontes = {}, {}, [rel(PACOTE), rel(RESULTADO_A), rel(AVALIACAO_A), rel(VERDADE)]
    for chave, info in ORIGENS:
        resultado = arquivo_b('resultado', chave)
        if not os.path.exists(resultado):
            continue
        registros = {r['id']: resumo_do_registro(r) for r in ler(resultado)['resultados']}
        relatorio = ler(arquivo_b('relatorio', chave))
        comparacao = ler(arquivo_b('comparacao', chave))
        avaliacao = relatorio.get('avaliacao_contra_a_verdade') or {}
        canais_iguais, posicoes_iguais = 0, 0
        for ident, b in registros.items():
            c, p = conferir(software[ident], b)
            canais_iguais += c
            posicoes_iguais += p
        origem = dict(info)
        origem.update({
            'arquivos': [rel(resultado), rel(arquivo_b('comparacao', chave)), rel(arquivo_b('relatorio', chave))],
            'ensaios': len(registros),
            'concluidos': relatorio['ensaios']['concluidos'],
            'canais': 2 * len(registros),
            'chegadas_iguais_ao_software': canais_iguais,
            'posicoes_iguais_ao_software': posicoes_iguais,
            'maior_divergencia_de_posicao_m': comparacao['resumo']['maior_divergencia_de_posicao_m'],
            'contagens': avaliacao.get('contagens'),
            'erro_mediano_m': (avaliacao.get('erro_de_localizacao_geral') or {}).get('mediano_m'),
            'erro_maximo_m': (avaliacao.get('erro_de_localizacao_geral') or {}).get('maximo_m'),
            'falsos_alarmes': (avaliacao.get('falso_alarme') or {}).get('falsos_alarmes'),
            'oportunidades_sem_evento': (avaliacao.get('falso_alarme') or {}).get('oportunidades_de_decisao'),
        })
        if chave == 'simulacao' and os.path.exists(PROVA):
            prova = ler(PROVA)
            p = prova['processamento_na_placa']
            origem['processamento'] = {'ciclos_maximo': p['ciclos_maximo'],
                                       'ms_a_100_mhz': p['microssegundos_maximo_a_100_mhz'] / 1000.0,
                                       'ensaio': p['ensaio_mais_longo'],
                                       'amostras': p['amostras_do_ensaio_mais_longo']}
            origem['criterios'] = {k: v['passou'] for k, v in prova['criterios'].items()}
            origem['arquivos'].append(rel(PROVA))
        origens[chave] = origem
        placa[chave] = registros
        fontes += origem['arquivos']

    if not origens:
        raise SystemExit('nenhum resultado do cenario B com origem fpga ou simulacao em 06_fpga/resultados')

    ensaios = []
    for e in pacote['ensaios']:
        preparo = PP.preparar_ensaio(e, escala, cal)
        v = real[e['id']]
        ensaios.append({
            'id': e['id'],
            'linha': v['linha_da_matriz'],
            'tem_evento': v['tem_evento'],
            'posicao_real_m': v['posicao_real_m'] if v['tem_evento'] else None,
            't0_s': e['tempo_s'][0],
            'ts_s': e['tempo_s'][1] - e['tempo_s'][0],
            'degrau_m': preparo['representacao']['degrau_m'],
            'codigos_A': [int(x) for x in preparo['conversao']['canal_A']['codigos']],
            'codigos_B': [int(x) for x in preparo['conversao']['canal_B']['codigos']],
            'software': software[e['id']],
            'placa': {k: placa[k][e['id']] for k in placa},
        })

    dados = {
        'cenario': NOME_DO_CENARIO,
        'rotulo_software': ROTULO_SOFTWARE,
        'entrada': ENTRADA,
        'ordem_das_origens': [k for k, _ in ORIGENS if k in origens],
        'origens': origens,
        'fontes': sorted(set(fontes)),
        'bar_por_metro': 0.0981,
        'ensaios': ensaios,
        'latencia': latencia_fpga_e_notebook(),
    }
    if dados['latencia']:
        dados['fontes'] = sorted(set(dados['fontes']) | {rel(LATENCIA)})
    corpo = json.dumps(dados, ensure_ascii=False, separators=(',', ':'))
    with open(SAIDA, 'w', encoding='utf-8') as f:
        f.write('/* Gerado por web/gerar_dados_fpga.py a partir de 03_ensaios, 04_detector e '
                '06_fpga/resultados. Nao editar a mao. */\n')
        f.write('var LEAKMAP_FPGA = ' + corpo + ';\n')
    print('escrito: %s (%.0f kB), origens: %s' % (rel(SAIDA), os.path.getsize(SAIDA) / 1024,
                                                 ', '.join(dados['ordem_das_origens'])))


if __name__ == '__main__':
    main()

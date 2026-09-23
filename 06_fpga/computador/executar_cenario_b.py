"""LEAKMAP - executa o cenario B e fecha o relatorio (B-01 a B-14, lado do computador).

Uso:
  python executar_cenario_b.py                         referencia Python da placa
  python executar_cenario_b.py --serial COM5           FPGA na porta serial
  python executar_cenario_b.py --serial COM5 --ensaios MX-001 MX-002

Para cada ensaio: seleciona pelo selo (B-01), converte (B-02, B-03),
configura e confere (B-07), carrega os blocos (B-04, B-05, B-06), executa e
recebe o resultado (B-08 a B-10) e registra (B-11). Depois compara com o
cenario A (B-13), manda o avaliador independente comparar com a verdade e
fecha o relatorio (B-14).

A origem do processamento vai no nome de cada arquivo gravado:
`referencia` quando a "placa" e o modelo Python, `fpga` quando e a placa de
verdade. Resultado da referencia nunca e apresentado como resultado de FPGA.

A contagem de ensaios tentados e gravada antes da execucao, nao depois.
"""
import argparse
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import comparador as CP  # noqa: E402
import detector as D  # noqa: E402
import hospedeiro as HO  # noqa: E402
import placa_referencia as PLACA  # noqa: E402
import preparo as PP  # noqa: E402
import registro_b as RB  # noqa: E402
import selo as SE  # noqa: E402
import transporte as TR  # noqa: E402

PACOTE = SE.PACOTE
SELOS = SE.SELOS
RESULTADO_A = SE.RESULTADO_A
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_verdade_matriz_v1.json')
SAIDA = os.path.join(RAIZ, '06_fpga', 'resultados')

SUFIXO = {'referencia_python_da_placa': 'referencia', 'fpga': 'fpga'}


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def gravar(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(caminho, RAIZ))


def caminhos(origem, saida=SAIDA):
    s = SUFIXO[origem]
    return {n: os.path.join(saida, 'leakmap_cenario_b_%s_%s_v1.json' % (n, s))
            for n in ('tentativas', 'resultado', 'comparacao', 'avaliacao', 'relatorio')}


def executar(transporte, identificadores=None, tentativas=3, tempo_limite_s=2.0, saida=SAIDA):
    origem = transporte.origem
    arquivos = caminhos(origem, saida)
    pacote, selos, resultado_a = ler(PACOTE), ler(SELOS), ler(RESULTADO_A)
    escala = pacote.get('escala') or {}
    cal = D.calibracao_padrao()
    por_id = {e['id']: e for e in pacote['ensaios']}
    registros_a = {r['id']: r for r in resultado_a['resultados']}
    ids = identificadores or [e['id'] for e in pacote['ensaios']]

    # B-14: tentativas gravadas antes da execucao
    gravar(arquivos['tentativas'], {
        'descricao': 'Ensaios que o cenario B vai tentar, gravados antes da execucao.',
        'origem': origem,
        'n_tentativas': len(ids),
        'ensaios': ids,
    })

    hospedeiro = HO.Hospedeiro(transporte, tentativas=tentativas, tempo_limite_s=tempo_limite_s)
    registros, linhas = [], []
    recusados_pelo_selo, falhas_de_comunicacao = [], []
    for identificador in ids:
        try:
            ensaio = SE.selecionar(identificador, pacote, selos)
        except SE.EnsaioSemSelo as e:
            recusados_pelo_selo.append({'id': identificador, 'motivo': str(e)})
            registros.append({'id': identificador, 'origem': origem,
                              'classe': D.CLASSE_FALHA, 'motivo': 'recusado: %s' % e})
            continue
        preparo = PP.preparar_ensaio(ensaio, escala, cal)
        try:
            rodada = hospedeiro.rodar(identificador,
                                      preparo['conversao']['canal_A']['codigos'],
                                      preparo['conversao']['canal_B']['codigos'],
                                      preparo['parametros'])
        except HO.FalhaNaPlaca as e:
            falhas_de_comunicacao.append({'id': identificador, 'motivo': str(e)})
            rodada = None
            preparo['motivo_de_falha'] = 'falha na comunicacao com a placa: %s' % e
        registro = RB.montar_registro(ensaio, preparo, rodada, escala, cal, origem)
        registros.append(registro)
        if identificador in registros_a:
            linhas.append(CP.comparar_ensaio(registros_a[identificador], registro,
                                             ensaio, preparo, escala, cal))

    contagem = {}
    for r in registros:
        contagem[r['classe']] = contagem.get(r['classe'], 0) + 1
    gravar(arquivos['resultado'], {
        'descricao': ('Registros de resultado do cenario B, um por ensaio tentado. Origem do '
                      'processamento: %s. Mesmo formato dos registros do cenario A.' % origem),
        'origem': origem,
        'versao_do_formato': 'resultado-v1',
        'pacote_de_origem': os.path.basename(PACOTE),
        'cadeia_de_deteccao': ('B-08 a B-10 na %s: reproducao por indice comum, passa-altas em '
                               'Q16, somas de energia, limiar por multiplicacao cruzada e '
                               'retrocesso; B-11 no computador: delta_t pelos indices, decisao '
                               'de evidencia e posicao com o codigo do cenario A.'
                               % ('FPGA' if origem == 'fpga' else 'referencia Python da placa')),
        'n_ensaios': len(registros),
        'contagem_por_classe': contagem,
        'resultados': registros,
    })

    resumo = CP.resumir(linhas)
    gravar(arquivos['comparacao'], {
        'descricao': ('Comparacao B-13 entre o cenario B (%s) e o cenario A em software, '
                      'ensaio a ensaio. O cenario A e referencia entre implementacoes, nao '
                      'verdade.' % origem),
        'origem_B': origem,
        'resumo': resumo,
        'ensaios': linhas,
    })

    avaliacao = None
    todos = sorted(ids) == sorted(e['id'] for e in pacote['ensaios'])
    if todos and os.path.exists(VERDADE):
        codigo = ('import sys; sys.path.insert(0, %r); import avaliador as A; A.main(%r, %r, %r)'
                  % (os.path.join(RAIZ, '05_avaliacao'), arquivos['resultado'], VERDADE,
                     arquivos['avaliacao']))
        processo = subprocess.run([sys.executable, '-c', codigo], cwd=RAIZ,
                                  capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=''))
        if processo.returncode == 0:
            avaliacao = ler(arquivos['avaliacao'])
        else:
            print(processo.stderr)

    concluidos = [r for r in registros if r['classe'] != D.CLASSE_FALHA]
    relatorio = {
        'descricao': 'Relatorio do cenario B (B-14).',
        'origem': origem,
        'o_que_este_cenario_valida': ('o processamento digital na placa (deteccao e marcacao '
                                       'das chegadas) nas condicoes ensaiadas'),
        'o_que_nao_valida': ('sensores fisicos, resposta de transmissores, entrada analogica, '
                             'conversor analogico-digital real e instalacao industrial'),
        'nome_correto': 'reproducao de sinais digitais em FPGA fisica',
        'ensaios': {
            'tentados': len(ids),
            'concluidos': len(concluidos),
            'nao_concluidos': len(ids) - len(concluidos),
            'recusados_pelo_selo': recusados_pelo_selo,
            'falhas_de_comunicacao': falhas_de_comunicacao,
            'sem_resultado_ou_recusados_pela_placa': [
                {'id': r['id'], 'motivo': r.get('motivo')} for r in registros
                if r['classe'] == D.CLASSE_FALHA and r['id'] not in
                {x['id'] for x in recusados_pelo_selo + falhas_de_comunicacao}],
        },
        'contagem_por_classe': contagem,
        'divergencia_com_o_software': resumo,
        'contadores_da_placa_somados': {
            k: sum((r.get('contadores_da_placa') or {}).get(k, 0) for r in registros)
            for k in ('falhas_de_crc', 'descontinuidades_de_sequencia', 'eventos_de_buffer')},
        'eventos_de_comunicacao_somados': {
            k: sum((r.get('comunicacao') or {}).get('eventos_de_comunicacao', {}).get(k, 0)
                   for r in registros)
            for k in ('reenvios_de_bloco', 'reenvios_de_configuracao', 'pedidos_de_resultado',
                      'quadros_com_crc_invalido_recebidos')},
        'amostras_saturadas_na_conversao': sum(
            v for r in registros for c in (r.get('conversao') or {}).values() for v in c.values()),
        'tempos': {
            'tempo_simulado_total_s': sum(len(por_id[r['id']]['tempo_s']) * r['periodo_de_amostragem_s']
                                          for r in registros if 'periodo_de_amostragem_s' in r),
            'comunicacao_medida_no_computador_s': sum(
                sum(((r.get('comunicacao') or {}).get('tempos_de_comunicacao') or {}).values())
                for r in registros) if origem == 'fpga' else None,
            'observacao': ('tempo simulado, tempo de reproducao e latencia de processamento sao '
                           'grandezas diferentes. Os tempos de comunicacao medidos aqui nao sao '
                           'tempo real de processamento, e a expressao tempo real so vale com '
                           'ensaio que demonstre a taxa sustentada sem perdas.'),
        },
        'avaliacao_contra_a_verdade': None if avaliacao is None else {
            'arquivo': os.path.basename(arquivos['avaliacao']),
            'contagens': avaliacao['contagens'],
            'erro_de_localizacao_geral': avaliacao['erro_de_localizacao_geral'],
            'falso_alarme': avaliacao['falso_alarme'],
        },
    }
    gravar(arquivos['relatorio'], relatorio)
    return relatorio


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--serial', help='porta serial da FPGA (ex.: COM5). Sem ela, usa a referencia Python.')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--ensaios', nargs='*', help='identificadores; sem eles, todos os ensaios do pacote')
    ap.add_argument('--tempo-limite', type=float, default=2.0)
    args = ap.parse_args()

    if args.serial:
        transporte = TR.TransporteSerial(args.serial, args.baud)
    else:
        transporte = TR.TransporteMemoria(PLACA.PlacaReferencia())
    try:
        rel = executar(transporte, args.ensaios, tempo_limite_s=args.tempo_limite)
    finally:
        transporte.fechar()

    e, dv = rel['ensaios'], rel['divergencia_com_o_software']
    print('origem: %s' % rel['origem'])
    print('tentados %d | concluidos %d | nao concluidos %d'
          % (e['tentados'], e['concluidos'], e['nao_concluidos']))
    print('iguais ao software: %d de %d | maior divergencia: %d amostra(s), %.3f m'
          % (dv['identicos'], dv['n_ensaios'], dv['maior_divergencia_amostras'],
             dv['maior_divergencia_de_posicao_m']))
    if dv['contagem_por_causa']:
        print('causas: %r' % dv['contagem_por_causa'])
    av = rel['avaliacao_contra_a_verdade']
    if av:
        g = av['erro_de_localizacao_geral'] or {}
        print('contra a verdade: deteccoes %d, falsos alarmes %d, erro mediano %.3f m, maximo %.3f m'
              % (av['contagens']['deteccao'], av['contagens']['falso_alarme'],
                 g.get('mediano_m', 0), g.get('maximo_m', 0)))


if __name__ == '__main__':
    main()

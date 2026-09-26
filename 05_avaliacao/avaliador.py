"""LEAKMAP A-17 - avaliador independente.

Processo separado. Le dois arquivos ja gravados e nada mais:

  04_detector/resultados/leakmap_resultado_matriz_v1.json   (saida de A-15)
  03_ensaios/verdade_do_cenario/leakmap_verdade_matriz_v1.json

Cruza os dois pelo identificador do ensaio e grava
05_avaliacao/leakmap_avaliacao_matriz_v1.json.

Este modulo nao importa nem chama nada de 04_detector. A funcao
`conferir_independencia` verifica isso em tempo de execucao e faz o programa
parar se algum modulo do detector tiver sido carregado, para que o criterio de
conclusao de A-17 seja checado e nao apenas prometido.

Metricas produzidas, por linha da matriz e no total:

  - erro de localizacao nos casos localizados (medio, mediano, maximo, p95);
  - tempo de deteccao, contado do instante do evento ate o instante em que o
    produto declarou o evento;
  - contagem de deteccoes, nao deteccoes, falsos alarmes, inconclusivos e
    falhas de execucao.
"""
import json
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTADO = os.path.join(RAIZ, '04_detector', 'resultados',
                         'leakmap_resultado_matriz_v1.json')
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario',
                       'leakmap_verdade_matriz_v1.json')
SAIDA = os.path.join(RAIZ, '05_avaliacao', 'leakmap_avaliacao_matriz_v1.json')

MODULOS_DO_DETECTOR = ('detector', 'modelo_sensor', 'amostragem', 'posicao',
                       'matriz', 'gerar_ensaios', 'rodar_detector',
                       'detector_ponto_fixo')

CLASSE_LOCALIZADO = 'localizado'
CLASSE_SEM_LOCALIZACAO = 'detectado_sem_localizacao'
CLASSE_SEM_DETECCAO = 'sem_deteccao'
CLASSE_FALHA = 'falha_execucao'
# evento reconhecido como de origem no sensor ou fora do trecho: sai como
# suspeita, entao conta como declarado; a manobra reconhecida nao conta
CLASSE_FORA_DO_TRECHO = 'fora_do_trecho'


def conferir_independencia():
    """Garante que nenhum modulo de 04_detector foi carregado."""
    carregados = [m for m in MODULOS_DO_DETECTOR if m in sys.modules]
    if carregados:
        raise SystemExit(
            'A-17 exige avaliacao independente: modulos do detector '
            'carregados neste processo: %s' % ', '.join(carregados))
    pasta = os.path.join(RAIZ, '04_detector')
    for caminho in sys.path:
        if caminho and os.path.abspath(caminho) == os.path.abspath(pasta):
            raise SystemExit('A-17 exige avaliacao independente: '
                             '04_detector esta no sys.path')


def _resumo(valores):
    if not len(valores):
        return None
    v = np.asarray(valores, dtype=float)
    return {
        'n': int(v.size),
        'medio_m': float(v.mean()),
        'mediano_m': float(np.median(v)),
        'maximo_m': float(v.max()),
        'p95_m': float(np.percentile(v, 95)),
    }


def _resumo_tempo(valores):
    if not len(valores):
        return None
    v = np.asarray(valores, dtype=float)
    return {
        'n': int(v.size),
        'medio_s': float(v.mean()),
        'mediano_s': float(np.median(v)),
        'maximo_s': float(v.max()),
    }


def avaliar(resultado, verdade):
    """Cruza resultado e verdade e devolve o relatorio completo."""
    por_id = {e['id']: e for e in verdade['ensaios']}
    registros = resultado['resultados']

    vistos = set()
    detalhes = []
    for reg in registros:
        identificador = reg['id']
        if identificador in vistos:
            raise SystemExit('ensaio %s tem mais de um registro de resultado'
                             % identificador)
        vistos.add(identificador)
        verd = por_id.get(identificador)
        if verd is None:
            raise SystemExit('ensaio %s aparece no resultado mas nao na '
                             'verdade do cenario' % identificador)

        classe = reg.get('classe')
        tem_evento = bool(verd['tem_evento'])
        declarou = classe in (CLASSE_LOCALIZADO, CLASSE_SEM_LOCALIZACAO, CLASSE_FORA_DO_TRECHO)

        item = {
            'id': identificador,
            'linha_da_matriz': verd['linha_da_matriz'],
            'tem_evento': tem_evento,
            'classe': classe,
            'motivo': reg.get('motivo'),
            'posicao_real_m': verd.get('posicao_real_m'),
            'posicao_estimada_m': reg.get('posicao_estimada_m'),
            'erro_de_localizacao_m': None,
            'tempo_de_deteccao_s': None,
            'incerteza_declarada_m': reg.get('incerteza_de_posicao_m'),
            'erro_dentro_da_incerteza_declarada': None,
        }

        if classe == CLASSE_FALHA:
            item['desfecho'] = 'falha_de_execucao'
        elif tem_evento and declarou:
            item['desfecho'] = 'deteccao'
        elif tem_evento and not declarou:
            item['desfecho'] = 'nao_deteccao'
        elif not tem_evento and declarou:
            item['desfecho'] = 'falso_alarme'
        else:
            item['desfecho'] = 'silencio_correto'

        if classe == CLASSE_SEM_LOCALIZACAO:
            item['inconclusivo'] = True

        if (classe == CLASSE_LOCALIZADO and tem_evento
                and reg.get('posicao_estimada_m') is not None):
            erro = abs(float(reg['posicao_estimada_m'])
                       - float(verd['posicao_real_m']))
            item['erro_de_localizacao_m'] = erro
            u = reg.get('incerteza_de_posicao_m')
            if u is not None:
                item['erro_dentro_da_incerteza_declarada'] = bool(erro <= u)

        if (declarou and tem_evento
                and reg.get('tempo_de_declaracao_s') is not None
                and verd.get('instante_do_evento_s') is not None):
            item['tempo_de_deteccao_s'] = (
                float(reg['tempo_de_declaracao_s'])
                - float(verd['instante_do_evento_s']))

        detalhes.append(item)

    faltando = sorted(set(por_id) - vistos)
    if faltando:
        raise SystemExit('ensaios sem registro de resultado: %s'
                         % ', '.join(faltando))

    # Oportunidades de decisao nos ensaios sem evento, para que a taxa de
    # falso alarme tenha denominador e nao seja apenas "zero em 15 ensaios".
    oportunidades = 0
    for reg in registros:
        if por_id[reg['id']]['tem_evento']:
            continue
        for canal in ('canal_A', 'canal_B'):
            oportunidades += int(reg.get(canal, {})
                                 .get('n_oportunidades_de_decisao', 0) or 0)

    consolidado = _consolidar(detalhes)
    falsos = sum(1 for d in detalhes if d['desfecho'] == 'falso_alarme')
    sem_evento = sum(1 for d in detalhes if not d['tem_evento'])

    falso_alarme = {
        'ensaios_sem_evento': sem_evento,
        'falsos_alarmes': falsos,
        'taxa_por_ensaio': (falsos / sem_evento) if sem_evento else None,
        'oportunidades_de_decisao': oportunidades,
        'taxa_por_oportunidade': ((falsos / oportunidades)
                                  if oportunidades else None),
    }
    if falsos == 0 and oportunidades:
        # Regra de tres: com zero ocorrencias em N tentativas, o limite
        # superior de 95% de confianca para a taxa e 3/N.
        falso_alarme['limite_superior_95_por_oportunidade'] = 3.0 / oportunidades
        falso_alarme['observacao'] = (
            'nenhum falso alarme observado; o limite superior de 95% de '
            'confianca vem da regra de tres, 3/N')

    return {
        'descricao': ('Avaliacao independente (A-17) da matriz de ensaios. '
                      'Produzida por 05_avaliacao/avaliador.py, que le apenas '
                      'o resultado gravado pelo detector e a verdade do '
                      'cenario, e nao importa nenhum modulo de 04_detector.'),
        'resultado_de_origem': os.path.basename(RESULTADO),
        'verdade_de_origem': os.path.basename(VERDADE),
        'cadeia_de_deteccao_declarada_pelo_detector':
            resultado.get('cadeia_de_deteccao'),
        'n_ensaios': len(detalhes),
        'contagens': _contagens(detalhes),
        'falso_alarme': falso_alarme,
        'erro_de_localizacao_geral': _resumo(
            [d['erro_de_localizacao_m'] for d in detalhes
             if d['erro_de_localizacao_m'] is not None]),
        'tempo_de_deteccao_geral': _resumo_tempo(
            [d['tempo_de_deteccao_s'] for d in detalhes
             if d['tempo_de_deteccao_s'] is not None]),
        'por_linha_da_matriz': consolidado,
        'ensaios': detalhes,
    }


def _contagens(detalhes):
    contagem = {'deteccao': 0, 'nao_deteccao': 0, 'falso_alarme': 0,
                'silencio_correto': 0, 'inconclusivo': 0,
                'falha_de_execucao': 0, 'localizado': 0}
    for d in detalhes:
        contagem[d['desfecho']] = contagem.get(d['desfecho'], 0) + 1
        if d.get('inconclusivo'):
            contagem['inconclusivo'] += 1
        if d['classe'] == CLASSE_LOCALIZADO:
            contagem['localizado'] += 1
    return contagem


def _consolidar(detalhes):
    linhas = {}
    for d in detalhes:
        linhas.setdefault(d['linha_da_matriz'], []).append(d)
    saida = []
    for nome in sorted(linhas):
        grupo = linhas[nome]
        erros = [g['erro_de_localizacao_m'] for g in grupo
                 if g['erro_de_localizacao_m'] is not None]
        tempos = [g['tempo_de_deteccao_s'] for g in grupo
                  if g['tempo_de_deteccao_s'] is not None]
        saida.append({
            'linha_da_matriz': nome,
            'n_ensaios': len(grupo),
            'contagens': _contagens(grupo),
            'erro_de_localizacao': _resumo(erros),
            'tempo_de_deteccao': _resumo_tempo(tempos),
        })
    return saida


def main(caminho_resultado=RESULTADO, caminho_verdade=VERDADE, saida=SAIDA):
    conferir_independencia()
    with open(caminho_resultado, encoding='utf-8') as f:
        resultado = json.load(f)
    with open(caminho_verdade, encoding='utf-8') as f:
        verdade = json.load(f)

    relatorio = avaliar(resultado, verdade)

    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    print('escrito: %s' % os.path.relpath(saida, RAIZ))
    print('ensaios avaliados: %d' % relatorio['n_ensaios'])
    c = relatorio['contagens']
    print('  deteccoes %d | nao deteccoes %d | falsos alarmes %d | '
          'inconclusivos %d | falhas %d'
          % (c['deteccao'], c['nao_deteccao'], c['falso_alarme'],
             c['inconclusivo'], c['falha_de_execucao']))
    geral = relatorio['erro_de_localizacao_geral']
    if geral:
        print('  erro de localizacao: medio %.3f m, mediano %.3f m, '
              'maximo %.3f m (n=%d)'
              % (geral['medio_m'], geral['mediano_m'], geral['maximo_m'],
                 geral['n']))
    print()
    print('%-26s %4s %7s %7s %7s' % ('linha da matriz', 'n', 'medio', 'max',
                                     'det'))
    for linha in relatorio['por_linha_da_matriz']:
        e = linha['erro_de_localizacao']
        print('%-26s %4d %7s %7s %7d'
              % (linha['linha_da_matriz'], linha['n_ensaios'],
                 ('%.3f' % e['medio_m']) if e else '-',
                 ('%.3f' % e['maximo_m']) if e else '-',
                 linha['contagens']['deteccao']))


if __name__ == '__main__':
    main()

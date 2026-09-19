"""LEAKMAP - gera os ensaios da matriz. Etapas A-09 e A-10.

Le os sinais limpos de 03_ensaios/amostras/leakmap_amostras_v1.json e os
parametros de 03_ensaios/parametros/leakmap_parametros_v1.json, aplica o
modelo de sensor (A-09) e a amostragem com base de tempo comum (A-10), e
grava, sem sobrescrever nada do v1:

  03_ensaios/amostras/leakmap_amostras_ruido_v1.json
      mesmo formato do v1, na base do solucionador, com a lista de efeitos
      de sensor aplicados e seus parametros;
  03_ensaios/pacotes/leakmap_pacote_matriz_v1.json
      pacote do ensaio da etapa A-10, ja decimado, que e o unico arquivo que
      o detector le;
  03_ensaios/matriz/leakmap_matriz_v1.json
      plano da matriz: de qual ensaio de origem cada linha veio e com que
      configuracao. E o contrato entre a geracao e o avaliador.

Este script nunca le nem escreve 03_ensaios/verdade_do_cenario.
"""
import json
import os

import numpy as np

import amostragem as AM
import matriz as MX
import modelo_sensor as MS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RHO_G = 9810.0  # Pa/m; pressao em bar = carga * RHO_G / 1e5

ENTRADA_AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras',
                                'leakmap_amostras_v1.json')
ENTRADA_PARAMETROS = os.path.join(RAIZ, '03_ensaios', 'parametros',
                                  'leakmap_parametros_v1.json')
SAIDA_AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras',
                              'leakmap_amostras_ruido_v1.json')
SAIDA_PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes',
                            'leakmap_pacote_matriz_v1.json')
SAIDA_PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz',
                           'leakmap_matriz_v1.json')


def carga_para_bar(h):
    return np.asarray(h, dtype=float) * RHO_G / 1e5


def ler_json(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def escrever_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(caminho, RAIZ))


def main():
    amostras = ler_json(ENTRADA_AMOSTRAS)
    parametros = ler_json(ENTRADA_PARAMETROS)

    ts_solucionador = float(amostras['base_de_tempo_s'])
    c_efetiva = float(parametros['velocidade_de_onda']['efetiva_ajustada_m_s'])
    l_sensores = float(parametros['sensores']['distancia_entre_sensores_L_m'])
    pos_a = float(parametros['sensores']['A']['posicao_m'])
    pos_b = float(parametros['sensores']['B']['posicao_m'])

    # --- A-10: escolha da frequencia de amostragem -------------------------
    escolha = AM.escolher_frequencia(c_efetiva, ts_solucionador)
    print('A-10 %s' % escolha['conta'])

    por_id = {e['id']: e for e in amostras['ensaios']}
    menor_trecho_antes = min(
        min(_primeira_variacao(e['canal_A_carga_m']),
            _primeira_variacao(e['canal_B_carga_m']))
        for e in amostras['ensaios'])
    checagem = AM.verificar_janela_de_referencia(
        menor_trecho_antes, escolha['fator_de_decimacao'],
        n_curta=6, n_guarda=3, n_longa=30)
    print('A-10 janela de referencia: %r' % checagem)
    if not checagem['aprovado']:
        raise SystemExit('as janelas do detector nao cabem no trecho anterior '
                         'ao evento; rever o fator de decimacao')

    velocidades = MX.velocidades(c_efetiva)
    escala = {
        'minimo_m': MX.ESCALA_MIN_M,
        'maximo_m': MX.ESCALA_MAX_M,
        'resolucao_declarada_m': None,
        'observacao': ('resolucao declarada por ensaio, no campo '
                       'efeitos_de_sensor_aplicados; o valor do cabecalho e o '
                       'pior caso da matriz'),
    }

    linhas, ensaios_ruido, ensaios_pacote = [], [], []
    piores_resolucoes = []
    contador = 0

    # --- ensaios com evento ------------------------------------------------
    for nivel in MX.NIVEIS_DE_RUIDO:
        for indice_origem, id_origem in enumerate(MX.ENSAIOS_DE_ORIGEM):
            origem = por_id[id_origem]
            cfg = MX.configuracoes_de_sensor(semente=indice_origem * 7)[nivel]
            a, b, registro = MS.aplicar(origem['canal_A_carga_m'],
                                        origem['canal_B_carga_m'],
                                        ts_solucionador, cfg)
            resolucao = MS.resolucao_declarada_m(cfg)
            piores_resolucoes.append(resolucao or 0.0)

            for nome_c, dados_c in velocidades.items():
                contador += 1
                identificador = 'MX-%03d' % contador
                par_detector = {
                    'posicao_sensor_A_m': pos_a,
                    'posicao_sensor_B_m': pos_b,
                    'distancia_entre_sensores_L_m': l_sensores,
                    'velocidade_de_onda_m_s': dados_c['c_m_s'],
                    'incerteza_de_velocidade_de_onda_m_s':
                        dados_c['incerteza_m_s'],
                    'origem_da_velocidade_de_onda': (
                        'valor declarado pela linha "%s" da matriz' % nome_c),
                }
                efeitos = {
                    'nivel_de_ruido': nivel,
                    'resolucao_declarada_m': resolucao,
                    'efeitos': registro,
                }
                ensaios_pacote.append(AM.montar_ensaio(
                    identificador, origem['tempo_s'], a, b,
                    par_detector, efeitos, escolha))
                linhas.append({
                    'id': identificador,
                    'ensaio_de_origem': id_origem,
                    'tem_evento': True,
                    'nivel_de_ruido': nivel,
                    'velocidade_declarada': nome_c,
                    'velocidade_declarada_m_s': dados_c['c_m_s'],
                    'desvio_relativo_de_c': dados_c['desvio_relativo'],
                    'linha_da_matriz': 'evento/%s/%s' % (nivel, nome_c),
                })

            ensaios_ruido.append({
                'id': '%s@%s' % (id_origem, nivel),
                'ensaio_de_origem': id_origem,
                'nivel_de_ruido': nivel,
                'n_pontos': int(len(a)),
                'tempo_s': [float(v) for v in origem['tempo_s']],
                'canal_A_carga_m': [float(v) for v in a],
                'canal_B_carga_m': [float(v) for v in b],
                'canal_A_pressao_bar': [float(v) for v in carga_para_bar(a)],
                'canal_B_pressao_bar': [float(v) for v in carga_para_bar(b)],
                'efeitos_de_sensor_aplicados': registro,
                'resolucao_declarada_m': resolucao,
            })

    # --- ensaios sem evento, para a taxa de falso alarme (A-11) ------------
    h0_a = float(por_id[MX.ENSAIOS_DE_ORIGEM[0]]['canal_A_carga_m'][0])
    h0_b = float(por_id[MX.ENSAIOS_DE_ORIGEM[0]]['canal_B_carga_m'][0])
    for nivel in MX.NIVEIS_DE_RUIDO:
        for k, semente in enumerate(MX.SEMENTES_SEM_EVENTO):
            t, a0, b0 = MX.sinal_sem_evento(h0_a, h0_b,
                                            MX.N_PONTOS_SEM_EVENTO,
                                            ts_solucionador)
            cfg = MX.configuracoes_de_sensor(semente=semente)[nivel]
            a, b, registro = MS.aplicar(a0, b0, ts_solucionador, cfg)
            resolucao = MS.resolucao_declarada_m(cfg)
            contador += 1
            identificador = 'MX-%03d' % contador
            par_detector = {
                'posicao_sensor_A_m': pos_a,
                'posicao_sensor_B_m': pos_b,
                'distancia_entre_sensores_L_m': l_sensores,
                'velocidade_de_onda_m_s': velocidades['casada']['c_m_s'],
                'incerteza_de_velocidade_de_onda_m_s': 0.0,
                'origem_da_velocidade_de_onda': (
                    'valor declarado pela linha "casada" da matriz'),
            }
            ensaios_pacote.append(AM.montar_ensaio(
                identificador, t, a, b, par_detector,
                {'nivel_de_ruido': nivel, 'resolucao_declarada_m': resolucao,
                 'efeitos': registro}, escolha))
            linhas.append({
                'id': identificador,
                'ensaio_de_origem': None,
                'tem_evento': False,
                'nivel_de_ruido': nivel,
                'velocidade_declarada': 'casada',
                'velocidade_declarada_m_s': velocidades['casada']['c_m_s'],
                'desvio_relativo_de_c': 0.0,
                'semente': semente,
                'repeticao': k + 1,
                'linha_da_matriz': 'sem_evento/%s' % nivel,
            })

    escala['resolucao_declarada_m'] = float(max(piores_resolucoes))

    escrever_json(SAIDA_AMOSTRAS, {
        'descricao': ('Sinais de sensor (A-09) na base de tempo do '
                      'solucionador. Mesmo formato de leakmap_amostras_v1, '
                      'com os efeitos aplicados registrados por ensaio. Nao '
                      'contem a posicao real do vazamento.'),
        'gerado_a_partir_de': os.path.basename(ENTRADA_AMOSTRAS),
        'base_de_tempo_s': ts_solucionador,
        'unidades': {'carga': 'm', 'pressao': 'bar'},
        'escala_do_transmissor': {'minimo_m': MX.ESCALA_MIN_M,
                                  'maximo_m': MX.ESCALA_MAX_M},
        'ensaios': ensaios_ruido,
    })

    escrever_json(SAIDA_PACOTE, AM.montar_pacote(
        descricao=('Pacote do ensaio (A-10) da matriz essencial. Unico '
                   'arquivo lido pelo detector. Nao contem a posicao real do '
                   'vazamento.'),
        escolha=escolha,
        escala=escala,
        ensaios=ensaios_pacote,
        ts_solucionador_s=ts_solucionador,
        observacoes=[checagem,
                     ('o atraso de grupo do antisserrilhamento e igual nos '
                      'dois canais e por isso nao entra em delta_t')]))

    escrever_json(SAIDA_PLANO, {
        'descricao': ('Plano da matriz de ensaios. Diz de qual ensaio de '
                      'origem cada linha veio e com que configuracao. Nao '
                      'contem a posicao real do vazamento; o avaliador cruza '
                      'este plano com a verdade do cenario.'),
        'eixos': {
            'posicao': list(MX.ENSAIOS_DE_ORIGEM),
            'ruido': list(MX.NIVEIS_DE_RUIDO),
            'velocidade': {k: v for k, v in velocidades.items()},
            'sem_evento': {'repeticoes': len(MX.SEMENTES_SEM_EVENTO),
                           'n_pontos': MX.N_PONTOS_SEM_EVENTO},
        },
        'observacao_sobre_o_eixo_de_velocidade': (
            'o eixo varia a velocidade de onda declarada ao detector, nao a '
            'velocidade com que o solucionador gerou os sinais; ver o '
            'cabecalho de 04_detector/matriz.py'),
        'n_ensaios': len(linhas),
        'ensaios': linhas,
    })
    print('ensaios gerados: %d (%d com evento, %d sem evento)'
          % (len(linhas),
             sum(1 for x in linhas if x['tem_evento']),
             sum(1 for x in linhas if not x['tem_evento'])))


def _primeira_variacao(canal, limiar=1e-3):
    x = np.asarray(canal, dtype=float)
    acima = np.nonzero(np.abs(x - x[0]) > limiar)[0]
    return int(acima[0]) if len(acima) else len(x)


if __name__ == '__main__':
    main()

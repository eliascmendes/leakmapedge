"""LEAKMAP - gabarito de paridade entre o Python e a adaptacao em JavaScript.

O Python de 04_detector e a implementacao de referencia. Este script roda o
proprio Python sobre entradas fixas e grava o que ele produziu, para que a
adaptacao em web/leakmap_detector.js seja conferida contra esse resultado:

  web/gabarito/leakmap_gabarito_js_v1.json

O gabarito so e gerado pelo Python, nunca pelo JavaScript. Toda mudanca no
algoritmo comeca em 04_detector; depois se roda este script, e so entao o
JavaScript e ajustado ate o teste de paridade voltar a passar.

Conteudo:

- `configuracoes`: a configuracao neutra e as configuracoes de sensor da
  matriz, para conferir que a tela usa exatamente os mesmos parametros;
- `modelo_sensor`: saidas de A-09 na base do solucionador, um efeito por vez
  e as configuracoes completas, com os sorteios gaussianos que o NumPy usou;
- `cadeia`: A-09, A-10 e A-11 a A-14 de ponta a ponta nos cinco eventos, com
  os mesmos sorteios;
- `detector`: o registro de resultado de cada ensaio do pacote da matriz,
  mais os sinais intermediarios de alguns canais, amostra a amostra.

O gerador de numeros aleatorios do NumPy nao tem equivalente em JavaScript.
Por isso os sorteios vao gravados aqui: com eles o JavaScript tem de
reproduzir o Python exatamente. Sem eles, no navegador, o ruido e outro
sorteio com a mesma estatistica.
"""
import json
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import amostragem as AM  # noqa: E402
import detector as D  # noqa: E402
import matriz as MX  # noqa: E402
import modelo_sensor as MS  # noqa: E402

AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_v1.json')
PARAMETROS = os.path.join(RAIZ, '03_ensaios', 'parametros',
                          'leakmap_parametros_v1.json')
PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes',
                      'leakmap_pacote_matriz_v1.json')
SAIDA = os.path.join(RAIZ, 'web', 'gabarito', 'leakmap_gabarito_js_v1.json')

N_INTERMEDIARIOS = 6   # ensaios do pacote com sinais intermediarios gravados


def sem_nan(obj):
    """JSON nao representa NaN nem infinito; viram null."""
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sem_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sem_nan(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [sem_nan(float(v)) for v in obj]
    if isinstance(obj, (np.floating,)):
        return sem_nan(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def sorteios(cfg, n_a, n_b):
    """Os sorteios gaussianos que MS.aplicar consome, na mesma ordem.

    `ruido`: um gerador com a semente do efeito, primeiro o canal A, depois o
    canal B. `erro_de_sincronizacao`: um gerador por canal, sementes s e s+1,
    e nenhum sorteio quando o jitter e zero. Generator.normal(0, s) e
    s * standard_normal() sobre a mesma sequencia; a igualdade e conferida
    aqui antes de gravar, para o gabarito nao carregar uma suposicao falsa.
    """
    saida = {}
    r = cfg.get('ruido', {})
    if r.get('ligado'):
        sem = int(r.get('semente', 0))
        g = np.random.default_rng(sem)
        za = g.standard_normal(n_a)
        zb = g.standard_normal(n_b)
        conf = np.random.default_rng(sem)
        sigma = float(r['desvio_padrao_m'])
        assert np.array_equal(conf.normal(0.0, sigma, n_a), sigma * za)
        assert np.array_equal(conf.normal(0.0, sigma, n_b), sigma * zb)
        saida['ruido_A'] = za
        saida['ruido_B'] = zb
    j = cfg.get('erro_de_sincronizacao', {})
    if j.get('ligado') and float(j['jitter_s']) != 0.0:
        sem = int(j.get('semente', 0))
        saida['jitter_A'] = np.random.default_rng(sem).standard_normal(n_a)
        saida['jitter_B'] = np.random.default_rng(sem + 1).standard_normal(n_b)
    return saida


def um_efeito_por_vez(ts):
    """Mesmos parametros usados em 04_detector/testes/teste_modelo_sensor.py."""
    casos = []

    def caso(nome, efeito, **par):
        cfg = MS.config_neutra()
        cfg[efeito].update(ligado=True, **par)
        casos.append((nome, cfg))

    caso('banda', 'banda', corte_hz=300.0, ordem=2)
    caso('atraso_comum', 'atraso_comum', atraso_s=5 * ts)
    caso('atraso_comum_fracionario', 'atraso_comum', atraso_s=2.37 * ts)
    caso('diferenca_de_atraso', 'diferenca_de_atraso', atraso_s=3 * ts)
    caso('erro_de_sincronizacao', 'erro_de_sincronizacao', jitter_s=2e-5,
         semente=3)
    caso('offset', 'offset', offset_A_m=0.25, offset_B_m=-0.40)
    caso('ruido', 'ruido', desvio_padrao_m=0.05, semente=7)
    caso('saturacao', 'saturacao', minimo_m=30.0, maximo_m=55.0)
    caso('quantizacao', 'quantizacao', bits=12, fundo_de_escala_min_m=0.0,
         fundo_de_escala_max_m=100.0)
    caso('amortecimento', 'amortecimento', constante_de_tempo_s=0.002)
    # fases declaradas: o sorteio do NumPy nao e reproduzido no navegador
    caso('atualizacao', 'atualizacao', periodo_s=10 * ts, fase_A_s=3.3 * ts, fase_B_s=7.1 * ts)
    casos.append(('neutra', MS.config_neutra()))
    return casos


def casos_de_classificacao():
    """Sinais sinteticos para a classificacao por polaridade e origem.

    Os mesmos formatos de 04_detector/testes/teste_detector.py: patamar e uma
    rampa curta de subida ou de descida, com o atraso entre canais escolhido
    para cair dentro do trecho, no limite fisico, um pouco alem e muito alem.
    """
    ts, l_m, c_m_s = 4.0130559895570352e-4, 120.0, 1200.899544131626
    limite = int(round(l_m / c_m_s / ts))

    def degrau(n, inicio, amplitude):
        x = np.full(n, 58.0)
        rampa = np.linspace(0.0, amplitude, 4)[1:]
        x[inicio:inicio + 3] = 58.0 + rampa
        x[inicio + 3:] = 58.0 + amplitude
        return x

    def ensaio(nome, a, b):
        n = len(a)
        return {'id': nome, 'n_pontos': n, 'indice': list(range(n)), 'tempo_s': [i * ts for i in range(n)],
                'canal_A_carga_m': [float(v) for v in a], 'canal_B_carga_m': [float(v) for v in b],
                'parametros_do_detector': {'posicao_sensor_A_m': 40.0, 'posicao_sensor_B_m': 160.0,
                                           'distancia_entre_sensores_L_m': l_m, 'velocidade_de_onda_m_s': c_m_s,
                                           'incerteza_de_velocidade_de_onda_m_s': 0.0}}

    n = limite + 900
    sinais = [
        ('vazamento_dentro', degrau(n, 300, -5.0), degrau(n, 340, -5.0), True),
        ('alta_nos_dois', degrau(n, 300, 5.0), degrau(n, 340, 5.0), True),
        ('polaridades_opostas', degrau(n, 300, 5.0), degrau(n, 340, -5.0), True),
        ('alta_so_em_A', degrau(n, 300, 5.0), np.full(n, 52.0), True),
        ('limite_lado_A', degrau(n, 300, -5.0), degrau(n, 300 + limite, -5.0), True),
        ('limite_lado_B', degrau(n, 300 + limite, -5.0), degrau(n, 300, -5.0), True),
        ('pouco_alem_do_limite', degrau(n, 300, -5.0), degrau(n, 300 + limite + 2, -5.0), True),
        ('muito_alem_do_limite', degrau(n, 300, -5.0), degrau(n, 300 + limite + 60, -5.0), True),
        ('alta_sem_classificacao', degrau(n, 300, 5.0), degrau(n, 340, 5.0), False),
    ]
    escala = {'minimo_m': 0.0, 'maximo_m': 100.0, 'resolucao_declarada_m': 1e-3}
    casos = []
    for nome, a, b, classificar in sinais:
        e = ensaio(nome, a, b)
        casos.append({'nome': nome, 'classificar': classificar, 'escala': escala, 'ensaio': e,
                      'registro': D.processar_ensaio(e, escala, None, classificar)})
    return casos


def main():
    with open(AMOSTRAS, encoding='utf-8') as f:
        amostras = json.load(f)
    with open(PARAMETROS, encoding='utf-8') as f:
        parametros = json.load(f)
    with open(PACOTE, encoding='utf-8') as f:
        pacote = json.load(f)

    ts = float(amostras['base_de_tempo_s'])
    c_ef = float(parametros['velocidade_de_onda']['efetiva_ajustada_m_s'])
    por_id = {e['id']: e for e in amostras['ensaios']}
    escolha = AM.escolher_frequencia(c_ef, ts)

    # --- configuracoes ------------------------------------------------------
    configuracoes = {
        'neutra': MS.config_neutra(),
        'matriz_por_semente': {str(s): MX.configuracoes_de_sensor(semente=s)
                               for s in (0, 7, 101)},
        'velocidades': MX.velocidades(c_ef),
        'calibracao_padrao': D.calibracao_padrao(),
        'escolha_de_frequencia': escolha,
    }

    # --- A-09 um efeito por vez e configuracoes completas ------------------
    base = por_id['EV-01']
    a0 = np.asarray(base['canal_A_carga_m'], dtype=float)
    b0 = np.asarray(base['canal_B_carga_m'], dtype=float)
    casos_sensor = um_efeito_por_vez(ts)
    for nivel in ('baixo', 'alto'):
        casos_sensor.append(('matriz_' + nivel,
                             MX.configuracoes_de_sensor(semente=0)[nivel]))
    modelo = []
    for nome, cfg in casos_sensor:
        sa, sb, reg = MS.aplicar(a0, b0, ts, cfg)
        modelo.append({
            'nome': nome,
            'ensaio': base['id'],
            'config': cfg,
            'sorteios': sorteios(cfg, len(a0), len(b0)),
            'saida_A': sa,
            'saida_B': sb,
            'registro': reg,
            'resolucao_declarada_m': MS.resolucao_declarada_m(cfg),
        })

    # --- cadeia de ponta a ponta, como gerar_ensaios.py -------------------
    cadeia = []
    calibracao = D.calibracao_padrao()
    for indice, id_origem in enumerate(MX.ENSAIOS_DE_ORIGEM):
        origem = por_id[id_origem]
        for nivel in MX.NIVEIS_DE_RUIDO:
            cfg = MX.configuracoes_de_sensor(semente=indice * 7)[nivel]
            a = np.asarray(origem['canal_A_carga_m'], dtype=float)
            b = np.asarray(origem['canal_B_carga_m'], dtype=float)
            sa, sb, reg = MS.aplicar(a, b, ts, cfg)
            resolucao = MS.resolucao_declarada_m(cfg)
            escala = {'minimo_m': MX.ESCALA_MIN_M,
                      'maximo_m': MX.ESCALA_MAX_M,
                      'resolucao_declarada_m': resolucao}
            grupo = {
                'ensaio_de_origem': id_origem,
                'nivel': nivel,
                'config': cfg,
                'sorteios': sorteios(cfg, len(a), len(b)),
                'escala': escala,
                'decimado_A': None,
                'decimado_B': None,
                'por_velocidade': [],
            }
            for nome_c, dados_c in MX.velocidades(c_ef).items():
                par = {
                    'posicao_sensor_A_m': float(parametros['sensores']['A']['posicao_m']),
                    'posicao_sensor_B_m': float(parametros['sensores']['B']['posicao_m']),
                    'distancia_entre_sensores_L_m':
                        float(parametros['sensores']['distancia_entre_sensores_L_m']),
                    'velocidade_de_onda_m_s': dados_c['c_m_s'],
                    'incerteza_de_velocidade_de_onda_m_s': dados_c['incerteza_m_s'],
                }
                ensaio = AM.montar_ensaio('%s/%s/%s' % (id_origem, nivel, nome_c),
                                          origem['tempo_s'], sa, sb, par,
                                          {'resolucao_declarada_m': resolucao},
                                          escolha)
                registro = D.processar_ensaio(ensaio, escala, calibracao)
                grupo['decimado_A'] = ensaio['canal_A_carga_m']
                grupo['decimado_B'] = ensaio['canal_B_carga_m']
                grupo['por_velocidade'].append({
                    'velocidade': nome_c,
                    'parametros_do_detector': par,
                    'registro': registro,
                })
            cadeia.append(grupo)

    # --- detector sobre o pacote da matriz --------------------------------
    escala_pacote = pacote.get('escala') or {}
    detector = []
    for k, ensaio in enumerate(pacote['ensaios']):
        registro = D.processar_ensaio(ensaio, escala_pacote, calibracao)
        item = {'id': ensaio['id'], 'registro': registro}
        if k < N_INTERMEDIARIOS:
            t = np.asarray(ensaio['tempo_s'], dtype=float)
            ts_d = float(np.median(np.diff(t)))
            resolucao = escala_pacote.get('resolucao_declarada_m')
            inter = {}
            for canal in ('canal_A_carga_m', 'canal_B_carga_m'):
                _, y, razao, e_longa = D.detectar_canal(ensaio[canal], ts_d,
                                                       calibracao, resolucao)
                inter[canal[:7]] = {'passa_altas': y, 'razao': razao,
                                    'energia_longa': e_longa}
            item['intermediarios'] = inter
        detector.append(item)

    gabarito = {
        'descricao': ('Gabarito de paridade gerado pelo Python de '
                      '04_detector. A adaptacao em web/leakmap_detector.js '
                      'tem de reproduzir estes valores. Nunca editar a mao: '
                      'rodar web/gerar_gabarito.py.'),
        'versao': 'gabarito-js-v1',
        'origem': ['04_detector/modelo_sensor.py', '04_detector/amostragem.py',
                   '04_detector/detector.py', '04_detector/posicao.py',
                   '04_detector/matriz.py'],
        'pacote_de_origem': os.path.basename(PACOTE),
        'amostras_de_origem': os.path.basename(AMOSTRAS),
        'base_de_tempo_s': ts,
        'configuracoes': configuracoes,
        'modelo_sensor': modelo,
        'cadeia': cadeia,
        'detector': detector,
        'classificacao': casos_de_classificacao(),
    }

    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(sem_nan(gabarito), f, ensure_ascii=False, allow_nan=False)
    print('escrito: %s (%.0f kB)' % (os.path.relpath(SAIDA, RAIZ),
                                     os.path.getsize(SAIDA) / 1024))
    print('casos: modelo de sensor %d | cadeia %d | detector %d'
          % (len(modelo), len(cadeia), len(detector)))


if __name__ == '__main__':
    main()

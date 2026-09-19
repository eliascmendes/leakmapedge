"""LEAKMAP A-10 - amostragem e referencia temporal comum.

Escolhe a frequencia de amostragem por criterio, decima o passo do
solucionador e monta o pacote do ensaio: amostras dos dois canais, indice
comum, frequencia de amostragem, unidades, escala e os parametros que o
detector pode conhecer.

CRITERIO DA FREQUENCIA DE AMOSTRAGEM
------------------------------------
A resolucao de posicao alcancavel sem refinamento adicional e

    resolucao = c * Ts / 2

porque um erro de uma amostra em delta_t vira c * Ts / 2 metros na formula
x = (L + c * delta_t) / 2.

A escolha e feita em dois passos, os dois verificaveis:

1. Requisito de produto: localizar dentro de 0,5 m em um trecho de 200 m.
   Sobre esse requisito aplica-se um fator de seguranca 2, porque a resolucao
   de amostragem nao e a unica contribuicao de erro (ruido, jitter, diferenca
   de atraso entre canais e incerteza de c entram junto). Resolucao de
   projeto: 0,25 m, logo fs >= c / (2 * 0,25).

2. A decimacao a partir do passo do solucionador e por fator inteiro, para
   que o indice comum continue alinhado com a base de tempo original. Toma-se
   o maior fator inteiro que ainda satisfaz o passo 1.

3. Verificacao adicional: as janelas do detector (A-11) precisam caber no
   trecho anterior ao evento que o ensaio gravou. Isso e checado por
   `verificar_janela_de_referencia`, nao suposto.

Interpolar para uma frequencia maior nao cria informacao fisica ausente,
apenas suaviza a curva; por isso so ha decimacao aqui, nunca sobreamostragem.
"""
import numpy as np

RESOLUCAO_REQUISITO_M = 0.5    # requisito de produto
FATOR_DE_SEGURANCA = 2.0       # demais contribuicoes de erro


def escolher_frequencia(c_m_s, ts_solucionador_s,
                        resolucao_requisito_m=RESOLUCAO_REQUISITO_M,
                        fator_de_seguranca=FATOR_DE_SEGURANCA):
    """Devolve a escolha de frequencia com a conta que a justifica."""
    fs_solucionador = 1.0 / ts_solucionador_s
    resolucao_de_projeto = resolucao_requisito_m / fator_de_seguranca
    fs_minima = c_m_s / (2.0 * resolucao_de_projeto)
    fator = int(np.floor(fs_solucionador / fs_minima))
    if fator < 1:
        raise ValueError(
            'o passo do solucionador (%g s) ja e mais lento que o periodo de '
            'amostragem exigido (%g s); nao ha decimacao possivel'
            % (ts_solucionador_s, 1.0 / fs_minima))
    fs = fs_solucionador / fator
    ts = 1.0 / fs
    resolucao = c_m_s * ts / 2.0
    return {
        'requisito_de_resolucao_m': float(resolucao_requisito_m),
        'fator_de_seguranca': float(fator_de_seguranca),
        'resolucao_de_projeto_m': float(resolucao_de_projeto),
        'velocidade_de_onda_usada_m_s': float(c_m_s),
        'frequencia_minima_hz': float(fs_minima),
        'frequencia_do_solucionador_hz': float(fs_solucionador),
        'fator_de_decimacao': int(fator),
        'frequencia_de_amostragem_hz': float(fs),
        'periodo_de_amostragem_s': float(ts),
        'resolucao_de_posicao_m': float(resolucao),
        'conta': ('fs >= c / (2 * resolucao_de_projeto) = %.6g / (2 * %.6g) '
                  '= %.3f Hz; maior fator inteiro de decimacao a partir de '
                  '%.3f Hz e %d, resultando em %.3f Hz e resolucao de '
                  '%.4f m' % (c_m_s, resolucao_de_projeto, fs_minima,
                              fs_solucionador, fator, fs, resolucao)),
    }


def verificar_janela_de_referencia(n_amostras_antes_do_evento, fator,
                                   n_curta, n_guarda, n_longa):
    """As janelas do detector precisam caber no trecho anterior ao evento.

    `n_amostras_antes_do_evento` e contado na base do solucionador; as janelas
    sao contadas na base decimada.
    """
    disponivel = n_amostras_antes_do_evento // fator
    necessario = n_curta + n_guarda + n_longa
    return {
        'amostras_disponiveis_antes_do_evento': int(disponivel),
        'amostras_necessarias_pelas_janelas': int(necessario),
        'folga_em_amostras': int(disponivel - necessario),
        'aprovado': bool(disponivel >= necessario),
    }


def media_movel(x, fator):
    """Anti-serrilhamento causal antes da decimacao.

    Media movel de `fator` amostras. Antes do inicio da serie o sinal e
    mantido em x[0], que e o regime permanente. O atraso de grupo,
    (fator - 1) / 2 amostras, e igual nos dois canais e por isso se cancela em
    delta_t = tA - tB; ele afeta apenas o tempo de deteccao absoluto e esta
    registrado no pacote.
    """
    x = np.asarray(x, dtype=float)
    if fator <= 1:
        return x
    enchimento = np.full(fator - 1, x[0], dtype=float)
    return np.convolve(np.concatenate([enchimento, x]),
                       np.ones(fator) / fator, mode='valid')


def decimar(x, fator, antisserrilhamento=True):
    x = np.asarray(x, dtype=float)
    if fator <= 1:
        return x.copy()
    if antisserrilhamento:
        x = media_movel(x, fator)
    return x[::fator].copy()


def atraso_de_grupo_s(fator, ts_solucionador_s, antisserrilhamento=True):
    if fator <= 1 or not antisserrilhamento:
        return 0.0
    return (fator - 1) / 2.0 * ts_solucionador_s


def montar_ensaio(identificador, tempo_s, canal_a, canal_b, parametros,
                  efeitos_de_sensor, escolha, antisserrilhamento=True):
    """Monta um ensaio do pacote a partir das series na base do solucionador."""
    fator = escolha['fator_de_decimacao']
    t = np.asarray(tempo_s, dtype=float)[::fator]
    a = decimar(canal_a, fator, antisserrilhamento)
    b = decimar(canal_b, fator, antisserrilhamento)
    n = min(len(t), len(a), len(b))
    return {
        'id': identificador,
        'n_pontos': int(n),
        'indice': list(range(int(n))),
        'tempo_s': [float(v) for v in t[:n]],
        'canal_A_carga_m': [float(v) for v in a[:n]],
        'canal_B_carga_m': [float(v) for v in b[:n]],
        'parametros_do_detector': parametros,
        'efeitos_de_sensor_aplicados': efeitos_de_sensor,
    }


def montar_pacote(descricao, escolha, escala, ensaios, ts_solucionador_s,
                  antisserrilhamento=True, observacoes=None):
    """Pacote do ensaio, formato `pacote-v1`.

    Campos, todos obrigatorios para quem for ler ou escrever o formato:

    - `versao_do_formato`: identificador do formato.
    - `amostragem`: a escolha de frequencia com a conta que a justifica.
    - `unidades`: unidade de cada serie.
    - `escala`: faixa util e resolucao declarada do instrumento.
    - `atraso_de_grupo_do_antisserrilhamento_s`: atraso comum aos dois canais
      introduzido pela decimacao; nao afeta delta_t.
    - `ensaios[]`: para cada ensaio, `id`, `n_pontos`, `indice` (comum aos
      dois canais), `tempo_s`, `canal_A_carga_m`, `canal_B_carga_m`,
      `parametros_do_detector` e `efeitos_de_sensor_aplicados`.

    O pacote nunca carrega a posicao real do vazamento: essa informacao vive
    so em 03_ensaios/verdade_do_cenario e e de uso exclusivo do avaliador.
    """
    return {
        'descricao': descricao,
        'versao_do_formato': 'pacote-v1',
        'amostragem': escolha,
        'unidades': {'tempo': 's', 'carga': 'm', 'indice': 'amostra'},
        'escala': escala,
        'atraso_de_grupo_do_antisserrilhamento_s': atraso_de_grupo_s(
            escolha['fator_de_decimacao'], ts_solucionador_s,
            antisserrilhamento),
        'observacoes': observacoes or [],
        'ensaios': ensaios,
    }

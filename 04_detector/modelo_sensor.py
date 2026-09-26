"""LEAKMAP A-09 - modelo dos sensores.

Transforma a carga ideal do solucionador no sinal que um transmissor
entregaria. Cada efeito tem seu proprio parametro e pode ser ligado ou
desligado sozinho, para que a matriz de ensaios varra um efeito por vez.

Criterio de conclusao da etapa: com todos os efeitos desligados a saida e
identica a entrada, bit a bit. Ligando um efeito por vez, so a caracteristica
esperada daquele efeito muda. Ver 04_detector/testes/teste_modelo_sensor.py.

Ressalva de modelagem (vem do proprio fluxograma A-09): sem dados do
transmissor instalado no cais, estes parametros sao hipoteses para analise de
sensibilidade, nao um modelo fiel do instrumento. Por isso a matriz varre
faixas de parametro em vez de fixar um valor unico apresentado como real.
"""
import numpy as np

# Ordem em que os efeitos sao aplicados. E a ordem fisica da cadeia:
# o transmissor primeiro responde a pressao (banda), um transmissor
# inteligente ainda filtra (amortecimento) e so atualiza a saida analogica de
# tempos em tempos (atualizacao), o sinal leva um tempo
# para chegar ao registrador (atrasos), a base de tempo tem imprecisao
# (sincronizacao), e so entao vem os efeitos de eletronica e de conversao.
ORDEM_DOS_EFEITOS = (
    'banda',
    'amortecimento',
    'atualizacao',
    'atraso_comum',
    'diferenca_de_atraso',
    'erro_de_sincronizacao',
    'offset',
    'ruido',
    'saturacao',
    'quantizacao',
)


def config_neutra():
    """Configuracao com todos os efeitos desligados.

    Aplicada a qualquer sinal, devolve o proprio sinal de entrada.
    """
    return {
        # Resposta do transmissor: passa-baixas de primeira ordem em cascata.
        'banda': {'ligado': False, 'corte_hz': 400.0, 'ordem': 1},
        # Filtro de amortecimento (damping) de transmissor inteligente:
        # passa-baixas de primeira ordem com a constante de tempo configurada.
        'amortecimento': {'ligado': False, 'constante_de_tempo_s': 0.0},
        # Atualizacao da saida analogica de transmissor inteligente: a saida
        # so muda a cada `periodo_s` e segura o valor entre as atualizacoes.
        # Cada transmissor tem o proprio relogio, entao a fase de A e de B e
        # independente; sem fase declarada, ela e sorteada pela semente.
        'atualizacao': {'ligado': False, 'periodo_s': 0.0, 'fase_A_s': None,
                        'fase_B_s': None, 'semente': 0},
        # Atraso igual nos dois canais (cabo, conversao, tempo de resposta).
        # Nao altera delta_t, altera o tempo de deteccao absoluto.
        'atraso_comum': {'ligado': False, 'atraso_s': 0.0},
        # Atraso adicional so no canal B. Este sim entra direto no delta_t.
        'diferenca_de_atraso': {'ligado': False, 'atraso_s': 0.0},
        # Imprecisao aleatoria do instante de cada amostra.
        'erro_de_sincronizacao': {'ligado': False, 'jitter_s': 0.0, 'semente': 0},
        # Desvio de zero de cada transmissor.
        'offset': {'ligado': False, 'offset_A_m': 0.0, 'offset_B_m': 0.0},
        # Ruido eletronico, branco e gaussiano, independente por canal.
        'ruido': {'ligado': False, 'desvio_padrao_m': 0.0, 'semente': 0},
        # Faixa util do transmissor.
        'saturacao': {'ligado': False, 'minimo_m': 0.0, 'maximo_m': 100.0},
        # Conversor A/D sobre o fundo de escala declarado.
        'quantizacao': {'ligado': False, 'bits': 16,
                        'fundo_de_escala_min_m': 0.0,
                        'fundo_de_escala_max_m': 100.0},
    }


def resolucao_declarada_m(cfg):
    """Resolucao que o instrumento declara, em m de carga.

    E o degrau do conversor quando a quantizacao esta ligada. Serve de piso
    para o limiar do detector (A-11): nenhum limiar pode ficar abaixo da
    resolucao declarada do sensor. Sem quantizacao ligada, nao ha resolucao
    declarada e a funcao devolve None.
    """
    q = cfg.get('quantizacao', {})
    if not q.get('ligado'):
        return None
    return degrau_de_quantizacao(q['bits'], q['fundo_de_escala_min_m'],
                                 q['fundo_de_escala_max_m'])


def degrau_de_quantizacao(bits, vmin, vmax):
    return (float(vmax) - float(vmin)) / (2 ** int(bits) - 1)


# --- efeitos isolados -------------------------------------------------------

def filtrar_passa_baixas(x, corte_hz, ts, ordem=1):
    """Passa-baixas de primeira ordem em cascata, em NumPy puro.

    y[n] = y[n-1] + alfa * (x[n] - y[n-1]), com y[0] = x[0] para que o regime
    permanente anterior ao evento seja preservado e o filtro nao introduza um
    transiente proprio no inicio da janela.
    """
    x = np.asarray(x, dtype=float)
    tau = 1.0 / (2.0 * np.pi * float(corte_hz))
    alfa = ts / (tau + ts)
    y = x
    for _ in range(int(ordem)):
        saida = np.empty_like(y)
        acc = y[0]
        for n in range(len(y)):
            acc += alfa * (y[n] - acc)
            saida[n] = acc
        y = saida
    return y


def amortecer(x, constante_de_tempo_s, ts):
    """Amortecimento de primeira ordem; constante de tempo zero e identidade."""
    x = np.asarray(x, dtype=float)
    if float(constante_de_tempo_s) <= 0.0:
        return x
    return filtrar_passa_baixas(x, 1.0 / (2.0 * np.pi * float(constante_de_tempo_s)), ts, 1)


def atualizar(x, periodo_s, fase_s, ts):
    """Saida que so muda nos instantes fase + m * periodo e segura o valor.

    Em cada atualizacao a saida passa a valer a ultima amostra da entrada
    ate aquele instante. Antes da primeira atualizacao, segura x[0], o regime
    permanente. Periodo menor ou igual ao passo de amostragem e identidade.
    """
    x = np.asarray(x, dtype=float)
    periodo_s = float(periodo_s)
    if periodo_s <= ts:
        return x
    t = np.arange(len(x), dtype=float) * ts
    m = np.floor((t - float(fase_s)) / periodo_s + 1e-9)
    instante = float(fase_s) + m * periodo_s
    indice = np.floor(instante / ts + 1e-9).astype(int)
    indice[m < 0] = 0
    return x[np.clip(indice, 0, len(x) - 1)]


def atrasar(x, atraso_s, ts):
    """Atrasa o sinal de `atraso_s` segundos, com parte fracionaria.

    Antes do inicio da serie o sinal e mantido no primeiro valor: o trecho
    esta em regime permanente antes do evento, entao segurar h[0] e a
    continuacao fisicamente correta. Atraso zero devolve o proprio sinal.
    """
    x = np.asarray(x, dtype=float)
    d = float(atraso_s) / ts
    if d == 0.0:
        return x
    if d < 0.0:
        raise ValueError('atraso negativo nao e representavel: %r' % atraso_s)
    n = np.arange(len(x), dtype=float)
    return np.interp(n - d, n, x, left=x[0])


def aplicar_jitter(x, jitter_s, ts, semente):
    """Erro de sincronizacao: cada amostra e lida em t[n] + e[n].

    e[n] e gaussiano, independente entre amostras, com desvio `jitter_s`.
    Diferente de `diferenca_de_atraso`, que e um desvio fixo: aqui o erro
    muda a cada amostra e nao se cancela na diferenca entre canais, apenas
    alarga a incerteza da marca de chegada.
    """
    x = np.asarray(x, dtype=float)
    if jitter_s == 0.0:
        return x
    rng = np.random.default_rng(semente)
    n = np.arange(len(x), dtype=float)
    desvio = rng.normal(0.0, float(jitter_s) / ts, size=len(x))
    return np.interp(n + desvio, n, x, left=x[0], right=x[-1])


def saturar(x, minimo_m, maximo_m):
    return np.clip(np.asarray(x, dtype=float), float(minimo_m), float(maximo_m))


def quantizar(x, bits, vmin, vmax):
    """Conversor A/D de `bits` sobre o fundo de escala [vmin, vmax]."""
    x = np.asarray(x, dtype=float)
    passo = degrau_de_quantizacao(bits, vmin, vmax)
    codigo = np.rint((x - float(vmin)) / passo)
    codigo = np.clip(codigo, 0, 2 ** int(bits) - 1)
    return float(vmin) + codigo * passo


# --- cadeia completa --------------------------------------------------------

def aplicar(canal_a, canal_b, ts, cfg):
    """Aplica a cadeia de efeitos aos dois canais.

    Devolve (canal_A, canal_B, registro), em que `registro` lista, na ordem,
    os efeitos que de fato foram aplicados e com quais parametros. O registro
    acompanha o arquivo de amostras para que qualquer resultado possa ser
    reproduzido a partir do sinal limpo.
    """
    a = np.asarray(canal_a, dtype=float).copy()
    b = np.asarray(canal_b, dtype=float).copy()
    registro = []

    for nome in ORDEM_DOS_EFEITOS:
        par = cfg.get(nome)
        if par is None or not par.get('ligado'):
            continue

        if nome == 'banda':
            a = filtrar_passa_baixas(a, par['corte_hz'], ts, par.get('ordem', 1))
            b = filtrar_passa_baixas(b, par['corte_hz'], ts, par.get('ordem', 1))
        elif nome == 'amortecimento':
            a = amortecer(a, par['constante_de_tempo_s'], ts)
            b = amortecer(b, par['constante_de_tempo_s'], ts)
        elif nome == 'atualizacao':
            periodo = float(par['periodo_s'])
            rng = np.random.default_rng(int(par.get('semente', 0)))
            sorteio = rng.uniform(0.0, periodo, size=2)
            fase_a = sorteio[0] if par.get('fase_A_s') is None else float(par['fase_A_s'])
            fase_b = sorteio[1] if par.get('fase_B_s') is None else float(par['fase_B_s'])
            a = atualizar(a, periodo, fase_a, ts)
            b = atualizar(b, periodo, fase_b, ts)
            par = dict(par, fase_A_s=float(fase_a), fase_B_s=float(fase_b))
        elif nome == 'atraso_comum':
            a = atrasar(a, par['atraso_s'], ts)
            b = atrasar(b, par['atraso_s'], ts)
        elif nome == 'diferenca_de_atraso':
            b = atrasar(b, par['atraso_s'], ts)
        elif nome == 'erro_de_sincronizacao':
            s = int(par.get('semente', 0))
            a = aplicar_jitter(a, par['jitter_s'], ts, s)
            b = aplicar_jitter(b, par['jitter_s'], ts, s + 1)
        elif nome == 'offset':
            a = a + float(par.get('offset_A_m', 0.0))
            b = b + float(par.get('offset_B_m', 0.0))
        elif nome == 'ruido':
            rng = np.random.default_rng(int(par.get('semente', 0)))
            sigma = float(par['desvio_padrao_m'])
            a = a + rng.normal(0.0, sigma, size=len(a))
            b = b + rng.normal(0.0, sigma, size=len(b))
        elif nome == 'saturacao':
            a = saturar(a, par['minimo_m'], par['maximo_m'])
            b = saturar(b, par['minimo_m'], par['maximo_m'])
        elif nome == 'quantizacao':
            a = quantizar(a, par['bits'], par['fundo_de_escala_min_m'],
                          par['fundo_de_escala_max_m'])
            b = quantizar(b, par['bits'], par['fundo_de_escala_min_m'],
                          par['fundo_de_escala_max_m'])
        else:
            raise ValueError('efeito desconhecido: %r' % nome)

        registro.append({'efeito': nome,
                         'parametros': {k: v for k, v in par.items()
                                        if k != 'ligado'}})

    return a, b, registro

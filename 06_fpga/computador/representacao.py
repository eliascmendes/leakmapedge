"""LEAKMAP B-02 e B-03 - representacao das amostras em inteiros.

Traduz a carga em metros do pacote do ensaio (A-10) em inteiros que a FPGA
processa, com a traducao inteira registrada. E uma conversao de formato feita
no computador: nao e um conversor analogico-digital e nao representa o
comportamento de um conversor real.

ESPECIFICACAO (B-03), identica no computador e na FPGA
------------------------------------------------------
- unidade fisica: metro de carga (1 m de carga = 0,0981 bar, com rho*g = 9810)
- palavra: 16 bits, sem sinal, de 0 a 65 535
- ponto de referencia: codigo 0 corresponde a 0 m de carga
- degrau: a resolucao declarada do transmissor do ensaio; quando o ensaio nao
  declara conversor (linha sem ruido da matriz), 1 mm de carga
- conversao: codigo = arredonda((carga - referencia) / degrau), com empate
  para o par, que e o arredondamento do NumPy (np.rint)
- fora da faixa: satura no extremo e incrementa um contador por canal. O
  contador acompanha o resultado do ensaio: saturacao nunca e silenciosa
- valor nao numerico (NaN ou infinito): o ensaio e recusado

O degrau e o mesmo que 04_detector/detector_ponto_fixo.py usa, entao os
codigos daqui sao exatamente a entrada da referencia em ponto fixo.
"""
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector_ponto_fixo as PF  # noqa: E402

BITS = 16
CODIGO_MINIMO = 0
CODIGO_MAXIMO = (1 << BITS) - 1
REFERENCIA_M = 0.0
DEGRAU_PADRAO_M = PF.DEGRAU_PADRAO_M
BAR_POR_METRO_DE_CARGA = 9810.0 / 1e5


class ValorInvalido(ValueError):
    pass


def degrau_do_ensaio(ensaio):
    """Degrau da conversao: a resolucao declarada do transmissor, ou 1 mm."""
    efeitos = ensaio.get('efeitos_de_sensor_aplicados') or {}
    return float(efeitos.get('resolucao_declarada_m') or DEGRAU_PADRAO_M)


def especificacao(degrau_m):
    """A especificacao da representacao, gravada junto com o ensaio."""
    degrau_m = float(degrau_m)
    return {
        'unidade': 'metro de carga',
        'bar_por_metro_de_carga': BAR_POR_METRO_DE_CARGA,
        'bits': BITS,
        'com_sinal': False,
        'codigo_minimo': CODIGO_MINIMO,
        'codigo_maximo': CODIGO_MAXIMO,
        'referencia_m': REFERENCIA_M,
        'degrau_m': degrau_m,
        'faixa_util_m': [REFERENCIA_M, REFERENCIA_M + CODIGO_MAXIMO * degrau_m],
        'resolucao_em_bar': degrau_m * BAR_POR_METRO_DE_CARGA,
        'arredondamento': 'mais proximo, empate para o par (np.rint)',
        'fora_da_faixa': 'satura no extremo e incrementa o contador do canal',
        'valor_nao_numerico': 'ensaio recusado',
    }


def converter(carga_m, espec):
    """Carga em metros para codigos inteiros.

    Devolve (codigos, saturadas_abaixo, saturadas_acima). Os codigos sao uma
    lista de int do Python, para nao depender da largura do tipo do NumPy.
    """
    x = np.asarray(carga_m, dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValorInvalido('amostra nao numerica (NaN ou infinito)')
    bruto = np.rint((x - espec['referencia_m']) / espec['degrau_m'])
    abaixo = int(np.count_nonzero(bruto < espec['codigo_minimo']))
    acima = int(np.count_nonzero(bruto > espec['codigo_maximo']))
    codigos = np.clip(bruto, espec['codigo_minimo'], espec['codigo_maximo'])
    return [int(v) for v in codigos], abaixo, acima


def desconverter(codigos, espec):
    """Funcao inversa, usada na conferencia (B-02)."""
    c = np.asarray(codigos, dtype=float)
    return espec['referencia_m'] + c * espec['degrau_m']


def tabela_de_bordas(espec):
    """Casos de borda da conversao, com o codigo que a especificacao exige.

    Criterio de conclusao de B-03: software e FPGA produzem o mesmo inteiro
    para a mesma entrada. Esta tabela e o lado do software; a FPGA recebe
    os codigos prontos e os devolve na leitura de volta da memoria.
    """
    d, r = espec['degrau_m'], espec['referencia_m']
    topo = r + espec['codigo_maximo'] * d

    def empate(v):
        # O empate e decidido sobre o quociente em ponto flutuante: com um
        # degrau que nao e potencia de dois, 1,5 degrau pode virar 1,4999...
        return int(np.rint((v - r) / d))

    casos = [
        ('referencia', r, 0),
        ('meio degrau acima da referencia (empate, par)', r + 0.5 * d, empate(r + 0.5 * d)),
        ('um degrau e meio (empate, par)', r + 1.5 * d, empate(r + 1.5 * d)),
        ('logo abaixo de meio degrau', r + 0.49 * d, 0),
        ('logo acima de meio degrau', r + 0.51 * d, 1),
        ('abaixo da referencia (satura em 0)', r - 3 * d, 0),
        ('topo da faixa', topo, espec['codigo_maximo']),
        ('acima do topo (satura no maximo)', topo + 10 * d, espec['codigo_maximo']),
        ('regime tipico do canal A, 58 m', 58.0, int(np.rint((58.0 - r) / d))),
    ]
    return [{'caso': nome, 'entrada_m': float(v), 'codigo_esperado': int(c)}
            for nome, v, c in casos]

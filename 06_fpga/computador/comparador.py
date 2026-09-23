"""LEAKMAP B-13 - comparacao entre o cenario B e a referencia em software.

Compara, ensaio a ensaio, o registro do cenario B com o registro do cenario A
de mesmo identificador: classe, indice de chegada e de cruzamento por canal,
diferenca temporal em amostras e posicao estimada. A divergencia sai em
amostras e em metros.

O resultado de A e referencia de comparacao entre implementacoes, nao
verdade: a comparacao com a verdade do cenario e feita separadamente, pelo
avaliador independente, para A e para B.

Toda divergencia diferente de zero sai com causa apontada. Para separar as
causas, o detector do cenario A roda de novo sobre a mesma entrada ja
convertida em inteiros (desconvertida para metros):

  - se esse resultado difere de A, a conversao para inteiros (B-02, B-03)
    mudou a marca;
  - se o cenario B difere desse resultado, a aritmetica inteira mudou a
    marca.
Se nenhuma das duas explica a divergencia, ela vira pendencia aberta.
"""
import copy
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import representacao as RP  # noqa: E402

CAUSA_CONVERSAO = 'conversao para inteiros (B-02, B-03)'
CAUSA_ARITMETICA = 'aritmetica inteira em ponto fixo (B-09)'
CAUSA_SEM_RESULTADO = 'o cenario B nao produziu resultado'
PENDENCIA = 'pendencia aberta: divergencia sem causa identificada'


def _marcas(registro):
    saida = {'classe': registro.get('classe')}
    for canal in ('canal_A', 'canal_B'):
        d = registro.get(canal) or {}
        saida[canal] = (d.get('indice_de_chegada'), d.get('indice_de_cruzamento'))
    saida['delta_t_amostras'] = registro.get('delta_t_amostras')
    return saida


def _entrada_convertida(ensaio, preparo):
    copia = copy.deepcopy(ensaio)
    for canal in ('canal_A', 'canal_B'):
        copia[canal + '_carga_m'] = [float(v) for v in RP.desconverter(
            preparo['conversao'][canal]['codigos'], preparo['representacao'])]
    return copia


def comparar_ensaio(registro_a, registro_b, ensaio, preparo, escala, cal):
    linha = {'id': registro_b['id'], 'origem_B': registro_b.get('origem'),
             'classe_A': registro_a.get('classe'), 'classe_B': registro_b.get('classe')}
    if registro_b.get('classe') == D.CLASSE_FALHA:
        linha.update({'igual': False, 'causas': [CAUSA_SEM_RESULTADO]})
        return linha

    for canal in ('canal_A', 'canal_B'):
        a = registro_a.get(canal) or {}
        b = registro_b.get(canal) or {}
        for campo in ('indice_de_chegada', 'indice_de_cruzamento'):
            va, vb = a.get(campo), b.get(campo)
            linha['%s_%s_A' % (canal, campo)] = va
            linha['%s_%s_B' % (canal, campo)] = vb
            linha['%s_%s_divergencia_amostras' % (canal, campo)] = (
                None if va is None or vb is None else vb - va)
    dta, dtb = registro_a.get('delta_t_amostras'), registro_b.get('delta_t_amostras')
    linha['delta_t_divergencia_amostras'] = None if dta is None or dtb is None else dtb - dta
    pa, pb = registro_a.get('posicao_estimada_m'), registro_b.get('posicao_estimada_m')
    linha['posicao_A_m'], linha['posicao_B_m'] = pa, pb
    linha['posicao_divergencia_m'] = None if pa is None or pb is None else pb - pa

    igual = _marcas(registro_a) == _marcas(registro_b)
    linha['igual'] = igual
    if igual:
        linha['causas'] = []
        return linha

    ref_convertida = D.processar_ensaio(_entrada_convertida(ensaio, preparo), escala, cal)
    causas = []
    if _marcas(ref_convertida) != _marcas(registro_a):
        causas.append(CAUSA_CONVERSAO)
    if _marcas(registro_b) != _marcas(ref_convertida):
        causas.append(CAUSA_ARITMETICA)
    linha['causas'] = causas or [PENDENCIA]
    return linha


def resumir(linhas):
    comparaveis = [l for l in linhas if CAUSA_SEM_RESULTADO not in l['causas']]
    div_amostras = [abs(l[k]) for l in comparaveis for k in l
                    if k.endswith('_divergencia_amostras') and l[k] is not None]
    div_metros = [abs(l['posicao_divergencia_m']) for l in comparaveis
                  if l.get('posicao_divergencia_m') is not None]
    causas = {}
    for l in linhas:
        for c in l['causas']:
            causas[c] = causas.get(c, 0) + 1
    return {
        'n_ensaios': len(linhas),
        'identicos': sum(1 for l in linhas if l['igual']),
        'divergentes': sum(1 for l in linhas if not l['igual']),
        'maior_divergencia_amostras': max(div_amostras) if div_amostras else 0,
        'maior_divergencia_de_posicao_m': max(div_metros) if div_metros else 0.0,
        'contagem_por_causa': causas,
        'toda_divergencia_tem_causa': PENDENCIA not in causas,
    }

"""LEAKMAP B-01 - selo de verificacao e selecao de ensaio.

O cenario B nao cria dado novo: reexecuta em hardware exatamente um ensaio
ja aceito no cenario A. O selo registra que o ensaio passou pelas
verificacoes abaixo e grava a impressao digital (SHA-256) do seu conteudo.
O seletor recusa ensaio sem selo, e recusa tambem ensaio cujo conteudo
mudou depois do selo.

Verificacoes do selo:
  - formato: n_pontos igual ao tamanho de tempo e dos dois canais;
  - valores numericos: nenhuma amostra NaN ou infinita;
  - base de tempo comum e uniforme, no periodo declarado pelo pacote;
  - comprimento suficiente para as janelas do detector;
  - o cenario A processou o ensaio e gravou um registro que nao e falha.

Grava 03_ensaios/pacotes/leakmap_selos_v1.json. Nao le a verdade do cenario.
"""
import hashlib
import json
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402

PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes', 'leakmap_pacote_matriz_v1.json')
RESULTADO_A = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_matriz_v1.json')
SELOS = os.path.join(RAIZ, '03_ensaios', 'pacotes', 'leakmap_selos_v1.json')

CAMPOS_SELADOS = ('id', 'n_pontos', 'tempo_s', 'canal_A_carga_m', 'canal_B_carga_m',
                  'parametros_do_detector', 'efeitos_de_sensor_aplicados')


class EnsaioSemSelo(LookupError):
    pass


def impressao(ensaio):
    conteudo = {k: ensaio[k] for k in CAMPOS_SELADOS}
    texto = json.dumps(conteudo, sort_keys=True, separators=(',', ':'), allow_nan=True)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def verificar(ensaio, periodo_s, registro_a, cal=None):
    cal = cal or D.calibracao_padrao()
    n = ensaio['n_pontos']
    t = np.asarray(ensaio['tempo_s'], dtype=float)
    a = np.asarray(ensaio['canal_A_carga_m'], dtype=float)
    b = np.asarray(ensaio['canal_B_carga_m'], dtype=float)
    passos = np.diff(t)
    minimo = cal['n_curta'] + cal['n_guarda'] + cal['n_longa']
    return [
        ('formato', len(t) == len(a) == len(b) == n,
         'n_pontos %d, tempo %d, A %d, B %d' % (n, len(t), len(a), len(b))),
        ('valores_numericos', bool(np.all(np.isfinite(a)) and np.all(np.isfinite(b))
                                   and np.all(np.isfinite(t))), 'NaN ou infinito'),
        ('base_de_tempo_uniforme', bool(len(passos) and np.allclose(passos, periodo_s, rtol=1e-9, atol=0)),
         'passo diferente do periodo declarado de %.9e s' % periodo_s),
        ('comprimento_minimo', n >= minimo, '%d amostras, minimo %d' % (n, minimo)),
        ('processado_no_cenario_A', bool(registro_a) and registro_a.get('classe') != D.CLASSE_FALHA,
         'sem registro valido no resultado do cenario A'),
    ]


def gerar_selos(pacote, resultado_a):
    periodo = float(pacote['amostragem']['periodo_de_amostragem_s'])
    registros = {r['id']: r for r in resultado_a['resultados']}
    selos, recusados = {}, {}
    for ensaio in pacote['ensaios']:
        verificacoes = verificar(ensaio, periodo, registros.get(ensaio['id']))
        falhas = [{'verificacao': nome, 'detalhe': detalhe}
                  for nome, ok, detalhe in verificacoes if not ok]
        if falhas:
            recusados[ensaio['id']] = falhas
        else:
            selos[ensaio['id']] = {
                'impressao_sha256': impressao(ensaio),
                'verificacoes': [nome for nome, _, _ in verificacoes],
            }
    return {
        'descricao': ('Selos de verificacao do cenario B (B-01). Um ensaio so e '
                      'reexecutado na FPGA se tiver selo e se o seu conteudo '
                      'ainda tiver a mesma impressao digital.'),
        'versao': 'selos-v1',
        'pacote_de_origem': os.path.basename(PACOTE),
        'resultado_do_cenario_A': os.path.basename(RESULTADO_A),
        'n_selados': len(selos),
        'n_recusados': len(recusados),
        'selos': selos,
        'recusados': recusados,
    }


def selecionar(identificador, pacote, selos):
    """Devolve o ensaio pelo identificador, so se o selo conferir."""
    registro = selos['selos'].get(identificador)
    if registro is None:
        motivo = selos.get('recusados', {}).get(identificador)
        raise EnsaioSemSelo('ensaio %s sem selo de verificacao%s'
                            % (identificador, ': %r' % motivo if motivo else ''))
    for ensaio in pacote['ensaios']:
        if ensaio['id'] == identificador:
            if impressao(ensaio) != registro['impressao_sha256']:
                raise EnsaioSemSelo('ensaio %s mudou depois do selo' % identificador)
            return ensaio
    raise EnsaioSemSelo('ensaio %s nao esta no pacote' % identificador)


def main():
    with open(PACOTE, encoding='utf-8') as f:
        pacote = json.load(f)
    with open(RESULTADO_A, encoding='utf-8') as f:
        resultado_a = json.load(f)
    selos = gerar_selos(pacote, resultado_a)
    with open(SELOS, 'w', encoding='utf-8') as f:
        json.dump(selos, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(SELOS, RAIZ))
    print('selados: %d | recusados: %d' % (selos['n_selados'], selos['n_recusados']))


if __name__ == '__main__':
    main()

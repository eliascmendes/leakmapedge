"""LEAKMAP - confere se o ambiente do TSNet reproduz as simulacoes gravadas.

Refaz simulacoes que ja estao gravadas em 03_ensaios/amostras e compara, ponto
a ponto, a carga nos sensores e a base de tempo. Serve para saber, numa
maquina nova, se o ambiente esta pronto para refazer os ensaios do zero.

  padrao        o evento EV-01 do trecho de 200 m da matriz (alguns segundos)
  --completo    tambem um vazamento da linha do cais e um da rede com ramais
                (cerca de 1 e 2 minutos)

Sai com codigo 0 quando tudo confere dentro da tolerancia, 1 quando nao.
Uso, com o Python do ambiente:
  python 02_bancada/ambiente/conferir_ambiente.py [--completo]
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import warnings
from importlib import metadata

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
CODIGO = os.path.join(RAIZ, '02_bancada', 'codigo')
AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras')

VERSOES = {'numpy': '1.26.4', 'wntr': '1.3.2', 'tsnet': '0.3.1'}
TOLERANCIA_CARGA_M = 1e-4       # o arquivo de rede arredonda; a diferenca medida foi de 5e-6 m
TOLERANCIA_TEMPO_S = 1e-9


def calado():
    """O TSNet imprime o progresso da simulacao; aqui so interessa a comparacao."""
    return contextlib.redirect_stdout(io.StringIO())


def conferir_versoes():
    ok = True
    for pacote, esperada in VERSOES.items():
        try:
            instalada = metadata.version(pacote)     # tsnet.__version__ devolve 0.2.2 na wheel 0.3.1
        except metadata.PackageNotFoundError:
            instalada = None
        certo = instalada == esperada
        ok &= certo
        print('%-6s %-8s %s' % (pacote, instalada or '-', 'ok' if certo else 'ESPERADO %s' % esperada))
    print('python %s' % sys.version.split()[0])
    return ok


def comparar(nome, t, canais, gravado):
    """Maior diferenca entre a simulacao refeita e a gravada, por canal e no tempo."""
    import numpy as np
    tg = np.asarray(gravado['tempo_s'], dtype=float)
    i0 = int(np.argmin(np.abs(np.asarray(t) - tg[0])))
    n = len(tg)
    dif_t = float(np.max(np.abs(np.asarray(t[i0:i0 + n]) - tg))) if len(t) >= i0 + n else float('inf')
    difs = {}
    for canal, refeito in canais.items():
        g = np.asarray(gravado[canal], dtype=float)
        r = np.asarray(refeito, dtype=float)[i0:i0 + n]
        difs[canal] = float(np.max(np.abs(r - g))) if len(r) == len(g) else float('inf')
    certo = dif_t <= TOLERANCIA_TEMPO_S and all(d <= TOLERANCIA_CARGA_M for d in difs.values())
    print('%-34s tempo %.1e s | %s | %s' % (nome, dif_t, ', '.join('%s %.1e m' % kv for kv in difs.items()),
                                          'ok' if certo else 'DIFERENTE'))
    return certo


def ler(nome):
    with open(os.path.join(AMOSTRAS, nome), encoding='utf-8') as f:
        return json.load(f)


def matriz_ev01(pasta):
    import numpy as np
    import simular as S
    from build_model import escrever_inp, nome_no, SENSOR_A, SENSOR_B, POS_EVENTO
    gravado = next(e for e in ler('leakmap_amostras_v1.json')['ensaios'] if e['id'] == 'EV-01')
    with calado():
        tm = S.rodar(POS_EVENTO[0], escrever_inp(os.path.join(pasta, 'trecho200.inp')))
    canais = {'canal_A_carga_m': np.asarray(tm.get_node(nome_no(SENSOR_A))._head),
              'canal_B_carga_m': np.asarray(tm.get_node(nome_no(SENSOR_B))._head)}
    return comparar('matriz, EV-01 (trecho de 200 m)', tm.simulation_timestamps, canais, gravado)


def linha_do_cais(pasta):
    import linha_cais as LC
    import velocidade_de_onda as VO
    gravado = next(e for e in ler('leakmap_amostras_linha_cais_v1.json')['ensaios'] if e['id'] == 'LC-05')
    c = VO.velocidade(LC.PRODUTO, LC.NOMINAL, LC.MATERIAL, LC.SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(LC.NOMINAL, LC.SCHEDULE)
    inp = LC.escrever_inp(os.path.join(pasta, 'linha_cais.inp'), d)
    with calado():
        tm = LC.rodar(inp, c, 450.0, LC.TAMANHOS['grande'], pasta)
    canais = {'canal_A_carga_m': LC.serie(tm, LC.POS_SENSOR_A), 'canal_B_carga_m': LC.serie(tm, LC.POS_SENSOR_B)}
    return comparar('linha do cais, LC-05 (450 m, grande)', tm.simulation_timestamps, canais, gravado)


def rede_do_cais(pasta):
    import linha_cais as LC
    import rede_cais as RC
    import velocidade_de_onda as VO
    gravado = next(e for e in ler('leakmap_amostras_rede_cais_v1.json')['ensaios'] if e['id'] == 'RC-01')
    c = VO.velocidade(LC.PRODUTO, LC.NOMINAL, LC.MATERIAL, LC.SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(LC.NOMINAL, LC.SCHEDULE)
    inp = RC.escrever_inp(os.path.join(pasta, 'rede_cais.inp'), d)
    with calado():
        tm = RC.rodar(inp, c, RC.VAZAMENTOS[0], RC.TAMANHOS['grande'], pasta)
    canais = {k: RC.serie(tm, k) for k in RC.SENSORES}
    return comparar('rede do cais, RC-01 (tronco, grande)', tm.simulation_timestamps, canais,
                    dict(gravado['canais_carga_m'], tempo_s=gravado['tempo_s']))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--completo', action='store_true', help='tambem a linha do cais e a rede (~3 min)')
    args = ap.parse_args()
    warnings.filterwarnings('ignore')
    versoes = conferir_versoes()
    sys.path.insert(0, CODIGO)
    pasta = tempfile.mkdtemp(prefix='leakmap_conferencia_')
    os.chdir(pasta)                  # o TSNet grava arquivos de resultado na pasta corrente
    casos = [matriz_ev01] + ([linha_do_cais, rede_do_cais] if args.completo else [])
    resultados = [caso(pasta) for caso in casos]
    ok = versoes and all(resultados)
    print('\nambiente %s' % ('CONFERE com as simulacoes gravadas' if ok else 'NAO confere: veja acima'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()

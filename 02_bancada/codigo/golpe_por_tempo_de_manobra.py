"""LEAKMAP - golpe de ariete em funcao do tempo de manobra (TSNet).

Referencia para a previsao do pico antes da manobra (07_servico/previsao_de_golpe.py).
As simulacoes de manobra da bancada (manobras_cais.py, manobras_rede.py,
manobras_trecho_200.py) fecham cada valvula num tempo so (0,3 s; 20 ms no
trecho de 200 m). Para conferir a previsao, e sobretudo o conselho "feche em
pelo menos X s", aqui o mesmo fechamento roda com varios tempos de manobra e
cortando metade ou toda a vazao do equipamento, nos mesmos modelos:

  cais        XV-108 (navio do berco 108, fim da linha) e XV-106 (berco 106,
              no meio da linha), retiradas de 0,040 e 0,015 m3/s
  rede        XV-108 (navio no fim do ramal_108), retirada de 0,020 m3/s
  trecho_200  XV-100 (tomada em 100 m, entre dois reservatorios), 0,010 m3/s

Para cada simulacao, grava a maior subida de carga em cada sensor e no no do
equipamento, com a carga de regime de cada um. Os casos de CONFERENCIA ficam
fora da grade (outras fracoes, tempos no meio e alem da tabela): a previsao
nao os usa, e eles medem o erro dela onde ela nao foi ajustada.

Grava:
  03_ensaios/verdade_do_cenario/leakmap_golpe_por_tempo_de_manobra_v1.json

Uso: python golpe_por_tempo_de_manobra.py [--casos cais_xv108 rede_xv108] [--sem-gravar]
"""
import argparse
import json
import os
import tempfile
import time

import numpy as np

import build_model as BM
import linha_cais as LC
import manobras_cais as MC
import manobras_rede as MR
import manobras_trecho_200 as MT
import rede_cais as RC
import velocidade_de_onda as VO

SAIDA = os.path.join(LC.RAIZ, '03_ensaios', 'verdade_do_cenario', 'leakmap_golpe_por_tempo_de_manobra_v1.json')

TEMPOS_S = [0.3, 0.6, 1.0, 1.5, 2.0, 3.0]
TEMPOS_TRECHO_200_S = [0.02, 0.05, 0.1, 0.2, 0.4]
FRACOES = [0.5, 1.0]               # fracao da vazao do equipamento cortada pelo fechamento
# passo de tempo: 2 ms (10 vezes o das simulacoes de deteccao). Para o pico basta, e cada simulacao cai de 7 min
# para menos de 1; o fechamento da XV-108 (metade da vazao em 0,3 s) deu a mesma subida com 0,2 ms e com 2 ms
DT_S = 2e-3
DT_TRECHO_200_S = 1e-3

CASOS = {
    'cais_xv108': {'linha': 'cais', 'equipamento': 'XV-108', 'no_m': MC.POS_NAVIO_108, 'tempos_s': TEMPOS_S},
    'cais_xv106': {'linha': 'cais', 'equipamento': 'XV-106', 'no_m': LC.POS_BERCO_106, 'tempos_s': TEMPOS_S},
    'rede_xv108': {'linha': 'rede', 'equipamento': 'XV-108', 'trecho': 'ramal_108',
                   'no_m': RC.RAMAIS_M['ramal_108'] + RC.NAVIO_APOS_SENSOR_M, 'tempos_s': TEMPOS_S},
    'trecho_200_xv100': {'linha': 'trecho_200', 'equipamento': 'XV-100', 'no_m': 100.0,
                         'tempos_s': TEMPOS_TRECHO_200_S, 'fracoes': [1.0]},
}


# (caso, fracao cortada, tempo de manobra): fora da grade acima, para medir o erro da previsao
CONFERENCIA = [('cais_xv108', 0.75, 1.2), ('cais_xv108', 0.30, 2.5), ('cais_xv108', 1.0, 5.0),
               ('cais_xv106', 0.75, 0.8), ('rede_xv108', 0.75, 1.2), ('rede_xv108', 0.30, 4.0),
               ('trecho_200_xv100', 0.5, 0.15)]


def simular(caso, inp, pasta, c, tempo_s, fracao):
    import tsnet
    tf = LC.TS_EVENTO + tempo_s + 2.5
    tm = tsnet.network.TransientModel(inp)
    if caso['linha'] == 'trecho_200':
        tm.set_wavespeed(MT.C_SOLICITADA)
        tm.set_time(MT.TS_MANOBRA + tempo_s + 0.6, DT_TRECHO_200_S)
        tm.add_demand_pulse(BM.nome_no(caso['no_m']), [100.0, MT.TS_MANOBRA, tempo_s, -fracao])
    else:
        tm.set_wavespeed(c)
        tm.set_time(tf, DT_S)
        no = LC.nome_no(caso['no_m']) if caso['linha'] == 'cais' else RC.nome_do_no(caso['trecho'], caso['no_m'])
        tm.add_demand_pulse(no, [100.0, LC.TS_EVENTO, tempo_s, -fracao])
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    return tsnet.simulation.MOCSimulator(tm, os.path.join(pasta, 'golpe'))


def series(caso, tm):
    """Carga em cada sensor e no no do equipamento."""
    if caso['linha'] == 'trecho_200':
        no = lambda x: np.asarray(tm.get_node(BM.nome_no(x))._head, dtype=float)
        return {'A': no(BM.SENSOR_A), 'B': no(BM.SENSOR_B)}, no(caso['no_m'])
    if caso['linha'] == 'cais':
        return {'A': LC.serie(tm, LC.POS_SENSOR_A), 'B': LC.serie(tm, LC.POS_SENSOR_B)}, LC.serie(tm, caso['no_m'])
    sens = {s: np.asarray(tm.get_node(RC.nome_do_no(*RC.SENSORES[s]))._head, dtype=float) for s in RC.SENSORES}
    return sens, np.asarray(tm.get_node(RC.nome_do_no(caso['trecho'], caso['no_m']))._head, dtype=float)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--casos', nargs='*', default=list(CASOS))
    ap.add_argument('--sem-gravar', action='store_true')
    args = ap.parse_args()
    c = VO.velocidade(LC.PRODUTO, LC.NOMINAL, LC.MATERIAL, LC.SCHEDULE)['velocidade_m_s']
    d = VO.diametro_interno_m(LC.NOMINAL, LC.SCHEDULE)
    pasta = tempfile.mkdtemp(prefix='leakmap_golpe_')
    inps = {'cais': MC.escrever_inp(os.path.join(pasta, 'cais.inp'), d),
            'rede': MR.escrever_inp(os.path.join(pasta, 'rede.inp'), d),
            'trecho_200': MT.escrever_inp(os.path.join(pasta, 'trecho200.inp'))}
    resultados = []
    rodadas = [(nome, fracao, tempo_s, 'grade') for nome in args.casos
               for fracao in CASOS[nome].get('fracoes', FRACOES) for tempo_s in CASOS[nome]['tempos_s']]
    rodadas += [(nome, fracao, tempo_s, 'conferencia') for nome, fracao, tempo_s in CONFERENCIA if nome in args.casos]
    for nome, fracao, tempo_s, papel in rodadas:
        caso = CASOS[nome]
        inicio = time.time()
        tm = simular(caso, inps[caso['linha']], pasta, c, tempo_s, fracao)
        sens, eq = series(caso, tm)
        r = {'caso': nome, 'papel': papel, 'linha': caso['linha'], 'equipamento': caso['equipamento'],
             'fracao_da_vazao_cortada': fracao, 'tempo_de_manobra_s': tempo_s,
             'carga_de_regime_m': {s: float(x[0]) for s, x in sens.items()},
             'maior_subida_m': {s: float(x.max() - x[0]) for s, x in sens.items()},
             'carga_de_regime_no_equipamento_m': float(eq[0]),
             'maior_subida_no_equipamento_m': float(eq.max() - eq[0])}
        resultados.append(r)
        print('%s corta %3.0f%% em %.2f s: subida no equipamento %6.2f m | %s (%.0f s)' % (
            nome, 100 * fracao, tempo_s, r['maior_subida_no_equipamento_m'],
            ', '.join('%s %.2f' % kv for kv in r['maior_subida_m'].items()), time.time() - inicio), flush=True)
    if args.sem_gravar:
        return
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Golpe de ariete por tempo de manobra, para conferir a previsao do pico antes da '
                                 'manobra (07_servico/previsao_de_golpe.py). Cargas em metro de coluna do produto '
                                 '(diesel no cais e na rede, agua no trecho de 200 m).'),
                   'metodo': ('TSNet, add_demand_pulse: a retirada do no cai pela fracao, em rampa linear; passo de '
                              '%g s (%g s no trecho de 200 m)' % (DT_S, DT_TRECHO_200_S)),
                   'resultados': resultados}, f, ensure_ascii=False, indent=1)
    print('escrito: %s' % os.path.relpath(SAIDA, LC.RAIZ))


if __name__ == '__main__':
    main()

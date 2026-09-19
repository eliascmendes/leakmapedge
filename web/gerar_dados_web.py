"""LEAKMAP - dados da simulacao interativa do painel.

Grava web/leakmap_dados_web.js a partir dos arquivos versionados em
03_ensaios, para que o simulador do painel parta exatamente da mesma entrada
que o Python:

  sinais     carga em metros de leakmap_amostras_v1.json, sem arredondar;
  parametros o que o detector pode conhecer (leakmap_parametros_v1.json);
  verdade    a posicao real de cada evento (leakmap_verdade_v1.json);
  sorteios   os sorteios gaussianos que o Python usou na matriz de ensaios,
             por evento e nivel de ruido. Com eles a primeira corrida de cada
             cenario no navegador repete exatamente o numero publicado em
             05_avaliacao; o botao de nova realizacao passa a usar o gerador
             do proprio navegador.

A verdade vai num bloco separado e so e usada pela funcao que faz o papel
do avaliador na tela, para calcular o erro. O detector em JavaScript recebe
apenas os sinais e os parametros, como o Python de 04_detector.

O arquivo e JavaScript, e nao JSON, para o painel funcionar tambem aberto
direto do disco, sem servidor.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))
sys.path.insert(0, os.path.join(RAIZ, 'web'))

import matriz as MX  # noqa: E402
from gerar_gabarito import sorteios  # noqa: E402

AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_v1.json')
PARAMETROS = os.path.join(RAIZ, '03_ensaios', 'parametros',
                          'leakmap_parametros_v1.json')
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario',
                       'leakmap_verdade_v1.json')
SAIDA = os.path.join(RAIZ, 'web', 'leakmap_dados_web.js')


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def sorteios_da_matriz(amostras):
    """Mesmas sementes de 04_detector/gerar_ensaios.py: indice do evento * 7."""
    por_id = {e['id']: e for e in amostras['ensaios']}
    saida = {}
    for indice, id_origem in enumerate(MX.ENSAIOS_DE_ORIGEM):
        n_a = len(por_id[id_origem]['canal_A_carga_m'])
        n_b = len(por_id[id_origem]['canal_B_carga_m'])
        cfgs = MX.configuracoes_de_sensor(semente=indice * 7)
        for nivel in ('baixo', 'alto'):
            z = sorteios(cfgs[nivel], n_a, n_b)
            saida['%s/%s' % (id_origem, nivel)] = {
                k: [float(v) for v in arr] for k, arr in z.items()}
    return saida


def main():
    amostras = ler(AMOSTRAS)
    parametros = ler(PARAMETROS)
    verdade = ler(VERDADE)

    dados = {
        'origem': [os.path.relpath(p, RAIZ).replace(os.sep, '/')
                   for p in (AMOSTRAS, PARAMETROS, VERDADE)],
        'parametros': {
            'trecho_m': float(parametros['trecho_m']),
            'posicao_sensor_A_m': float(parametros['sensores']['A']['posicao_m']),
            'posicao_sensor_B_m': float(parametros['sensores']['B']['posicao_m']),
            'distancia_entre_sensores_L_m':
                float(parametros['sensores']['distancia_entre_sensores_L_m']),
            'velocidade_de_onda_efetiva_m_s':
                float(parametros['velocidade_de_onda']['efetiva_ajustada_m_s']),
            'passo_do_solucionador_s': float(amostras['base_de_tempo_s']),
        },
        'sinais': [{
            'id': e['id'],
            'tempo_s': e['tempo_s'],
            'canal_A_carga_m': e['canal_A_carga_m'],
            'canal_B_carga_m': e['canal_B_carga_m'],
        } for e in amostras['ensaios']],
        'sorteios_da_matriz': sorteios_da_matriz(amostras),
        'verdade': [{
            'id': e['id'],
            'posicao_real_m': float(e['posicao_real_m']),
        } for e in verdade['ensaios']],
    }

    corpo = json.dumps(dados, ensure_ascii=False, separators=(',', ':'))
    with open(SAIDA, 'w', encoding='utf-8') as f:
        f.write('/* Gerado por web/gerar_dados_web.py a partir de 03_ensaios. '
                'Nao editar a mao. */\n')
        f.write('var LEAKMAP_DADOS = ' + corpo + ';\n')
    print('escrito: %s (%.0f kB)' % (os.path.relpath(SAIDA, RAIZ),
                                     os.path.getsize(SAIDA) / 1024))


if __name__ == '__main__':
    main()

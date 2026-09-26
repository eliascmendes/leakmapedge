"""LEAKMAP - detector sobre a rede do cais com manifold e ramais.

Le os sinais dos quatro sensores da simulacao da rede
(02_bancada/codigo/rede_cais.py), aplica o modelo de sensor (A-09) com as
mesmas seis configuracoes de transmissor da linha do cais, decima como no
pacote (A-10) e roda a deteccao em cada canal e a localizacao na rede
(rede.py), sem nunca ler a posicao do vazamento.

O periodo de atualizacao da saida de cada transmissor inteligente entra
declarado na escala, como a resolucao: e dado de folha de dados.

O modelo de sensor trabalha com dois canais por vez: os quatro sensores vao
em dois pares, (A, B104) e (B106, B108), com sementes diferentes.

Grava:
  03_ensaios/matriz/leakmap_plano_rede_cais_v1.json   (config e ensaio de origem, sem posicao)
  04_detector/resultados/leakmap_resultado_rede_cais_v1.json
"""
import json
import os

import numpy as np

import amostragem as AM
import linha_cais as LQ
import modelo_sensor as MS
import rede as RD

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_rede_cais_v1.json')
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_rede_cais_v1.json')
RESULTADO = os.path.join(AQUI, 'resultados', 'leakmap_resultado_rede_cais_v1.json')
PARES = (('A', 'B104'), ('B106', 'B108'))


def main():
    with open(AMOSTRAS, encoding='utf-8') as f:
        amostras = json.load(f)
    ts_solucionador = float(amostras['base_de_tempo_s'])
    topo = amostras['topologia']
    faixa_m = LQ.faixa_em_carga_m(amostras)
    escolha = AM.escolher_frequencia(float(topo['velocidade_de_onda_m_s']), ts_solucionador)
    fator = escolha['fator_de_decimacao']
    print('A-10 %s' % escolha['conta'])
    escala = {'minimo_m': 0.0, 'maximo_m': faixa_m,
              'resolucao_declarada_m': MS.degrau_de_quantizacao(16, 0.0, faixa_m)}

    regime = next(e for e in amostras['ensaios'] if e['id'] == 'RC-REGIME')
    rodadas = [(e, 400 + k * 7, True) for k, e in enumerate(amostras['ensaios']) if e['id'] != 'RC-REGIME']
    rodadas += [(regime, s, False) for s in LQ.SEMENTES_SEM_EVENTO]

    registros, plano, contador = [], [], 0
    for origem, semente, tem_evento in rodadas:
        for nome in LQ.configuracoes(faixa_m, 0):
            canais, efeitos = {}, {}
            for k, (a_nome, b_nome) in enumerate(PARES):
                cfg = LQ.configuracoes(faixa_m, semente + 500 * k)[nome]
                a, b, efeito = MS.aplicar(origem['canais_carga_m'][a_nome], origem['canais_carga_m'][b_nome],
                                          ts_solucionador, cfg)
                canais[a_nome], canais[b_nome] = AM.decimar(a, fator), AM.decimar(b, fator)
                efeitos['%s_%s' % (a_nome, b_nome)] = efeito
            t = np.asarray(origem['tempo_s'], dtype=float)[::fator]
            n = min([len(t)] + [len(v) for v in canais.values()])
            contador += 1
            identificador = 'RQ-%03d' % contador
            ensaio = {'id': identificador, 'tempo_s': [float(v) for v in t[:n]],
                      'canais_carga_m': {k: np.asarray(v[:n], dtype=float) for k, v in canais.items()}}
            # o periodo de atualizacao da saida e dado de folha de dados, declarado como a resolucao
            atualizacao = LQ.configuracoes(faixa_m, 0)[nome]['atualizacao']
            escala_do_tx = dict(escala, periodo_de_atualizacao_declarado_s=(
                atualizacao['periodo_s'] if atualizacao.get('ligado') else 0.0))
            registro = RD.processar_ensaio_rede(ensaio, escala_do_tx, topo)
            registro['configuracao'] = nome
            registros.append(registro)
            plano.append({'id': identificador, 'ensaio_de_origem': origem['id'], 'configuracao': nome,
                          'tem_evento': tem_evento, 'semente': semente})

    with open(PLANO, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Plano dos ensaios da rede do cais: configuracao de transmissor e simulacao de '
                                 'origem de cada ensaio. Nao contem a posicao do vazamento.'),
                   'ensaios': plano}, f, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(RESULTADO), exist_ok=True)
    with open(RESULTADO, 'w', encoding='utf-8') as f:
        json.dump({'descricao': 'Registros do detector (A-11, A-12 e localizacao na rede) sobre a rede do cais.',
                   'topologia': topo, 'amostragem': escolha, 'escala': escala,
                   'n_ensaios': len(registros), 'resultados': registros}, f, ensure_ascii=False,
                  default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    contagem = {}
    for r in registros:
        contagem[r['classe']] = contagem.get(r['classe'], 0) + 1
    print('%d ensaios | %r' % (len(registros), contagem))
    for caminho in (PLANO, RESULTADO):
        print('escrito: %s' % os.path.relpath(caminho, RAIZ))


if __name__ == '__main__':
    main()

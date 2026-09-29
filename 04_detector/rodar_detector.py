"""LEAKMAP - roda o detector sobre o pacote de ensaios. Etapas A-11 a A-15.

Le so 03_ensaios/pacotes/leakmap_pacote_matriz_v1.json e grava
04_detector/resultados/leakmap_resultado_matriz_v1.json, com exatamente um
registro por ensaio.

Nao le 03_ensaios/verdade_do_cenario. O erro de localizacao e calculado pelo
avaliador (A-17), que e outro processo e nao importa nada daqui.
"""
import json
import os

import detector as D
import fisica as FL
import refino as RF

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRADA_PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes',
                              'leakmap_pacote_matriz_v1.json')
SAIDA = os.path.join(RAIZ, '04_detector', 'resultados',
                     'leakmap_resultado_matriz_v1.json')
# geometria do trecho de 200 m (02_bancada/codigo/build_model.py): tubo de 300 mm com agua, sensores em 40 e 160 m,
# reservatorios em 0 e 200 m. A rugosidade de Darcy-Weisbach do modelo e 0,25 (o wntr le em metros); fica a mesma
# aqui para a fisica ser coerente com a simulacao.
GEOMETRIA = {'diametro_interno_m': 0.3, 'rugosidade_m': 0.25, 'viscosidade_m2_s': 1.0e-6,
             'contorno_antes_de_a_m': 40.0, 'contorno_depois_de_b_m': 40.0}


def main(entrada=ENTRADA_PACOTE, saida=SAIDA):
    with open(entrada, encoding='utf-8') as f:
        pacote = json.load(f)

    registros = RF.refinar_pacote(pacote, D.processar_pacote(pacote))
    registros = FL.caracterizar_pacote(pacote, registros, GEOMETRIA)
    if len(registros) != len(pacote['ensaios']):
        raise SystemExit('contagem de registros (%d) diferente da contagem de '
                         'ensaios (%d)' % (len(registros),
                                           len(pacote['ensaios'])))

    contagem = {}
    for r in registros:
        contagem[r['classe']] = contagem.get(r['classe'], 0) + 1

    dados = {
        'descricao': ('Registros de resultado do detector (A-15), um por '
                      'ensaio. Nao contem a posicao real do vazamento nem '
                      'qualquer erro de localizacao: isso e calculado pelo '
                      'avaliador, em 05_avaliacao/avaliador.py.'),
        'pacote_de_origem': os.path.basename(entrada),
        'versao_do_formato': 'resultado-v1',
        'cadeia_de_deteccao': (
            'A-11 passa-altas de primeira ordem em %.0f Hz, energia media em '
            'janela curta de %d amostras contra janela longa de referencia de '
            '%d amostras separada por %d amostras de guarda, evento declarado '
            'quando a razao atinge %.1f e o valor eficaz da janela curta fica '
            'acima do piso de amplitude; A-12 retrocesso do cruzamento ate a '
            'amostra que sai da faixa de %.0f sigma do ruido de referencia; '
            'A-13 exige os dois canais validos, razao acima do limiar nos '
            'dois e delta_t dentro de -L/c a +L/c; A-14 x = (L + c * delta_t) '
            '/ 2. Sem CUSUM.'
            % (D.CORTE_PASSA_ALTAS_HZ, D.N_CURTA, D.N_LONGA, D.N_GUARDA,
               D.LIMIAR_DE_RAZAO, D.K_FAIXA_DE_RUIDO)),
        'calibracao': D.calibracao_padrao(),
        'n_ensaios': len(registros),
        'contagem_por_classe': contagem,
        'resultados': registros,
    }

    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print('escrito: %s' % os.path.relpath(saida, RAIZ))
    print('ensaios: %d' % len(registros))
    for classe, n in sorted(contagem.items()):
        print('  %-28s %d' % (classe, n))


if __name__ == '__main__':
    main()

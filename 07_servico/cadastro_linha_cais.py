"""LEAKMAP - cadastro de equipamentos aplicado aos ensaios da linha do cais.

Pega os registros do detector com a classificacao por polaridade e origem
(04_detector/linha_cais.py) e confronta cada evento com o cadastro de exemplo
(cadastro.exemplo.json) e com o registro de operacao que o sistema de controle
daria (03_ensaios/amostras/leakmap_operacoes_manobras_cais_v1.json, gravado
por 02_bancada/codigo/manobras_cais.py). Os vazamentos nao tem operacao
registrada: e o caso em que a coincidencia de posicao sozinha nao pode
rebaixar o alerta.

Nao le a verdade do cenario. Grava:
  07_servico/resultados/leakmap_resultado_linha_cais_com_cadastro_v1.json
"""
import json
import os

import cadastro as CD

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
RESULTADO = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_resultado_linha_cais_v1.json')
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_linha_cais_v1.json')
OPERACOES = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_operacoes_manobras_cais_v1.json')
AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_linha_cais_v1.json')
CADASTRO = os.path.join(AQUI, 'cadastro.exemplo.json')
SAIDA = os.path.join(AQUI, 'resultados', 'leakmap_resultado_linha_cais_com_cadastro_v1.json')


def sensores_da_linha():
    """Posicao dos sensores, lida do cabecalho das amostras (sem abrir os ensaios)."""
    with open(AMOSTRAS, encoding='utf-8') as f:
        s = json.load(f)['sensores']
    return {'A': {'posicao_m': s['A']['posicao_m']}, 'B': {'posicao_m': s['B']['posicao_m']}}


def main():
    resultado, plano = CD.ler(RESULTADO), CD.ler(PLANO)
    cadastro = CD.ler(CADASTRO)
    operacoes = CD.ler(OPERACOES)['operacoes_por_ensaio'] if os.path.exists(OPERACOES) else {}
    origem = {p['id']: p['ensaio_de_origem'] for p in plano['ensaios']}
    sensores = sensores_da_linha()

    registros, contagem = [], {}
    for r in resultado['resultados']:
        instante = r.get('tempo_de_declaracao_s')
        if instante is None:
            registros.append(r)
            continue
        conferencia = CD.conferir(r, cadastro, operacoes.get(origem[r['id']], []), instante, sensores)
        registros.append(CD.aplicar(r, conferencia))
        contagem[conferencia['decisao']] = contagem.get(conferencia['decisao'], 0) + 1

    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Registros do detector sobre a linha do cais, com a classificacao por polaridade '
                                 'e origem e a conferencia com o cadastro de equipamentos e o registro de operacao.'),
                   'resultado_de_origem': os.path.basename(RESULTADO),
                   'cadastro': os.path.basename(CADASTRO),
                   'registro_de_operacao': os.path.basename(OPERACOES),
                   'regras': {'tolerancia_minima_m': CD.TOLERANCIA_MINIMA_M,
                              'janela_antes_s': CD.JANELA_ANTES_S, 'janela_depois_s': CD.JANELA_DEPOIS_S},
                   'n_ensaios': len(registros), 'resultados': registros}, f, ensure_ascii=False)
    print('cadastro: %r' % contagem)
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))


if __name__ == '__main__':
    main()

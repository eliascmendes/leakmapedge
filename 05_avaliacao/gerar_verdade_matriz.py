"""LEAKMAP - monta a verdade do cenario da matriz de ensaios.

Le o plano da matriz (03_ensaios/matriz/leakmap_matriz_v1.json), que diz de
qual ensaio de origem cada linha veio, e a verdade do cenario v1, que diz onde
estava o vazamento em cada ensaio de origem. Grava
03_ensaios/verdade_do_cenario/leakmap_verdade_matriz_v1.json.

Fica em 05_avaliacao porque a verdade do cenario e de uso exclusivo do
avaliador. Nada em 04_detector le, escreve ou importa este arquivo.
"""
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_matriz_v1.json')
VERDADE_V1 = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario',
                          'leakmap_verdade_v1.json')
PARAMETROS = os.path.join(RAIZ, '03_ensaios', 'parametros',
                          'leakmap_parametros_v1.json')
SAIDA = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario',
                     'leakmap_verdade_matriz_v1.json')


def instante_do_evento_s(ensaio):
    """Instante de abertura do vazamento, em segundos.

    O v1 guarda o valor dentro da descricao textual do evento
    ("add_burst: abertura de vazamento em ts=0.050 s, ..."). Aqui ele passa a
    ser campo proprio, para que o avaliador nao precise interpretar texto.
    """
    if 'instante_do_evento_s' in ensaio:
        return float(ensaio['instante_do_evento_s'])
    achado = re.search(r'ts=([0-9.]+)', ensaio.get('evento', ''))
    if not achado:
        raise ValueError('nao foi possivel obter o instante do evento de %r'
                         % ensaio.get('id'))
    return float(achado.group(1))


def main():
    with open(PLANO, encoding='utf-8') as f:
        plano = json.load(f)
    with open(VERDADE_V1, encoding='utf-8') as f:
        v1 = json.load(f)
    with open(PARAMETROS, encoding='utf-8') as f:
        par = json.load(f)

    c_real = float(par['velocidade_de_onda']['efetiva_ajustada_m_s'])
    origem = {e['id']: e for e in v1['ensaios']}

    ensaios = []
    for linha in plano['ensaios']:
        registro = {
            'id': linha['id'],
            'tem_evento': bool(linha['tem_evento']),
            'linha_da_matriz': linha['linha_da_matriz'],
            'nivel_de_ruido': linha['nivel_de_ruido'],
            'velocidade_declarada': linha['velocidade_declarada'],
            'velocidade_declarada_ao_detector_m_s':
                linha['velocidade_declarada_m_s'],
            'velocidade_de_onda_real_m_s': c_real,
        }
        if linha['tem_evento']:
            base = origem[linha['ensaio_de_origem']]
            registro.update({
                'ensaio_de_origem': base['id'],
                'posicao_real_m': float(base['posicao_real_m']),
                'no_do_evento': base['no_do_evento'],
                'instante_do_evento_s': instante_do_evento_s(base),
                'evento': base['evento'],
            })
        else:
            registro.update({
                'ensaio_de_origem': None,
                'posicao_real_m': None,
                'instante_do_evento_s': None,
                'evento': 'nenhum: regime permanente com o modelo de sensor '
                          'da linha aplicado',
            })
        ensaios.append(registro)

    saida = {
        'descricao': ('VERDADE DO CENARIO da matriz de ensaios. Uso exclusivo '
                      'do avaliador. Nunca entra no detector.'),
        'gerado_a_partir_de': [os.path.basename(PLANO),
                               os.path.basename(VERDADE_V1)],
        'n_ensaios': len(ensaios),
        'ensaios': ensaios,
    }
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))
    print('ensaios: %d (%d com evento, %d sem evento)'
          % (len(ensaios),
             sum(1 for e in ensaios if e['tem_evento']),
             sum(1 for e in ensaios if not e['tem_evento'])))


if __name__ == '__main__':
    main()

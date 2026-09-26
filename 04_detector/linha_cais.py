"""LEAKMAP - detector sobre a linha de produto do cais, com transmissores reais e rapidos.

Le os sinais da simulacao da linha do cais (02_bancada/codigo/linha_cais.py),
aplica o modelo de sensor (A-09) em seis configuracoes de transmissor, monta o
pacote (A-10) e roda o detector (A-11 a A-15), sem nunca ler a posicao do
vazamento.

Configuracoes de transmissor, todas com faixa de 0 a 15 bar lida por um
conversor de 16 bits no no do LEAKMAP:

  ideal            nenhum efeito: a hidraulica pura, referencia
  rapido           transmissor dedicado de resposta rapida (banda de 800 Hz),
                   saida analogica continua
  inteligente_Xms  transmissor inteligente com HART, o tipo comum em
                   instalacao industrial: mesma banda, ruido de 0,02% da faixa
                   (repetibilidade tipica de transmissor calibrado) e saida
                   analogica atualizada a cada X ms (1, 10, 50 e 100), com a
                   fase de cada transmissor independente. O tempo de
                   atualizacao de um instrumento especifico sai da folha de
                   dados dele; os quatro valores cobrem a faixa usual.

Entram tambem as manobras operacionais (02_bancada/codigo/manobras_cais.py),
que nao sao vazamento, e o detector roda duas vezes: com a classificacao por
polaridade e origem e sem ela, para medir o que ela muda.

Grava:
  03_ensaios/pacotes/leakmap_pacote_linha_cais_v1.json
  03_ensaios/matriz/leakmap_plano_linha_cais_v1.json   (config e ensaio de origem, sem posicao)
  04_detector/resultados/leakmap_resultado_linha_cais_v1.json
  04_detector/resultados/leakmap_resultado_linha_cais_sem_classificacao_v1.json
"""
import json
import os

import numpy as np

import amostragem as AM
import detector as D
import modelo_sensor as MS

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_linha_cais_v1.json')
PACOTE = os.path.join(RAIZ, '03_ensaios', 'pacotes', 'leakmap_pacote_linha_cais_v1.json')
PLANO = os.path.join(RAIZ, '03_ensaios', 'matriz', 'leakmap_plano_linha_cais_v1.json')
RESULTADO = os.path.join(AQUI, 'resultados', 'leakmap_resultado_linha_cais_v1.json')
RESULTADO_SEM_CLASSIFICACAO = os.path.join(AQUI, 'resultados',
                                           'leakmap_resultado_linha_cais_sem_classificacao_v1.json')
MANOBRAS = os.path.join(RAIZ, '03_ensaios', 'amostras', 'leakmap_amostras_manobras_cais_v1.json')

FAIXA_BAR = 15.0
RUIDO_FRACAO_DA_FAIXA = 0.0002         # 0,02% da faixa
PERIODOS_DE_ATUALIZACAO_MS = (1, 10, 50, 100)
SEMENTES_SEM_EVENTO = (201, 202, 203, 204, 205)


def faixa_em_carga_m(amostras):
    rho = amostras['premissas']['massa_especifica_kg_m3']
    return FAIXA_BAR * 1e5 / (rho * 9.81)


def configuracoes(faixa_m, semente):
    """As seis configuracoes de transmissor, com as sementes do ensaio."""
    def base():
        cfg = MS.config_neutra()
        cfg['banda'].update(ligado=True, corte_hz=800.0, ordem=2)
        cfg['atraso_comum'].update(ligado=True, atraso_s=1.0e-3)
        cfg['diferenca_de_atraso'].update(ligado=True, atraso_s=1.0e-4)
        cfg['erro_de_sincronizacao'].update(ligado=True, jitter_s=5.0e-6, semente=semente)
        cfg['offset'].update(ligado=True, offset_A_m=0.02, offset_B_m=-0.03)
        cfg['ruido'].update(ligado=True, desvio_padrao_m=RUIDO_FRACAO_DA_FAIXA * faixa_m,
                            semente=semente + 1000)
        cfg['saturacao'].update(ligado=True, minimo_m=0.0, maximo_m=faixa_m)
        cfg['quantizacao'].update(ligado=True, bits=16, fundo_de_escala_min_m=0.0,
                                  fundo_de_escala_max_m=faixa_m)
        return cfg

    saida = {'ideal': MS.config_neutra(), 'rapido': base()}
    for periodo_ms in PERIODOS_DE_ATUALIZACAO_MS:
        cfg = base()
        cfg['atualizacao'].update(ligado=True, periodo_s=periodo_ms / 1000.0, semente=semente + 2000)
        saida['inteligente_%dms' % periodo_ms] = cfg
    return saida


def main():
    with open(AMOSTRAS, encoding='utf-8') as f:
        amostras = json.load(f)
    ts_solucionador = float(amostras['base_de_tempo_s'])
    c = float(amostras['velocidade_de_onda_efetiva_m_s'])
    l_m = float(amostras['sensores']['distancia_entre_sensores_L_m'])
    pos_a = float(amostras['sensores']['A']['posicao_m'])
    pos_b = float(amostras['sensores']['B']['posicao_m'])
    faixa_m = faixa_em_carga_m(amostras)

    escolha = AM.escolher_frequencia(c, ts_solucionador)
    print('A-10 %s' % escolha['conta'])
    par_detector = {
        'posicao_sensor_A_m': pos_a, 'posicao_sensor_B_m': pos_b,
        'distancia_entre_sensores_L_m': l_m, 'velocidade_de_onda_m_s': c,
        'incerteza_de_velocidade_de_onda_m_s': 0.0,
        'origem_da_velocidade_de_onda': 'velocidade efetiva da simulacao (casada)',
    }

    ensaios, plano = [], []
    contador = 0
    com_evento = [e for e in amostras['ensaios'] if e['id'] != 'LC-REGIME']
    regime = next(e for e in amostras['ensaios'] if e['id'] == 'LC-REGIME')
    rodadas = [(e, k * 7, True) for k, e in enumerate(com_evento)]
    rodadas += [(regime, s, False) for s in SEMENTES_SEM_EVENTO]
    # manobras operacionais (02_bancada/codigo/manobras_cais.py): nao sao vazamento
    if os.path.exists(MANOBRAS):
        with open(MANOBRAS, encoding='utf-8') as f:
            rodadas += [(e, 300 + k * 11, False) for k, e in enumerate(json.load(f)['ensaios'])]
    for origem, semente, tem_evento in rodadas:
        for nome, cfg in configuracoes(faixa_m, semente).items():
            a, b, registro = MS.aplicar(origem['canal_A_carga_m'], origem['canal_B_carga_m'],
                                        ts_solucionador, cfg)
            contador += 1
            identificador = 'LQ-%03d' % contador
            efeitos = {'configuracao': nome, 'resolucao_declarada_m': MS.resolucao_declarada_m(cfg),
                       'efeitos': registro}
            ensaios.append(AM.montar_ensaio(identificador, origem['tempo_s'], a, b, par_detector,
                                            efeitos, escolha))
            plano.append({'id': identificador, 'ensaio_de_origem': origem['id'], 'configuracao': nome,
                          'tem_evento': tem_evento, 'semente': semente})

    escala = {'minimo_m': 0.0, 'maximo_m': faixa_m,
              'resolucao_declarada_m': MS.degrau_de_quantizacao(16, 0.0, faixa_m),
              'observacao': 'transmissor de 0 a %.0f bar, em metros de coluna de produto' % FAIXA_BAR}
    pacote = AM.montar_pacote(
        descricao=('Pacote do ensaio (A-10) da linha de produto do cais, com seis configuracoes de '
                   'transmissor. Nao contem a posicao real do vazamento.'),
        escolha=escolha, escala=escala, ensaios=ensaios, ts_solucionador_s=ts_solucionador,
        observacoes=['premissas da simulacao: ver 03_ensaios/amostras/leakmap_amostras_linha_cais_v1.json'])
    os.makedirs(os.path.dirname(PACOTE), exist_ok=True)
    with open(PACOTE, 'w', encoding='utf-8') as f:
        json.dump(pacote, f, ensure_ascii=False)
    with open(PLANO, 'w', encoding='utf-8') as f:
        json.dump({'descricao': ('Plano dos ensaios da linha do cais: configuracao de transmissor e '
                                 'simulacao de origem de cada ensaio. Nao contem a posicao do vazamento.'),
                   'configuracoes': list(configuracoes(faixa_m, 0)),
                   'ensaios': plano}, f, ensure_ascii=False, indent=1)

    os.makedirs(os.path.dirname(RESULTADO), exist_ok=True)
    # com a classificacao por polaridade e origem, e sem ela (o detector de antes)
    for classificar, caminho in ((True, RESULTADO), (False, RESULTADO_SEM_CLASSIFICACAO)):
        registros = D.processar_pacote(pacote, classificar=classificar)
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump({'descricao': ('Registros do detector (A-15) sobre a linha do cais, %s a classificacao '
                                     'por polaridade e origem.' % ('com' if classificar else 'sem')),
                       'pacote_de_origem': os.path.basename(PACOTE),
                       'cadeia_de_deteccao': 'A-11 a A-15, o mesmo detector da matriz',
                       'classificacao_por_polaridade_e_origem': classificar,
                       'n_ensaios': len(registros), 'resultados': registros}, f, ensure_ascii=False)
        contagem = {}
        for r in registros:
            contagem[r['classe']] = contagem.get(r['classe'], 0) + 1
        print('%s classificacao: %d ensaios | %r' % ('com' if classificar else 'sem', len(registros), contagem))
    for caminho in (PACOTE, PLANO, RESULTADO, RESULTADO_SEM_CLASSIFICACAO):
        print('escrito: %s' % os.path.relpath(caminho, RAIZ))


if __name__ == '__main__':
    main()

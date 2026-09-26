"""LEAKMAP - preparo de um ensaio para a placa (B-02, B-03 e B-07).

Converte os dois canais para inteiros com a representacao declarada e
calcula os parametros inteiros que a placa recebe na configuracao. Os
parametros saem de 04_detector/detector_ponto_fixo.py, com a mesma
calibracao e a mesma escala que o cenario A usou no mesmo ensaio.

Tambem monta os limites do autoteste dos canais (PEDIR_SAUDE), a partir do
transmissor declarado no ensaio:
  - faixa: a faixa de medicao do transmissor (efeito "saturacao" do modelo de
    sensor), sem os extremos; um transmissor encostado no limite da faixa esta
    fora dela;
  - congelado: 32 amostras seguidas com o mesmo codigo (12,8 ms), so quando o
    ensaio tem ruido de sensor: um transmissor vivo nunca repete o codigo por
    tanto tempo, e um sinal ideal, sem ruido, pode;
  - salto: meia faixa do transmissor entre duas amostras seguidas, que nenhuma
    onda de pressao atravessa em um periodo de amostragem.
Sem transmissor declarado (linha sem ruido da matriz), so a saturacao da
palavra e conferida.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector_ponto_fixo as PF  # noqa: E402
import protocolo as PR  # noqa: E402
import registro_b as RB  # noqa: E402
import representacao as RP  # noqa: E402


SEQUENCIA_DE_CONGELAMENTO = 32
FRACAO_DA_FAIXA_NO_SALTO = 0.5


def limites_de_saude(ensaio, espec):
    efeitos = (ensaio.get('efeitos_de_sensor_aplicados') or {}).get('efeitos') or []
    por_nome = {e['efeito']: e.get('parametros') or {} for e in efeitos}
    limites = dict(PR.LIMITES_ABERTOS)
    faixa = por_nome.get('saturacao')
    if faixa:
        def codigo(m):
            bruto = round((m - espec['referencia_m']) / espec['degrau_m'])
            return min(max(bruto, espec['codigo_minimo']), espec['codigo_maximo'])
        baixo, alto = codigo(faixa['minimo_m']), codigo(faixa['maximo_m'])
        limites['codigo_minimo'] = min(baixo + 1, espec['codigo_maximo'])
        limites['codigo_maximo'] = max(alto - 1, espec['codigo_minimo'])
        limites['limite_salto'] = min(0xFFFF, round(FRACAO_DA_FAIXA_NO_SALTO * (alto - baixo)))
    if 'ruido' in por_nome:
        limites['limite_congelado'] = SEQUENCIA_DE_CONGELAMENTO
    return limites


def preparar_ensaio(ensaio, escala, cal):
    espec = RP.especificacao(RP.degrau_do_ensaio(ensaio))
    conversao = {}
    for canal in ('canal_A', 'canal_B'):
        codigos, abaixo, acima = RP.converter(ensaio[canal + '_carga_m'], espec)
        conversao[canal] = {'codigos': codigos, 'abaixo': abaixo, 'acima': acima}
    parametros = PF.parametros_inteiros(cal, RB.periodo(ensaio), espec['degrau_m'],
                                        (escala or {}).get('resolucao_declarada_m'))
    return {'representacao': espec, 'conversao': conversao, 'parametros': parametros,
            'limites_de_saude': limites_de_saude(ensaio, espec)}

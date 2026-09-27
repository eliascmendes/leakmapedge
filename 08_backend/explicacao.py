"""LEAKMAP - explicacao do evento em portugues, pronta para a tela.

Os mesmos textos das telas do painel (web/cais.js, web/rede.js e
web/simulador.js), a partir do registro do detector.
"""

NOMES_DOS_TRECHOS = {'principal': 'trecho', 'tronco': 'tronco', 'ramal_104': 'ramal do 104',
                     'ramal_106': 'ramal do 106', 'ramal_108': 'ramal do 108'}
NOMES_DAS_FALHAS = {'congelado': 'sinal travado', 'saturado': 'sinal no limite da escala',
                    'fora_da_faixa': 'fora da faixa do transmissor', 'salto': 'salto impossível'}
ACOES = {'abertura': 'abertura', 'fechamento': 'fechamento', 'parada': 'parada', 'partida': 'partida'}


def _polaridades(registro):
    if 'canais' in registro:
        return [d.get('polaridade') for d in registro['canais'].values() if d.get('detectado')]
    return [(registro.get(c) or {}).get('polaridade') for c in ('canal_A', 'canal_B')
            if (registro.get(c) or {}).get('detectado')]


def texto(registro, reprovados=None, saude=None, confirmado=False):
    base = _texto(registro, reprovados, saude, confirmado)
    if reprovados and registro.get('classe') != 'localizado':
        base += ' O autoteste acusa falha no %s.' % ' e no '.join(_falhas(reprovados, saude))
    return base


def _falhas(reprovados, saude):
    saida = []
    for canal in reprovados:
        nomes = [NOMES_DAS_FALHAS.get(f, f) for f in (saude or {}).get('canal_' + canal, {}).get('falhas', [])]
        saida.append('sensor %s (%s)' % (canal, ', '.join(nomes)))
    return saida


def _texto(registro, reprovados=None, saude=None, confirmado=False):
    classe = registro.get('classe')
    cad = registro.get('cadastro') or {}
    motivo = registro.get('motivo') or ''
    if reprovados and classe == 'localizado':
        falhas = _falhas(reprovados, saude)
        return ('O autoteste acusou falha no %s. Uma posição calculada com um sensor defeituoso não é '
                'publicada: o alerta sai como suspeita, até o sensor ser conferido.' % ' e no '.join(falhas))
    if classe == 'localizado':
        if 'trecho_estimado' in registro:
            n = len(registro.get('sensores_usados') or [])
            base = ('Queda de pressão em %d sensores. Das chegadas, o LEAKMAP procura em cada trecho o ponto '
                    'cujos tempos pela tubulação até os sensores batem com os medidos, e aponta o %s: vazamento, '
                    'com a posição publicada junto com o alerta.'
                    % (n, NOMES_DOS_TRECHOS.get(registro['trecho_estimado'], registro['trecho_estimado'])))
        else:
            base = ('Queda de pressão nos dois sensores, com diferença de tempo possível dentro do trecho: '
                    'vazamento, com a posição publicada junto com o alerta.')
        if cad.get('decisao') == 'conferir':
            base += (' A posição coincide com %s, mas não há operação registrada dele: o alerta continua, com a '
                     'anotação para conferir.' % cad['equipamento'])
        if confirmado:
            base += (' O sensor de gás (simulado) acusou vapor na região: duas físicas independentes apontam o '
                     'mesmo lugar, e o alerta sobe para confirmado.')
        return base
    if classe == 'manobra' and 'classe_antes_do_cadastro' in registro:
        op = cad.get('operacao') or {}
        onde = ('do lado %s, onde fica ' % registro['lado_da_origem']) if registro.get('lado_da_origem') \
            else 'na posição de '
        return ('A onda é de queda, a mesma de um vazamento, e nasceu %s%s. O sistema de controle registrou a %s '
                'de %s naquele instante: é manobra registrada. Fica no histórico, não alarma.'
                % (onde, cad.get('equipamento'), ACOES.get(op.get('acao'), 'operação'), cad.get('equipamento')))
    if classe == 'manobra':
        pol = _polaridades(registro)
        if 'queda' in pol and 'alta' in pol:
            onde = 'alta de um lado e queda do outro: uma válvula que fecha entre os sensores'
        elif len(pol) > 1:
            onde = 'alta de pressão nos sensores'
        else:
            onde = 'alta de pressão num sensor'
        base = ('A onda é de %s. Um rompimento sempre derruba a pressão: é manobra de operação, não vazamento. '
                'Fica no histórico, nunca alarma.' % onde)
        if cad.get('decisao') == 'manobra_registrada':
            op = cad.get('operacao') or {}
            base += ' O registro de operação confirma: %s de %s.' % (ACOES.get(op.get('acao'), 'operação'),
                                                                      cad.get('equipamento'))
        return base
    if classe == 'fora_do_trecho':
        base = ('A onda chegou ao sensor %s com a diferença de tempo no limite físico: nasceu no sensor ou fora '
                'do trecho monitorado, do lado dele. O LEAKMAP avisa e diz o lado, sem inventar uma posição que '
                'não mede.' % registro.get('lado_da_origem'))
        if cad.get('decisao') == 'conferir':
            base += ' Do lado dele fica %s, sem operação registrada: conferir.' % cad['equipamento']
        return base
    if classe == 'detectado_sem_localizacao':
        if 'ambigua' in motivo:
            porque = 'dois trechos da rede explicam as chegadas igualmente bem'
        elif 'incoerentes' in motivo:
            porque = ('as chegadas não batem com nenhum ponto da rede dentro da incerteza das marcas; com '
                      'transmissor lento, a saída em degraus embaralha os tempos')
        elif 'faixa fisica' in motivo:
            porque = ('a diferença de tempo passou do limite físico do trecho, além do que o ruído de tempo explica; '
                      'com transmissor lento, a saída em degraus embaralha os tempos, e numa frente lenta, como a '
                      'parada de uma bomba, a marca no sensor mais distante sai tarde')
        elif 'nao declarou' in motivo or 'menos de dois' in motivo:
            porque = 'só um dos sensores viu a onda, e sem dois não há diferença de tempo'
        elif 'fundo de escala' in motivo:
            porque = 'um transmissor saiu da faixa de medida'
        elif 'abaixo do limiar' in motivo:
            porque = 'a onda não se destacou do ruído com margem suficiente'
        else:
            porque = motivo
        return 'Evento detectado, posição retida: %s. O alerta sai como suspeita, sem apontar lugar.' % porque
    return motivo

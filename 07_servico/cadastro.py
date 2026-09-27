"""LEAKMAP - cadastro de equipamentos e registro de operacao.

Uma onda de queda que nasce na posicao de uma valvula ou de uma bomba pode ser
vazamento ou pode ser a propria operacao: a valvula do berco abrindo para
comecar um carregamento, a bomba parando. A fisica da onda e a mesma, entao
nem a polaridade nem a posicao separam as duas coisas. O que separa e saber
que o equipamento foi operado naquele instante.

Regra, conservadora de proposito:

  a origem coincide com um equipamento do cadastro E ha registro de operacao
  dele, compativel com a onda, na janela de tempo do evento
      -> manobra registrada: nivel `registro`, com o equipamento e a
         operacao no motivo; fica no historico, nao alarma

  a origem coincide com um equipamento, mas nao ha registro de operacao
      -> o alerta continua como estava, com a anotacao "coincide com o
         equipamento X, sem operacao registrada: conferir"

  a origem nao coincide com nenhum equipamento
      -> nada muda

So o registro de operacao rebaixa um alerta; a coincidencia de posicao
sozinha nunca rebaixa. Cada operacao registrada explica um evento so: depois de
usada (campo "usada" na operacao), ela nao serve para outro, mesmo dentro da
janela de tempo. Um vazamento na propria valvula, no mesmo instante em
que ela e operada, sai como manobra registrada: o risco fica documentado em
07_servico/LEIAME.md.

Compatibilidade entre a operacao e a onda: abrir uma valvula de retirada e
parar uma bomba geram QUEDA; fechar uma valvula e partir uma bomba geram
ALTA. Uma operacao incompativel com a polaridade medida nao explica o evento.

O cadastro (posicao de cada equipamento, na mesma referencia dos sensores)
vem do isometrico da linha. Numa rede com manifold, cada equipamento diz tambem
o trecho ("trecho": "ramal_106") e a conferencia recebe a geometria da rede
(GeometriaDaRede): a distancia passa a ser medida pela tubulacao, e "alem do
sensor" quer dizer mais longe do manifold que ele, no mesmo trecho. O registro de operacao vem do sistema de
controle da planta (os eventos de abertura, fechamento, partida e parada) ou
de um lancamento manual do operador; aqui e so uma lista de dicionarios, no
formato de cadastro.exemplo.json.
"""
import copy
import json

CLASSE_LOCALIZADO = 'localizado'
CLASSE_MANOBRA = 'manobra'
CLASSE_FORA_DO_TRECHO = 'fora_do_trecho'
CLASSE_SEM_LOCALIZACAO = 'detectado_sem_localizacao'

TOLERANCIA_MINIMA_M = 15.0     # coincidencia de posicao: o maior entre isto e 3 incertezas declaradas
JANELA_ANTES_S = 5.0           # a operacao registrada pode vir ate 5 s antes do evento
JANELA_DEPOIS_S = 2.0           # e ate 2 s depois (atraso do registro no sistema de controle)
FOLGA_DO_PRIMEIRO_S = 0.002     # rede sem posicao: o lado e o do sensor que viu a onda primeiro, com esta vantagem

ONDA_DA_OPERACAO = {'abertura': 'queda', 'parada': 'queda', 'fechamento': 'alta', 'partida': 'alta'}

DECISAO_MANOBRA = 'manobra_registrada'
DECISAO_CONFERIR = 'conferir'
DECISAO_NADA = 'sem_equipamento'


class GeometriaDaRede:
    """Distancias numa rede em arvore com um no de juncao, pela topologia de 04_detector/rede.py.

    Um ponto e (trecho, s): s conta do sensor A no tronco e do manifold em cada
    ramal. A distancia entre pontos de trechos diferentes passa pelo manifold.
    """

    def __init__(self, topologia):
        self.topo = topologia

    def _juncao(self, trecho):
        return float(self.topo['trechos'][trecho]['juncao_em_s_m'])

    def distancia(self, p, q):
        if p[0] == q[0]:
            return abs(p[1] - q[1])
        return abs(p[1] - self._juncao(p[0])) + abs(q[1] - self._juncao(q[0]))

    def alem_do_sensor(self, equipamento, sensor):
        """O equipamento fica no trecho do sensor, mais longe do manifold que ele."""
        s = self.topo['sensores'][sensor]
        if equipamento.get('trecho') != s['trecho']:
            return False
        j = self._juncao(s['trecho'])
        return abs(equipamento['posicao_m'] - j) > abs(s['s_m'] - j)

    def ate_o_sensor(self, equipamento, sensor):
        s = self.topo['sensores'][sensor]
        return abs(equipamento['posicao_m'] - s['s_m'])


def _canais_do_registro(registro):
    """Os canais de um registro, na linha reta (canal_A, canal_B) ou na rede (canais)."""
    if isinstance(registro.get('canais'), dict):
        return dict(registro['canais'])
    return {c[-1]: registro.get(c) or {} for c in ('canal_A', 'canal_B')}


def _onde_fica(e):
    if e.get('trecho') and e['trecho'] != 'principal':
        return '%s em %s, %.0f m' % (e.get('tipo', ''), e['trecho'], e['posicao_m'])
    return '%s em %.0f m' % (e.get('tipo', ''), e['posicao_m'])


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def polaridade_do_evento(registro):
    """A polaridade da frente de onda, se os canais que detectaram concordam."""
    pol = {d.get('polaridade') for d in _canais_do_registro(registro).values() if d.get('detectado')}
    pol.discard(None)
    return pol.pop() if len(pol) == 1 else None


def lado_alem_do_limite(registro):
    """Lado de origem de um evento sem localizacao cuja diferenca de tempo passou do limite fisico.

    Uma frente lenta (a parada de uma bomba, que perde rotacao em segundos) e
    marcada tarde no sensor mais distante, e a diferenca de tempo passa de L/c
    alem da tolerancia do detector: o evento sai sem localizacao. O sinal da
    diferenca ainda diz de que lado a onda veio, e isso basta para confrontar
    com os equipamentos daquele lado. Quando o sensor mais distante nem chega a
    declarar (no acompanhamento continuo, a espera e mais curta que o registro
    dos ensaios), o lado e o do unico sensor que viu a queda. Numa rede, sem
    posicao, o lado e o do sensor que viu a queda primeiro, com folga (na linha
    reta, com a diferenca de tempo dentro do limite, nao ha lado a inferir). Em
    todos eles, so o registro de operacao de um equipamento daquele lado rebaixa
    o evento.
    """
    par = registro.get('parametros_do_detector') or {}
    dt = registro.get('delta_t_s')
    if registro.get('classe') != CLASSE_SEM_LOCALIZACAO or polaridade_do_evento(registro) != 'queda':
        return None
    canais = {k: d for k, d in _canais_do_registro(registro).items() if d.get('detectado')}
    if dt is None and len(canais) == 1:
        # so um canal viu a queda; o outro nao viu nada em toda a espera do detector: a frente e lenta
        # demais para ele ou ainda nem chegou, e a onda veio do lado de quem viu
        return next(iter(canais))
    if dt is not None and par.get('distancia_entre_sensores_L_m') and par.get('velocidade_de_onda_m_s'):
        if abs(dt) > float(par['distancia_entre_sensores_L_m']) / float(par['velocidade_de_onda_m_s']):
            return 'A' if dt < 0 else 'B'
    # sem posicao e sem limite fisico passado (numa rede, chegadas que nao batem com ponto nenhum, como a
    # frente lenta de uma valvula de navio, marcada em pontos diferentes da rampa em cada sensor): a onda
    # veio do lado do sensor que a viu primeiro
    chegadas = sorted((d['tempo_de_chegada_s'], k) for k, d in canais.items() if d.get('tempo_de_chegada_s') is not None)
    if dt is None and len(chegadas) >= 2 and chegadas[1][0] - chegadas[0][0] > FOLGA_DO_PRIMEIRO_S:
        return chegadas[0][1]
    return None


def candidatos(registro, cadastro, sensores, geometria=None):
    """Equipamentos que podem ser a origem do evento, com a distancia ate a origem estimada."""
    equipamentos = cadastro.get('equipamentos', [])
    classe = registro.get('classe')
    lado = registro.get('lado_da_origem') or lado_alem_do_limite(registro)
    tolerancia = max(TOLERANCIA_MINIMA_M, 3.0 * float(registro.get('incerteza_de_posicao_m') or 0.0))
    if geometria is not None:
        trecho = registro.get('trecho_estimado', registro.get('trecho_da_origem'))
        s = registro.get('s_estimado_m', registro.get('posicao_da_origem_m'))
        if classe in (CLASSE_LOCALIZADO, CLASSE_MANOBRA) and trecho is not None and s is not None:
            dist = [(geometria.distancia((e.get('trecho'), e['posicao_m']), (trecho, s)), e) for e in equipamentos]
            return sorted([p for p in dist if p[0] <= tolerancia], key=lambda par: par[0]), tolerancia
        if classe in (CLASSE_FORA_DO_TRECHO, CLASSE_MANOBRA, CLASSE_SEM_LOCALIZACAO) and lado in geometria.topo['sensores']:
            saida = [(geometria.ate_o_sensor(e, lado), e) for e in equipamentos if geometria.alem_do_sensor(e, lado)]
            return sorted(saida, key=lambda par: par[0]), None
        return [], None
    posicao = registro.get('posicao_estimada_m', registro.get('posicao_da_origem_m'))
    if classe in (CLASSE_LOCALIZADO, CLASSE_MANOBRA) and posicao is not None:
        saida = [(abs(e['posicao_m'] - posicao), e) for e in equipamentos
                 if abs(e['posicao_m'] - posicao) <= tolerancia]
        return sorted(saida, key=lambda par: par[0]), tolerancia
    if classe in (CLASSE_FORA_DO_TRECHO, CLASSE_MANOBRA, CLASSE_SEM_LOCALIZACAO) and lado in ('A', 'B'):
        # so o lado e conhecido: vale qualquer equipamento alem do sensor daquele lado
        x = sensores[lado]['posicao_m']
        saida = [(abs(e['posicao_m'] - x), e) for e in equipamentos
                 if (e['posicao_m'] < x if lado == 'A' else e['posicao_m'] > x)]
        return sorted(saida, key=lambda par: par[0]), None
    return [], None


def conferir(registro, cadastro, operacoes, instante_do_evento_s, sensores, geometria=None):
    """Confronta o evento com o cadastro e o registro de operacao.

    `instante_do_evento_s` e `operacoes[i]['instante_s']` na mesma base de tempo
    (segundos; epoch ou relativo). `sensores`: {'A': {'posicao_m'}, 'B': {...}} na
    linha reta; numa rede, `geometria` (GeometriaDaRede) no lugar deles.
    Devolve {'decisao', 'equipamento', 'operacao', 'distancia_m', 'tolerancia_m', 'texto'}.
    """
    lista, tolerancia = candidatos(registro, cadastro, sensores, geometria)
    if not lista:
        return {'decisao': DECISAO_NADA, 'equipamento': None, 'operacao': None, 'distancia_m': None,
                'tolerancia_m': tolerancia, 'texto': None}
    polaridade = polaridade_do_evento(registro)
    for distancia, equipamento in lista:
        for op in operacoes or []:
            if op.get('equipamento') != equipamento['nome'] or op.get('usada'):
                continue                    # uma operacao explica um evento so (quem aplica marca "usada")
            atraso = instante_do_evento_s - float(op['instante_s'])
            if not -JANELA_DEPOIS_S <= atraso <= JANELA_ANTES_S:
                continue
            if polaridade is not None and ONDA_DA_OPERACAO.get(op.get('acao')) not in (None, polaridade):
                continue
            return {'decisao': DECISAO_MANOBRA, 'equipamento': equipamento['nome'], 'operacao': op,
                    'distancia_m': distancia, 'tolerancia_m': tolerancia,
                    'texto': ('%s de %s (%s) registrada %.1f s %s do evento'
                              % (op.get('acao', 'operacao'), equipamento['nome'], _onde_fica(equipamento),
                                 abs(atraso), 'antes' if atraso >= 0 else 'depois'))}
    distancia, equipamento = lista[0]
    onde = ('coincide com' if tolerancia is not None
            else 'origem do lado %s, onde fica' % (registro.get('lado_da_origem') or lado_alem_do_limite(registro)))
    return {'decisao': DECISAO_CONFERIR, 'equipamento': equipamento['nome'], 'operacao': None,
            'distancia_m': distancia, 'tolerancia_m': tolerancia,
            'texto': ('%s %s (%s), sem operacao registrada: conferir'
                      % (onde, equipamento['nome'], _onde_fica(equipamento)))}


def aplicar(registro, conferencia):
    """Registro com a decisao do cadastro aplicada; o original nao muda."""
    r = copy.deepcopy(registro)
    r['cadastro'] = conferencia
    if conferencia['decisao'] == DECISAO_MANOBRA and r.get('classe') != CLASSE_MANOBRA:
        r['classe_antes_do_cadastro'] = r.get('classe')
        r['classe'] = CLASSE_MANOBRA
        r['motivo'] = 'manobra registrada: %s' % conferencia['texto']
        if not r.get('lado_da_origem') and lado_alem_do_limite(registro):
            r['lado_da_origem'] = lado_alem_do_limite(registro)
        if 'posicao_estimada_m' in r:
            # a posicao calculada fica como origem da onda, nao como vazamento
            r['posicao_da_origem_m'] = r.pop('posicao_estimada_m')
        if 's_estimado_m' in r:                     # o mesmo, na rede
            r['posicao_da_origem_m'] = r.pop('s_estimado_m')
            r['trecho_da_origem'] = r.pop('trecho_estimado', None)
    elif conferencia['decisao'] == DECISAO_CONFERIR:
        r['motivo'] = '%s; %s' % (r.get('motivo') or '', conferencia['texto'])
    return r

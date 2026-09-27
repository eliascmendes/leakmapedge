"""LEAKMAP - a bancada virtual: a linha, os sensores e o detector ao vivo.

A cada passo (0,1 s de relogio), a bancada:

  1. calcula a carga limpa em cada sensor: o regime da linha mais os eventos
     abertos (gerador.py, a partir das simulacoes do TSNet);
  2. passa o sinal pelo modelo do transmissor escolhido
     (04_detector/modelo_sensor.py, com as configuracoes de
     04_detector/linha_cais.py), com um trecho do passo anterior como
     contexto, para os filtros e a saida em degraus nao emendarem errado;
  3. aplica as falhas de sensor pedidas (cabo rompido, sinal travado);
  4. procura a chegada de uma onda (04_detector/detector.py, A-11). Quando o
     primeiro sensor a ve, espera o maior tempo de percurso entre sensores e
     fecha o evento com o detector inteiro sobre a janela: detector.py na
     linha reta, rede.py na rede; depois o autoteste dos canais (o modelo da
     placa, 06_fpga/computador), o cadastro com o registro de operacao e a
     escala de alerta (07_servico).

Confirmacao do degrau. O detector foi calibrado sobre registros de 0,2 s; em
operacao continua ele toma cerca de 10 mil decisoes por segundo (2,5 mil por
canal), e o ruido do transmissor acaba passando do limiar num canal so, cerca
de uma vez a cada 2,5 minutos (medido: 4 em 10 minutos com o transmissor
rapido e com o de 10 ms, nenhum com duas chegadas). Um evento de verdade num
canal so (cabo rompido, frente lenta de bomba) muda o nivel e o nivel fica
mudado; o pico de ruido nao. Quando so um canal declarou, a bancada confere o
nivel medio de 5 a 25 ms depois da chegada contra o de 20 a 120 ms antes; sem
degrau acima de 6 desvios da media (ou de 3 degraus de quantizacao), a
deteccao e descartada como ruido e contada em `descartadas_como_ruido`. O
detector em si nao muda.

Em paralelo, e sem mexer na deteccao de vazamento, o alerta de sobrepressao
(07_servico/sobrepressao.py) acompanha o pico de pressao de cada sensor contra
o limite da linha (premissa, ajustavel) e publica os episodios de golpe de
ariete a parte, na mensagem "sobrepressao".

O detector so recebe o sinal dos sensores. A bancada sabe onde esta o
vazamento, porque foi ela que o criou, e manda isso a parte, em "verdade".

Tempo: t_s, segundos desde o inicio da bancada. instante_utc e o inicio mais t_s.
"""
import datetime
import math

import numpy as np

import explicacao as EX
import gerador as GE
import historico as HI
import linhas as LN
import projeto as P

FS_HZ = 2500.0                    # a mesma taxa do detector nos ensaios (2,5 mil amostras por segundo)
TS = 1.0 / FS_HZ
AMOSTRAS_POR_PASSO = 250          # 0,1 s
CONTEXTO_MINIMO = 100             # amostras do passo anterior dadas ao modelo de sensor
HISTORICO_S = 4.0
JANELA_DE_PROCURA_S = 0.3
ANTES_DA_CHEGADA_S = 0.3
FOLGA_DE_ESPERA_S = 0.25
REFRATARIO_S = 1.0                # depois de fechar um evento, as reflexoes dele nao abrem outro
SILENCIO_APOS_MUDANCA_S = 1.5     # depois de reparar ou trocar linha/transmissor
SAUDE_A_CADA_PASSOS = 5
JANELA_DE_SAUDE_S = 0.5
ANTECEDENCIA_DO_EVENTO_S = 0.02   # a acao pedida entra logo no proximo passo

TRANSMISSORES = {
    'ideal': 'Ideal: a hidráulica pura, sem transmissor',
    'rapido': 'Rápido dedicado: saída contínua, banda de 800 Hz',
    'inteligente_1ms': 'Inteligente: saída atualizada a cada 1 ms',
    'inteligente_10ms': 'Inteligente: saída atualizada a cada 10 ms',
    'inteligente_50ms': 'Inteligente: saída atualizada a cada 50 ms',
    'inteligente_100ms': 'Inteligente: saída atualizada a cada 100 ms',
}
ACOES_DO_EQUIPAMENTO = {'valvula': {'abrir': ('fechada', 'aberta'), 'fechar': ('aberta', 'fechada')},
                        'bomba': {'partir': ('desligada', 'ligada'), 'parar': ('ligada', 'desligada')}}
ACAO_REGISTRADA = {'abrir': 'abertura', 'fechar': 'fechamento', 'partir': 'partida', 'parar': 'parada'}
FALHAS = ('cabo_rompido', 'travado', 'nenhuma')


class ErroDaBancada(Exception):
    def __init__(self, codigo, texto, extra=None):
        super().__init__(texto)
        self.codigo, self.texto, self.extra = codigo, texto, extra or {}


class Bancada:
    def __init__(self, linhas=None, linha='cais', transmissor='rapido', semente=0, historico=None, inicio_utc=None):
        self.linhas = linhas or LN.todas()
        self.historico = historico or HI.Historico()
        self.inicio_utc = inicio_utc or datetime.datetime.now(datetime.timezone.utc)
        self.rng = np.random.default_rng(semente)
        self.t = 0.0
        self.n_passo = 0
        self.cal = P.D.calibracao_padrao()
        self.transmissor = transmissor
        self.roteiro = None
        self._contador = 0
        self.descartadas_como_ruido = 0
        # limite de pressao de cada linha para o alerta de sobrepressao: premissa, ajustavel pela API
        self.limites = {k: l.limite_de_pressao_bar for k, l in self.linhas.items()}
        self._reiniciar(linha)

    # --- estado ---------------------------------------------------------------
    def _reiniciar(self, linha):
        if linha not in self.linhas:
            raise ErroDaBancada(422, 'linha desconhecida: %s' % linha)
        self.linha = self.linhas[linha]
        self.eventos = []
        self.equipamentos = {e['id']: e['estado_inicial'] for e in self.linha.equipamentos}
        self.falhas = {}
        self.gas = False
        self.operacoes = []
        self.buf_t = np.empty(0)
        self.buf = {s: np.empty(0) for s in self.linha.sensores}
        self.aguardando = None
        self.refratario_ate = self.t + SILENCIO_APOS_MUDANCA_S
        self.saude = None
        self.ultimo = None
        self._ultimo_reparo = -1.0
        self.efeitos = []
        nomes = list(self.linha.sensores)
        self.pares = [tuple(nomes[i:i + 2]) for i in range(0, len(nomes), 2)]
        # fase propria da saida em degraus de cada transmissor, fixa na sessao
        self.fase = {s: float(self.rng.uniform(0.0, 1.0)) for s in nomes}
        self.monitor = P.SP.Monitor(self.limites[self.linha.id], faixa_bar=LN.FAIXA_BAR)
        self.ultima_sobrepressao = None

    def utc(self, t_s):
        return (self.inicio_utc + datetime.timedelta(seconds=float(t_s))).isoformat().replace('+00:00', 'Z')

    def t_de_utc(self, instante_utc):
        instante = datetime.datetime.fromisoformat(instante_utc.replace('Z', '+00:00'))
        return (instante - self.inicio_utc).total_seconds()

    def escala(self):
        faixa = self.linha.faixa_m
        return {'minimo_m': 0.0, 'maximo_m': faixa, 'resolucao_declarada_m': P.MS.degrau_de_quantizacao(16, 0.0, faixa)}

    def periodo_de_atualizacao(self):
        cfg = P.TX.configuracoes(self.linha.faixa_m, 0)[self.transmissor]['atualizacao']
        return float(cfg['periodo_s']) if cfg.get('ligado') else 0.0

    def nivel_atual(self):
        return self.ultimo[0]['nivel'] if self.ultimo and not self._reparado_depois_do_ultimo() else None

    def _reparado_depois_do_ultimo(self):
        return self.ultimo is not None and self.ultimo[2] < getattr(self, '_ultimo_reparo', -1.0)

    def estado(self, perfil='demonstracao'):
        saude = self.saude or {}
        e = {
            'modo': 'simulacao',
            'linha': self.linha.id,
            'transmissor': self.transmissor,
            't_s': round(self.t, 3),
            'instante_utc': self.utc(self.t),
            'equipamentos': dict(self.equipamentos),
            'sensores': {s: (self.falhas[s]['tipo'] if s in self.falhas else 'normal') for s in self.linha.sensores},
            'gas': {'acusando': self.gas},
            'monitoramento': P.AL.estado_do_monitoramento(saude)['monitoramento'] if saude else 'sem_autoteste',
            'nivel_atual': self.nivel_atual(),
            'roteiro': None if self.roteiro is None else {'roteiro': self.roteiro['nome'],
                                                          'intervalo_s': self.roteiro['intervalo_s']},
            'sobrepressao': {'limite_bar': self.limites[self.linha.id], 'nivel_atual': self.monitor.nivel_atual(),
                             'pico_bar': (round(P.SP.Monitor.pico(self.monitor.episodio)[1], 3)
                                          if self.monitor.nivel_atual() else None)},
        }
        if perfil == 'demonstracao':
            e['vazamentos_abertos'] = [{'id': v['id'], 'trecho': v['trecho'], 's_m': v['s_m'], 'tamanho': v['tamanho'],
                                        'fonte': v['fonte']} for v in self.eventos
                                       if v['tipo'] == 'vazamento' and v['fim'] is None]
        return e

    # --- acoes ------------------------------------------------------------------
    def _novo_id(self, prefixo):
        self._contador += 1
        return '%s-%d' % (prefixo, self._contador)

    def definir_limite(self, limite_bar, linha=None):
        """Muda o limite de pressao de uma linha (o componente mais fraco): premissa ate o dado da planta."""
        linha = linha or self.linha.id
        if linha not in self.linhas:
            raise ErroDaBancada(422, 'linha desconhecida: %s' % linha)
        if not 1.0 <= float(limite_bar) <= LN.FAIXA_BAR:
            raise ErroDaBancada(422, 'o limite tem de ficar entre 1 e %.0f bar (a faixa do transmissor)' % LN.FAIXA_BAR)
        self.limites[linha] = float(limite_bar)
        if linha == self.linha.id:
            self.monitor.limite_bar = float(limite_bar)
        resposta = {'linha': linha, 'limite_bar': float(limite_bar), 'aviso': None}
        regime = max(float(self.linhas[linha].bar(h)) for h in self.linhas[linha].regime.values())
        if regime >= P.SP.FRACAO_ATENCAO * float(limite_bar):
            resposta['aviso'] = ('a pressao de regime da linha (%.2f bar) ja passa de %d%% deste limite: a linha fica em '
                                 'atencao o tempo todo' % (regime, round(100 * P.SP.FRACAO_ATENCAO)))
        return resposta

    def situacao_da_sobrepressao(self):
        return {'linha': self.linha.id, 'limite_bar': self.limites[self.linha.id],
                'origem_do_limite': self.linha.origem_do_limite,
                'fracao_atencao': P.SP.FRACAO_ATENCAO, 'fracao_alarme': P.SP.FRACAO_ALARME,
                'limites_por_linha_bar': dict(self.limites), 'estado': self.estado()['sobrepressao'],
                'ultima': self.ultima_sobrepressao}

    def trocar_linha(self, linha):
        self._reiniciar(linha)

    def trocar_transmissor(self, transmissor):
        if transmissor not in TRANSMISSORES:
            raise ErroDaBancada(422, 'transmissor desconhecido: %s' % transmissor,
                                {'opcoes': list(TRANSMISSORES)})
        self.transmissor = transmissor
        self.aguardando = None
        self.refratario_ate = self.t + SILENCIO_APOS_MUDANCA_S

    def vazamento(self, trecho, s_m, tamanho, fonte='gerador'):
        erro = self.linha.ponto_valido(trecho, s_m)
        if erro:
            raise ErroDaBancada(422, erro)
        if tamanho not in self.linha.tamanhos:
            raise ErroDaBancada(422, 'tamanho %s nao simulado nesta linha' % tamanho, {'opcoes': self.linha.tamanhos})
        ev = GE.vazamento(self.linha, trecho, s_m, tamanho, self.t + ANTECEDENCIA_DO_EVENTO_S)
        if fonte == 'tsnet' and ev['fonte'] != 'tsnet':
            pontos = sorted((c for c in self.linha.cenarios_tsnet() if c['trecho'] == trecho and tamanho in c['tamanhos']),
                            key=lambda c: abs(c['s_m'] - s_m))
            raise ErroDaBancada(422, 'nao ha simulacao completa do TSNet neste ponto; use fonte "gerador" ou um dos '
                                'pontos simulados', {'pontos_mais_proximos': pontos[:3]})
        ev['id'] = self._novo_id('vz')
        self.eventos.append(ev)
        return {'id': ev['id'], 'fonte_usada': ev['fonte'], 'trecho': trecho, 's_m': float(s_m), 'tamanho': tamanho,
                'simulacao_de_origem': ev['molde'].id}

    def equipamento(self, equipamento, acao, registrar_operacao=True):
        eq = next((e for e in self.linha.equipamentos if e['id'] == equipamento), None)
        if eq is None:
            raise ErroDaBancada(404, 'equipamento desconhecido nesta linha: %s' % equipamento)
        acoes = ACOES_DO_EQUIPAMENTO[eq['tipo']]
        if acao not in acoes:
            raise ErroDaBancada(422, 'acao %s nao vale para %s' % (acao, eq['tipo']), {'opcoes': list(acoes)})
        de, para = acoes[acao]
        if self.equipamentos[equipamento] != de:
            raise ErroDaBancada(409, '%s ja esta %s' % (equipamento, self.equipamentos[equipamento]))
        t0 = self.t + ANTECEDENCIA_DO_EVENTO_S
        ev = GE.manobra(self.linha, equipamento, acao, t0)
        ev['id'] = self._novo_id('mn')
        ev['registrada'] = bool(registrar_operacao)
        self.eventos.append(ev)
        self.equipamentos[equipamento] = para
        if registrar_operacao:
            self.operacoes.append({'equipamento': equipamento, 'acao': ACAO_REGISTRADA[acao], 'instante_s': t0,
                                   'origem': 'bancada (registro do sistema de controle simulado)'})
        return {'id': ev['id'], 'equipamento': equipamento, 'estado': para, 'operacao_registrada': bool(registrar_operacao),
                'fonte_usada': ev['fonte']}

    def registrar_operacao(self, equipamento, acao, instante_utc=None, origem='sistema de controle'):
        if acao not in ('abertura', 'fechamento', 'partida', 'parada'):
            raise ErroDaBancada(422, 'acao desconhecida: %s' % acao)
        t = self.t if instante_utc is None else self.t_de_utc(instante_utc)
        op = {'equipamento': equipamento, 'acao': acao, 'instante_s': t, 'origem': origem}
        self.operacoes.append(op)
        return dict(op, instante_utc=self.utc(t))

    def sensor(self, sensor, falha):
        if sensor not in self.linha.sensores:
            raise ErroDaBancada(404, 'sensor desconhecido nesta linha: %s' % sensor)
        if falha not in FALHAS:
            raise ErroDaBancada(422, 'falha desconhecida: %s' % falha, {'opcoes': list(FALHAS)})
        if falha == 'nenhuma':
            self.falhas.pop(sensor, None)
        else:
            self.falhas[sensor] = {'tipo': falha, 't': self.t + ANTECEDENCIA_DO_EVENTO_S, 'valor': None}
        return {'sensor': sensor, 'falha': falha}

    def definir_gas(self, acusando):
        """Liga ou desliga o gas; um provavel recente sobe para confirmado. Devolve mensagens a difundir."""
        self.gas = bool(acusando)
        if not (self.gas and self.ultimo and self.ultimo[0]['nivel'] == 'provavel'
                and not self._reparado_depois_do_ultimo()):
            return []
        ev, verdade, t_c, registro, saude = self.ultimo
        ev = dict(ev, nivel='confirmado', confirmacao_por_gas=True, revisao=ev.get('revisao', 1) + 1,
                  explicacao=EX.texto(registro, P.AL.canais_reprovados(saude), saude, confirmado=True))
        self.ultimo = (ev, verdade, t_c, registro, saude)
        self.historico.gravar(ev, verdade, self.historico.sinal(ev['id']))
        return [{'tipo': 'evento', 'evento': ev, 'verdade': verdade}]

    def reparar(self):
        for ev in self.eventos:
            if ev['fim'] is None:
                ev['fim'] = self.t + ANTECEDENCIA_DO_EVENTO_S
        self.falhas = {}
        self.gas = False
        self.aguardando = None
        self.refratario_ate = self.t + SILENCIO_APOS_MUDANCA_S
        self._ultimo_reparo = self.t

    def definir_roteiro(self, nome, intervalo_s=60.0):
        if nome is None:
            self.roteiro = None
            return
        if nome != 'demonstracao':
            raise ErroDaBancada(422, 'roteiro desconhecido: %s' % nome, {'opcoes': ['demonstracao']})
        self.roteiro = {'nome': nome, 'intervalo_s': max(10.0, float(intervalo_s)), 'proximo': self.t + 1.0, 'passo': 0}

    def _passo_do_roteiro(self):
        r = self.roteiro
        if r is None or self.t < r['proximo']:
            return
        r['proximo'] = self.t + r['intervalo_s']
        passos = [('vazamento', 'grande'), ('reparar',)]
        # a valvula do roteiro: a do berco 106 quando existe, senao a primeira valvula da linha
        valvulas = [e['id'] for e in self.linha.equipamentos if e['tipo'] == 'valvula']
        valvula = 'XV-106' if 'XV-106' in valvulas else (valvulas[0] if valvulas else None)
        if valvula:
            passos += [('manobra', valvula, True), ('manobra', valvula, True), ('vazamento', 'pequeno'),
                       ('reparar',), ('manobra', valvula, False), ('manobra', valvula, False)]
        else:
            passos += [('vazamento', 'pequeno'), ('reparar',)]
        passo = passos[r['passo'] % len(passos)]
        r['passo'] += 1
        if passo[0] == 'reparar':
            self.reparar()
        elif passo[0] == 'vazamento':
            trecho = str(self.rng.choice(list(self.linha.trechos)))
            de, ate = self.linha.trechos[trecho]['monitorado']
            tamanho = passo[1] if passo[1] in self.linha.tamanhos else self.linha.tamanhos[0]
            self.vazamento(trecho, float(round(self.rng.uniform(de + 10.0, ate - 10.0))), tamanho)
        else:
            eq = passo[1]
            acao = 'fechar' if self.equipamentos[eq] == 'aberta' else 'abrir'
            self.equipamento(eq, acao, passo[2])

    # --- sinal ----------------------------------------------------------------
    def _config(self, k):
        semente = (self.n_passo * 7919 + k * 104729) % (2 ** 31)
        return P.TX.configuracoes(self.linha.faixa_m, semente)[self.transmissor]

    def _gerar(self):
        n = AMOSTRAS_POR_PASSO
        t_novo = self.t + TS * np.arange(1, n + 1)
        periodo = self.periodo_de_atualizacao()
        contexto = max(CONTEXTO_MINIMO, int(math.ceil(periodo / TS)) + 20)
        t_ext = self.t + TS * np.arange(1 - contexto, n + 1)
        limpo = GE.carga_limpa(self.linha, self.eventos, t_ext)
        saida = {}
        for k, par in enumerate(self.pares):
            cfg = self._config(k)
            if cfg['atualizacao'].get('ligado'):
                fases = [(self.fase[s] * periodo - t_ext[0]) % periodo for s in par]
                cfg['atualizacao'].update(fase_A_s=fases[0], fase_B_s=fases[-1])
            a = limpo[par[0]]
            b = limpo[par[1]] if len(par) > 1 else limpo[par[0]]
            sa, sb, registro = P.MS.aplicar(a, b, TS, cfg)
            saida[par[0]] = sa[-n:]
            if len(par) > 1:
                saida[par[1]] = sb[-n:]
            if k == 0:
                self.efeitos = registro
        for s, f in self.falhas.items():
            depois = t_novo >= f['t']
            if not depois.any():
                continue
            if f['tipo'] == 'cabo_rompido':
                saida[s] = np.where(depois, 0.0, saida[s])
            else:
                if f['valor'] is None:
                    i = int(np.argmax(depois))
                    f['valor'] = float(saida[s][i - 1] if i > 0 else (self.buf[s][-1] if len(self.buf[s]) else saida[s][i]))
                saida[s] = np.where(depois, f['valor'], saida[s])
        return t_novo, saida

    def _guardar(self, t_novo, saida):
        manter = int(HISTORICO_S * FS_HZ)
        self.buf_t = np.concatenate([self.buf_t, t_novo])[-manter:]
        for s in self.buf:
            self.buf[s] = np.concatenate([self.buf[s], saida[s]])[-manter:]

    # --- autoteste --------------------------------------------------------------
    def _saude(self, sinais):
        espec = P.RP.especificacao(self.escala()['resolucao_declarada_m'])
        limites = P.PP.limites_de_saude({'efeitos_de_sensor_aplicados': {'efeitos': self.efeitos}}, espec)
        periodo = self.periodo_de_atualizacao()
        if limites.get('limite_congelado') and periodo > 0:
            # a saida em degraus repete o codigo por um periodo inteiro: travado e mais que dois periodos
            limites['limite_congelado'] = max(limites['limite_congelado'], int(math.ceil(2 * periodo / TS)))
        saude = {}
        for s, x in sinais.items():
            canal = P.PLACA.SaudeDoCanal()
            for c in P.RP.converter(x, espec)[0]:
                canal.amostra(c)
            e = dict(canal.estatisticas)
            bandeiras = P.PR.bandeiras_de_saude(e, limites)
            e['falhas'] = [nome for bit, nome in P.PR.NOMES_DA_SAUDE if bandeiras & bit]
            saude['canal_' + s] = e
        return saude

    def mensagem_de_saude(self):
        saude = self.saude or {}
        return {'tipo': 'saude',
                'sensores': {k[len('canal_'):]: {'situacao': 'reprovado' if v['falhas'] else 'ok', 'falhas': v['falhas']}
                             for k, v in saude.items()},
                'monitoramento': P.AL.estado_do_monitoramento(saude)['monitoramento'] if saude else 'sem_autoteste'}

    # --- deteccao em fluxo --------------------------------------------------------
    def _procurar_chegada(self, t_inicio_do_passo):
        inicio = max(self.buf_t[-1] - JANELA_DE_PROCURA_S, self.refratario_ate - 0.05)
        sel = self.buf_t >= inicio
        minimo = self.cal['n_longa'] + self.cal['n_guarda'] + self.cal['n_curta'] + 10
        if np.count_nonzero(sel) < minimo:
            return None
        t = self.buf_t[sel]
        resolucao = self.escala()['resolucao_declarada_m']
        chegadas = []
        for s in self.buf:
            det = P.D.detectar_canal(self.buf[s][sel], TS, self.cal, resolucao)[0]
            if det['detectado']:
                tc = float(t[det['indice_de_cruzamento']])
                if tc >= t_inicio_do_passo - 0.05 and tc > self.refratario_ate:
                    chegadas.append(tc)
        return min(chegadas) if chegadas else None

    def _fechar_evento(self):
        t_c, fim = self.aguardando['t_c'], self.aguardando['fim']
        self.aguardando = None
        self.refratario_ate = fim + REFRATARIO_S
        sel = (self.buf_t >= t_c - ANTES_DA_CHEGADA_S) & (self.buf_t <= fim)
        t = self.buf_t[sel]
        sinais = {s: self.buf[s][sel] for s in self.buf}
        ident = 'BV-%05d' % (self._contador + 1)
        escala = self.escala()
        if self.linha.tipo == 'rede':
            escala_tx = dict(escala, periodo_de_atualizacao_declarado_s=self.periodo_de_atualizacao())
            registro = P.RD.processar_ensaio_rede({'id': ident, 'tempo_s': t, 'canais_carga_m': sinais},
                                                  escala_tx, self.linha.topo, self.cal)
        else:
            sa, sb = self.linha.sensores['A']['s_m'], self.linha.sensores['B']['s_m']
            ensaio = {'id': ident, 'n_pontos': int(len(t)), 'tempo_s': t, 'canal_A_carga_m': sinais['A'],
                      'canal_B_carga_m': sinais['B'],
                      'parametros_do_detector': {'posicao_sensor_A_m': sa, 'posicao_sensor_B_m': sb,
                                                 'distancia_entre_sensores_L_m': sb - sa,
                                                 'velocidade_de_onda_m_s': self.linha.c,
                                                 'incerteza_de_velocidade_de_onda_m_s': 0.0}}
            registro = P.D.processar_ensaio(ensaio, escala, self.cal)
            refino = P.RF.refinar(ensaio, registro, self.cal)
            if refino:
                registro['refino_por_correlacao'] = refino
        if registro.get('classe') in (P.D.CLASSE_SEM_DETECCAO, None):
            return []
        if not self._confirmar_degrau(registro, t, sinais):
            self.descartadas_como_ruido += 1
            return []
        saude = self._saude(sinais)
        if self.linha.cadastro:
            sensores_cad = {s: {'posicao_m': v['s_m']} for s, v in self.linha.sensores.items()}
            geometria = P.CD.GeometriaDaRede(self.linha.topo) if self.linha.topo is not None else None
            conf = P.CD.conferir(registro, self.linha.cadastro, self.operacoes, registro['tempo_de_declaracao_s'],
                                 sensores_cad, geometria)
            if conf.get('operacao') is not None:
                conf['operacao']['usada'] = True     # a mesma operacao nao explica um segundo evento
                conf['operacao'] = {k: v for k, v in conf['operacao'].items() if k != 'usada'}
            registro = P.CD.aplicar(registro, conf)
        return [self._montar_evento(registro, saude, t_c, t, sinais)]

    def _canais_que_declararam(self, registro):
        if 'canais' in registro:
            return {s: d for s, d in registro['canais'].items() if d.get('detectado')}
        return {s: registro[c] for s, c in (('A', 'canal_A'), ('B', 'canal_B')) if (registro.get(c) or {}).get('detectado')}

    def _confirmar_degrau(self, registro, t, sinais):
        """Com um canal so, o nivel tem que ter mudado e ficado mudado (ver o comeco do modulo)."""
        canais = self._canais_que_declararam(registro)
        if len(canais) != 1:
            return True
        sensor, det = next(iter(canais.items()))
        tc = det.get('tempo_de_chegada_s')
        if tc is None:
            return True
        x = sinais[sensor]
        antes = x[(t >= tc - 0.12) & (t < tc - 0.02)]
        depois = x[(t >= tc + 0.005) & (t < tc + 0.025)]
        if len(antes) < 10 or len(depois) < 5:
            return True
        limiar = max(6.0 * float(np.std(antes)) / np.sqrt(len(depois)), 3.0 * self.escala()['resolucao_declarada_m'])
        return abs(float(np.mean(depois)) - float(np.mean(antes))) > limiar

    def _montar_evento(self, registro, saude, t_c, t, sinais):
        sensores = {s: {'nome': v['nome'], 'trecho': v['trecho'], 'posicao_m': v['s_m']}
                    for s, v in self.linha.sensores.items()}
        ev = P.AL.montar_evento(registro, self.linha.id, sensores, 'software', saude, gas_na_regiao=self.gas,
                                agora=self.inicio_utc + datetime.timedelta(seconds=t_c))
        ev['instante_utc'] = self.utc(t_c)
        reprovados = P.AL.canais_reprovados(saude)
        publica = registro['classe'] == P.D.CLASSE_LOCALIZADO and not reprovados
        if self.linha.tipo == 'rede':
            ev['trecho'] = registro.get('trecho_estimado') if publica else None
            ev['posicao_m'] = registro.get('s_estimado_m') if publica else None
            ev['canais'] = {s: {'detectou': bool(d.get('detectado')), 'polaridade': d.get('polaridade'),
                                'instante_de_chegada_s': d.get('tempo_de_chegada_s')}
                            for s, d in registro['canais'].items()}
        else:
            ev['trecho'] = 'principal' if publica else None
            refino = registro.get('refino_por_correlacao') or {}
            ev['posicao_refinada_m'] = refino.get('posicao_estimada_m') if publica and refino.get('aplicado') else None
        for campo, casas in (('posicao_m', 3), ('incerteza_m', 3), ('posicao_refinada_m', 3)):
            if ev.get(campo) is not None:
                ev[campo] = round(float(ev[campo]), casas)
        for canal in ev['canais'].values():
            if canal.get('instante_de_chegada_s') is not None:
                canal['instante_de_chegada_s'] = round(float(canal['instante_de_chegada_s']), 5)
        ev['modo'] = 'simulacao'
        ev['transmissor'] = self.transmissor
        ev['explicacao'] = EX.texto(registro, reprovados, saude, confirmado=ev['nivel'] == 'confirmado')
        verdade = self._verdade(ev, t_c)
        marcas = {s: v.get('instante_de_chegada_s') for s, v in ev['canais'].items()}
        sinal = {'periodo_s': TS, 't0_s': round(float(t[0]), 4),
                 'pressao_bar': {s: [round(float(v), 4) for v in self.linha.bar(x)] for s, x in sinais.items()},
                 'marcas_de_chegada_s': marcas}
        self.historico.gravar(ev, verdade, sinal)
        self.ultimo = (ev, verdade, t_c, registro, saude)
        return {'tipo': 'evento', 'evento': ev, 'verdade': verdade}

    def _causa(self, t_c):
        """O que a bancada fez que explica uma chegada em t_c: o evento cuja onda chegou mais perto
        desse instante, ou uma falha de sensor que comecou ali."""
        candidatos = []
        for e in self.eventos:
            chegada = e['t0'] + min(self.linha.tempo_de_percurso(e['trecho'], e['s_m'], s) for s in self.linha.sensores)
            if -0.05 <= t_c - chegada <= 2.5:
                candidatos.append((abs(t_c - chegada), 'evento', e))
        for s, f in self.falhas.items():
            if -0.05 <= t_c - f['t'] <= 0.5:
                candidatos.append((abs(t_c - f['t']), 'falha', (s, f)))
        return min(candidatos, key=lambda c: c[0]) if candidatos else None

    def _verdade(self, ev, t_c):
        causa = self._causa(t_c)
        if causa is None:
            return None
        if causa[1] == 'falha':
            sensor, f = causa[2]
            return {'tipo': 'falha_de_sensor', 'sensor': sensor, 'falha': f['tipo']}
        e = causa[2]
        v = {'tipo': e['tipo'], 'trecho': e['trecho'], 's_m': e['s_m'], 'fonte': e['fonte'],
             'simulacao_de_origem': e['molde'].id}
        if e['tipo'] == 'vazamento':
            v['tamanho'] = e['tamanho']
        else:
            v.update(equipamento=e['equipamento'], acao=e['acao'], operacao_registrada=e.get('registrada', False))
        if ev['posicao_m'] is not None and e['tipo'] == 'vazamento':
            if self.linha.topo is not None:
                v['erro_m'] = round(float(P.RD.distancia_entre_pontos(
                    self.linha.topo, (ev['trecho'], ev['posicao_m']), (e['trecho'], e['s_m']))), 3)
            else:
                v['erro_m'] = round(abs(float(ev['posicao_m']) - e['s_m']), 3)
        return v

    # --- sobrepressao -------------------------------------------------------------
    def _sobrepressao(self, t_novo, pressao_bar):
        reprovados = [s for s in self.linha.sensores if ((self.saude or {}).get('canal_' + s) or {}).get('falhas')]
        acontecimentos = self.monitor.passo(t_novo, pressao_bar, excluir=reprovados)
        tipos = [a for a, _ in acontecimentos]
        mensagens = []
        for acontecimento, ep in acontecimentos:
            if acontecimento == 'encerrar' and 'abrir' in tipos:
                continue                        # episodio curto: abriu e acabou no mesmo passo, sai uma vez so
            mensagens.append(self._mensagem_de_sobrepressao(ep, em_curso=acontecimento != 'encerrar'
                                                            and 'encerrar' not in tipos))
        return mensagens

    def _mensagem_de_sobrepressao(self, ep, em_curso):
        _, _, instante = P.SP.Monitor.pico(ep)
        ev = P.SP.montar_evento(ep, self.linha.id, self.limites[self.linha.id], self.linha.origem_do_limite,
                                self.operacoes, self.utc(instante), em_curso, faixa_bar=LN.FAIXA_BAR, modo='simulacao')
        # a verdade da simulacao: a manobra da bancada que provocou o pico, se houve
        manobras = [e for e in self.eventos if e['tipo'] == 'manobra' and -0.5 <= ep['inicio_s'] - e['t0'] <= 3.0]
        verdade = None
        if manobras:
            e = max(manobras, key=lambda x: x['t0'])
            verdade = {'tipo': 'manobra', 'equipamento': e['equipamento'], 'acao': e['acao'],
                       'operacao_registrada': e.get('registrada', False)}
        self.historico.gravar(ev, verdade, None, tabela='sobrepressoes')
        self.ultima_sobrepressao = ev
        return {'tipo': 'sobrepressao', 'evento': ev, 'verdade': verdade}

    # --- o passo ----------------------------------------------------------------
    def passo(self):
        """Avanca 0,1 s. Devolve (t, pressao_bar por sensor, mensagens)."""
        self._passo_do_roteiro()
        t_inicio = self.t
        t_novo, saida = self._gerar()
        self._guardar(t_novo, saida)
        self.t = float(t_novo[-1])
        self.n_passo += 1
        mensagens = []
        if self.aguardando is None and self.t > self.refratario_ate:
            t_c = self._procurar_chegada(t_inicio)
            if t_c is not None:
                self.aguardando = {'t_c': t_c, 'fim': t_c + self.linha.espera_s() + FOLGA_DE_ESPERA_S}
        if self.aguardando is not None and self.t >= self.aguardando['fim']:
            mensagens += self._fechar_evento()
        pressao_bar = {s: self.linha.bar(x) for s, x in saida.items()}
        mensagens += self._sobrepressao(t_novo, pressao_bar)
        if self.n_passo % SAUDE_A_CADA_PASSOS == 0:
            n = int(JANELA_DE_SAUDE_S * FS_HZ)
            antes = self.mensagem_de_saude()
            self.saude = self._saude({s: x[-n:] for s, x in self.buf.items()})
            depois = self.mensagem_de_saude()
            if depois != antes:
                mensagens.append(depois)
        # eventos que ja terminaram de sumir saem da conta: reparados, e manobras cujo efeito ja decaiu
        self.eventos = [e for e in self.eventos if not self._efeito_acabou(e)]
        return t_novo, pressao_bar, mensagens

    def _efeito_acabou(self, e):
        if e['fim'] is not None:
            return self.t >= e['fim'] + GE.RAMPA_DE_REPARO_S + 0.1
        if e['tipo'] == 'manobra':
            # depois do fim da simulacao, 6 constantes de relaxacao (0,25%), mais o maior percurso da onda
            return self.t >= e['t0'] + e['molde'].t_rel[-1] + 6 * GE.RELAXACAO_DA_MANOBRA_S + self.linha.espera_s()
        return False

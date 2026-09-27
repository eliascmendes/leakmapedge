"""LEAKMAP - alerta de sobrepressao (golpe de ariete).

Funcionalidade complementar a deteccao e localizacao de vazamento, que
continua sendo o centro do LEAKMAP: os mesmos sensores de pressao tambem
mostram os picos que, com o tempo, causam o proximo vazamento. Fechar uma
valvula ou partir uma bomba de repente freia ou acelera o produto na linha, e
a pressao sobe (golpe de ariete). O tubo de aco aguenta muito mais; os elos
fracos sao mangotes, bracos de carregamento, flanges e trechos com a parede
afinada.

O monitor acompanha a pressao de cada sensor e compara com o LIMITE da linha,
a pressao maxima admissivel do componente mais fraco. Enquanto nao chega o
dado da planta, o limite e uma premissa.

  atencao   o pico passou de 80% do limite
  alarme    o pico passou de 95% do limite

Um episodio comeca quando algum sensor passa do nivel de atencao. O evento e
publicado 1 s depois (para pegar o pico inteiro, nao so a subida), e de novo,
com o mesmo id e revisao seguinte, se o nivel subir de atencao para alarme e
quando o episodio acaba (todos os sensores abaixo do nivel de atencao, com
0,3 bar de folga, por 1 s). Sensores reprovados no autoteste ficam de fora:
um sinal estragado nao vira alarme de pressao.

A pressao so e medida onde ha sensor: entre eles o pico pode ser maior. O
pico acima da faixa do transmissor fica cortado; o evento avisa quando isso
acontece.

A causa provavel e a operacao registrada (abertura, fechamento, partida,
parada) mais proxima antes do pico, no registro de operacao do sistema de
controle, o mesmo do cadastro (cadastro.py).
"""
import datetime
import uuid

import numpy as np

VERSAO = '1'
FRACAO_ATENCAO = 0.80
FRACAO_ALARME = 0.95
HISTERESE_BAR = 0.3
PUBLICAR_APOS_S = 1.0
ENCERRAR_APOS_S = 1.0
JANELA_DA_CAUSA_ANTES_S = 5.0
JANELA_DA_CAUSA_DEPOIS_S = 1.0
NIVEIS = ('atencao', 'alarme')
ACAO_TEXTO = {'fechamento': 'do fechamento', 'abertura': 'da abertura', 'partida': 'da partida', 'parada': 'da parada'}


def nivel_da_fracao(fracao):
    if fracao >= FRACAO_ALARME:
        return 'alarme'
    if fracao >= FRACAO_ATENCAO:
        return 'atencao'
    return None


class Monitor:
    """Acompanha os picos de pressao, bloco a bloco, e devolve os acontecimentos do episodio."""

    def __init__(self, limite_bar, faixa_bar=None):
        self.limite_bar = float(limite_bar)
        self.faixa_bar = faixa_bar
        self.episodio = None

    @property
    def limiar_bar(self):
        return FRACAO_ATENCAO * self.limite_bar

    def passo(self, t, pressao_bar, excluir=()):
        """`t`: instantes do bloco (s); `pressao_bar`: {sensor: valores}. Devolve [(acontecimento, episodio)],
        com acontecimento 'abrir', 'subir' (de atencao para alarme) ou 'encerrar'."""
        t = np.asarray(t, dtype=float)
        picos = {}
        for s, x in pressao_bar.items():
            if s in excluir or not len(x):
                continue
            x = np.asarray(x, dtype=float)
            i = int(np.argmax(x))
            picos[s] = (float(x[i]), float(t[i]))
        if not picos:
            return []
        maior = max(picos.values(), key=lambda p: p[0])
        ep = self.episodio
        saida = []
        if ep is None:
            if maior[0] < self.limiar_bar:
                return []
            ep = self.episodio = {'inicio_s': maior[1], 'picos': {}, 'publicado': False, 'nivel': None,
                                  'ultimo_acima_s': float(t[-1]), 'id': str(uuid.uuid4()), 'revisao': 0}
        for s, (valor, instante) in picos.items():
            if s not in ep['picos'] or valor > ep['picos'][s][0]:
                ep['picos'][s] = (valor, instante)
        if maior[0] >= self.limiar_bar - HISTERESE_BAR:
            ep['ultimo_acima_s'] = float(t[-1])
        nivel = nivel_da_fracao(self.pico(ep)[1] / self.limite_bar)
        fim = float(t[-1]) - ep['ultimo_acima_s'] >= ENCERRAR_APOS_S
        if not ep['publicado'] and (float(t[-1]) - ep['inicio_s'] >= PUBLICAR_APOS_S or fim):
            ep['publicado'], ep['nivel'] = True, nivel
            saida.append(('abrir', ep))
        elif ep['publicado'] and NIVEIS.index(nivel) > NIVEIS.index(ep['nivel']):
            ep['nivel'] = nivel
            saida.append(('subir', ep))
        if fim:
            ep['fim_s'] = float(t[-1])
            saida.append(('encerrar', ep))
            self.episodio = None
        return saida

    @staticmethod
    def pico(ep):
        """(sensor, pico em bar, instante) do maior pico do episodio."""
        s, (valor, instante) = max(ep['picos'].items(), key=lambda kv: kv[1][0])
        return s, valor, instante

    def nivel_atual(self):
        return self.episodio['nivel'] if self.episodio and self.episodio['publicado'] else None


def causa_provavel(operacoes, instante_s):
    """A operacao registrada mais proxima antes do pico (ou logo depois, por atraso do registro)."""
    candidatas = [op for op in operacoes or []
                  if -JANELA_DA_CAUSA_DEPOIS_S <= instante_s - float(op['instante_s']) <= JANELA_DA_CAUSA_ANTES_S]
    if not candidatas:
        return None
    op = min(candidatas, key=lambda o: abs(instante_s - float(o['instante_s'])))
    return {'equipamento': op['equipamento'], 'acao': op['acao'], 'instante_s': round(float(op['instante_s']), 4),
            'antes_do_pico_s': round(instante_s - float(op['instante_s']), 2), 'origem': op.get('origem')}


def _bar(v):
    return ('%.2f' % v).replace('.', ',')


def explicacao(ep, limite_bar, causa, em_curso, cortado):
    sensor, valor, _ = Monitor.pico(ep)
    fracao = round(valor / limite_bar, 3)          # o mesmo valor do campo fracao_do_limite
    partes = ['A pressão no sensor %s chegou a %s bar, %d%% do limite de %s bar da linha.'
              % (sensor, _bar(valor), int(100 * fracao + 0.5), _bar(limite_bar))]
    if fracao > 1.0:
        partes.append('O pico passou do limite.')
    if causa:
        # registro um pouco atrasado (ate JANELA_DA_CAUSA_DEPOIS_S): o pico vem "antes" da operacao registrada
        partes.append('O pico veio %s s %s %s da %s, %s pelo sistema de controle: é golpe de aríete de '
                      'manobra, não vazamento.' % (('%.1f' % abs(causa['antes_do_pico_s'])).replace('.', ','),
                                                   'depois' if causa['antes_do_pico_s'] >= 0 else 'antes',
                                                   ACAO_TEXTO.get(causa['acao'], 'da operação'), causa['equipamento'],
                                                   'registrado' if causa['acao'] == 'fechamento' else 'registrada'))
        if causa['acao'] in ('fechamento', 'partida'):
            partes.append('Fazer a manobra mais devagar reduz o pico.')
    else:
        partes.append('Nenhuma operação registrada explica o pico: conferir o que aconteceu na linha.')
    if fracao >= FRACAO_ALARME:
        partes.append('Perto do limite do componente mais fraco: conferir mangotes, braços de carregamento e flanges.')
    if cortado:
        partes.append('O pico passou da faixa do transmissor: o valor real pode ser maior.')
    if not em_curso and ep.get('fim_s') is not None:
        partes.append('A pressão voltou abaixo do nível de atenção.')
    elif em_curso:
        partes.append('A pressão ainda está acima do nível de atenção.')
    return ' '.join(partes)


def montar_evento(ep, linha, limite_bar, origem_do_limite, operacoes, instante_utc, em_curso, faixa_bar=None,
                  modo=None):
    """Evento padronizado de sobrepressao (tipo leakmap.sobrepressao)."""
    sensor, valor, instante = Monitor.pico(ep)
    causa = causa_provavel(operacoes, instante)
    cortado = faixa_bar is not None and valor >= float(faixa_bar) - 1e-6
    ep['revisao'] += 1
    evento = {
        'tipo': 'leakmap.sobrepressao',
        'versao': VERSAO,
        'id': ep['id'],
        'revisao': ep['revisao'],
        'instante_utc': instante_utc,
        'linha': linha,
        'nivel': ep['nivel'],
        'em_curso': bool(em_curso),
        'limite_bar': round(float(limite_bar), 3),
        'origem_do_limite': origem_do_limite,
        'pico_bar': round(valor, 3),
        'fracao_do_limite': round(valor / float(limite_bar), 3),
        'sensor_do_pico': sensor,
        'instante_do_pico_s': round(instante, 4),
        'picos_por_sensor_bar': {s: round(v, 3) for s, (v, _) in sorted(ep['picos'].items())},
        'duracao_s': (round(ep['fim_s'] - ep['inicio_s'], 2) if ep.get('fim_s') is not None else None),
        'causa_provavel': causa,
        'pico_pode_ser_maior': bool(cortado),
        'explicacao': explicacao(ep, limite_bar, causa, em_curso, cortado),
    }
    if modo:
        evento['modo'] = modo
    return evento


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

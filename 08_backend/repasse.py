"""LEAKMAP - repasse dos eventos da bancada pelo webhook.

Cada evento que sai no WebSocket sai tambem por HTTP POST, em JSON, para a URL
configurada, pelo mesmo codigo de 07_servico/integracao.py: filtro por nivel,
tentativas e fila local para o que nao conseguiu sair. E o ponto de entrada
para a automacao da empresa (n8n, Node-RED, o sistema de controle).

O envio roda numa linha de execucao propria: um destino lento ou fora do ar
nunca atrasa a bancada nem o detector. Vai so o evento (leakmap.evento), sem a
verdade da simulacao; o evento traz "modo": "simulacao", e o receptor deve
tratar assim. Quando o gas confirma um alerta, o mesmo evento sai de novo com o
mesmo "id" e "revisao": 2. Os alertas de sobrepressao (leakmap.sobrepressao)
saem tambem, com os niveis proprios deles (atencao, alarme), sem passar pelo
filtro de niveis de vazamento.

Configuracao, pela ordem:
  LEAKMAP_WEBHOOK_URL          liga o repasse para esta URL
  LEAKMAP_WEBHOOK_NIVEIS       niveis que saem, separados por virgula
                               (padrao: suspeita,provavel,confirmado)
  LEAKMAP_WEBHOOK_CABECALHOS   cabecalhos extras em JSON, ex.: {"Authorization": "Bearer ..."}
  LEAKMAP_WEBHOOK_PENDENTES    arquivo da fila local (padrao: na pasta temporaria)
Sem LEAKMAP_WEBHOOK_URL, vale 07_servico/integracao.json, se existir; sem os
dois, o repasse fica desligado.
"""
import json
import os
import queue
import tempfile
import threading
import time
import urllib.parse

import projeto as P

REENVIAR_A_CADA_S = 60.0


def configuracao_do_ambiente():
    url = os.environ.get('LEAKMAP_WEBHOOK_URL')
    if not url:
        return P.IN.ler_config()
    niveis = os.environ.get('LEAKMAP_WEBHOOK_NIVEIS')
    return dict(P.IN.PADRAO, ligado=True, url=url,
                niveis=[n.strip() for n in niveis.split(',')] if niveis else P.IN.PADRAO['niveis'],
                cabecalhos=json.loads(os.environ.get('LEAKMAP_WEBHOOK_CABECALHOS') or '{}'))


class Repasse:
    def __init__(self, cfg=None, pendentes=None):
        self.cfg = cfg if cfg is not None else configuracao_do_ambiente()
        self.pendentes = pendentes or os.environ.get('LEAKMAP_WEBHOOK_PENDENTES') or \
            os.path.join(tempfile.gettempdir(), 'leakmap_webhook_pendentes.jsonl')
        self.fila = queue.Queue(maxsize=1000)
        self.contagem = {'enviado': 0, 'filtrado': 0, 'pendente': 0, 'reenviado': 0, 'descartado_fila_cheia': 0}
        self.ultimo = None
        self._trava = threading.Lock()
        if self.ligado:
            threading.Thread(target=self._laco, name='leakmap-webhook', daemon=True).start()

    @property
    def ligado(self):
        return bool(self.cfg.get('ligado') and self.cfg.get('url'))

    def por(self, evento):
        """Enfileira um evento para o webhook. Nunca bloqueia."""
        if not self.ligado:
            return
        try:
            self.fila.put_nowait(evento)
        except queue.Full:
            with self._trava:
                self.contagem['descartado_fila_cheia'] += 1

    def _registrar(self, resultado, evento):
        with self._trava:
            self.contagem[resultado] = self.contagem.get(resultado, 0) + 1
            self.ultimo = {'resultado': resultado, 'evento_id': evento.get('id'), 'nivel': evento.get('nivel'),
                           'quando_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    def _laco(self):
        proximo_reenvio = time.monotonic() + REENVIAR_A_CADA_S
        while True:
            try:
                evento = self.fila.get(timeout=5.0)
                cfg = self.cfg
                if evento.get('tipo') == 'leakmap.sobrepressao':
                    # o alerta de sobrepressao tem niveis proprios (atencao, alarme) e sai sempre
                    cfg = dict(self.cfg, niveis=list(self.cfg.get('niveis') or []) + list(P.SP.NIVEIS))
                self._registrar(P.IN.enviar(evento, cfg, self.pendentes), evento)
            except queue.Empty:
                pass
            if time.monotonic() >= proximo_reenvio:
                proximo_reenvio = time.monotonic() + REENVIAR_A_CADA_S
                n = P.IN.reenviar(self.cfg, self.pendentes)
                if n:
                    with self._trava:
                        self.contagem['reenviado'] += n

    def testar(self, evento):
        """Envia agora um evento de teste, sem o filtro de nivel. Bloqueia: chamar fora do laco principal."""
        if not self.ligado:
            return 'desligado'
        cfg = dict(self.cfg, niveis=[evento.get('nivel')], tentativas=1)
        return P.IN.enviar(evento, cfg, os.devnull)

    def situacao(self):
        with self._trava:
            destino = urllib.parse.urlsplit(self.cfg.get('url') or '')
            fila_local = 0
            if os.path.exists(self.pendentes):
                with open(self.pendentes, encoding='utf-8') as f:
                    fila_local = sum(1 for linha in f if linha.strip())
            return {'ligado': self.ligado,
                    'destino': '%s://%s' % (destino.scheme, destino.netloc) if destino.netloc else None,
                    'niveis': self.cfg.get('niveis'), 'contagem': dict(self.contagem),
                    'aguardando_envio': self.fila.qsize(), 'na_fila_local_para_reenvio': fila_local,
                    'ultimo': self.ultimo}

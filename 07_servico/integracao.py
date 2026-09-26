"""LEAKMAP - saida dos eventos para integracao externa (webhook).

Envia cada evento (alerta.montar_evento) como JSON, por HTTP POST, para a URL
configurada. Qualquer ferramenta que receba um webhook conecta sem mudar nada
do lado do LEAKMAP: n8n, Node-RED, um servico da empresa, o historico.

Configuracao em 07_servico/integracao.json (copie de integracao.exemplo.json).
Sem o arquivo, ou com "ligado": false, nada sai: o alarme local continua
funcionando sem rede.

  {
    "webhook": {
      "ligado": false,
      "url": "http://127.0.0.1:8765/leakmap",
      "niveis": ["suspeita", "provavel", "confirmado"],
      "tempo_limite_s": 3,
      "tentativas": 3,
      "cabecalhos": {}
    }
  }

Uma falha de envio nunca derruba a deteccao: o evento fica numa fila local
(07_servico/pendentes.jsonl) e e reenviado na proxima chamada de `reenviar`.
"""
import json
import os
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(AQUI, 'integracao.json')
PENDENTES = os.path.join(AQUI, 'pendentes.jsonl')
PADRAO = {'ligado': False, 'url': '', 'niveis': ['suspeita', 'provavel', 'confirmado'],
          'tempo_limite_s': 3, 'tentativas': 3, 'cabecalhos': {}}


def ler_config(caminho=CONFIG):
    if not os.path.exists(caminho):
        return dict(PADRAO)
    with open(caminho, encoding='utf-8') as f:
        return dict(PADRAO, **(json.load(f).get('webhook') or {}))


def _postar(evento, cfg):
    corpo = json.dumps(evento, ensure_ascii=False).encode('utf-8')
    cabecalhos = dict({'Content-Type': 'application/json; charset=utf-8'}, **cfg.get('cabecalhos', {}))
    pedido = urllib.request.Request(cfg['url'], data=corpo, headers=cabecalhos, method='POST')
    with urllib.request.urlopen(pedido, timeout=float(cfg['tempo_limite_s'])) as resposta:
        return resposta.status


def enviar(evento, cfg=None, pendentes=PENDENTES):
    """Envia um evento. Devolve 'desligado', 'filtrado', 'enviado' ou 'pendente'."""
    cfg = cfg or ler_config()
    if not cfg.get('ligado') or not cfg.get('url'):
        return 'desligado'
    if evento.get('nivel') not in cfg.get('niveis', []):
        return 'filtrado'
    for _ in range(max(1, int(cfg.get('tentativas', 1)))):
        try:
            if 200 <= _postar(evento, cfg) < 300:
                return 'enviado'
        except (urllib.error.URLError, OSError):
            continue
    with open(pendentes, 'a', encoding='utf-8') as f:
        f.write(json.dumps(evento, ensure_ascii=False) + '\n')
    return 'pendente'


def reenviar(cfg=None, pendentes=PENDENTES):
    """Tenta de novo os eventos da fila local. Devolve quantos sairam."""
    cfg = cfg or ler_config()
    if not os.path.exists(pendentes) or not cfg.get('ligado'):
        return 0
    with open(pendentes, encoding='utf-8') as f:
        eventos = [json.loads(l) for l in f if l.strip()]
    os.remove(pendentes)
    return sum(1 for e in eventos if enviar(e, cfg, pendentes) == 'enviado')

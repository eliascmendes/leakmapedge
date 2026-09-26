"""LEAKMAP - receptor minimo de webhook, para testar a integracao sem instalar nada.

Escuta em http://127.0.0.1:8765/leakmap e mostra cada evento recebido. Faz o
papel da ferramenta da empresa (n8n, Node-RED, sistema de controle).

  python 07_servico/receptor_teste.py [--porta 8765]
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Receptor(BaseHTTPRequestHandler):
    recebidos = []

    def do_POST(self):
        tamanho = int(self.headers.get('Content-Length', 0))
        evento = json.loads(self.rfile.read(tamanho).decode('utf-8'))
        Receptor.recebidos.append(evento)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')
        pos = evento.get('posicao_m')
        print('[%s] linha %s: %s (%s)%s | monitoramento %s' % (
            evento.get('nivel'), evento.get('linha'), evento.get('classificacao'),
            evento.get('origem_do_processamento'),
            '' if pos is None else ' em %.1f m +- %.1f m' % (pos, evento.get('incerteza_m') or 0.0),
            evento.get('saude', {}).get('monitoramento')), flush=True)

    def log_message(self, *args):
        pass


def servidor(porta=8765):
    return HTTPServer(('127.0.0.1', porta), Receptor)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--porta', type=int, default=8765)
    args = ap.parse_args()
    print('esperando eventos em http://127.0.0.1:%d/leakmap' % args.porta)
    servidor(args.porta).serve_forever()

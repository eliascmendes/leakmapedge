"""LEAKMAP - cliente de linha de comando da bancada virtual.

Conecta no WebSocket, dispara um cenario pela API e mostra (ou grava) o que
chega. Serve para provar o backend sem o front-end e para gravar uma sessao de
exemplo para a equipe de front.

Uso:
  python 08_backend/cliente.py                                   # so escuta 10 s
  python 08_backend/cliente.py --vazamento principal 320 grande   # rompe e mostra o evento
  python 08_backend/cliente.py --manobra XV-106 fechar --sem-registro
  python 08_backend/cliente.py --endereco https://<servico>.onrender.com --chave <chave>
  python 08_backend/cliente.py --vazamento principal 320 grande --gravar sessao.jsonl

Precisa do pacote websockets (vem com uvicorn[standard], em 08_backend/requirements.txt).
"""
import argparse
import asyncio
import json
import time
import urllib.error
import urllib.request

import websockets


def api(endereco, metodo, rota, corpo=None, chave=None):
    cab = {'Content-Type': 'application/json'}
    if chave:
        cab['X-LEAKMAP-Chave'] = chave
    req = urllib.request.Request(endereco.rstrip('/') + rota, method=metodo, headers=cab,
                                 data=json.dumps(corpo).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def resumo(m):
    if m['tipo'] == 'amostras':
        return 'amostras t=%.2f s  %s' % (m['t_s'], '  '.join('%s %.3f bar' % (k, v[-1]) for k, v in m['pressao_bar'].items()))
    if m['tipo'] == 'evento':
        e, v = m['evento'], m.get('verdade')
        pos = 'sem posicao' if e['posicao_m'] is None else '%s %.2f m' % (e['trecho'], e['posicao_m'])
        real = '' if not v else ' | real: %s' % ({k: v[k] for k in ('tipo', 'trecho', 's_m', 'erro_m') if k in v})
        return 'EVENTO %s · %s · %s%s\n    %s' % (e['nivel'], e['classificacao'], pos, real, e['explicacao'])
    if m['tipo'] == 'saude':
        return 'saude %s %s' % (m['monitoramento'], {k: v['falhas'] for k, v in m['sensores'].items()})
    if m['tipo'] == 'estado':
        return 'estado linha=%s transmissor=%s nivel=%s' % (m['estado']['linha'], m['estado']['transmissor'],
                                                            m['estado']['nivel_atual'])
    return m['tipo']


async def principal(args):
    ws_url = args.endereco.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/')
    ws_url += '/ws?perfil=%s&taxa=%d' % (args.perfil, args.taxa)
    gravacao = open(args.gravar, 'w', encoding='utf-8') if args.gravar else None
    inicio = time.monotonic()
    async with websockets.connect(ws_url, max_size=None) as ws:
        async def escutar():
            ultimas = 0.0
            async for texto in ws:
                m = json.loads(texto)
                if gravacao:
                    gravacao.write(json.dumps({'recebido_em_s': round(time.monotonic() - inicio, 3), 'mensagem': m},
                                              ensure_ascii=False) + '\n')
                if m['tipo'] == 'amostras':
                    if time.monotonic() - ultimas < 1.0:
                        continue
                    ultimas = time.monotonic()
                print('%6.2f s  %s' % (time.monotonic() - inicio, resumo(m)), flush=True)

        tarefa = asyncio.create_task(escutar())
        await asyncio.sleep(args.antes)
        if args.linha:
            print('linha ->', api(args.endereco, 'POST', '/api/bancada/linha', {'linha': args.linha}, args.chave)[0])
            await asyncio.sleep(2.0)
        if args.vazamento:
            trecho, s_m, tamanho = args.vazamento
            st, r = api(args.endereco, 'POST', '/api/bancada/vazamento',
                        {'trecho': trecho, 's_m': float(s_m), 'tamanho': tamanho}, args.chave)
            print('vazamento ->', st, r.get('resultado') or r)
        if args.manobra:
            st, r = api(args.endereco, 'POST', '/api/bancada/equipamento',
                        {'equipamento': args.manobra[0], 'acao': args.manobra[1],
                         'registrar_operacao': not args.sem_registro}, args.chave)
            print('manobra ->', st, r.get('resultado') or r)
        await asyncio.sleep(args.depois)
        tarefa.cancel()
    if gravacao:
        gravacao.close()
        print('gravado:', args.gravar)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--endereco', default='http://localhost:8000')
    ap.add_argument('--chave', default=None)
    ap.add_argument('--perfil', default='demonstracao', choices=['demonstracao', 'operador'])
    ap.add_argument('--taxa', type=int, default=30)
    ap.add_argument('--linha', choices=['trecho_200', 'cais', 'rede'])
    ap.add_argument('--vazamento', nargs=3, metavar=('TRECHO', 'S_M', 'TAMANHO'))
    ap.add_argument('--manobra', nargs=2, metavar=('EQUIPAMENTO', 'ACAO'))
    ap.add_argument('--sem-registro', action='store_true')
    ap.add_argument('--antes', type=float, default=2.0, help='segundos escutando antes da acao')
    ap.add_argument('--depois', type=float, default=8.0, help='segundos escutando depois da acao')
    ap.add_argument('--gravar', help='grava todas as mensagens num arquivo .jsonl')
    args = ap.parse_args()
    # a primeira chamada acorda o servico no plano gratuito do Render
    print('servico ->', api(args.endereco, 'GET', '/api/servico'))
    asyncio.run(principal(args))


if __name__ == '__main__':
    main()

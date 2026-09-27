"""LEAKMAP - conferencia de um backend da bancada no ar (Render ou local).

Roda uma bateria de cenarios com resultado esperado conhecido contra o servico
e confere cada um: consultas, seguranca, validacao, WebSocket, vazamentos na
linha do cais, na rede e no trecho de 200 m, manobras com e sem registro de
operacao, sensor com defeito, gas, transmissor lento, historico e ausencia de
falso alarme. No fim, devolve a bancada ao estado inicial.

O servico e compartilhado: se houver alguem conectado ao WebSocket, a
conferencia nao comeca (a menos que se use --forcar), porque ela mexe na
bancada que os outros estao vendo.

Uso:
  python 08_backend/conferir_servico.py --endereco https://leakmap-bancada.onrender.com --chave <chave>
  python 08_backend/conferir_servico.py                     # local, http://127.0.0.1:8000
  LEAKMAP_CHAVE=<chave> python 08_backend/conferir_servico.py --endereco ... --relatorio relatorio.json

Sai com codigo 0 se tudo conferir, 1 se algo falhar.
Precisa do pacote websockets (vem com uvicorn[standard], em 08_backend/requirements.txt).
"""
import argparse
import asyncio
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

import websockets

# entre duas manobras: o transitorio da anterior tem de assentar, senao a frente lenta da seguinte (parada
# da bomba) pode nao ser marcada; com 1,5 s (cerca de 2,6 s entre os comandos) ela se perdia
ASSENTAR_S = 4.0
# pressao de regime esperada em cada sensor, em bar (simulacoes do TSNet em 03_ensaios)
REGIME_BAR = {'cais': {'A': 6.75, 'B': 6.15}, 'rede': {'A': 6.60, 'B104': 6.16, 'B106': 6.13, 'B108': 6.11}}
ACAO_PARA = {('valvula', 'aberta'): 'abrir', ('valvula', 'fechada'): 'fechar',
             ('bomba', 'ligada'): 'partir', ('bomba', 'desligada'): 'parar'}


class Conferencia:
    def __init__(self, endereco, chave, espera_s):
        self.endereco = endereco.rstrip('/')
        self.chave = chave
        self.espera_s = espera_s
        self.resultados = []
        self.fila = None
        self.ws = None
        self.amostras = []

    # --- acesso ao servico --------------------------------------------------------
    def http(self, metodo, rota, corpo=None, chave=True, chave_errada=False):
        cab = {'Content-Type': 'application/json'}
        if chave and self.chave:
            cab['X-LEAKMAP-Chave'] = 'errada' if chave_errada else self.chave
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(self.endereco + rota, method=metodo, headers=cab, data=dados)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            texto = e.read()
            try:
                return e.code, json.loads(texto)
            except ValueError:
                return e.code, {'texto': texto.decode(errors='replace')}

    async def api(self, metodo, rota, corpo=None, **k):
        return await asyncio.to_thread(self.http, metodo, rota, corpo, **k)

    async def comando(self, rota, corpo):
        st, r = await self.api('POST', rota, corpo)
        if st != 200:
            raise RuntimeError('%s devolveu %s: %s' % (rota, st, r))
        return r

    async def escutar(self):
        async for texto in self.ws:
            m = json.loads(texto)
            if m['tipo'] == 'amostras':
                self.amostras.append(m)
                self.amostras = self.amostras[-50:]
            else:
                await self.fila.put(m)

    def limpar_fila(self):
        while not self.fila.empty():
            self.fila.get_nowait()

    async def evento(self, espera=None):
        """O proximo evento que chegar pelo WebSocket, ou None."""
        limite = time.monotonic() + (espera or self.espera_s)
        while True:
            falta = limite - time.monotonic()
            if falta <= 0:
                return None
            try:
                m = await asyncio.wait_for(self.fila.get(), falta)
            except asyncio.TimeoutError:
                return None
            if m['tipo'] == 'evento':
                return m

    async def calma(self, segundos=2.0):
        """Deixa passar as reflexoes do ultimo evento e esvazia a fila."""
        await asyncio.sleep(segundos)
        self.limpar_fila()

    # --- registro -------------------------------------------------------------------------
    def conferir(self, grupo, nome, ok, detalhe=''):
        self.resultados.append({'grupo': grupo, 'teste': nome, 'ok': bool(ok), 'detalhe': detalhe})
        print('  [%s] %-58s %s' % ('ok' if ok else 'FALHOU', nome, detalhe), flush=True)
        return ok

    # --- preparo ------------------------------------------------------------------------------
    async def preparar(self, linha='cais', transmissor='rapido'):
        est = (await self.api('GET', '/api/estado'))[1]
        if est['linha'] != linha:
            await self.comando('/api/bancada/linha', {'linha': linha})
            await asyncio.sleep(1.0)
        if est['transmissor'] != transmissor:
            await self.comando('/api/bancada/transmissor', {'transmissor': transmissor})
        await self.comando('/api/bancada/reparar', {})
        await self.equipamentos_iniciais()
        await self.calma(2.0)

    async def equipamentos_iniciais(self):
        cad = (await self.api('GET', '/api/cadastro'))[1]
        for e in cad['equipamentos']:
            if e['estado'] != e['estado_inicial']:
                await self.comando('/api/bancada/equipamento', {'equipamento': e['id'],
                                                                'acao': ACAO_PARA[(e['tipo'], e['estado_inicial'])],
                                                                'registrar_operacao': True})
                await self.calma(2.5)

    async def romper(self, trecho, s_m, tamanho='grande'):
        self.limpar_fila()
        await self.comando('/api/bancada/vazamento', {'trecho': trecho, 's_m': s_m, 'tamanho': tamanho})
        t0 = time.monotonic()                   # conta de quando o servico aceitou o comando
        m = await self.evento()
        return m, time.monotonic() - t0

    # --- grupos de testes -------------------------------------------------------------------
    async def consultas(self):
        g = 'consultas'
        st, s = await self.api('GET', '/api/servico')
        self.conferir(g, 'GET /api/servico responde ok', st == 200 and s.get('situacao') == 'ok', 'HTTP %s' % st)
        self.conferir(g, 'versao do contrato e 1', s.get('versao_do_contrato') == '1', s.get('versao_do_contrato'))
        self.conferir(g, 'modo simulacao', s.get('modo') == 'simulacao')
        self.conferir(g, 'comandos exigem chave', s.get('comandos_exigem_chave') is True)
        st, l = await self.api('GET', '/api/linhas')
        ids = {x['id'] for x in l.get('linhas', [])}
        self.conferir(g, 'tres linhas: trecho_200, cais, rede', ids == {'trecho_200', 'cais', 'rede'}, sorted(ids))
        rede = next((x for x in l.get('linhas', []) if x['id'] == 'rede'), {})
        self.conferir(g, 'rede com quatro sensores', {x['id'] for x in rede.get('sensores', [])} ==
                      {'A', 'B104', 'B106', 'B108'})
        st, _ = await self.api('GET', '/api/linhas/nao_existe')
        self.conferir(g, 'linha inexistente da 404', st == 404, 'HTTP %s' % st)
        st, tx = await self.api('GET', '/api/transmissores')
        self.conferir(g, 'seis transmissores', len(tx or []) == 6, len(tx or []))
        st, e = await self.api('GET', '/api/estado?perfil=operador')
        self.conferir(g, 'estado do operador sem a verdade', 'vazamentos_abertos' not in e)
        st, c = await self.api('GET', '/api/cadastro')
        self.conferir(g, 'cadastro da linha do cais com 4 equipamentos', len(c.get('equipamentos', [])) == 4)

    async def seguranca_e_validacao(self):
        g = 'seguranca'
        st, r = await self.api('POST', '/api/bancada/reparar', {}, chave=False)
        self.conferir(g, 'comando sem chave da 401', st == 401 and 'erro' in r, 'HTTP %s' % st)
        st, r = await self.api('POST', '/api/bancada/reparar', {}, chave_errada=True)
        self.conferir(g, 'comando com chave errada da 401', st == 401, 'HTTP %s' % st)
        g = 'validacao'
        st, r = await self.api('POST', '/api/bancada/vazamento', {'trecho': 'principal', 's_m': 5000})
        self.conferir(g, 'posicao fora da linha da 422 com "erro"', st == 422 and 'fora da linha' in r.get('erro', ''),
                      'HTTP %s' % st)
        st, r = await self.api('POST', '/api/bancada/transmissor', {'transmissor': 'xyz'})
        self.conferir(g, 'transmissor invalido da 422 com "erro"', st == 422 and 'erro' in r, 'HTTP %s %s' % (st, list(r)))
        st, r = await self.api('POST', '/api/bancada/equipamento', {'equipamento': 'XV-106', 'acao': 'abrir'})
        self.conferir(g, 'abrir valvula ja aberta da 409', st == 409, 'HTTP %s' % st)
        st, r = await self.api('POST', '/api/bancada/vazamento', {'trecho': 'principal', 's_m': 320, 'fonte': 'tsnet'})
        self.conferir(g, 'fonte tsnet fora de ponto simulado da 422 com sugestoes',
                      st == 422 and bool(r.get('pontos_mais_proximos')), 'HTTP %s' % st)

    async def websocket(self):
        g = 'websocket'
        # a bancada e compartilhada: um vazamento ou manobra deixado por outra pessoa tira a linha do regime
        await self.preparar('cais', 'rapido')
        self.amostras.clear()
        await asyncio.sleep(2.0)
        self.conferir(g, 'amostras chegando', len(self.amostras) >= 5, '%d mensagens' % len(self.amostras))
        if self.amostras:
            m = self.amostras[-1]
            self.conferir(g, 'amostras marcadas como simulacao', m.get('modo') == 'simulacao')
            n = len(next(iter(m['pressao_bar'].values())))
            self.conferir(g, '30 pontos por segundo (3 por mensagem)', 2 <= n <= 4 and abs(m['periodo_s'] - 1 / 30) < 1e-6,
                          '%d pontos, periodo %.4f s' % (n, m['periodo_s']))
            regime = REGIME_BAR.get(m.get('linha'), {})
            difs = {s: abs(v[-1] - regime[s]) for s, v in m['pressao_bar'].items() if s in regime}
            self.conferir(g, 'pressao de regime dentro de 0,05 bar do TSNet', difs and max(difs.values()) < 0.05,
                          ' '.join('%s %.3f bar' % (s, v[-1]) for s, v in m['pressao_bar'].items()))
        url = self.endereco.replace('https://', 'wss://').replace('http://', 'ws://') + '/ws?perfil=operador&taxa=10'
        async with websockets.connect(url, max_size=None) as ws:
            m = json.loads(await asyncio.wait_for(ws.recv(), 30))
            self.conferir(g, 'perfil operador: boas_vindas sem a verdade',
                          m['tipo'] == 'boas_vindas' and 'vazamentos_abertos' not in m['estado'])
            m = json.loads(await asyncio.wait_for(ws.recv(), 30))
            n = len(next(iter(m['pressao_bar'].values()))) if m['tipo'] == 'amostras' else 0
            self.conferir(g, 'taxa pedida na conexao (10 por segundo)', m['tipo'] == 'amostras' and n == 1,
                          '%d ponto(s) por mensagem' % n)

    def conferir_vazamento(self, g, nome, m, dt, trecho, s_m, erro_max, nivel='provavel'):
        if not self.conferir(g, nome + ': evento chegou', m is not None, '%.1f s' % dt if m else 'nenhum evento'):
            return None
        e, v = m['evento'], m.get('verdade') or {}
        ok = e['nivel'] == nivel and e['trecho'] == trecho and e['posicao_m'] is not None \
            and abs(e['posicao_m'] - s_m) <= erro_max
        self.conferir(g, nome + ': %s no %s, erro <= %.1f m' % (nivel, trecho, erro_max), ok,
                      '%s %s %s m (erro %s m)' % (e['nivel'], e['trecho'], e['posicao_m'], v.get('erro_m'))
                      + ('' if ok else ' | motivo: %s | real: %s' % (e.get('motivo'), v or None)))
        return e

    async def linha_do_cais(self):
        g = 'linha do cais'
        await self.preparar('cais', 'rapido')
        for s_m, tamanho in ((50.0, 'grande'), (320.0, 'grande'), (650.0, 'grande'), (450.0, 'pequeno')):
            m, dt = await self.romper('principal', s_m, tamanho)
            e = self.conferir_vazamento(g, 'vazamento %s em %.0f m' % (tamanho, s_m), m, dt, 'principal', s_m, 1.0)
            if e and s_m == 320.0:
                self.conferir(g, 'evento chega em ate 2 s do comando aceito', dt <= 2.0, '%.1f s' % dt)
                self.conferir(g, 'verdade no perfil demonstracao', (m.get('verdade') or {}).get('s_m') == 320.0)
                self.conferir(g, 'explicacao em portugues', 'vazamento' in e.get('explicacao', ''))
            if e and s_m == 450.0:
                self.conferir(g, 'em 450 m: anotacao "conferir" da XV-106',
                              (e.get('cadastro') or {}).get('decisao') == 'conferir', (e.get('cadastro') or {}).get('decisao'))
            await self.comando('/api/bancada/reparar', {})
            await self.calma(2.0)
        m, dt = await self.romper('principal', -150.0, 'grande')
        e = (m or {}).get('evento') or {}
        self.conferir(g, 'vazamento antes do sensor A: fora do trecho, lado A',
                      e.get('classificacao') == 'fora_do_trecho' and e.get('lado') == 'A' and e.get('posicao_m') is None,
                      '%s lado %s' % (e.get('classificacao'), e.get('lado')))
        await self.comando('/api/bancada/reparar', {})
        await self.calma(2.0)

    async def manobras(self):
        g = 'manobras'
        await self.preparar('cais', 'rapido')

        async def operar(eq, acao, registrar):
            self.limpar_fila()
            await self.comando('/api/bancada/equipamento', {'equipamento': eq, 'acao': acao, 'registrar_operacao': registrar})
            m = await self.evento()
            await self.calma(ASSENTAR_S)
            return (m or {}).get('evento') or {}

        e = await operar('XV-106', 'fechar', True)
        self.conferir(g, 'fechar XV-106 (onda de alta): registro', e.get('nivel') == 'registro', e.get('nivel'))
        e = await operar('XV-106', 'abrir', True)
        self.conferir(g, 'abrir XV-106 com registro de operacao: registro', e.get('nivel') == 'registro',
                      '%s, cadastro %s' % (e.get('nivel'), (e.get('cadastro') or {}).get('decisao')))
        await operar('XV-106', 'fechar', False)
        e = await operar('XV-106', 'abrir', False)
        self.conferir(g, 'abrir XV-106 sem registro: alarma em 450 m (mesma onda de vazamento)',
                      e.get('nivel') == 'provavel' and abs((e.get('posicao_m') or 0) - 450.0) < 2.0,
                      '%s %s m' % (e.get('nivel'), e.get('posicao_m')))
        e = await operar('B-01', 'parar', True)
        # frente lenta da bomba, perto do limiar do detector (ver manobras_nas_outras_linhas): pode nao ser marcada;
        # marcada, sai do lado A (a chegada pelo nivel da bancada corrige o lado quando so o sensor B declara)
        self.conferir(g, 'parar a bomba com registro: registro do lado A, ou nao marcada',
                      e == {} or (e.get('nivel') == 'registro' and e.get('lado') == 'A'),
                      'frente lenta nao marcada' if e == {} else '%s lado %s' % (e.get('nivel'), e.get('lado')))
        await operar('B-01', 'partir', True)
        await self.preparar('cais', 'rapido')

    async def operar(self, eq, acao, registrar):
        self.limpar_fila()
        await self.comando('/api/bancada/equipamento', {'equipamento': eq, 'acao': acao, 'registrar_operacao': registrar})
        m = await self.evento()
        await self.calma(ASSENTAR_S)
        return (m or {}).get('evento') or {}

    async def manobras_nas_outras_linhas(self):
        g = 'manobras no trecho de 200 m'
        await self.preparar('trecho_200', 'rapido')
        e = await self.operar('XV-100', 'fechar', True)
        self.conferir(g, 'fechar XV-100 com registro: registro', e.get('nivel') == 'registro', e.get('nivel'))
        e = await self.operar('XV-100', 'abrir', True)
        self.conferir(g, 'abrir XV-100 com registro: registro', e.get('nivel') == 'registro', e.get('nivel'))
        await self.operar('XV-100', 'fechar', False)
        e = await self.operar('XV-100', 'abrir', False)
        self.conferir(g, 'abrir XV-100 sem registro: alarma em 100 m, "conferir"',
                      e.get('nivel') == 'provavel' and abs((e.get('posicao_m') or 0) - 100.0) < 3.0
                      and (e.get('cadastro') or {}).get('decisao') == 'conferir',
                      '%s %s m' % (e.get('nivel'), e.get('posicao_m')))
        g = 'manobras na rede'
        await self.preparar('rede', 'rapido')
        e = await self.operar('XV-106', 'fechar', True)
        self.conferir(g, 'fechar XV-106 com registro: registro', e.get('nivel') == 'registro', e.get('nivel'))
        e = await self.operar('XV-106', 'abrir', True)
        self.conferir(g, 'abrir XV-106 com registro: registro, equipamento XV-106',
                      e.get('nivel') == 'registro' and (e.get('cadastro') or {}).get('equipamento') == 'XV-106',
                      '%s %s' % (e.get('nivel'), (e.get('cadastro') or {}).get('equipamento')))
        e = await self.operar('B-01', 'parar', True)
        # na rede, a frente lenta da parada da bomba fica perto do limiar do detector no sensor A (razao de
        # energia de 10 a 23, limiar 12): as vezes nao e marcada. O que nao pode e virar alarme.
        self.conferir(g, 'parar a bomba com registro: sem alarme (registro de B-01, ou nao marcada)',
                      e == {} or (e.get('nivel') == 'registro' and (e.get('cadastro') or {}).get('equipamento') == 'B-01'),
                      'frente lenta nao marcada' if e == {} else
                      '%s %s' % (e.get('nivel'), (e.get('cadastro') or {}).get('equipamento')))
        await self.operar('B-01', 'partir', True)
        await self.preparar('cais', 'rapido')

    async def mensagens_por(self, segundos):
        """Todas as mensagens (menos amostras) que chegarem nesse tempo."""
        saida, limite = [], time.monotonic() + segundos
        while time.monotonic() < limite:
            try:
                saida.append(await asyncio.wait_for(self.fila.get(), max(0.05, limite - time.monotonic())))
            except asyncio.TimeoutError:
                break
        return saida

    async def sobrepressao(self):
        g = 'sobrepressao'
        await self.preparar('cais', 'rapido')
        st, s = await self.api('GET', '/api/sobrepressao')
        self.conferir(g, 'GET /api/sobrepressao com o limite da linha', st == 200 and s.get('limite_bar') == 12.0,
                      '%s bar' % s.get('limite_bar'))
        st, prev = await self.api('GET', '/api/sobrepressao/previsao?equipamento=XV-108&acao=fechar')
        self.conferir(g, 'previsao antes de fechar a XV-108: atencao, tempo minimo seguro',
                      st == 200 and prev.get('nivel') == 'atencao' and (prev.get('tempo_minimo_seguro_s') or 0) > 0.3,
                      '%s bar, %s, pelo menos %s s' % (prev.get('pico_previsto_bar'), prev.get('nivel'),
                                                       prev.get('tempo_minimo_seguro_s')))
        self.limpar_fila()
        await self.comando('/api/bancada/equipamento', {'equipamento': 'XV-108', 'acao': 'fechar',
                                                        'registrar_operacao': True})
        sp = [m['evento'] for m in await self.mensagens_por(7.0) if m['tipo'] == 'sobrepressao']
        abre = sp[0] if sp else {}
        faixa = prev.get('faixa_bar') or [0, 0]
        self.conferir(g, 'o pico medido cai na faixa prevista', faixa[0] <= (abre.get('pico_bar') or -1) <= faixa[1],
                      'medido %s, previsto de %s a %s bar' % (abre.get('pico_bar'), faixa[0], faixa[1]))
        self.conferir(g, 'fechar XV-108: atencao, pico de 10 a 11 bar no sensor B, causa XV-108',
                      abre.get('nivel') == 'atencao' and abre.get('sensor_do_pico') == 'B'
                      and 10.0 <= (abre.get('pico_bar') or 0) <= 11.0
                      and (abre.get('causa_provavel') or {}).get('equipamento') == 'XV-108',
                      '%s %s bar em %s' % (abre.get('nivel'), abre.get('pico_bar'), abre.get('sensor_do_pico')))
        self.conferir(g, 'o episodio encerra com o mesmo id', len(sp) >= 2 and sp[-1].get('id') == abre.get('id')
                      and sp[-1].get('em_curso') is False, '%d mensagens' % len(sp))
        st, hist = await self.api('GET', '/api/sobrepressao/eventos?limite=1')
        self.conferir(g, 'historico da sobrepressao', st == 200 and hist and hist[0]['evento'].get('id') == abre.get('id'))
        await self.comando('/api/bancada/equipamento', {'equipamento': 'XV-108', 'acao': 'abrir',
                                                        'registrar_operacao': True})
        # o transitorio da reabertura decai com 2 s de constante (gerador.py): sem essa espera, o resto dele
        # abaixa o pico do fechamento seguinte
        await self.calma(10.0)
        await self.comando('/api/sobrepressao/limite', {'limite_bar': 10.5})
        try:
            self.limpar_fila()
            await self.comando('/api/bancada/equipamento', {'equipamento': 'XV-108', 'acao': 'fechar',
                                                            'registrar_operacao': True})
            sp = [m['evento'] for m in await self.mensagens_por(5.0) if m['tipo'] == 'sobrepressao']
            self.conferir(g, 'com o limite em 10,5 bar, o mesmo fechamento vira alarme',
                          bool(sp) and sp[0].get('nivel') == 'alarme', sp[0].get('nivel') if sp else 'nada')
        finally:
            await self.comando('/api/sobrepressao/limite', {'limite_bar': 12.0})
        await self.preparar('cais', 'rapido')

    async def integracao_e_historico(self):
        g = 'integracao'
        st, s = await self.api('GET', '/api/servico')
        self.conferir(g, 'servico informa o tipo do historico', s.get('historico') in
                      ('postgresql', 'sqlite', 'sqlite em memoria'), s.get('historico'))
        st, i = await self.api('GET', '/api/integracao')
        self.conferir(g, 'GET /api/integracao responde', st == 200 and 'ligado' in i,
                      'ligado' if i.get('ligado') else 'desligado')
        st, t = await self.api('POST', '/api/integracao/teste', {})
        esperado = ('enviado',) if i.get('ligado') else ('desligado',)
        self.conferir(g, 'evento de teste do webhook', st == 200 and t.get('resultado') in esperado,
                      str(t.get('resultado')))

    async def sensores_e_gas(self):
        g = 'autoteste e gas'
        await self.preparar('cais', 'rapido')
        self.limpar_fila()
        await self.comando('/api/bancada/sensor', {'sensor': 'A', 'falha': 'cabo_rompido'})
        await asyncio.sleep(2.5)
        s = (await self.api('GET', '/api/saude'))[1]
        self.conferir(g, 'cabo rompido: sensor A reprovado, monitoramento degradado',
                      s['sensores']['A']['situacao'] == 'reprovado' and s['monitoramento'] == 'degradado',
                      str(s['sensores']['A']['falhas']))
        self.limpar_fila()
        m, dt = await self.romper('principal', 400.0)
        e = (m or {}).get('evento') or {}
        self.conferir(g, 'vazamento com sensor reprovado: suspeita, posicao retida',
                      e.get('nivel') == 'suspeita' and e.get('posicao_m') is None, e.get('nivel'))
        await self.comando('/api/bancada/reparar', {})
        await asyncio.sleep(2.5)
        s = (await self.api('GET', '/api/saude'))[1]
        self.conferir(g, 'depois de reparar: monitoramento normal', s['monitoramento'] == 'normal', s['monitoramento'])
        await self.calma(1.0)
        m, dt = await self.romper('principal', 250.0)
        e = (m or {}).get('evento') or {}
        self.limpar_fila()
        await self.comando('/api/bancada/gas', {'acusando': True})
        r = await self.evento(10)
        r = (r or {}).get('evento') or {}
        self.conferir(g, 'gas: o mesmo evento volta confirmado, revisao 2',
                      r.get('id') == e.get('id') and r.get('nivel') == 'confirmado' and r.get('revisao') == 2,
                      '%s revisao %s' % (r.get('nivel'), r.get('revisao')))
        await self.comando('/api/bancada/gas', {'acusando': False})
        await self.comando('/api/bancada/reparar', {})
        await self.calma(2.0)

    async def transmissor_lento(self):
        g = 'transmissor'
        await self.preparar('cais', 'inteligente_10ms')
        m, dt = await self.romper('principal', 320.0)
        self.conferir_vazamento(g, 'inteligente 10 ms, vazamento em 320 m', m, dt, 'principal', 320.0, 5.0)
        await self.preparar('cais', 'rapido')

    async def rede(self):
        g = 'rede'
        await self.preparar('rede', 'rapido')
        for trecho, s_m, tamanho in (('ramal_106', 180.0, 'grande'), ('ramal_104', 100.0, 'pequeno'),
                                     ('ramal_108', 400.0, 'grande'), ('tronco', 60.0, 'grande')):
            m, dt = await self.romper(trecho, s_m, tamanho)
            e = self.conferir_vazamento(g, '%s %.0f m (%s)' % (trecho, s_m, tamanho), m, dt, trecho, s_m, 1.0)
            if e and trecho == 'ramal_106':
                self.conferir(g, 'evento da rede com os quatro canais', set(e['canais']) == {'A', 'B104', 'B106', 'B108'})
            await self.comando('/api/bancada/reparar', {})
            await self.calma(2.0)

    async def trecho_200(self):
        g = 'trecho de 200 m'
        await self.preparar('trecho_200', 'rapido')
        m, dt = await self.romper('principal', 100.0)
        self.conferir_vazamento(g, 'vazamento em 100 m', m, dt, 'principal', 100.0, 0.5)
        await self.comando('/api/bancada/reparar', {})
        await self.calma(2.0)

    async def historico(self):
        g = 'historico'
        st, l = await self.api('GET', '/api/eventos?perfil=demonstracao&limite=5')
        self.conferir(g, 'historico com eventos', st == 200 and len(l) > 0, '%d itens' % len(l or []))
        if l:
            self.conferir(g, 'perfil demonstracao traz a verdade', 'verdade' in l[0])
            ident = l[0]['evento']['id']
            st, op = await self.api('GET', '/api/eventos/%s' % ident)
            self.conferir(g, 'perfil operador (padrao) sem a verdade', st == 200 and 'verdade' not in op)
            st, s = await self.api('GET', '/api/eventos/%s/sinal' % ident)
            n = len(next(iter(s.get('pressao_bar', {}).values()), []))
            self.conferir(g, 'sinal em alta resolucao (2.500 por segundo)',
                          st == 200 and abs(s.get('periodo_s', 0) - 0.0004) < 1e-9 and n > 1000,
                          '%d amostras por sensor' % n)
        st, _ = await self.api('GET', '/api/eventos/nao-existe')
        self.conferir(g, 'evento inexistente da 404', st == 404, 'HTTP %s' % st)

    async def sem_falso_alarme(self):
        g = 'falso alarme'
        for linha in ('cais', 'rede'):
            await self.preparar(linha, 'rapido')
            m = await self.evento(20.0)
            self.conferir(g, '%s em regime, 20 s sem evento' % linha, m is None,
                          'evento indevido: %s, %s' % (m['evento']['nivel'], m['evento'].get('motivo')) if m else '')
        s = (await self.api('GET', '/api/servico'))[1]
        print('  (deteccoes de ruido descartadas desde o inicio do servico: %s)'
              % s.get('deteccoes_descartadas_como_ruido'), flush=True)

    # --- tudo ---------------------------------------------------------------------------------
    async def rodar(self, forcar, so=None):
        print('servico:', self.endereco, flush=True)
        st, s = await self.api('GET', '/api/servico')          # acorda o servico no plano gratuito
        if st != 200:
            self.conferir('consultas', 'servico no ar', False, 'HTTP %s' % st)
            return
        if s.get('clientes_conectados') and not forcar:
            print('ha %d cliente(s) conectado(s): a conferencia mexe na bancada que eles estao vendo. '
                  'Use --forcar para rodar assim mesmo.' % s['clientes_conectados'])
            sys.exit(2)
        self.fila = asyncio.Queue()
        url = self.endereco.replace('https://', 'wss://').replace('http://', 'ws://') + '/ws?perfil=demonstracao'
        async with websockets.connect(url, max_size=None) as ws:
            self.ws = ws
            escuta = asyncio.create_task(self.escutar())
            try:
                await self.comando('/api/bancada/roteiro', {'roteiro': None})
                grupos = (self.consultas, self.seguranca_e_validacao, self.websocket, self.linha_do_cais,
                          self.manobras, self.manobras_nas_outras_linhas, self.sensores_e_gas,
                          self.transmissor_lento, self.rede, self.trecho_200, self.historico,
                          self.integracao_e_historico, self.sobrepressao, self.sem_falso_alarme)
                for grupo in grupos:
                    if so and grupo.__name__ not in so:
                        continue
                    print('\n%s' % grupo.__name__.replace('_', ' '), flush=True)
                    try:
                        await grupo()
                    except Exception as e:                          # um grupo quebrado nao derruba os outros
                        self.conferir(grupo.__name__, 'grupo executado sem erro', False, '%s: %s' % (type(e).__name__, e))
            finally:
                print('\ndevolvendo a bancada ao estado inicial', flush=True)
                try:
                    await self.preparar('cais', 'rapido')
                except Exception as e:
                    print('  nao consegui devolver:', e)
                escuta.cancel()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--endereco', default='http://127.0.0.1:8000')
    ap.add_argument('--chave', default=os.environ.get('LEAKMAP_CHAVE'))
    ap.add_argument('--espera', type=float, default=8.0, help='segundos esperando cada evento')
    ap.add_argument('--forcar', action='store_true', help='roda mesmo com clientes conectados')
    ap.add_argument('--relatorio', help='grava o resultado em JSON')
    ap.add_argument('--grupos', help='roda so estes grupos, separados por virgula (ex.: manobras,sobrepressao)')
    args = ap.parse_args()
    c = Conferencia(args.endereco, args.chave, args.espera)
    inicio = time.monotonic()
    asyncio.run(c.rodar(args.forcar, args.grupos.split(',') if args.grupos else None))
    falhas = [r for r in c.resultados if not r['ok']]
    print('\n%d de %d conferencias ok em %.0f s' % (len(c.resultados) - len(falhas), len(c.resultados),
                                                    time.monotonic() - inicio))
    for r in falhas:
        print('  FALHOU: [%s] %s  %s' % (r['grupo'], r['teste'], r['detalhe']))
    if args.relatorio:
        with open(args.relatorio, 'w', encoding='utf-8') as f:
            json.dump({'endereco': args.endereco,
                       'quando_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'total': len(c.resultados), 'falhas': len(falhas), 'resultados': c.resultados},
                      f, ensure_ascii=False, indent=1)
        print('relatorio:', args.relatorio)
    sys.exit(1 if falhas or not c.resultados else 0)


if __name__ == '__main__':
    main()

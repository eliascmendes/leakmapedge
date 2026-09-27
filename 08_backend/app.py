"""LEAKMAP - backend da bancada virtual: REST e WebSocket.

Rodar localmente (a partir da raiz do repositorio):
    uvicorn --app-dir 08_backend app:app --port 8000
Documentacao viva em http://localhost:8000/docs

Variaveis de ambiente:
    LEAKMAP_CHAVE     chave exigida nos comandos (cabecalho X-LEAKMAP-Chave). Sem ela,
                      os comandos ficam abertos: so para desenvolvimento local
    LEAKMAP_ORIGENS   enderecos do front liberados no CORS, separados por virgula (padrao: *)
    LEAKMAP_BANCO     historico: endereco postgresql://... (sobrevive a reinicios) ou arquivo SQLite;
                      sem ela, vale DATABASE_URL; sem as duas, SQLite em memoria
    LEAKMAP_LINHA     linha ativa ao iniciar (padrao: cais)
    LEAKMAP_WEBHOOK_URL e afins: repasse dos eventos por webhook (repasse.py)
"""
import asyncio
import contextlib
import os
import time
from typing import Literal, Optional

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

import bancada as BA
import historico as HI
import repasse as RE

VERSAO_DO_CONTRATO = '1'
AQUI = os.path.dirname(os.path.abspath(__file__))
CHAVE = os.environ.get('LEAKMAP_CHAVE') or None
ORIGENS = [o.strip() for o in os.environ.get('LEAKMAP_ORIGENS', '*').split(',') if o.strip()]
TAXA_PADRAO, TAXA_MIN, TAXA_MAX = 30, 10, 100
PULSO_S = 15.0


class Estado:
    bancada: BA.Bancada = None
    repasse: RE.Repasse = None
    clientes: set = set()
    atrasos = 0


E = Estado()


class Cliente:
    def __init__(self, ws, perfil, taxa):
        self.ws, self.perfil, self.taxa = ws, perfil, taxa
        self.fila = asyncio.Queue(maxsize=300)
        self.proximo_t = None

    def por(self, mensagem):
        if self.fila.full():                    # cliente lento: descarta a mensagem mais antiga
            with contextlib.suppress(asyncio.QueueEmpty):
                self.fila.get_nowait()
        self.fila.put_nowait(mensagem)

    def amostras(self, t, pressao):
        """Os pontos deste passo na taxa pedida pelo cliente."""
        periodo = 1.0 / self.taxa
        if self.proximo_t is None or self.proximo_t < t[0] - 1.0:
            self.proximo_t = float(t[0])
        pontos = np.arange(self.proximo_t, t[-1] + 1e-9, periodo)
        if not len(pontos):
            return None
        self.proximo_t = float(pontos[-1] + periodo)
        return {'tipo': 'amostras', 'modo': 'simulacao', 'linha': E.bancada.linha.id, 't_s': round(float(pontos[0]), 4),
                'periodo_s': periodo,
                'pressao_bar': {s: [round(float(v), 4) for v in np.interp(pontos, t, x)] for s, x in pressao.items()}}


def para_o_perfil(mensagem, perfil):
    if perfil == 'demonstracao':
        return mensagem
    m = dict(mensagem)
    m.pop('verdade', None)
    if 'estado' in m and isinstance(m['estado'], dict):
        m['estado'] = {k: v for k, v in m['estado'].items() if k != 'vazamentos_abertos'}
    return m


def difundir(mensagem):
    if mensagem.get('tipo') in ('evento', 'sobrepressao') and E.repasse is not None:
        E.repasse.por(mensagem['evento'])       # o webhook recebe so o evento, nunca a verdade
    for c in list(E.clientes):
        c.por(para_o_perfil(mensagem, c.perfil))


def difundir_estado():
    difundir({'tipo': 'estado', 'estado': E.bancada.estado('demonstracao')})


async def ciclo():
    """Avanca a bancada a cada 0,1 s de relogio e difunde o que ela produziu."""
    proximo = time.monotonic()
    passo_s = BA.AMOSTRAS_POR_PASSO * BA.TS
    while True:
        proximo += passo_s
        t, pressao, mensagens = E.bancada.passo()
        for c in list(E.clientes):
            m = c.amostras(t, pressao)
            if m:
                c.por(m)
        for m in mensagens:
            difundir(m)
        espera = proximo - time.monotonic()
        if espera < -1.0:                       # ficou para tras (processo parado): retoma do agora
            E.atrasos += 1
            proximo = time.monotonic()
        await asyncio.sleep(max(0.0, espera))


async def pulso():
    while True:
        await asyncio.sleep(PULSO_S)
        difundir({'tipo': 'pulso', 't_s': round(E.bancada.t, 3)})


@contextlib.asynccontextmanager
async def ciclo_de_vida(app):
    E.repasse = RE.Repasse()
    E.bancada = BA.Bancada(linha=os.environ.get('LEAKMAP_LINHA', 'cais'),
                           historico=HI.Historico(os.environ.get('LEAKMAP_BANCO') or os.environ.get('DATABASE_URL')
                                                  or ':memory:'))
    tarefas = [asyncio.create_task(ciclo()), asyncio.create_task(pulso())]
    yield
    for t in tarefas:
        t.cancel()
    E.bancada.historico.fechar()


app = FastAPI(title='LEAKMAP Edge · bancada virtual', version=VERSAO_DO_CONTRATO, lifespan=ciclo_de_vida,
              description=('Backend da bancada virtual do LEAKMAP Edge: a linha, os sensores e o detector ao vivo. '
                           'Tudo o que sai daqui e simulacao e vem marcado com "modo": "simulacao". '
                           'Guia do contrato: 08_backend/LEIAME.md.'))
app.add_middleware(CORSMiddleware, allow_origins=ORIGENS, allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(HTTPException)
async def _erro_http(request, exc):
    corpo = exc.detail if isinstance(exc.detail, dict) else {'erro': str(exc.detail)}
    return JSONResponse(corpo, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _erro_de_validacao(request, exc):
    """Pedido com campo faltando ou valor fora das opcoes: o mesmo formato {"erro": ...} do contrato."""
    partes = []
    for e in exc.errors():
        campo = '.'.join(str(x) for x in e.get('loc', ()) if x != 'body')
        esperado = (e.get('ctx') or {}).get('expected')
        partes.append('%s: %s' % (campo or 'corpo', 'use %s' % esperado if esperado else e.get('msg')))
    return JSONResponse({'erro': 'pedido invalido: ' + '; '.join(partes), 'detalhes': jsonable_encoder(exc.errors())},
                        status_code=422)


@app.exception_handler(BA.ErroDaBancada)
async def _erro_da_bancada(request, exc):
    return JSONResponse(dict({'erro': exc.texto}, **exc.extra), status_code=exc.codigo)


def exigir_chave(x_leakmap_chave: Optional[str] = Header(default=None)):
    if CHAVE and x_leakmap_chave != CHAVE:
        raise HTTPException(401, 'chave ausente ou errada: envie o cabecalho X-LEAKMAP-Chave')


COMANDO = [Depends(exigir_chave)]


# --- consultas ---------------------------------------------------------------------------

@app.get('/', include_in_schema=False)
async def raiz():
    return RedirectResponse('/docs')


@app.get('/teste', include_in_schema=False)
async def pagina_de_teste():
    return FileResponse(os.path.join(AQUI, 'pagina_teste.html'))


@app.get('/api/servico', tags=['consultas'], summary='Situacao do servico (serve tambem para acorda-lo)')
async def servico():
    return {'situacao': 'ok', 'versao_do_contrato': VERSAO_DO_CONTRATO, 'modo': 'simulacao',
            'comandos_exigem_chave': bool(CHAVE), 't_s': round(E.bancada.t, 3), 'clientes_conectados': len(E.clientes),
            'passos_atrasados': E.atrasos, 'deteccoes_descartadas_como_ruido': E.bancada.descartadas_como_ruido,
            'webhook_ligado': E.repasse.ligado, 'historico': E.bancada.historico.tipo}


@app.get('/api/integracao', tags=['integracao'], summary='Situacao do repasse dos eventos por webhook')
async def integracao():
    return E.repasse.situacao()


@app.get('/api/linhas', tags=['consultas'], summary='As linhas da bancada, com trechos, sensores e equipamentos')
async def linhas():
    b = E.bancada
    return {'linha_ativa': b.linha.id,
            'linhas': [l.descricao(b.equipamentos if l.id == b.linha.id else None, b.limites[l.id])
                       for l in b.linhas.values()]}


@app.get('/api/linhas/{ident}', tags=['consultas'], summary='Uma linha')
async def linha(ident: str):
    b = E.bancada
    if ident not in b.linhas:
        raise HTTPException(404, 'linha desconhecida: %s' % ident)
    return b.linhas[ident].descricao(b.equipamentos if ident == b.linha.id else None, b.limites[ident])


@app.get('/api/transmissores', tags=['consultas'], summary='Os tipos de transmissor da bancada')
async def transmissores():
    return [{'id': k, 'descricao': v} for k, v in BA.TRANSMISSORES.items()]


@app.get('/api/estado', tags=['consultas'], summary='Estado atual da bancada')
async def estado(perfil: Literal['demonstracao', 'operador'] = 'demonstracao'):
    return E.bancada.estado(perfil)


@app.get('/api/saude', tags=['consultas'], summary='Autoteste de cada sensor')
async def saude():
    return E.bancada.mensagem_de_saude()


@app.get('/api/eventos', tags=['consultas'], summary='Historico de eventos, do mais novo para o mais antigo')
async def eventos(desde: Optional[str] = None, nivel: Optional[str] = None, linha: Optional[str] = None,
            limite: int = Query(50, ge=1, le=500), perfil: Literal['demonstracao', 'operador'] = 'operador'):
    return [para_o_perfil(e, perfil) for e in E.bancada.historico.listar(desde, nivel, linha, limite)]


@app.get('/api/eventos/{ident}', tags=['consultas'], summary='Um evento')
async def evento(ident: str, perfil: Literal['demonstracao', 'operador'] = 'operador'):
    e = E.bancada.historico.obter(ident)
    if e is None:
        raise HTTPException(404, 'evento desconhecido: %s' % ident)
    return para_o_perfil(e, perfil)


@app.get('/api/eventos/{ident}/sinal', tags=['consultas'],
         summary='Sinal em alta resolucao em volta do evento (2.500 amostras por segundo)')
async def sinal(ident: str):
    s = E.bancada.historico.sinal(ident)
    if s is None:
        raise HTTPException(404, 'evento desconhecido: %s' % ident)
    return s


@app.get('/api/sobrepressao', tags=['sobrepressao'],
         summary='Alerta de sobrepressao: limite da linha, estado atual e o ultimo episodio')
async def sobrepressao():
    return E.bancada.situacao_da_sobrepressao()


@app.get('/api/sobrepressao/eventos', tags=['sobrepressao'],
         summary='Historico dos episodios de sobrepressao, do mais novo para o mais antigo')
async def sobrepressao_eventos(desde: Optional[str] = None, nivel: Optional[str] = None, linha: Optional[str] = None,
                               limite: int = Query(50, ge=1, le=500),
                               perfil: Literal['demonstracao', 'operador'] = 'operador'):
    return [para_o_perfil(e, perfil) for e in E.bancada.historico.listar(desde, nivel, linha, limite,
                                                                          tabela='sobrepressoes')]


@app.get('/api/cadastro', tags=['consultas'], summary='Valvulas e bombas da linha ativa')
async def cadastro():
    b = E.bancada
    return {'linha': b.linha.id,
            'equipamentos': [dict(e, estado=b.equipamentos.get(e['id'])) for e in b.linha.equipamentos],
            'operacoes_registradas': [dict(o, instante_utc=b.utc(o['instante_s'])) for o in b.operacoes[-50:]]}


# --- comandos da bancada -------------------------------------------------------------------

class PedidoLinha(BaseModel):
    linha: Literal['trecho_200', 'cais', 'rede']


class PedidoTransmissor(BaseModel):
    transmissor: Literal['ideal', 'rapido', 'inteligente_1ms', 'inteligente_10ms', 'inteligente_50ms',
                         'inteligente_100ms']


class PedidoVazamento(BaseModel):
    trecho: str = Field('principal', examples=['principal'])
    s_m: float = Field(..., examples=[320.0])
    tamanho: Literal['grande', 'pequeno'] = 'grande'
    fonte: Literal['gerador', 'tsnet'] = 'gerador'


class PedidoEquipamento(BaseModel):
    equipamento: str = Field(..., examples=['XV-106'])
    acao: Literal['abrir', 'fechar', 'partir', 'parar']
    registrar_operacao: bool = True


class PedidoSensor(BaseModel):
    sensor: str = Field(..., examples=['A'])
    falha: Literal['cabo_rompido', 'travado', 'nenhuma']


class PedidoGas(BaseModel):
    acusando: bool


class PedidoRoteiro(BaseModel):
    roteiro: Optional[Literal['demonstracao']] = 'demonstracao'
    intervalo_s: float = Field(60.0, ge=10.0)


class PedidoOperacao(BaseModel):
    equipamento: str = Field(..., examples=['XV-106'])
    acao: Literal['abertura', 'fechamento', 'partida', 'parada']
    instante_utc: Optional[str] = Field(None, examples=['2026-09-26T14:03:10.900Z'])
    origem: str = 'sistema de controle'


def _depois(resposta=None):
    difundir_estado()
    return {'ok': True, 'resultado': resposta, 'estado': E.bancada.estado('demonstracao')}


@app.post('/api/bancada/linha', tags=['bancada'], dependencies=COMANDO, summary='Troca a linha ativa')
async def trocar_linha(p: PedidoLinha):
    E.bancada.trocar_linha(p.linha)
    for c in list(E.clientes):
        c.por(para_o_perfil(boas_vindas(c.perfil), c.perfil))
    return _depois()


@app.post('/api/bancada/transmissor', tags=['bancada'], dependencies=COMANDO, summary='Troca o transmissor')
async def trocar_transmissor(p: PedidoTransmissor):
    E.bancada.trocar_transmissor(p.transmissor)
    return _depois()


@app.post('/api/bancada/vazamento', tags=['bancada'], dependencies=COMANDO, summary='Abre um vazamento')
async def vazamento(p: PedidoVazamento):
    return _depois(E.bancada.vazamento(p.trecho, p.s_m, p.tamanho, p.fonte))


@app.post('/api/bancada/equipamento', tags=['bancada'], dependencies=COMANDO,
          summary='Opera uma valvula ou a bomba (manobra)')
async def equipamento(p: PedidoEquipamento):
    return _depois(E.bancada.equipamento(p.equipamento, p.acao, p.registrar_operacao))


@app.post('/api/bancada/sensor', tags=['bancada'], dependencies=COMANDO, summary='Estraga ou conserta um sensor')
async def sensor(p: PedidoSensor):
    return _depois(E.bancada.sensor(p.sensor, p.falha))


@app.post('/api/bancada/gas', tags=['bancada'], dependencies=COMANDO, summary='Sensor de gas (simulado)')
async def gas(p: PedidoGas):
    for m in E.bancada.definir_gas(p.acusando):
        difundir(m)
    return _depois()


@app.post('/api/bancada/reparar', tags=['bancada'], dependencies=COMANDO,
          summary='Fecha os vazamentos, conserta os sensores e desliga o gas')
async def reparar():
    E.bancada.reparar()
    return _depois()


@app.post('/api/bancada/roteiro', tags=['bancada'], dependencies=COMANDO,
          summary='Liga ou desliga a sequencia automatica de cenarios')
async def roteiro(p: PedidoRoteiro):
    E.bancada.definir_roteiro(p.roteiro, p.intervalo_s)
    return _depois()


class PedidoLimite(BaseModel):
    limite_bar: float = Field(..., examples=[12.0])
    linha: Optional[Literal['trecho_200', 'cais', 'rede']] = None


@app.post('/api/sobrepressao/limite', tags=['sobrepressao'], dependencies=COMANDO,
          summary='Muda o limite de pressao de uma linha (premissa ate chegar o dado da planta)')
async def sobrepressao_limite(p: PedidoLimite):
    return _depois(E.bancada.definir_limite(p.limite_bar, p.linha))


@app.post('/api/integracao/teste', tags=['integracao'], dependencies=COMANDO,
          summary='Manda agora um evento de teste pelo webhook (marcado "teste": true)')
async def integracao_teste():
    b = E.bancada
    evento = {'tipo': 'leakmap.evento', 'versao': '1', 'id': 'teste-%d' % int(time.time()), 'teste': True,
              'instante_utc': b.utc(b.t), 'linha': b.linha.id, 'modo': 'simulacao', 'nivel': 'provavel',
              'classificacao': 'vazamento', 'trecho': None, 'posicao_m': None,
              'explicacao': 'Evento de teste do webhook do LEAKMAP: nao e um alerta.'}
    resultado = await asyncio.to_thread(E.repasse.testar, evento)
    return {'ok': resultado == 'enviado', 'resultado': resultado, 'integracao': E.repasse.situacao()}


@app.post('/api/operacoes', tags=['integracao'], dependencies=COMANDO,
          summary='Registro de operacao de valvula ou bomba, como o sistema de controle informaria')
async def operacoes(p: PedidoOperacao):
    return _depois(E.bancada.registrar_operacao(p.equipamento, p.acao, p.instante_utc, p.origem))


# --- WebSocket ---------------------------------------------------------------------------------

def boas_vindas(perfil):
    b = E.bancada
    return {'tipo': 'boas_vindas', 'versao_do_contrato': VERSAO_DO_CONTRATO, 'perfil': perfil,
            'estado': b.estado(perfil), 'linha': b.linha.descricao(b.equipamentos, b.limites[b.linha.id]),
            'saude': b.mensagem_de_saude()}


@app.websocket('/ws')
async def ws(websocket: WebSocket, perfil: str = 'operador', taxa: int = TAXA_PADRAO):
    await websocket.accept()
    perfil = perfil if perfil in ('demonstracao', 'operador') else 'operador'
    cliente = Cliente(websocket, perfil, min(max(int(taxa), TAXA_MIN), TAXA_MAX))
    cliente.por(boas_vindas(perfil))
    E.clientes.add(cliente)

    async def enviar():
        while True:
            await websocket.send_json(await cliente.fila.get())

    envio = asyncio.create_task(enviar())
    try:
        while True:                               # o cliente nao precisa mandar nada; so detecta a saida
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        E.clientes.discard(cliente)
        envio.cancel()

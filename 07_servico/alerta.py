"""LEAKMAP - escala de alerta e evento padronizado.

Transforma o registro do detector (A-15), o autoteste dos canais e a
confirmacao por gas num unico EVENTO, no formato que sai para qualquer
integracao (webhook, sistema de controle, painel). O formato esta descrito em
07_servico/LEIAME.md e e versionado: campos novos podem entrar, os existentes
nao mudam de sentido.

Escala (secao 5.4 do projeto):

  suspeita    evento em um canal so, ou origem fora do trecho entre os
              sensores: registra e observa, nao alarma
  provavel    queda de pressao nos dois canais, com posicao fisicamente
              possivel dentro do trecho: alerta com a posicao
  confirmado  provavel e, alem disso, o sensor de gas acusou vapor na regiao
              indicada: alarme grave

  Uma manobra reconhecida (onda de alta, ou alta de um lado e queda do outro)
  gera evento de nivel `registro`: fica no historico, nunca alarma.

Monitoramento: `degradado` quando o autoteste acusa algum canal, com o
motivo; o evento sai assim mesmo, marcado, para o operador saber quando
confiar.
"""
import datetime
import uuid

VERSAO = '1'
NIVEIS = ('registro', 'suspeita', 'provavel', 'confirmado')

# classes que o detector devolve (04_detector/detector.py)
CLASSE_LOCALIZADO = 'localizado'
CLASSE_SEM_LOCALIZACAO = 'detectado_sem_localizacao'
CLASSE_SEM_DETECCAO = 'sem_deteccao'
CLASSE_FALHA = 'falha_execucao'
CLASSE_MANOBRA = 'manobra'
CLASSE_FORA_DO_TRECHO = 'fora_do_trecho'


def nivel_do_evento(registro, gas_na_regiao=False):
    """Nivel da escala para um registro do detector; None quando nao ha evento."""
    classe = registro.get('classe')
    if classe in (CLASSE_SEM_DETECCAO, CLASSE_FALHA, None):
        return None
    if classe == CLASSE_MANOBRA:
        return 'registro'
    if classe in (CLASSE_SEM_LOCALIZACAO, CLASSE_FORA_DO_TRECHO):
        return 'suspeita'
    if classe == CLASSE_LOCALIZADO:
        return 'confirmado' if gas_na_regiao else 'provavel'
    return 'suspeita'


def estado_do_monitoramento(saude):
    """`saude`: {'canal_A': {'falhas': [...]}, 'canal_B': {...}} do autoteste, ou None."""
    if not saude:
        return {'monitoramento': 'sem_autoteste', 'motivos': []}
    motivos = ['canal %s: %s' % (canal[-1], ', '.join(saude[canal]['falhas']))
               for canal in ('canal_A', 'canal_B') if saude.get(canal, {}).get('falhas')]
    return {'monitoramento': 'degradado' if motivos else 'normal', 'motivos': motivos}


def _canal(registro, canal):
    d = registro.get(canal) or {}
    return {'detectou': bool(d.get('detectado')),
            'polaridade': d.get('polaridade'),
            'instante_de_chegada_s': d.get('tempo_de_chegada_s')}


def montar_evento(registro, linha, sensores, origem_do_processamento, saude=None, gas_na_regiao=None,
                  agora=None):
    """Evento padronizado a partir de um registro do detector.

    `linha`: nome da linha (ex. 'L-01'). `sensores`: {'A': {'nome', 'posicao_m'}, 'B': {...}}.
    `origem_do_processamento`: 'fpga', 'simulacao_do_verilog', 'notebook' ou 'software'.
    Devolve None quando o registro nao tem evento (nada a informar).
    """
    nivel = nivel_do_evento(registro, bool(gas_na_regiao))
    if nivel is None:
        return None
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    classe = registro.get('classe')
    tipo = {CLASSE_MANOBRA: 'manobra', CLASSE_FORA_DO_TRECHO: 'fora_do_trecho',
            CLASSE_SEM_LOCALIZACAO: 'evento_sem_localizacao'}.get(classe, 'vazamento')
    return {
        'tipo': 'leakmap.evento',
        'versao': VERSAO,
        'id': str(uuid.uuid4()),
        'instante_utc': agora.isoformat(),
        'linha': linha,
        'sensores': sensores,
        'nivel': nivel,
        'classificacao': tipo,
        'posicao_m': registro.get('posicao_estimada_m') if classe == CLASSE_LOCALIZADO else None,
        'incerteza_m': registro.get('incerteza_de_posicao_m') if classe == CLASSE_LOCALIZADO else None,
        'lado': registro.get('lado_da_origem'),
        'motivo': registro.get('motivo'),
        'canais': {'A': _canal(registro, 'canal_A'), 'B': _canal(registro, 'canal_B')},
        'confirmacao_por_gas': gas_na_regiao,
        'saude': estado_do_monitoramento(saude),
        'origem_do_processamento': origem_do_processamento,
        'id_do_ensaio': registro.get('id'),
    }

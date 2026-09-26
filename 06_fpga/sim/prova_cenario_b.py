"""LEAKMAP - prova do cenario B no simulador, antes de ter placa.

Le a resposta que o proprio Verilog devolveu em cada caso (gravada por
tb_nucleo.v em 06_fpga/vetores/*.verilog.txt), decodifica os quadros e
confere os criterios do cenario B sem passar pelo modelo Python da placa:

  B-09  indice de cruzamento e de chegada do Verilog igual ao da referencia
        em ponto fixo (04_detector/detector_ponto_fixo.py), nos 45 ensaios da
        matriz e nos sinais sinteticos de retrocesso;
  B-08  canal B igual ao A atrasado 40 amostras: o Verilog tem de devolver
        exatamente 40 amostras de diferenca, e reproduzir todas as amostras
        com um indice so para os dois canais;
  B-07  configuracao lida de volta igual a enviada, e o mesmo ensaio rodado
        duas vezes na mesma placa com resultado identico byte a byte;
  B-06  bloco corrompido no enlace recusado pelo CRC, reenviado e aceito,
        com o resultado igual ao do ensaio sem corrupcao; bloco fora de
        sequencia recusado e execucao recusada.
  Tempos os ciclos que o proprio circuito conta (mensagem TEMPOS) conferidos
        contra a contagem do simulador; em tempo real, a amostra k entregue
        exatamente k periodos depois da primeira, a declaracao dentro do
        periodo da amostra do cruzamento, nenhuma amostra atrasada, e o
        resultado identico ao da execucao em lote.
  Autoteste o autoteste que o circuito faz em cada canal (mensagem SAUDE):
        as estatisticas do Verilog iguais as contadas aqui, direto nas
        amostras enviadas, nos 90 canais da matriz, todos saudaveis com os
        limites do transmissor; e cada canal doente de proposito acusado com
        a falha certa, e so ela.

Depois liga o computador do cenario B (hospedeiro, registro, comparacao com o
cenario A e avaliador independente) a essas respostas gravadas, com a origem
`simulacao_do_verilog`, e grava os arquivos do cenario B com `simulacao` no
nome. Nada disso e resultado de FPGA: e o Verilog que vai para a placa,
rodando no simulador, ciclo a ciclo.

Grava 06_fpga/resultados/leakmap_cenario_b_prova_simulacao_v1.json.
Sai com codigo diferente de zero se algum criterio falhar.
Roda depois de rodar_simulacao.py, que e quem chama este script.
"""
import json
import os
import statistics
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
FPGA = os.path.dirname(AQUI)
RAIZ = os.path.dirname(FPGA)
sys.path.insert(0, os.path.join(FPGA, 'computador'))
sys.path.insert(0, os.path.join(RAIZ, '04_detector'))

import detector as D  # noqa: E402
import detector_ponto_fixo as PF  # noqa: E402
import executar_cenario_b as EX  # noqa: E402
import protocolo as PR  # noqa: E402
import selo as SE  # noqa: E402
import transporte as TR  # noqa: E402

sys.path.insert(0, AQUI)
import rodar_simulacao as RS  # noqa: E402

VETORES = os.path.join(FPGA, 'vetores')
SAIDA = os.path.join(FPGA, 'resultados', 'leakmap_cenario_b_prova_simulacao_v1.json')
PONTO_FIXO = os.path.join(RAIZ, '04_detector', 'resultados', 'leakmap_ponto_fixo_v1.json')
RELOGIO_HZ = 100_000_000
ATRASO = 40
# sinais sinteticos de gerar_vetores.py: degrau de 1 mm e a resolucao do cabecalho
DEGRAU_SINTETICO_M = 1e-3


# --- leitura dos arquivos do simulador ------------------------------------------------

def ler_hex(caminho):
    with open(caminho) as f:
        return bytes(int(l, 16) for l in f if l.strip())


def ler_verilog(caminho):
    """Linhas `byte posicao ciclo ultima_entrada` gravadas pelo testbench."""
    linhas = []
    with open(caminho) as f:
        for l in f:
            if l.strip():
                b, pos, ciclo, ultima = l.split()
                linhas.append((int(b, 16), int(pos), int(ciclo), int(ultima)))
    return linhas


def quadros(dados):
    """Quadros validos na ordem, com o deslocamento do primeiro byte de cada um."""
    saida, i = [], 0
    while i < len(dados):
        if dados[i:i + 2] != PR.SINCRONISMO or len(dados) < i + 5:
            i += 1
            continue
        tamanho = int.from_bytes(dados[i + 3:i + 5], 'little')
        total = 7 + tamanho
        eventos = PR.LeitorDeQuadros().alimentar(dados[i:i + total])
        if len(eventos) == 1 and eventos[0][0] == 'ok':
            saida.append((i, eventos[0][1], eventos[0][2]))
            i += total
        else:
            i += 1
    return saida


class Caso:
    def __init__(self, nome, info):
        self.nome = nome
        self.info = info
        self.entrada = ler_hex(os.path.join(VETORES, nome + '.entrada.hex'))
        self.esperado = ler_hex(os.path.join(VETORES, nome + '.saida.hex'))
        arquivo_mascara = os.path.join(VETORES, nome + '.mascara.hex')
        self.mascara = (ler_hex(arquivo_mascara) if os.path.exists(arquivo_mascara)
                        else bytes([1]) * len(self.esperado))
        self.linhas = ler_verilog(os.path.join(VETORES, nome + '.verilog.txt'))
        self.obtido = bytes(l[0] for l in self.linhas)
        self.recebidos = quadros(self.entrada)
        self.devolvidos = quadros(self.obtido)

    def do_tipo(self, tipo, lado='devolvidos'):
        return [(i, c) for i, t, c in getattr(self, lado) if t == tipo]

    def igual_ao_modelo(self):
        """Byte a byte, fora a parte de TEMPOS que so o circuito mede."""
        return len(self.obtido) == len(self.esperado) and all(
            m == 0 or a == b for a, b, m in zip(self.obtido, self.esperado, self.mascara))

    def tempos(self):
        return [(i, PR.ler_tempos(c)) for i, c in self.do_tipo(PR.TEMPOS)]

    def saudes(self):
        return [(i, PR.ler_saude(c)) for i, c in self.do_tipo(PR.SAUDE)]

    def resultados(self):
        return [(i, PR.ler_resultado(c), c) for i, c in self.do_tipo(PR.RESULTADO)]

    def latencia(self, deslocamento):
        """Ciclos entre o ultimo byte do EXECUTAR consumido e o primeiro byte do RESULTADO."""
        _, _, ciclo, ultima = self.linhas[deslocamento]
        return ciclo - ultima

    def codigos(self):
        """Amostras que o computador enviou, montadas de volta a partir dos blocos aceitos."""
        a, b = {}, {}
        for _, carga in self.do_tipo(PR.AMOSTRAS, 'recebidos'):
            _, _, inicio, pares = PR.ler_amostras(carga)
            for k, (va, vb) in enumerate(pares):
                a[inicio + k], b[inicio + k] = va, vb
        return [a[k] for k in sorted(a)], [b[k] for k in sorted(b)]


# --- referencia em ponto fixo ------------------------------------------------------------

def canal_do_verilog(canal):
    detectado = canal['detectado']
    return {
        'detectado': detectado,
        'indice_de_cruzamento': canal['indice_de_cruzamento'] if detectado else None,
        'indice_de_chegada': canal['indice_de_chegada'] if detectado else None,
        'retrocesso_truncado': canal['retrocesso_truncado'],
        'n_oportunidades_de_decisao': canal['n_oportunidades_de_decisao'],
    }


def canal_do_ponto_fixo(sinal_m, ts, degrau_m, cal, resolucao_m):
    det, _, _, _ = PF.detectar_canal_inteiro(sinal_m, ts, degrau_m, cal, resolucao_m)
    return {
        'detectado': det['detectado'],
        'indice_de_cruzamento': det['indice_de_cruzamento'],
        'indice_de_chegada': det.get('indice_de_chegada'),
        'retrocesso_truncado': bool(det.get('retrocesso_truncado', False)),
        'n_oportunidades_de_decisao': det['n_oportunidades_de_decisao'],
    }


def comparar_canais(verilog, ponto_fixo):
    return [c for c in verilog if verilog[c] != ponto_fixo[c]]


# --- criterios ------------------------------------------------------------------------------

def criterio_b09(casos, pacote, cal, ts):
    arquivo_pf = {(c['id'], c['canal']): c for c in json.load(open(PONTO_FIXO, encoding='utf-8'))['comparacoes']}
    linhas, latencias = [], []
    for ensaio in pacote['ensaios']:
        caso = casos['ensaio_%s' % ensaio['id']]
        (deslocamento, res, _), = caso.resultados()
        latencias.append(caso.latencia(deslocamento))
        resolucao = (ensaio.get('efeitos_de_sensor_aplicados') or {}).get('resolucao_declarada_m')
        degrau = resolucao or PF.DEGRAU_PADRAO_M
        linha = {'id': ensaio['id'], 'situacao_da_placa': res['situacao'],
                 'amostras_reproduzidas': res['n_amostras_reproduzidas'],
                 'amostras_do_ensaio': len(ensaio['tempo_s']),
                 'ciclos_de_processamento': latencias[-1]}
        for canal in ('A', 'B'):
            v = canal_do_verilog(res['canal_' + canal])
            p = canal_do_ponto_fixo(ensaio['canal_%s_carga_m' % canal], ts, degrau, cal, resolucao)
            divergentes = comparar_canais(v, p)
            gravado = arquivo_pf[(ensaio['id'], canal)]['indice_de_chegada_ponto_fixo']
            if v['indice_de_chegada'] != gravado:
                divergentes.append('indice_de_chegada do arquivo do ponto fixo')
            linha['canal_' + canal] = {'verilog': v, 'ponto_fixo': p, 'divergencias': divergentes}
        linha['igual'] = (res['situacao'] == PR.RESULTADO_CONCLUIDO
                          and not linha['canal_A']['divergencias'] and not linha['canal_B']['divergencias'])
        linhas.append(linha)

    sinteticos = []
    resolucao_cabecalho = pacote['escala']['resolucao_declarada_m']
    for nome in sorted(casos):
        if not nome.startswith('sintetico_frente_fraca') and nome != 'sintetico_retrocesso_truncado':
            continue
        caso = casos[nome]
        (_, res, _), = caso.resultados()
        codigos = caso.codigos()
        item = {'caso': nome, 'descricao': caso.info['descricao']}
        for canal, cod in zip(('A', 'B'), codigos):
            v = canal_do_verilog(res['canal_' + canal])
            p = canal_do_ponto_fixo(np.asarray(cod, dtype=float) * DEGRAU_SINTETICO_M, ts,
                                    DEGRAU_SINTETICO_M, cal, resolucao_cabecalho)
            item['canal_' + canal] = {'verilog': v, 'ponto_fixo': p, 'divergencias': comparar_canais(v, p),
                                      'amostras_retrocedidas': (v['indice_de_cruzamento'] - v['indice_de_chegada']
                                                                if v['detectado'] else None)}
        item['igual'] = not item['canal_A']['divergencias'] and not item['canal_B']['divergencias']
        sinteticos.append(item)

    canais = 2 * len(linhas)
    iguais = sum((not l['canal_A']['divergencias']) + (not l['canal_B']['divergencias']) for l in linhas)
    return {
        'criterio': 'indice da FPGA igual ao da referencia em ponto fixo',
        'referencia': '04_detector/detector_ponto_fixo.py, rodado sobre o sinal original do ensaio',
        'ensaios': len(linhas),
        'canais_comparados': canais,
        'canais_iguais': iguais,
        'campos_comparados': ['detectado', 'indice_de_cruzamento', 'indice_de_chegada',
                              'retrocesso_truncado', 'n_oportunidades_de_decisao'],
        'sinais_sinteticos_de_retrocesso': sinteticos,
        'passou': iguais == canais and all(l['igual'] for l in linhas) and all(s['igual'] for s in sinteticos),
    }, linhas, latencias


def criterio_b08(casos, linhas):
    caso = casos['sintetico_atraso_40']
    (_, res, _), = caso.resultados()
    a, b = res['canal_A'], res['canal_B']
    n = len(caso.codigos()[0])
    diferenca_chegada = b['indice_de_chegada'] - a['indice_de_chegada']
    diferenca_cruzamento = b['indice_de_cruzamento'] - a['indice_de_cruzamento']
    todas = all(l['amostras_reproduzidas'] == l['amostras_do_ensaio'] for l in linhas)
    return {
        'criterio': 'reproducao por indice comum: atraso conhecido entre canais devolvido exato',
        'atraso_imposto_amostras': ATRASO,
        'diferenca_de_chegada_amostras': diferenca_chegada,
        'diferenca_de_cruzamento_amostras': diferenca_cruzamento,
        'amostras_reproduzidas': res['n_amostras_reproduzidas'],
        'amostras_enviadas': n,
        'todas_as_amostras_reproduzidas_nos_45_ensaios': todas,
        'passou': (a['detectado'] and b['detectado'] and diferenca_chegada == ATRASO
                   and diferenca_cruzamento == ATRASO and res['n_amostras_reproduzidas'] == n and todas),
    }


def criterio_b07(casos, pacote):
    conferidas, divergentes = 0, []
    for ensaio in pacote['ensaios']:
        caso = casos['ensaio_%s' % ensaio['id']]
        (_, enviada), = caso.do_tipo(PR.CONFIGURAR, 'recebidos')
        (_, lida), = caso.do_tipo(PR.CONFIGURACAO_LIDA)
        ident, valores = PR.ler_configurar(enviada)
        ident_lido, lidos, contadores = PR.ler_configuracao_lida(lida)
        conferidas += 1
        if ident_lido != ident or any(lidos[c] != valores[c] for c in PR.CAMPOS_DE_CONFIGURACAO) \
                or any(contadores.values()):
            divergentes.append(ensaio['id'])

    def cargas(nome):
        return [c for _, _, c in casos[nome].resultados()]

    duas = cargas('protocolo_mesmo_ensaio_duas_vezes')
    sozinho = cargas('ensaio_MX-005')
    tres = cargas('protocolo_tres_ensaios_seguidos')
    repeticao = len(duas) == 2 and duas[0] == duas[1] == sozinho[0]
    intercalado = (len(tres) == 3 and tres[0] == tres[2] == cargas('ensaio_MX-021')[0]
                   and tres[1] == cargas('ensaio_MX-001')[0])
    return {
        'criterio': ('configuracao lida de volta igual a enviada, e o mesmo ensaio rodado de novo '
                     'com resultado identico'),
        'configuracoes_conferidas': conferidas,
        'configuracoes_divergentes': divergentes,
        'mesmo_ensaio_duas_vezes': {
            'ensaio': 'MX-005',
            'resultados_identicos_byte_a_byte': repeticao,
            'bytes_do_resultado': len(duas[0]) if duas else 0,
        },
        'mesmo_ensaio_com_outro_no_meio': {
            'sequencia': ['MX-021', 'MX-001', 'MX-021'],
            'resultados_identicos_aos_de_cada_ensaio_sozinho': intercalado,
        },
        'passou': not divergentes and repeticao and intercalado,
    }


def criterio_b06(casos):
    caso = casos['protocolo_bloco_corrompido']
    recibos = [PR.ler_bloco_recebido(c) for _, c in caso.do_tipo(PR.BLOCO_RECEBIDO)]
    recusados_crc = [r for r in recibos if r[2] == PR.BLOCO_CRC_INVALIDO]
    enviados = caso.do_tipo(PR.AMOSTRAS, 'recebidos')
    corrompidos = [e for e in PR.LeitorDeQuadros().alimentar(caso.entrada) if e[0] != 'ok']
    # o recibo de CRC invalido vem logo antes do mesmo bloco aceito no reenvio
    k = next((k for k, r in enumerate(recibos) if r[2] == PR.BLOCO_CRC_INVALIDO), None)
    reenviado = k is not None and k + 1 < len(recibos) and recibos[k + 1][1] == recibos[k - 1][1] + 1         and recibos[k + 1][2] == PR.BLOCO_OK
    (_, res, carga), = caso.resultados()
    (_, _, carga_limpa), = casos['ensaio_MX-001'].resultados()
    limpo = PR.ler_resultado(carga_limpa)
    mesmo_resultado = res['canal_A'] == limpo['canal_A'] and res['canal_B'] == limpo['canal_B']
    blocos = casos['ensaio_MX-001'].do_tipo(PR.AMOSTRAS, 'recebidos')

    lacuna = casos['protocolo_lacuna_de_sequencia']
    recibos_lacuna = [PR.ler_bloco_recebido(c) for _, c in lacuna.do_tipo(PR.BLOCO_RECEBIDO)]
    (_, res_lacuna, _), = lacuna.resultados()
    fora = [r for r in recibos_lacuna if r[2] == PR.BLOCO_FORA_DE_SEQUENCIA]

    passou = (len(recusados_crc) == 1 and len(corrompidos) == 1 and reenviado and len(enviados) == len(blocos)
              and all(r[2] == PR.BLOCO_OK for r in recibos if r not in recusados_crc)
              and res['situacao'] == PR.RESULTADO_CONCLUIDO
              and res['contadores']['falhas_de_crc'] == 1 and mesmo_resultado
              and len(fora) == 1 and res_lacuna['situacao'] == PR.RESULTADO_RECUSADO_AMOSTRAS_FALTANDO
              and res_lacuna['contadores']['descontinuidades_de_sequencia'] == 1)
    return {
        'criterio': 'bloco corrompido rejeitado; so segue com o bloco certo',
        'bloco_corrompido': {
            'ensaio': 'MX-001',
            'quadros_corrompidos_no_enlace': len(corrompidos),
            'recibos_de_crc_invalido': len(recusados_crc),
            'bloco_reenviado_e_aceito': reenviado,
            'blocos_aceitos': len(enviados),
            'blocos_do_ensaio': len(blocos),
            'falhas_de_crc_contadas_pela_placa': res['contadores']['falhas_de_crc'],
            'resultado_igual_ao_do_ensaio_sem_corrupcao': mesmo_resultado,
        },
        'bloco_fora_de_sequencia': {
            'ensaio': 'MX-003',
            'recibos_fora_de_sequencia': len(fora),
            'descontinuidades_contadas_pela_placa': res_lacuna['contadores']['descontinuidades_de_sequencia'],
            'execucao': 'recusada, amostras faltando'
            if res_lacuna['situacao'] == PR.RESULTADO_RECUSADO_AMOSTRAS_FALTANDO else res_lacuna['situacao'],
        },
        'passou': passou,
    }


def criterio_tempos(casos):
    falhas = []

    def exigir(condicao, texto):
        if not condicao:
            falhas.append(texto)

    (_, t0), = casos['tempos_antes_de_executar'].tempos()
    exigir(t0['situacao'] == PR.TEMPOS_SEM_EXECUCAO and t0['contado_pelo_circuito']
           and t0['frequencia_hz'] == RELOGIO_HZ and t0['ciclos_execucao'] == 0,
           'TEMPOS antes de qualquer execucao')

    # lote: o contador do circuito contra a contagem do simulador
    caso = casos['tempos_lote_MX-013']
    (deslocamento, res, _), = caso.resultados()
    (_, lote), = caso.tempos()
    no_simulador = caso.latencia(deslocamento)
    (desl_ensaio, _, _), = casos['ensaio_MX-013'].resultados()
    folga = no_simulador - lote['ciclos_execucao']
    exigir(0 <= folga <= 8, 'ciclos_execucao %d contra %d contados no simulador'
           % (lote['ciclos_execucao'], no_simulador))
    exigir(no_simulador == casos['ensaio_MX-013'].latencia(desl_ensaio),
           'a mesma execucao levou ciclos diferentes em dois casos')
    exigir(lote['modo'] == PR.MODO_LOTE and lote['amostras_atrasadas'] == 0
           and lote['n_amostras'] == res['n_amostras_reproduzidas'], 'TEMPOS do lote')
    for canal in 'AB':
        detectou = res['canal_' + canal]['detectado']
        exigir((lote['ciclo_declaracao_' + canal] is not None) == detectou, 'declaracao no canal ' + canal)
        if detectou:
            exigir(lote['latencia_declaracao_' + canal] <= lote['ciclos_por_amostra_max']
                   and lote['ciclo_declaracao_' + canal] <= lote['ciclos_execucao'],
                   'latencia de declaracao no canal ' + canal)

    # tempo real: ritmo marcado pelo relogio do circuito
    tempo_real = []
    for nome, ident in (('tempo_real_MX-001', 'MX-001'), ('tempo_real_MX-039', 'MX-039')):
        caso = casos[nome]
        (_, res, carga), = caso.resultados()
        (_, t), = caso.tempos()
        (_, _, carga_lote), = casos['ensaio_' + ident].resultados()
        periodo, n = t['periodo_ciclos'], t['n_amostras']
        exigir(carga == carga_lote, '%s: resultado diferente do lote' % nome)
        exigir(t['modo'] == PR.MODO_TEMPO_REAL and t['amostras_atrasadas'] == 0, '%s: amostras atrasadas' % nome)
        exigir(t['ciclos_por_amostra_max'] < periodo, '%s: amostra mais longa que o periodo' % nome)
        exigir(t['ciclos_execucao'] >= (n - 1) * periodo, '%s: execucao mais curta que o ritmo' % nome)
        bases, latencias = [], {}
        for canal in 'AB':
            if res['canal_' + canal]['detectado']:
                entrega = t['ciclo_declaracao_' + canal] - t['latencia_declaracao_' + canal]
                bases.append(entrega - res['canal_' + canal]['indice_de_cruzamento'] * periodo)
                latencias[canal] = t['latencia_declaracao_' + canal]
                exigir(t['latencia_declaracao_' + canal] < periodo, '%s: declaracao fora do periodo' % nome)
        # a amostra k sai k periodos depois da primeira, que sai logo depois do
        # preparo do detector: a mesma base nos dois canais, menor que um periodo
        exigir(len(set(bases)) <= 1 and all(0 <= b < periodo for b in bases),
               '%s: amostras fora do ritmo (%r)' % (nome, bases))
        tempo_real.append({
            'caso': nome, 'periodo_ciclos': periodo, 'amostras': n,
            'ciclos_execucao': t['ciclos_execucao'],
            'ciclos_por_amostra_min': t['ciclos_por_amostra_min'],
            'ciclos_por_amostra_max': t['ciclos_por_amostra_max'],
            'latencia_de_declaracao_ciclos': latencias,
            'primeira_amostra_no_ciclo': bases[0] if bases else None,
            'amostras_atrasadas': t['amostras_atrasadas'],
        })

    (_, _, carga), = casos['tempo_real_atrasado'].resultados()
    (_, atrasado), = casos['tempo_real_atrasado'].tempos()
    (_, _, carga_lote), = casos['ensaio_MX-005'].resultados()
    exigir(atrasado['amostras_atrasadas'] > 0 and carga == carga_lote,
           'periodo curto: atrasos contados e resultado igual ao lote')

    tempos_mal = casos['tempo_real_mal_formado'].tempos()
    exigir(len(tempos_mal) == 1 and tempos_mal[0][1]['situacao'] == PR.RESULTADO_RECUSADO_SEM_CONFIGURACAO
           and tempos_mal[0][1]['modo'] == PR.MODO_TEMPO_REAL, 'tempo real sem configuracao')

    return {
        'criterio': ('os ciclos contados pelo circuito conferem com o simulador, e o tempo real segue o '
                     'relogio da placa sem mudar o resultado'),
        'lote_MX-013': {
            'ciclos_execucao_contados_pelo_circuito': lote['ciclos_execucao'],
            'ciclos_contados_pelo_simulador': no_simulador,
            'ciclos_por_amostra_min': lote['ciclos_por_amostra_min'],
            'ciclos_por_amostra_max': lote['ciclos_por_amostra_max'],
            'latencia_de_declaracao_ciclos': {c: lote['latencia_declaracao_' + c] for c in 'AB'},
        },
        'tempo_real': tempo_real,
        'amostras_atrasadas_com_periodo_de_8_ciclos': atrasado['amostras_atrasadas'],
        'falhas': falhas,
        'passou': not falhas,
    }


def estatisticas_das_amostras(codigos):
    """O autoteste de um canal contado aqui, direto nas amostras, sem o modelo da placa."""
    c = np.asarray(codigos, dtype=np.int64)
    iguais = np.flatnonzero(np.diff(c) != 0)                 # onde cada sequencia termina
    fronteiras = np.concatenate([[-1], iguais, [c.size - 1]])
    return {
        'codigo_min': int(c.min()), 'codigo_max': int(c.max()),
        'maior_sequencia': int(np.diff(fronteiras).max()),
        'maior_variacao': int(np.abs(np.diff(c)).max()) if c.size > 1 else 0,
        'amostras_no_extremo': int(np.count_nonzero((c == 0) | (c == 0xFFFF))),
    }


def criterio_autoteste(casos):
    falhas = []

    def exigir(condicao, texto):
        if not condicao:
            falhas.append(texto)

    campos = PR.CAMPOS_DA_SAUDE[1:]
    canais, saudaveis, iguais = 0, 0, 0
    for nome, caso in casos.items():
        if not nome.startswith('ensaio_'):
            continue
        saudes = caso.saudes()
        exigir(len(saudes) == 1 and saudes[0][1]['situacao'] == PR.RESULTADO_CONCLUIDO,
               '%s: sem SAUDE da execucao' % nome)
        if len(saudes) != 1:
            continue
        saude = saudes[0][1]
        for canal, codigos in zip(('canal_A', 'canal_B'), caso.codigos()):
            canais += 1
            saudaveis += not saude[canal]['falhas']
            iguais += all(saude[canal][k] == v for k, v in estatisticas_das_amostras(codigos).items())
    exigir(canais == 90 and saudaveis == canais and iguais == canais,
           'matriz: %d canais, %d saudaveis, %d com as estatisticas certas' % (canais, saudaveis, iguais))

    def falhas_de(nome):
        return [(s['canal_A']['falhas'], s['canal_B']['falhas']) for _, s in casos[nome].saudes()]

    doentes = {
        'saude_canal_congelado': [([], ['congelado']), ([], [])],
        'saude_cabo_rompido': [(['congelado', 'saturado', 'fora_da_faixa'], [])],
        'saude_pico_isolado': [([], ['salto'])],
    }
    acusados = {}
    for nome, esperado in doentes.items():
        obtido = falhas_de(nome)
        acusados[nome] = obtido
        exigir(obtido == esperado, '%s: acusou %r, esperado %r' % (nome, obtido, esperado))

    caso = casos['saude_sem_execucao_e_mal_formado']
    situacoes = [s['situacao'] for _, s in caso.saudes()]
    zerados = all(s[c][k] == 0 for _, s in caso.saudes() for c in ('canal_A', 'canal_B') for k in campos)
    recibos = [PR.ler_bloco_recebido(c)[2] for _, c in caso.do_tipo(PR.BLOCO_RECEBIDO)]
    exigir(situacoes == [PR.SAUDE_SEM_EXECUCAO, PR.RESULTADO_RECUSADO_SEM_CONFIGURACAO] and zerados
           and recibos == [PR.BLOCO_MAL_FORMADO],
           'SAUDE sem execucao, depois de execucao recusada e mal formado')

    return {
        'criterio': ('o circuito acompanha cada canal amostra a amostra e acusa canal congelado, saturado, '
                     'fora da faixa do transmissor ou com salto impossivel, sem acusar canal saudavel'),
        'canais_da_matriz': canais,
        'canais_saudaveis': saudaveis,
        'canais_com_estatisticas_iguais_as_das_amostras': iguais,
        'canais_doentes_de_proposito': acusados,
        'falhas': falhas,
        'passou': not falhas,
    }


# --- cadeia completa do computador sobre a resposta do Verilog --------------------------------

def cadeia_completa(casos, pacote):
    gravacoes = []
    for ensaio in pacote['ensaios']:
        caso = casos['ensaio_%s' % ensaio['id']]
        gravacoes.append((caso.entrada, [(b, pos) for b, pos, _, _ in caso.linhas]))
    transporte = TR.TransporteSimulacaoDoVerilog(gravacoes)
    relatorio = EX.executar(transporte)
    if not transporte.tudo_consumido():
        raise SystemExit('a cadeia do computador nao consumiu toda a resposta simulada')
    return relatorio


def main():
    indice = json.load(open(os.path.join(VETORES, 'casos.json'), encoding='utf-8'))['casos']
    casos = {nome: Caso(nome, info) for nome, info in indice.items()}
    pacote = json.load(open(SE.PACOTE, encoding='utf-8'))
    cal = D.calibracao_padrao()
    ts = float(pacote['amostragem']['periodo_de_amostragem_s'])

    identicos = [n for n, c in casos.items() if c.igual_ao_modelo()]
    b09, linhas, latencias = criterio_b09(casos, pacote, cal, ts)
    b08 = criterio_b08(casos, linhas)
    b07 = criterio_b07(casos, pacote)
    b06 = criterio_b06(casos)
    tempos = criterio_tempos(casos)
    autoteste = criterio_autoteste(casos)
    relatorio = cadeia_completa(casos, pacote)

    maior = max(linhas, key=lambda l: l['ciclos_de_processamento'])
    criterios = {'B-06': b06, 'B-07': b07, 'B-08': b08, 'B-09': b09, 'Tempos': tempos,
                 'Autoteste': autoteste}
    prova = {
        'descricao': ('Prova do cenario B no simulador: a resposta gravada do proprio Verilog da placa, '
                      'decodificada e conferida contra a referencia em ponto fixo e contra os criterios '
                      'de B-06 a B-09. E o mesmo Verilog que vai para a FPGA, rodando ciclo a ciclo no '
                      'Icarus Verilog. Nao e resultado de FPGA fisica; a placa confirma o que esta '
                      'prova ja mostra.'),
        'origem': 'simulacao_do_verilog',
        'verilog': sorted('06_fpga/' + f for f in RS.RTL_TOPO),
        'casos_simulados': len(casos),
        'casos_identicos_ao_modelo_byte_a_byte': len(identicos),
        'criterios': criterios,
        'todos_os_criterios_passaram': all(c['passou'] for c in criterios.values()),
        'processamento_na_placa': {
            'o_que_conta': ('ciclos de relogio entre o ultimo byte do EXECUTAR e o primeiro byte do '
                            'RESULTADO: reproducao das amostras e deteccao nos dois canais'),
            'ciclos_mediano': int(statistics.median(latencias)),
            'ciclos_maximo': maior['ciclos_de_processamento'],
            'ensaio_mais_longo': maior['id'],
            'amostras_do_ensaio_mais_longo': maior['amostras_do_ensaio'],
            'microssegundos_maximo_a_100_mhz': round(maior['ciclos_de_processamento'] / RELOGIO_HZ * 1e6, 1),
            'observacao': ('ciclos contados no simulador; em segundos dependem do relogio da placa, que '
                           'so fica fixo com o fechamento de tempo no Vivado ou no Quartus'),
        },
        'cadeia_do_computador_sobre_a_resposta_do_verilog': {
            'arquivos': sorted(os.path.basename(p) for p in EX.caminhos('simulacao_do_verilog').values()),
            'ensaios_concluidos': relatorio['ensaios']['concluidos'],
            'divergencia_com_o_software': relatorio['divergencia_com_o_software'],
            'avaliacao_contra_a_verdade': relatorio['avaliacao_contra_a_verdade'],
        },
        'ensaios': linhas,
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(prova, f, ensure_ascii=False, indent=2)
    print('escrito: %s' % os.path.relpath(SAIDA, RAIZ))

    print('casos identicos ao modelo, byte a byte: %d de %d' % (len(identicos), len(casos)))
    print('B-09 indices iguais ao ponto fixo: %d de %d canais, %d sinais sinteticos -> %s'
          % (b09['canais_iguais'], b09['canais_comparados'], len(b09['sinais_sinteticos_de_retrocesso']),
             'passou' if b09['passou'] else 'FALHOU'))
    print('B-08 atraso imposto %d, devolvido %d (chegada) e %d (cruzamento) -> %s'
          % (ATRASO, b08['diferenca_de_chegada_amostras'], b08['diferenca_de_cruzamento_amostras'],
             'passou' if b08['passou'] else 'FALHOU'))
    print('B-07 configuracoes conferidas %d, repeticao identica %s -> %s'
          % (b07['configuracoes_conferidas'], b07['mesmo_ensaio_duas_vezes']['resultados_identicos_byte_a_byte'],
             'passou' if b07['passou'] else 'FALHOU'))
    print('B-06 bloco corrompido recusado %d vez, reenviado e resultado igual %s -> %s'
          % (b06['bloco_corrompido']['recibos_de_crc_invalido'],
             b06['bloco_corrompido']['resultado_igual_ao_do_ensaio_sem_corrupcao'],
             'passou' if b06['passou'] else 'FALHOU'))
    print('Tempos contador do circuito %d ciclos contra %d no simulador; tempo real sem atraso -> %s'
          % (tempos['lote_MX-013']['ciclos_execucao_contados_pelo_circuito'],
             tempos['lote_MX-013']['ciclos_contados_pelo_simulador'], 'passou' if tempos['passou'] else 'FALHOU'))
    for f in tempos['falhas']:
        print('   ' + f)
    print('Autoteste %d de %d canais da matriz saudaveis, 4 canais doentes acusados -> %s'
          % (autoteste['canais_saudaveis'], autoteste['canais_da_matriz'],
             'passou' if autoteste['passou'] else 'FALHOU'))
    for f in autoteste['falhas']:
        print('   ' + f)
    p = prova['processamento_na_placa']
    print('processamento: mediana %d ciclos, maximo %d ciclos (%s, %.1f us a 100 MHz)'
          % (p['ciclos_mediano'], p['ciclos_maximo'], p['ensaio_mais_longo'], p['microssegundos_maximo_a_100_mhz']))
    dv = relatorio['divergencia_com_o_software']
    print('cadeia do computador: %d ensaios concluidos, %d de %d iguais ao software'
          % (relatorio['ensaios']['concluidos'], dv['identicos'], dv['n_ensaios']))
    if not prova['todos_os_criterios_passaram'] or len(identicos) != len(casos):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

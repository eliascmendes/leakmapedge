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
        self.linhas = ler_verilog(os.path.join(VETORES, nome + '.verilog.txt'))
        self.obtido = bytes(l[0] for l in self.linhas)
        self.recebidos = quadros(self.entrada)
        self.devolvidos = quadros(self.obtido)

    def do_tipo(self, tipo, lado='devolvidos'):
        return [(i, c) for i, t, c in getattr(self, lado) if t == tipo]

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

    identicos = [n for n, c in casos.items() if c.obtido == c.esperado]
    b09, linhas, latencias = criterio_b09(casos, pacote, cal, ts)
    b08 = criterio_b08(casos, linhas)
    b07 = criterio_b07(casos, pacote)
    b06 = criterio_b06(casos)
    relatorio = cadeia_completa(casos, pacote)

    maior = max(linhas, key=lambda l: l['ciclos_de_processamento'])
    criterios = {'B-06': b06, 'B-07': b07, 'B-08': b08, 'B-09': b09}
    prova = {
        'descricao': ('Prova do cenario B no simulador: a resposta gravada do proprio Verilog da placa, '
                      'decodificada e conferida contra a referencia em ponto fixo e contra os criterios '
                      'de B-06 a B-09. E o mesmo Verilog que vai para a FPGA, rodando ciclo a ciclo no '
                      'Icarus Verilog. Nao e resultado de FPGA fisica; a placa confirma o que esta '
                      'prova ja mostra.'),
        'origem': 'simulacao_do_verilog',
        'verilog': sorted('06_fpga/rtl/' + f for f in os.listdir(os.path.join(FPGA, 'rtl')) if f.endswith('.v')),
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

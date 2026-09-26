"""LEAKMAP - localizacao numa rede em arvore, com N sensores.

Com dois sensores numa linha reta, a posicao sai da diferenca de tempo:
x = (L + c * dt) / 2. Numa rede com manifold e ramais, cada sensor ve a onda
depois de percorrer um caminho diferente, e a pergunta passa a ser "em que
trecho e em que ponto dele" o vazamento esta.

Um ponto da rede e (trecho, s): no tronco, s conta do sensor A; em cada ramal,
s conta do manifold. A distancia pela tubulacao de um ponto a um sensor e
|s - s_sensor| no mesmo trecho, e a soma das distancias ate o manifold quando
estao em trechos diferentes.

Para cada ponto candidato, os tempos de chegada previstos sao
t_i = t0 + d_i / c, com t0 (o instante do rompimento) desconhecido. O
localizador percorre cada trecho monitorado em passos de 5 cm, estima t0 pela
media e fica com o ponto de menor residuo (raiz do erro quadratico medio entre
chegadas medidas e previstas). Com quatro sensores sobram duas equacoes: o
residuo mede a coerencia das chegadas.

Classes, as mesmas do detector de dois sensores (detector.py):

  localizado        melhor ponto unico, dentro da rede monitorada, com residuo
                    compativel com a incerteza das marcas
  fora_do_trecho    o melhor ponto e o proprio sensor da ponta de um trecho: a
                    onda veio de fora da rede monitorada, do lado dele (como na
                    linha reta, um vazamento em cima do sensor e indistinguivel)
  manobra           onda de alta
  detectado_sem_localizacao  menos de dois sensores com queda, residuo alto
                    demais ou dois trechos igualmente possiveis
  sem_deteccao, falha_execucao

Com quatro sensores sobra redundancia, e o residuo denuncia chegadas que nao
batem. Um transmissor inteligente atualiza a saida a cada T (de 1 a 100 ms,
na folha de dados): cada chegada atrasa entre 0 e T, sem relacao entre os
canais. Esse periodo, quando declarado na escala do instrumento
(`periodo_de_atualizacao_declarado_s`), entra na incerteza de cada chegada
como T / raiz(12); sem ele, a coerencia seria cobrada com a incerteza de um
transmissor rapido e a posicao seria retida.
"""
import numpy as np

import detector as D

PASSO_DE_BUSCA_M = 0.05


def juncao(topo, trecho):
    return float(topo['trechos'][trecho]['juncao_em_s_m'])


def distancia(topo, trecho, s, sensor):
    """Distancia pela tubulacao de (trecho, s) ate um sensor da topologia (vetorizada em s)."""
    alvo = topo['sensores'][sensor]
    if alvo['trecho'] == trecho:
        return np.abs(s - alvo['s_m'])
    return np.abs(s - juncao(topo, trecho)) + abs(alvo['s_m'] - juncao(topo, alvo['trecho']))


def distancia_entre_pontos(topo, p, q):
    """Distancia pela tubulacao entre dois pontos (trecho, s)."""
    if p[0] == q[0]:
        return abs(p[1] - q[1])
    return abs(p[1] - juncao(topo, p[0])) + abs(q[1] - juncao(topo, q[0]))


def melhor_ponto_no_trecho(topo, trecho, chegadas, c_m_s):
    comp = float(topo['trechos'][trecho]['comprimento_monitorado_m'])
    s = np.arange(0.0, comp + PASSO_DE_BUSCA_M / 2, PASSO_DE_BUSCA_M)
    nomes = sorted(chegadas)
    t = np.array([chegadas[n] for n in nomes])
    previsto = np.array([distancia(topo, trecho, s, n) / c_m_s for n in nomes])      # sensores x pontos
    resto = t[:, None] - previsto
    t0 = resto.mean(axis=0)
    rms = np.sqrt(((resto - t0) ** 2).mean(axis=0))
    k = int(np.argmin(rms))
    return {'trecho': trecho, 's_m': float(s[k]), 'residuo_rms_s': float(rms[k]),
            'instante_do_rompimento_s': float(t0[k])}


def ponta_de_sensor(topo, trecho, s, tolerancia_m):
    """O sensor cuja posicao coincide com (trecho, s), se houver."""
    for nome, alvo in topo['sensores'].items():
        if alvo['trecho'] == trecho and abs(alvo['s_m'] - s) <= tolerancia_m:
            return nome
    return None


def localizar_na_rede(chegadas, incertezas_s, topo, c_m_s, ts):
    """Melhor ponto da rede para as chegadas {sensor: t}. Devolve (classe, motivo, detalhe)."""
    candidatos = sorted((melhor_ponto_no_trecho(topo, tr, chegadas, c_m_s) for tr in topo['trechos']),
                        key=lambda p: p['residuo_rms_s'])
    melhor = candidatos[0]
    u = float(np.sqrt(np.mean(np.square(list(incertezas_s.values()))))) if incertezas_s else ts
    limite = max(ts, 3.0 * u)
    detalhe = {'candidatos_por_trecho': candidatos, 'limite_de_residuo_s': limite}
    if melhor['residuo_rms_s'] > limite:
        return (D.CLASSE_SEM_LOCALIZACAO, 'chegadas incoerentes com qualquer ponto da rede (residuo %.2f ms)'
                % (1e3 * melhor['residuo_rms_s']), detalhe)
    # outro trecho igualmente possivel, num ponto que nao e o mesmo (o manifold e comum a todos)
    for outro in candidatos[1:]:
        separacao = distancia_entre_pontos(topo, (melhor['trecho'], melhor['s_m']), (outro['trecho'], outro['s_m']))
        if outro['residuo_rms_s'] <= limite and separacao > c_m_s * ts:
            if outro['residuo_rms_s'] - melhor['residuo_rms_s'] < u:
                return (D.CLASSE_SEM_LOCALIZACAO, 'posicao ambigua entre %s e %s' % (melhor['trecho'], outro['trecho']),
                        detalhe)
    sensor = ponta_de_sensor(topo, melhor['trecho'], melhor['s_m'], c_m_s * ts)
    if sensor is not None and len(chegadas) > 1:
        detalhe['lado_da_origem'] = sensor
        return (D.CLASSE_FORA_DO_TRECHO, 'melhor ponto em cima do sensor %s: origem fora da rede monitorada, '
                'do lado dele' % sensor, detalhe)
    detalhe.update(trecho_estimado=melhor['trecho'], s_estimado_m=melhor['s_m'])
    return D.CLASSE_LOCALIZADO, 'chegadas coerentes com um ponto da rede', detalhe


def processar_ensaio_rede(ensaio, escala, topo, cal=None):
    """A-11 e A-12 em cada canal, e a localizacao na rede. Nunca levanta excecao."""
    cal = dict(cal or D.calibracao_padrao())
    registro = {'id': ensaio['id']}
    try:
        t = np.asarray(ensaio['tempo_s'], dtype=float)
        ts = float(np.median(np.diff(t)))
        c_m_s = float(topo['velocidade_de_onda_m_s'])
        resolucao = (escala or {}).get('resolucao_declarada_m')
        canais = {}
        for nome, sinal in ensaio['canais_carga_m'].items():
            x = np.asarray(sinal, dtype=float)
            det, y, _, e_longa = D.detectar_canal(x, ts, cal, resolucao)
            det['saturado'] = D.canal_saturado(x, escala)
            if det['detectado']:
                det.update(D.marcar_chegada(y, e_longa, det['indice_de_cruzamento'], t, ts, cal))
            canais[nome] = det
        registro['canais'] = canais
        registro['periodo_de_amostragem_s'] = ts
        periodo = float((escala or {}).get('periodo_de_atualizacao_declarado_s') or 0.0)
        registro['periodo_de_atualizacao_declarado_s'] = periodo
        vistos = {n: d for n, d in canais.items() if d['detectado']}
        registro['tempo_de_declaracao_s'] = (float(min(t[d['indice_de_cruzamento']] for d in vistos.values()))
                                             if vistos else None)
        if not vistos:
            registro.update(classe=D.CLASSE_SEM_DETECCAO, motivo='nenhum sensor detectou')
            return registro
        if any(d['polaridade'] == D.POLARIDADE_ALTA for d in vistos.values()):
            registro.update(classe=D.CLASSE_MANOBRA, motivo='onda de alta: manobra, nao vazamento')
            return registro
        validos = {n: d for n, d in vistos.items() if not d['saturado']}
        if len(validos) < 2:
            registro.update(classe=D.CLASSE_SEM_LOCALIZACAO, motivo='menos de dois sensores com a chegada')
            return registro
        classe, motivo, detalhe = localizar_na_rede(
            {n: d['tempo_de_chegada_s'] for n, d in validos.items()},
            {n: float(np.hypot(d['incerteza_s'], periodo / np.sqrt(12.0))) for n, d in validos.items()},
            topo, c_m_s, ts)
        registro.update(classe=classe, motivo=motivo, sensores_usados=sorted(validos), **detalhe)
        return registro
    except Exception as e:  # nenhum ensaio sai sem registro (A-15)
        registro.update(classe=D.CLASSE_FALHA, motivo='%s: %s' % (type(e).__name__, e))
        return registro

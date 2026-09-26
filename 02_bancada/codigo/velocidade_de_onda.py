"""LEAKMAP - velocidade da onda de pressao por produto e por linha.

Formula de Korteweg para tubo de parede fina ancorado com juntas de
expansao (fator de ancoragem psi = 1):

    c = sqrt( (K / rho) / (1 + psi * K * D / (E * e)) )

K e o modulo de compressibilidade do liquido, rho a massa especifica, D o
diametro interno, e a espessura da parede e E o modulo de elasticidade do
material do tubo.

Os valores de produto e de tubo abaixo sao TIPICOS, de literatura e de norma
de tubulacao, e servem de premissa para a simulacao: a velocidade real da
linha instalada so sai de calibracao em campo, com transientes provocados em
posicoes conhecidas. O que a tabela mostra de util desde ja e a ordem de
grandeza e o quanto a velocidade muda de um produto para outro na mesma
linha.

Uso:
  python velocidade_de_onda.py        imprime a tabela produto x linha
"""
import math

# produto: massa especifica (kg/m3) e modulo de compressibilidade (Pa),
# valores tipicos a 20-25 graus C
PRODUTOS = {
    'diesel': {'rho_kg_m3': 840.0, 'k_pa': 1.50e9},
    'gasolina': {'rho_kg_m3': 740.0, 'k_pa': 1.10e9},
    'agua': {'rho_kg_m3': 998.0, 'k_pa': 2.19e9},
}

# material do tubo: modulo de elasticidade (Pa)
MATERIAIS = {
    'aco_carbono': 200e9,
    'aco_inox': 193e9,
}

# tubos: diametro externo (m) e espessura (m) por diametro nominal e schedule
TUBOS = {
    ('8"', 'sch40'): {'diametro_externo_m': 0.2191, 'espessura_m': 0.00818},
    ('8"', 'sch10S'): {'diametro_externo_m': 0.2191, 'espessura_m': 0.00376},
    ('12"', 'sch40'): {'diametro_externo_m': 0.3238, 'espessura_m': 0.01031},
    ('12"', 'sch10S'): {'diametro_externo_m': 0.3238, 'espessura_m': 0.00457},
}

# linhas de produto tipicas de cais, com a premissa de schedule: aco carbono em
# schedule 40 e aco inox em schedule 10S, os usuais para cada material; a
# espessura real sai da lista de linhas ou do isometrico da instalacao
LINHAS = {
    '8" carbono': ('8"', 'aco_carbono', 'sch40'),
    '8" inox': ('8"', 'aco_inox', 'sch10S'),
    '12" carbono': ('12"', 'aco_carbono', 'sch40'),
    '12" inox': ('12"', 'aco_inox', 'sch10S'),
}


def diametro_interno_m(nominal, schedule):
    t = TUBOS[(nominal, schedule)]
    return t['diametro_externo_m'] - 2.0 * t['espessura_m']


def velocidade(produto, nominal, material, schedule, ancoragem=1.0):
    """Velocidade da onda (m/s), com a conta registrada."""
    p = PRODUTOS[produto]
    t = TUBOS[(nominal, schedule)]
    e_mat = MATERIAIS[material]
    d = diametro_interno_m(nominal, schedule)
    c_liquido = math.sqrt(p['k_pa'] / p['rho_kg_m3'])
    parede = ancoragem * p['k_pa'] * d / (e_mat * t['espessura_m'])
    return {
        'produto': produto,
        'tubo': '%s %s %s' % (nominal, material, schedule),
        'diametro_interno_m': d,
        'velocidade_no_liquido_livre_m_s': c_liquido,
        'fator_da_parede': parede,
        'velocidade_m_s': c_liquido / math.sqrt(1.0 + parede),
    }


def tabela():
    linhas = []
    for nome, (nominal, material, schedule) in LINHAS.items():
        for produto in ('diesel', 'gasolina'):
            v = velocidade(produto, nominal, material, schedule)
            v['linha'] = nome
            linhas.append(v)
    return linhas


if __name__ == '__main__':
    print('%-12s %-9s %-24s %8s %10s' % ('linha', 'produto', 'tubo', 'D int mm', 'c (m/s)'))
    for v in tabela():
        print('%-12s %-9s %-24s %8.1f %10.0f' % (v['linha'], v['produto'], v['tubo'],
                                              v['diametro_interno_m'] * 1000, v['velocidade_m_s']))

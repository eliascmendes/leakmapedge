"""Monta o modelo hidraulico LEAKMAP: trecho unico de 200 m,
sensores virtuais em 40 m e 160 m, nos internos nas posicoes de evento."""
import wntr

L_TRECHO   = 200.0
SENSOR_A   = 40.0
SENSOR_B   = 160.0
POS_EVENTO = [60.0, 80.0, 100.0, 120.0, 140.0]
DIAMETRO   = 0.3
FRICCAO_DW = 0.02
H_MONTANTE = 60.0
H_JUSANTE  = 50.0

# todos os nos internos, geometria identica em todos os cenarios
NOS = sorted(set([SENSOR_A, SENSOR_B] + POS_EVENTO))

def nome_no(x):
    return "N%d" % int(round(x))

def escrever_inp(caminho):
    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.headloss = 'D-W'
    wn.options.time.duration = 0
    wn.add_reservoir('R1', base_head=H_MONTANTE, coordinates=(0.0, 0.0))
    wn.add_reservoir('R2', base_head=H_JUSANTE,  coordinates=(L_TRECHO, 0.0))
    for x in NOS:
        wn.add_junction(nome_no(x), base_demand=0.0, elevation=0.0,
                        coordinates=(x, 0.0))
    seq = ['R1'] + [nome_no(x) for x in NOS] + ['R2']
    pos = [0.0] + NOS + [L_TRECHO]
    for i in range(len(seq) - 1):
        wn.add_pipe('P%d' % (i + 1), seq[i], seq[i + 1],
                    length=pos[i + 1] - pos[i], diameter=DIAMETRO,
                    roughness=0.25, minor_loss=0.0)
    wntr.network.write_inpfile(wn, caminho, units='LPS')
    return caminho

if __name__ == '__main__':
    p = escrever_inp('/home/claude/leakmap/trecho200.inp')
    print('inp escrito:', p)
    print('nos internos:', [nome_no(x) for x in NOS])

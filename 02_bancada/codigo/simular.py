"""Simulacao transiente TSNet para o LEAKMAP: um evento por execucao."""
import numpy as np
import tsnet
from tsnet.postprocessing.detect_cusum import detect_cusum
from build_model import (escrever_inp, nome_no, SENSOR_A, SENSOR_B,
                         L_TRECHO, FRICCAO_DW)

C_SOLICITADA  = 1200.0   # m/s nominal pedida
DT_SOLICITADO = 1e-4     # s nominal pedido
TF            = 0.25     # s de simulacao
TS_BURST      = 0.05     # s: instante de abertura do vazamento
TC_BURST      = 0.001    # s: tempo de desenvolvimento
COEF_BURST    = 0.01     # coeficiente emissor final

def montar(inp):
    tm = tsnet.network.TransientModel(inp)
    tm.set_wavespeed(C_SOLICITADA)
    tm.set_time(TF, DT_SOLICITADO)
    tm.set_roughness(FRICCAO_DW)
    return tm

def wavespeed_efetiva_entre_sensores(tm):
    """Velocidade efetiva no caminho A-B: L / (soma dos tempos de transito)."""
    xs = {}
    for nome, no in tm.nodes():
        xs[nome] = no.coordinates[0]
    tempo, comp, por_trecho = 0.0, 0.0, []
    for nome, pipe in tm.pipes():
        x0 = xs[pipe.start_node.name]
        x1 = xs[pipe.end_node.name]
        if min(x0, x1) >= SENSOR_A - 1e-9 and max(x0, x1) <= SENSOR_B + 1e-9:
            tempo += pipe.length / pipe.wavev
            comp  += pipe.length
            por_trecho.append({'tubo': nome, 'comprimento_m': float(pipe.length),
                               'segmentos': int(pipe.number_of_segments),
                               'wavespeed_ajustada_m_s': float(pipe.wavev)})
    return comp / tempo, comp, por_trecho

def rodar(pos_evento, inp):
    tm = montar(inp)
    tm.add_burst(nome_no(pos_evento), TS_BURST, TC_BURST, COEF_BURST)
    tm = tsnet.simulation.Initializer(tm, 0, 'DD')
    tm = tsnet.simulation.MOCSimulator(tm, 'res_%d' % int(pos_evento))
    return tm

def chegada_cusum(tm, no, limiar, deriva):
    t = np.asarray(tm.simulation_timestamps, dtype=float)
    h = np.asarray(tm.get_node(no)._head, dtype=float)
    tai, taf, amp = detect_cusum(t, h, limiar, deriva, False)
    return t, h, tai

if __name__ == '__main__':
    import sys
    inp = escrever_inp('/home/claude/leakmap/trecho200.inp')
    tm = montar(inp)
    print('dt solicitado : %.6e s' % DT_SOLICITADO)
    print('dt efetivo    : %.9e s' % tm.time_step)
    c_ef, comp, det = wavespeed_efetiva_entre_sensores(tm)
    print('L entre sensores: %.4f m' % comp)
    print('c efetiva A-B   : %.6f m/s' % c_ef)
    for d in det:
        print('  ', d)

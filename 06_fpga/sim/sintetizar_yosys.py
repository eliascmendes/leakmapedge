"""LEAKMAP - sintese de conferencia do Verilog com o Yosys, sem ferramenta de fabricante.

Sintetiza 06_fpga/rtl para Xilinx serie 7 (familia da Spartan-7) e para
Cyclone V, e grava as estatisticas em 06_fpga/sintese/. Serve para provar que
o mesmo Verilog vira circuito nas duas familias, com as memorias de amostras
em blocos de memoria dedicados. Os numeros finais de ocupacao e de tempo vem
do Vivado ou do Quartus, na placa escolhida.

Usa o `yosys` do PATH ou o pacote Python `yowasp-yosys`
(pip install yowasp-yosys). Cada familia leva alguns minutos.
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FPGA = os.path.dirname(AQUI)
FONTES = ['rtl/leakmap_multiplicador.v', 'rtl/leakmap_detector.v', 'rtl/leakmap_saude.v', 'rtl/leakmap_nucleo.v',
          'rtl/leakmap_uart.v', 'rtl/leakmap_topo.v']
ALVOS = {
    'yosys_xilinx_serie7.txt': 'synth_xilinx -family xc7 -top leakmap_topo -flatten',
    'yosys_cyclone_v.txt': 'synth_intel_alm -family cyclonev -top leakmap_topo',
}


def comando_yosys():
    if shutil.which('yosys'):
        return ['yosys']
    try:
        import yowasp_yosys  # noqa: F401
    except ImportError:
        raise SystemExit('Yosys nao encontrado: instale o yosys ou `pip install yowasp-yosys`')
    return [sys.executable, '-c', 'import sys; from yowasp_yosys import run_yosys; '
                                  'sys.exit(run_yosys(sys.argv[1:]))']


def main():
    yosys = comando_yosys()
    os.makedirs(os.path.join(FPGA, 'sintese'), exist_ok=True)
    for arquivo, sintese in ALVOS.items():
        script = ('read_verilog -defer %s; hierarchy -check -top leakmap_topo; %s; '
                  'check -assert; tee -o sintese/%s stat' % (' '.join(FONTES), sintese, arquivo))
        print('sintetizando: %s' % arquivo, flush=True)
        subprocess.run(yosys + ['-q', '-p', script], cwd=FPGA, check=True)
    print('relatorios em 06_fpga/sintese/')


if __name__ == '__main__':
    main()

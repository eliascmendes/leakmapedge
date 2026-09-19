# FPGA

Verilog, testbench, sintese e integracao com a plataforma Itaqui Edge.

O cenario A roda o algoritmo em software e serve de referencia. O cenario B
roda em FPGA fisica. A comparacao entre os dois precisa usar exatamente as
mesmas amostras de `03_ensaios/amostras`, senao a diferenca observada mistura
efeito de plataforma com efeito de entrada.

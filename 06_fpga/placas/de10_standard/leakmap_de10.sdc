# Relogio da placa: CLOCK_50, 50 MHz
create_clock -name clk -period 20.0 [get_ports clk]
# Relogio do JTAG (USB-Blaster II, ate 24 MHz); 40 ns deixa folga
create_clock -name altera_reserved_tck -period 40.0 [get_ports altera_reserved_tck]
# Os dois relogios nao tem relacao: a ponte atravessa com filas em codigo Gray
set_clock_groups -asynchronous -group [get_clocks clk] -group [get_clocks altera_reserved_tck]
# O LED e a chave sao lentos: sem exigencia de tempo nos pinos
set_false_path -from [get_ports reinicio]
set_false_path -to [get_ports led_*]
derive_clock_uncertainty

# Relogio da placa: CLOCK_50, 50 MHz
create_clock -name clk -period 20.0 [get_ports CLOCK_50]
# Botoes, chaves, displays e LEDs sao lentos: sem exigencia de tempo nos pinos
set_false_path -from [get_ports {KEY[*] SW[*]}]
set_false_path -to [get_ports {HEX*[*] LEDR[*]}]
derive_clock_uncertainty

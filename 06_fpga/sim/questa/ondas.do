# LEAKMAP Edge - sinais principais do testbench da placa pelo JTAG.
onerror {resume}
add wave -divider "Placa: relogio, chave e LEDs"
add wave /tb_leakmap_jtag/clk /tb_leakmap_jtag/reinicio
add wave /tb_leakmap_jtag/led_vivo /tb_leakmap_jtag/led_ocupado /tb_leakmap_jtag/led_resultado /tb_leakmap_jtag/led_erro
add wave -divider "JTAG virtual (modelo do sld_virtual_jtag)"
add wave /tb_leakmap_jtag/dut/u_jtag/tck /tb_leakmap_jtag/dut/u_jtag/tdi /tb_leakmap_jtag/dut/u_jtag/tdo
add wave -radix unsigned /tb_leakmap_jtag/dut/u_jtag/ir_in
add wave /tb_leakmap_jtag/dut/u_jtag/virtual_state_cdr /tb_leakmap_jtag/dut/u_jtag/virtual_state_sdr
add wave -divider "Ponte: bytes entre o JTAG e o nucleo"
add wave -radix hex /tb_leakmap_jtag/dut/u_ponte/rx_dado
add wave /tb_leakmap_jtag/dut/u_ponte/rx_valido /tb_leakmap_jtag/dut/u_ponte/rx_pronto
add wave -radix hex /tb_leakmap_jtag/dut/u_ponte/tx_dado
add wave /tb_leakmap_jtag/dut/u_ponte/tx_valido /tb_leakmap_jtag/dut/u_ponte/tx_pronto
add wave -divider "Nucleo e detectores"
add wave -radix unsigned /tb_leakmap_jtag/dut/u_nucleo/estado
add wave /tb_leakmap_jtag/dut/u_nucleo/u_det_a/detectou
add wave -radix unsigned /tb_leakmap_jtag/dut/u_nucleo/u_det_a/indice_cruzamento /tb_leakmap_jtag/dut/u_nucleo/u_det_a/indice_chegada
add wave /tb_leakmap_jtag/dut/u_nucleo/u_det_b/detectou
add wave -radix unsigned /tb_leakmap_jtag/dut/u_nucleo/u_det_b/indice_cruzamento /tb_leakmap_jtag/dut/u_nucleo/u_det_b/indice_chegada
configure wave -namecolwidth 320
configure wave -timelineunits us

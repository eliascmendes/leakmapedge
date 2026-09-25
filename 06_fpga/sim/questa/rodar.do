# LEAKMAP Edge - testbench completo da placa pelo JTAG, no Questa.
#
# No Questa (o Questa Starter vem com o Quartus Prime Lite):
#   1. File > Change Directory > esta pasta (06_fpga/sim/questa)
#   2. no Transcript:  do rodar.do
# Abre a forma de onda dos sinais principais (ondas.do) e roda ate o fim. O
# resultado sai no Transcript, na linha "RESULTADO tb_leakmap_jtag ...".
# Sem janela:  vsim -c -do "do rodar.do; quit -f"   (ou python ../rodar_questa.py)
#
# O Questa nao consegue gravar a biblioteca de trabalho num caminho com acento
# ("Area de Trabalho" com acento), entao os arquivos sao copiados para
# %TEMP%\leakmap_questa (ou para LEAKMAP_QUESTA_TRABALHO, se definida) e
# compilados la. O topo que vai para a DE10-Standard entra sem alteracao; so o
# sld_virtual_jtag da Intel e trocado pelo modelo de ../modelos.

set origem [pwd]
if {![file exists [file join $origem roteiro_jtag.hex]]} {
    error "rode de dentro da pasta 06_fpga/sim/questa: File > Change Directory"
}
set fpga [file normalize [file join $origem .. ..]]
if {[info exists ::env(LEAKMAP_QUESTA_TRABALHO)]} {
    set trabalho $::env(LEAKMAP_QUESTA_TRABALHO)
} else {
    set trabalho [file join $::env(TEMP) leakmap_questa]
}
set fontes {
    rtl/leakmap_multiplicador.v
    rtl/leakmap_detector.v
    rtl/leakmap_nucleo.v
    rtl/leakmap_ponte_jtag.v
    placas/intel/leakmap_topo_jtag.v
    sim/modelos/sld_virtual_jtag.v
    sim/tb_leakmap_jtag.v
}
file mkdir $trabalho
foreach f [concat $fontes {sim/questa/roteiro_jtag.hex sim/questa/ondas.do}] {
    file copy -force [file join $fpga $f] $trabalho
}
cd $trabalho
if {[file exists work]} { vdel -lib work -all }
vlib work
set arquivos {}
foreach f $fontes { lappend arquivos [file tail $f] }
eval vlog -quiet $arquivos
vsim -quiet -voptargs="+acc" -onfinish stop work.tb_leakmap_jtag +roteiro=roteiro_jtag.hex
if {![batch_mode]} { do ondas.do }
run -all

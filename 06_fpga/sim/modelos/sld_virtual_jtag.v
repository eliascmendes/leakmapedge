`timescale 1ns / 1ps
// LEAKMAP Edge - modelo de simulacao do sld_virtual_jtag da Intel, so para testbench.
//
// Tem o mesmo nome, os mesmos parametros e as mesmas portas que o modulo da
// Intel usado em 06_fpga/placas/intel/leakmap_topo_jtag.v, entao o topo e
// simulado sem nenhuma alteracao. No lugar do cabo USB-Blaster e do hub JTAG
// da FPGA, duas tarefas fazem o que o quartus_stp faz na placa:
//
//   ir_scan(valor)                         -> device_virtual_ir_shift
//   dr_scan(comprimento, entrada, saida)   -> device_virtual_dr_shift
//
// Em dr_scan, o bit 0 de `entrada` e o primeiro a entrar pelo tdi, e o bit i de
// `saida` e o que o tdo mostrava antes da i-esima borda de subida do tck. Os
// sinais virtual_state_* seguem a ordem dos estados do JTAG: captura (cdr) por
// uma borda, deslocamento (sdr) por `comprimento` bordas, depois exit1 e update.
//
// O tck so anda durante as tarefas, como na placa, com periodo de 74 ns (cerca
// de 13,5 MHz; o USB-Blaster II vai ate 24 MHz) e sem relacao de fase com o
// relogio da placa. Nao entra na sintese: na placa vale o modulo da Intel.
//
// Como o hub JTAG da Intel na DE10-Standard (medido na placa em 25/09/2026), o
// que entra pelo tdi chega ATRASO_TDI bordas depois do comeco do deslocamento,
// com zeros antes; o tdo sai alinhado. O padrao e 7, o valor da placa; o
// argumento +atraso_tdi=N troca.
`default_nettype none

module sld_virtual_jtag #(
    parameter          sld_auto_instance_index = "YES",
    parameter integer  sld_instance_index      = 0,
    parameter integer  sld_ir_width            = 2
) (
    output reg                     tck,
    output reg                     tdi,
    input  wire                    tdo,
    output reg  [sld_ir_width-1:0] ir_in,
    input  wire [sld_ir_width-1:0] ir_out,
    output reg                     virtual_state_cdr,
    output reg                     virtual_state_sdr,
    output reg                     virtual_state_e1dr,
    output reg                     virtual_state_pdr,
    output reg                     virtual_state_e2dr,
    output reg                     virtual_state_udr,
    output reg                     virtual_state_cir,
    output reg                     virtual_state_uir
);
    localparam integer MAXIMO    = 2048;   // bits por deslocamento
    localparam integer MEIO_TCK  = 37;     // ns

    integer atraso_tdi;

    initial begin
        if (!$value$plusargs("atraso_tdi=%d", atraso_tdi)) atraso_tdi = 7;
        tck = 1'b0;
        tdi = 1'b0;
        ir_in = {sld_ir_width{1'b0}};
        virtual_state_cdr  = 1'b0;
        virtual_state_sdr  = 1'b0;
        virtual_state_e1dr = 1'b0;
        virtual_state_pdr  = 1'b0;
        virtual_state_e2dr = 1'b0;
        virtual_state_udr  = 1'b0;
        virtual_state_cir  = 1'b0;
        virtual_state_uir  = 1'b0;
    end

    task pulso;
        begin
            #MEIO_TCK tck = 1'b1;
            #MEIO_TCK tck = 1'b0;
        end
    endtask

    // instrucao virtual: captura, deslocamento pelo hub e atualizacao
    task ir_scan;
        input [sld_ir_width-1:0] valor;
        begin
            virtual_state_cir = 1'b1;
            pulso;
            virtual_state_cir = 1'b0;
            repeat (sld_ir_width + 10) pulso;
            ir_in = valor;
            virtual_state_uir = 1'b1;
            pulso;
            virtual_state_uir = 1'b0;
        end
    endtask

    // registro de dados: devolve em `saida` o que saiu pelo tdo
    task dr_scan;
        input  integer          comprimento;
        input  [MAXIMO-1:0]     entrada;
        output [MAXIMO-1:0]     saida;
        integer i;
        begin
            saida = {MAXIMO{1'b0}};
            virtual_state_cdr = 1'b1;
            pulso;
            virtual_state_cdr = 1'b0;
            virtual_state_sdr = 1'b1;
            for (i = 0; i < comprimento; i = i + 1) begin
                tdi = (i < atraso_tdi) ? 1'b0 : entrada[i - atraso_tdi];
                saida[i] = tdo;
                pulso;
            end
            virtual_state_sdr  = 1'b0;
            virtual_state_e1dr = 1'b1;
            pulso;
            virtual_state_e1dr = 1'b0;
            virtual_state_udr  = 1'b1;
            pulso;
            virtual_state_udr  = 1'b0;
            repeat (2) pulso;
        end
    endtask
endmodule

`default_nettype wire

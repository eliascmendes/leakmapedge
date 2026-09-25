`timescale 1ns / 1ps
// LEAKMAP Edge - topo para placas Intel, conversando pelo cabo de gravacao.
//
// O computador fala com a placa pelo mesmo cabo USB-Blaster que grava a
// FPGA, pelo JTAG virtual da Intel (sld_virtual_jtag). Nao precisa de
// adaptador serial nem de fio nos pinos. E o unico arquivo do projeto com
// modulo de fabricante; a ponte (rtl/leakmap_ponte_jtag.v), o nucleo e o
// detector sao os mesmos Verilog puros de 06_fpga/rtl.
//
// Pinos: clk, reinicio (ativo alto; numa chave deixada em 0) e quatro LEDs.
`default_nettype none

module leakmap_topo_jtag #(
    parameter integer MAX_AMOSTRAS  = 4096,
    parameter integer BITS_ENDERECO = 12
) (
    input  wire clk,
    input  wire reinicio,
    output wire led_vivo,             // pisca: o projeto esta rodando
    output wire led_ocupado,          // tratando mensagem ou executando
    output wire led_resultado,        // ha resultado esperando confirmacao
    output wire led_erro              // a fila de entrada transbordou
);
    // reinicio na energizacao, como em leakmap_topo.v
    reg [7:0] contagem_reinicio = 8'd0;
    reg       rst = 1'b1;
    always @(posedge clk) begin
        if (reinicio) begin
            contagem_reinicio <= 8'd0;
            rst               <= 1'b1;
        end else if (contagem_reinicio != 8'hFF) begin
            contagem_reinicio <= contagem_reinicio + 8'd1;
            rst               <= 1'b1;
        end else begin
            rst <= 1'b0;
        end
    end

    // --- JTAG virtual da Intel ------------------------------------------------------
    wire       tck, tdi, tdo, captura_dr, desloca_dr;
    wire [1:0] ir_in;

    sld_virtual_jtag #(
        .sld_auto_instance_index("YES"),
        .sld_instance_index(0),
        .sld_ir_width(2)
    ) u_jtag (
        .tck(tck),
        .tdi(tdi),
        .tdo(tdo),
        .ir_in(ir_in),
        .ir_out(2'b00),
        .virtual_state_cdr(captura_dr),
        .virtual_state_sdr(desloca_dr),
        .virtual_state_e1dr(),
        .virtual_state_pdr(),
        .virtual_state_e2dr(),
        .virtual_state_udr(),
        .virtual_state_cir(),
        .virtual_state_uir()
    );

    // --- ponte e nucleo --------------------------------------------------------------
    wire [7:0] rx_dado, tx_dado;
    wire       rx_valido, rx_pronto, tx_valido, tx_pronto;

    leakmap_ponte_jtag u_ponte (
        .tck(tck), .tdi(tdi), .tdo(tdo), .ir_in(ir_in),
        .captura_dr(captura_dr), .desloca_dr(desloca_dr),
        .clk(clk), .rx_dado(rx_dado), .rx_valido(rx_valido), .rx_pronto(rx_pronto),
        .tx_dado(tx_dado), .tx_valido(tx_valido), .tx_pronto(tx_pronto),
        .transbordou(led_erro));

    leakmap_nucleo #(.MAX_AMOSTRAS(MAX_AMOSTRAS), .BITS_ENDERECO(BITS_ENDERECO)) u_nucleo (
        .clk(clk), .rst(rst),
        .rx_dado(rx_dado), .rx_valido(rx_valido), .rx_pronto(rx_pronto),
        .tx_dado(tx_dado), .tx_valido(tx_valido), .tx_pronto(tx_pronto),
        .ocupado(led_ocupado), .resultado_pendente(led_resultado));

    reg [26:0] pisca = 27'd0;
    always @(posedge clk) pisca <= pisca + 27'd1;
    assign led_vivo = pisca[26];
endmodule

`default_nettype wire

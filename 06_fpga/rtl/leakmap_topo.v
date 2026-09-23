`timescale 1ns / 1ps
// LEAKMAP Edge - modulo de topo do cenario B.
//
// Liga a serial ao nucleo. E o unico modulo que conversa com os pinos da
// placa, e mesmo assim sem nada especifico de fabricante: a frequencia do
// relogio e a velocidade da serial sao parametros, e o reinicio vem de um
// contador interno ligado na energizacao, mais uma entrada opcional.
//
// Para cada placa basta um arquivo de pinos (XDC no Vivado, QSF no Quartus)
// que ligue:  clk, reinicio (botao, ativo alto; amarrar em 0 se nao houver),
//             uart_rx, uart_tx e os LEDs.
`default_nettype none

module leakmap_topo #(
    parameter integer FREQUENCIA_HZ = 100_000_000,
    parameter integer BAUD          = 115_200,
    parameter integer MAX_AMOSTRAS  = 4096,
    parameter integer BITS_ENDERECO = 12
) (
    input  wire clk,
    input  wire reinicio,
    input  wire uart_rx,
    output wire uart_tx,
    output wire led_vivo,             // pisca: o projeto esta rodando
    output wire led_ocupado,          // tratando mensagem ou executando
    output wire led_resultado,        // ha resultado esperando confirmacao
    output wire led_erro              // a fila de entrada transbordou
);
    localparam integer CICLOS_POR_BIT = FREQUENCIA_HZ / BAUD;

    // reinicio na energizacao, sem depender de botao da placa
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

    wire [7:0] rx_byte;
    wire       rx_byte_valido;
    wire [7:0] fila_dado;
    wire       fila_valido;
    wire       nucleo_pronto;
    wire [7:0] tx_byte;
    wire       tx_byte_valido;
    wire       tx_livre;
    wire       transbordou;

    leakmap_uart_rx #(.CICLOS_POR_BIT(CICLOS_POR_BIT)) u_rx (
        .clk(clk), .rst(rst), .rx(uart_rx), .dado(rx_byte), .valido(rx_byte_valido));

    leakmap_fila u_fila (
        .clk(clk), .rst(rst),
        .entra_dado(rx_byte), .entra_valido(rx_byte_valido),
        .sai_dado(fila_dado), .sai_valido(fila_valido), .sai_pronto(nucleo_pronto),
        .transbordou(transbordou));

    leakmap_nucleo #(.MAX_AMOSTRAS(MAX_AMOSTRAS), .BITS_ENDERECO(BITS_ENDERECO)) u_nucleo (
        .clk(clk), .rst(rst),
        .rx_dado(fila_dado), .rx_valido(fila_valido), .rx_pronto(nucleo_pronto),
        .tx_dado(tx_byte), .tx_valido(tx_byte_valido), .tx_pronto(tx_livre),
        .ocupado(led_ocupado), .resultado_pendente(led_resultado));

    leakmap_uart_tx #(.CICLOS_POR_BIT(CICLOS_POR_BIT)) u_tx (
        .clk(clk), .rst(rst), .dado(tx_byte), .valido(tx_byte_valido),
        .pronto(tx_livre), .tx(uart_tx));

    reg [26:0] pisca = 27'd0;
    always @(posedge clk) pisca <= pisca + 27'd1;
    assign led_vivo = pisca[26];
    assign led_erro = transbordou;
endmodule

`default_nettype wire

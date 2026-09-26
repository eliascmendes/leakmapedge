`timescale 1ns / 1ps
// LEAKMAP Edge - autoteste de um canal, amostra a amostra.
//
// Acompanha os codigos que chegam ao detector e guarda o que denuncia um
// canal doente: menor e maior codigo, maior sequencia de codigos iguais
// (canal congelado), maior variacao entre duas amostras seguidas (salto que
// nenhuma onda faz) e quantas amostras cairam no extremo da palavra, 0 ou
// 65 535 (saturacao). As bandeiras saem dos limites, sempre atualizadas:
//
//   bit 0  congelado      maior_sequencia >= limite_congelado (0 = nao confere)
//   bit 1  saturado       alguma amostra em 0 ou 65 535
//   bit 2  fora da faixa  codigo_min < codigo_minimo ou codigo_max > codigo_maximo
//   bit 3  salto          maior_variacao > limite_salto (0 = nao confere)
//
// A referencia e a classe SaudeDoCanal de 06_fpga/computador/placa_referencia.py
// e protocolo.bandeiras_de_saude. `preparar` zera tudo; `amostra` (um ciclo)
// entrega `codigo`, no mesmo ciclo em que o detector o recebe. As contagens
// sao de 16 bits: servem para ate 65 535 amostras por execucao.
`default_nettype none

module leakmap_saude (
    input  wire        clk,
    input  wire        rst,
    input  wire        preparar,
    input  wire        amostra,
    input  wire [15:0] codigo,
    input  wire [15:0] limite_congelado,
    input  wire [15:0] codigo_minimo,
    input  wire [15:0] codigo_maximo,
    input  wire [15:0] limite_salto,
    output reg  [15:0] codigo_min,
    output reg  [15:0] codigo_max,
    output reg  [15:0] maior_sequencia,
    output reg  [15:0] maior_variacao,
    output reg  [15:0] no_extremo,
    output wire [3:0]  bandeiras
);
    reg        primeira;
    reg [15:0] anterior;
    reg [15:0] sequencia;

    wire [15:0] variacao  = (codigo >= anterior) ? codigo - anterior : anterior - codigo;
    wire [15:0] seguinte  = (codigo == anterior) ? sequencia + 16'd1 : 16'd1;
    wire        extremo   = (codigo == 16'h0000) || (codigo == 16'hFFFF);

    assign bandeiras[0] = (limite_congelado != 16'd0) && (maior_sequencia >= limite_congelado);
    assign bandeiras[1] = (no_extremo != 16'd0);
    assign bandeiras[2] = (codigo_min < codigo_minimo) || (codigo_max > codigo_maximo);
    assign bandeiras[3] = (limite_salto != 16'd0) && (maior_variacao > limite_salto);

    always @(posedge clk) begin
        if (rst || preparar) begin
            primeira        <= 1'b1;
            anterior        <= 16'd0;
            sequencia       <= 16'd0;
            codigo_min      <= 16'd0;
            codigo_max      <= 16'd0;
            maior_sequencia <= 16'd0;
            maior_variacao  <= 16'd0;
            no_extremo      <= 16'd0;
        end else if (amostra) begin
            primeira   <= 1'b0;
            anterior   <= codigo;
            no_extremo <= no_extremo + (extremo ? 16'd1 : 16'd0);
            if (primeira) begin
                codigo_min      <= codigo;
                codigo_max      <= codigo;
                sequencia       <= 16'd1;
                maior_sequencia <= 16'd1;
            end else begin
                if (codigo < codigo_min) codigo_min <= codigo;
                if (codigo > codigo_max) codigo_max <= codigo;
                sequencia <= seguinte;
                if (seguinte > maior_sequencia) maior_sequencia <= seguinte;
                if (variacao > maior_variacao)  maior_variacao  <= variacao;
            end
        end
    end
endmodule

`default_nettype wire

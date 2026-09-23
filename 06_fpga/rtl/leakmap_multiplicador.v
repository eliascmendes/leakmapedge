`timescale 1ns / 1ps
// LEAKMAP Edge - multiplicador sequencial sem sinal (soma e deslocamento).
//
// Um bit do multiplicador por ciclo, com saida antecipada quando os bits
// restantes sao zero. Em vez de um multiplicador combinacional de 64 x 32
// bits, que cada fabricante sintetiza de um jeito e que pode nao fechar tempo
// em 100 MHz, e um somador de largura WA + WB por ciclo: portatil entre
// Spartan-7 e Cyclone V e folgado em tempo. A taxa de amostragem do ensaio e
// baixa e a reproducao vem da memoria, entao a latencia nao importa.
//
// Protocolo: `iniciar` em nivel alto por um ciclo com o modulo livre; `pronto`
// pulsa por um ciclo com `produto` valido. `produto` fica estavel ate a
// proxima multiplicacao.
`default_nettype none

module leakmap_multiplicador #(
    parameter integer WA = 64,
    parameter integer WB = 32
) (
    input  wire                 clk,
    input  wire                 rst,
    input  wire                 iniciar,
    input  wire [WA-1:0]        a,
    input  wire [WB-1:0]        b,
    output reg  [WA+WB-1:0]     produto,
    output reg                  pronto,
    output wire                 ocupado
);
    reg [WA+WB-1:0] acumulado;
    reg [WA+WB-1:0] a_deslocado;
    reg [WB-1:0]    b_deslocado;
    reg             trabalhando;

    assign ocupado = trabalhando;

    always @(posedge clk) begin
        if (rst) begin
            trabalhando <= 1'b0;
            pronto      <= 1'b0;
            produto     <= {(WA+WB){1'b0}};
        end else begin
            pronto <= 1'b0;
            if (!trabalhando) begin
                if (iniciar) begin
                    acumulado   <= {(WA+WB){1'b0}};
                    a_deslocado <= {{WB{1'b0}}, a};
                    b_deslocado <= b;
                    trabalhando <= 1'b1;
                end
            end else if (b_deslocado == {WB{1'b0}}) begin
                produto     <= acumulado;
                pronto      <= 1'b1;
                trabalhando <= 1'b0;
            end else begin
                if (b_deslocado[0])
                    acumulado <= acumulado + a_deslocado;
                a_deslocado <= a_deslocado << 1;
                b_deslocado <= b_deslocado >> 1;
            end
        end
    end
endmodule

`default_nettype wire

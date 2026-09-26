`timescale 1ns / 1ps
// LEAKMAP Edge - um digito num display de 7 segmentos, segmentos ativos em 0.
//
// segmentos[0] = a, [1] = b, ..., [6] = g, como nas placas da Terasic.
// Digitos 0 a 9; 4'hA = apagado; 4'hB = traco (so o g); 4'hE = E; e as letras do
// autoteste: 4'hC = A, 4'hD = b, 4'hF = F.
`default_nettype none

module leakmap_sete_segmentos (
    input  wire [3:0] digito,
    output reg  [6:0] segmentos
);
    always @(*) begin
        case (digito)                  //  gfedcba, 1 = aceso
            4'd0:    segmentos = ~7'b0111111;
            4'd1:    segmentos = ~7'b0000110;
            4'd2:    segmentos = ~7'b1011011;
            4'd3:    segmentos = ~7'b1001111;
            4'd4:    segmentos = ~7'b1100110;
            4'd5:    segmentos = ~7'b1101101;
            4'd6:    segmentos = ~7'b1111101;
            4'd7:    segmentos = ~7'b0000111;
            4'd8:    segmentos = ~7'b1111111;
            4'd9:    segmentos = ~7'b1101111;
            4'hB:    segmentos = ~7'b1000000;
            4'hC:    segmentos = ~7'b1110111;
            4'hD:    segmentos = ~7'b1111100;
            4'hE:    segmentos = ~7'b1111001;
            4'hF:    segmentos = ~7'b1110001;
            default: segmentos = ~7'b0000000;
        endcase
    end
endmodule

// Numero de 0 a 255 em tres digitos decimais, com os zeros a esquerda apagados.
module leakmap_tres_digitos (
    input  wire [7:0] valor,
    output wire [3:0] centena,
    output wire [3:0] dezena,
    output wire [3:0] unidade
);
    wire [7:0] c = valor / 8'd100;
    wire [7:0] d = (valor % 8'd100) / 8'd10;
    wire [7:0] u = valor % 8'd10;
    assign centena = (c == 0) ? 4'hA : c[3:0];
    assign dezena  = (c == 0 && d == 0) ? 4'hA : d[3:0];
    assign unidade = u[3:0];
endmodule

`default_nettype wire

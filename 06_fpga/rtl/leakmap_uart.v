`timescale 1ns / 1ps
// LEAKMAP Edge - serial assincrona 8N1 (8 bits de dado, sem paridade, 1 de parada).
//
// CICLOS_POR_BIT = frequencia do relogio / baud. Com relogio de 100 MHz e
// 115 200 bits/s, 868; com 50 MHz, 434. Sem nada especifico de fabricante.
`default_nettype none

module leakmap_uart_rx #(
    parameter integer CICLOS_POR_BIT = 868
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] dado,
    output reg        valido          // um ciclo por byte recebido
);
    localparam integer LARGURA = $clog2(CICLOS_POR_BIT + 1);
    localparam [1:0] OCIOSO = 2'd0, INICIO = 2'd1, DADOS = 2'd2, PARADA = 2'd3;

    reg [1:0]         estado;
    reg [LARGURA-1:0] contador;
    reg [2:0]         bit_atual;
    reg [7:0]         deslocado;
    reg               rx_1, rx_2;       // sincronizador de dois estagios

    always @(posedge clk) begin
        rx_1 <= rx;
        rx_2 <= rx_1;
        valido <= 1'b0;
        if (rst) begin
            estado <= OCIOSO;
            rx_1   <= 1'b1;
            rx_2   <= 1'b1;
        end else case (estado)
            OCIOSO: if (!rx_2) begin
                contador <= CICLOS_POR_BIT / 2;
                estado   <= INICIO;
            end
            INICIO: if (contador == 0) begin
                if (!rx_2) begin               // bit de partida confirmado no meio
                    contador  <= CICLOS_POR_BIT - 1;
                    bit_atual <= 3'd0;
                    estado    <= DADOS;
                end else begin
                    estado <= OCIOSO;
                end
            end else contador <= contador - 1'b1;
            DADOS: if (contador == 0) begin
                deslocado <= {rx_2, deslocado[7:1]};
                contador  <= CICLOS_POR_BIT - 1;
                if (bit_atual == 3'd7) estado <= PARADA;
                bit_atual <= bit_atual + 3'd1;
            end else contador <= contador - 1'b1;
            PARADA: if (contador == 0) begin
                if (rx_2) begin
                    dado   <= deslocado;
                    valido <= 1'b1;
                end
                estado <= OCIOSO;
            end else contador <= contador - 1'b1;
        endcase
    end
endmodule

module leakmap_uart_tx #(
    parameter integer CICLOS_POR_BIT = 868
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] dado,
    input  wire       valido,
    output wire       pronto,
    output reg        tx
);
    localparam integer LARGURA = $clog2(CICLOS_POR_BIT + 1);

    reg [LARGURA-1:0] contador;
    reg [3:0]         bits_restantes;
    reg [9:0]         quadro;
    reg               enviando;

    assign pronto = !enviando;

    always @(posedge clk) begin
        if (rst) begin
            enviando <= 1'b0;
            tx       <= 1'b1;
        end else if (!enviando) begin
            tx <= 1'b1;
            if (valido) begin
                quadro         <= {1'b1, dado, 1'b0};   // parada, dado, partida
                bits_restantes <= 4'd10;
                contador       <= 0;
                enviando       <= 1'b1;
            end
        end else if (contador == 0) begin
            if (bits_restantes == 4'd0) begin
                enviando <= 1'b0;
            end else begin
                tx             <= quadro[0];
                quadro         <= {1'b1, quadro[9:1]};
                bits_restantes <= bits_restantes - 4'd1;
                contador       <= CICLOS_POR_BIT - 1;
            end
        end else begin
            contador <= contador - 1'b1;
        end
    end
endmodule

// Fila de bytes entre a serial e o nucleo, para nenhum byte se perder
// enquanto o nucleo trata uma mensagem.
module leakmap_fila #(
    parameter integer BITS = 9            // 512 bytes
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] entra_dado,
    input  wire       entra_valido,
    output wire [7:0] sai_dado,
    output wire       sai_valido,
    input  wire       sai_pronto,
    output reg        transbordou
);
    reg [7:0]    memoria [0:(1<<BITS)-1];
    reg [BITS:0] escrita, leitura;

    wire vazia = (escrita == leitura);
    wire cheia = (escrita[BITS-1:0] == leitura[BITS-1:0]) && (escrita[BITS] != leitura[BITS]);

    assign sai_dado   = memoria[leitura[BITS-1:0]];
    assign sai_valido = !vazia;

    always @(posedge clk) begin
        if (rst) begin
            escrita     <= 0;
            leitura     <= 0;
            transbordou <= 1'b0;
        end else begin
            if (entra_valido) begin
                if (cheia) transbordou <= 1'b1;
                else begin
                    memoria[escrita[BITS-1:0]] <= entra_dado;
                    escrita <= escrita + 1'b1;
                end
            end
            if (sai_valido && sai_pronto)
                leitura <= leitura + 1'b1;
        end
    end
endmodule

`default_nettype wire

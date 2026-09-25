`timescale 1ns / 1ps
// LEAKMAP Edge - ponte entre o JTAG virtual e o nucleo, sem nada de fabricante.
//
// Deixa o computador conversar com a placa pelo mesmo cabo USB que grava a
// FPGA, sem adaptador serial e sem fio nos pinos. O modulo de fabricante que
// expoe a cadeia JTAG (na Intel, sld_virtual_jtag) fica no topo da placa, em
// 06_fpga/placas; esta ponte so recebe os sinais dele e entrega ao nucleo a
// mesma interface de bytes que a serial entrega. As mensagens nao mudam.
//
// Registradores, escolhidos pela instrucao virtual (ir_in):
//   1  ESCREVER  cada 8 bits deslocados viram um byte na fila de entrada;
//   2  LER       devolve 8 + 8*LER_MAX bits: primeiro n, quantos bytes vem a
//                seguir (no maximo LER_MAX), depois os bytes;
//   3  ESTADO    32 bits: 16'h4C4B ("LK"), a versao e a bandeira de
//                transbordo da fila de entrada.
// Em todos, o primeiro bit deslocado e o menos significativo do primeiro byte.
//
// As duas filas atravessam entre o relogio do JTAG (tck) e o relogio da placa
// com ponteiros em codigo Gray, cada lado com dois registradores de
// sincronismo. O tck so anda enquanto o computador desloca bits; por isso as
// filas nao tem reinicio e partem do valor de energizacao.
`default_nettype none

module leakmap_ponte_jtag #(
    parameter integer LER_MAX   = 64,
    parameter integer BITS_FILA = 8        // 256 bytes em cada sentido
) (
    // lado JTAG
    input  wire       tck,
    input  wire       tdi,
    output wire       tdo,
    input  wire [1:0] ir_in,
    input  wire       captura_dr,          // virtual_state_cdr
    input  wire       desloca_dr,          // virtual_state_sdr
    // lado da placa: a mesma interface de bytes da serial
    input  wire       clk,
    output wire [7:0] rx_dado,
    output wire       rx_valido,
    input  wire       rx_pronto,
    input  wire [7:0] tx_dado,
    input  wire       tx_valido,
    output wire       tx_pronto,
    output wire       transbordou          // no relogio da placa, para um LED
);
    localparam [1:0] IR_ESCREVER = 2'd1, IR_LER = 2'd2, IR_ESTADO = 2'd3;
    localparam [7:0] VERSAO = 8'd1;

    // --- computador -> placa ------------------------------------------------------
    reg  [7:0] byte_entra = 8'd0;
    reg  [2:0] bit_entra  = 3'd0;
    reg        perdeu_entrada = 1'b0;
    wire       entrada_cheia;
    wire       empurrar = desloca_dr && ir_in == IR_ESCREVER && bit_entra == 3'd7;

    leakmap_fila_dupla #(.BITS(BITS_FILA)) u_entrada (
        .clk_e(tck), .entra_dado({tdi, byte_entra[7:1]}), .entra_valido(empurrar),
        .cheia(entrada_cheia),
        .clk_s(clk), .sai_dado(rx_dado), .sai_valido(rx_valido), .sai_pronto(rx_pronto),
        .disponiveis_s());

    // --- placa -> computador ------------------------------------------------------
    wire [7:0]         saida_dado;
    wire               saida_valida;
    wire               saida_cheia;
    wire [BITS_FILA:0] saida_disponiveis;
    reg  [7:0]         registro = 8'd0;     // bits saindo pelo tdo
    reg  [2:0]         bit_sai  = 3'd0;
    reg  [7:0]         n_ler = 8'd0, entregues = 8'd0;
    wire               puxar = desloca_dr && ir_in == IR_LER && bit_sai == 3'd7 && entregues < n_ler;
    wire [7:0]         n_agora = (saida_disponiveis > LER_MAX) ? LER_MAX[7:0] : saida_disponiveis[7:0];

    leakmap_fila_dupla #(.BITS(BITS_FILA)) u_saida (
        .clk_e(clk), .entra_dado(tx_dado), .entra_valido(tx_valido), .cheia(saida_cheia),
        .clk_s(tck), .sai_dado(saida_dado), .sai_valido(saida_valida), .sai_pronto(puxar),
        .disponiveis_s(saida_disponiveis));

    assign tx_pronto = !saida_cheia;

    // --- deslocamento -------------------------------------------------------------
    reg [31:0] estado  = 32'd0;
    reg        passagem = 1'b0;             // instrucao sem registro: um bit

    always @(posedge tck) begin
        if (captura_dr) begin
            bit_entra <= 3'd0;
            bit_sai   <= 3'd0;
            entregues <= 8'd0;
            n_ler     <= n_agora;
            registro  <= n_agora;           // o primeiro byte lido e a quantidade
            estado    <= {16'h4C4B, VERSAO, 7'd0, perdeu_entrada};
        end else if (desloca_dr) begin
            case (ir_in)
                IR_ESCREVER: begin
                    byte_entra <= {tdi, byte_entra[7:1]};
                    bit_entra  <= bit_entra + 3'd1;
                    if (empurrar && entrada_cheia) perdeu_entrada <= 1'b1;
                end
                IR_LER: begin
                    bit_sai <= bit_sai + 3'd1;
                    if (bit_sai == 3'd7) begin
                        // acabou um byte: o proximo entra inteiro no registro
                        if (entregues < n_ler) begin
                            registro  <= saida_dado;
                            entregues <= entregues + 8'd1;
                        end else begin
                            registro <= 8'd0;
                        end
                    end else begin
                        registro <= {1'b0, registro[7:1]};
                    end
                end
                IR_ESTADO: estado <= {tdi, estado[31:1]};
                default:   passagem <= tdi;
            endcase
        end
    end

    assign tdo = (ir_in == IR_LER)    ? registro[0] :
                 (ir_in == IR_ESTADO) ? estado[0]   :
                 (ir_in == IR_ESCREVER) ? 1'b0      : passagem;

    // bandeira de transbordo levada para o relogio da placa
    reg [1:0] transbordou_sinc = 2'b00;
    always @(posedge clk) transbordou_sinc <= {transbordou_sinc[0], perdeu_entrada};
    assign transbordou = transbordou_sinc[1];
endmodule

// Fila de bytes entre dois relogios, com ponteiros em codigo Gray.
module leakmap_fila_dupla #(
    parameter integer BITS = 8
) (
    input  wire          clk_e,
    input  wire [7:0]    entra_dado,
    input  wire          entra_valido,
    output wire          cheia,
    input  wire          clk_s,
    output wire [7:0]    sai_dado,
    output wire          sai_valido,
    input  wire          sai_pronto,
    output wire [BITS:0] disponiveis_s
);
    reg [7:0]    memoria [0:(1<<BITS)-1];
    reg [BITS:0] esc_bin = 0, esc_gray = 0;           // lado de quem escreve
    reg [BITS:0] ler_bin = 0, ler_gray = 0;           // lado de quem le
    reg [BITS:0] ler_gray_1 = 0, ler_gray_2 = 0;      // ponteiro de leitura visto por quem escreve
    reg [BITS:0] esc_gray_1 = 0, esc_gray_2 = 0;      // ponteiro de escrita visto por quem le

    function [BITS:0] para_gray(input [BITS:0] b);
        para_gray = b ^ (b >> 1);
    endfunction

    function [BITS:0] de_gray(input [BITS:0] g);
        integer i;
        begin
            de_gray[BITS] = g[BITS];
            for (i = BITS - 1; i >= 0; i = i - 1)
                de_gray[i] = de_gray[i + 1] ^ g[i];
        end
    endfunction

    wire [BITS:0] esc_prox = esc_bin + 1'b1;
    assign cheia = (esc_gray == {~ler_gray_2[BITS:BITS-1], ler_gray_2[BITS-2:0]});

    always @(posedge clk_e) begin
        ler_gray_1 <= ler_gray;
        ler_gray_2 <= ler_gray_1;
        if (entra_valido && !cheia) begin
            memoria[esc_bin[BITS-1:0]] <= entra_dado;
            esc_bin  <= esc_prox;
            esc_gray <= para_gray(esc_prox);
        end
    end

    wire [BITS:0] ler_prox = ler_bin + 1'b1;
    assign disponiveis_s = de_gray(esc_gray_2) - ler_bin;
    assign sai_valido    = (disponiveis_s != 0);
    assign sai_dado      = memoria[ler_bin[BITS-1:0]];

    always @(posedge clk_s) begin
        esc_gray_1 <= esc_gray;
        esc_gray_2 <= esc_gray_1;
        if (sai_valido && sai_pronto) begin
            ler_bin  <= ler_prox;
            ler_gray <= para_gray(ler_prox);
        end
    end
endmodule

`default_nettype wire

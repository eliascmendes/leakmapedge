`timescale 1ns / 1ps
// LEAKMAP Edge - demonstracao autonoma na DE10-Standard, sem computador.
//
// Escolha nos botoes onde a linha rompe (40 a 160 m, entre os sensores em
// 40 m e 160 m); a placa gera os sinais dos dois sensores, entrega as amostras
// aos detectores no ritmo da amostragem, marca as chegadas e mostra a posicao.
//
//   KEY3  -10 m     KEY2  -1 m     KEY1  +1 m     KEY0  +10 m
//   SW1   ruido nos sinais (para cima = com ruido)
//   SW2   estraga o sensor A: cabo rompido      SW3   estraga o sensor B: transmissor travado
//   SW0   reinicio (para baixo em uso)
//   HEX5..HEX3  posicao escolhida, em metros
//   HEX2..HEX0  posicao que a placa calculou ("---" enquanto calcula, "E" sem as duas chegadas,
//               "F A", "F b" ou "FAb" quando o autoteste acusa o sensor A, o B ou os dois)
//   LEDR0 pisca   LEDR1 calculando   LEDR2 chegada no sensor A   LEDR3 chegada no sensor B
//   LEDR4 autoteste acusou o sensor A   LEDR5 autoteste acusou o sensor B
//
// Tudo em Verilog puro: rtl/leakmap_demo.v (gerador, detectores e posicao),
// rtl/leakmap_detector.v, rtl/leakmap_multiplicador.v, rtl/leakmap_saude.v e
// rtl/leakmap_sete_segmentos.v.
// Os sinais sao sinteticos, gerados na propria placa; a referencia e
// 06_fpga/computador/demo_autonoma.py.
`default_nettype none

module leakmap_demo_de10 #(
    parameter integer PERIODO_CICLOS   = 20065,      // periodo de amostragem a 50 MHz
    parameter integer CICLOS_DEBOUNCE  = 1_000_000   // 20 ms a 50 MHz
) (
    input  wire       CLOCK_50,
    input  wire [3:0] KEY,               // apertado = 0
    input  wire [3:0] SW,
    output wire [6:0] HEX0, HEX1, HEX2, HEX3, HEX4, HEX5,
    output wire [5:0] LEDR
);
    wire clk = CLOCK_50;

    // --- reinicio na energizacao e pela SW0 ---------------------------------------------
    reg [7:0] contagem_reinicio = 8'd0;
    reg       rst = 1'b1;
    always @(posedge clk) begin
        if (SW[0]) begin
            contagem_reinicio <= 8'd0;
            rst <= 1'b1;
        end else if (contagem_reinicio != 8'hFF) begin
            contagem_reinicio <= contagem_reinicio + 8'd1;
            rst <= 1'b1;
        end else begin
            rst <= 1'b0;
        end
    end

    // --- botoes: sincronismo, filtro de repique e borda de aperto -------------------------
    reg [3:0]  k1 = 4'hF, k2 = 4'hF, estavel = 4'hF, anterior = 4'hF;
    reg [31:0] filtro = 32'd0;
    always @(posedge clk) begin
        k1 <= KEY;
        k2 <= k1;
        if (k2 == estavel) begin
            filtro <= 32'd0;
        end else if (filtro + 32'd1 >= CICLOS_DEBOUNCE) begin
            estavel <= k2;
            filtro  <= 32'd0;
        end else begin
            filtro <= filtro + 32'd1;
        end
        anterior <= estavel;
    end
    wire [3:0] apertou = anterior & ~estavel;       // 1 -> 0: o botao foi apertado

    reg [2:0] s1 = 3'b000, s2 = 3'b000;
    always @(posedge clk) begin
        s1 <= SW[3:1];
        s2 <= s1;
    end
    wire       ruido = s2[0];
    wire [1:0] falha = s2[2:1];                     // SW3: sensor B travado; SW2: sensor A rompido

    // --- posicao escolhida e disparo da demonstracao -----------------------------------
    reg  [7:0] posicao;
    reg        ruido_usado;
    reg  [1:0] falha_usada;
    reg        pedido;                              // houve mudanca: rodar de novo
    wire       ocupado, pronto, det_a, det_b;
    wire [7:0] estimada;
    wire [3:0] saude_a, saude_b;
    wire       iniciar = pedido && !ocupado;

    function [7:0] somar;
        input [7:0]  p;
        input signed [8:0] passo;
        reg signed [9:0] r;
        begin
            r = $signed({2'b00, p}) + passo;
            if (r < 40) r = 40;
            if (r > 160) r = 160;
            somar = r[7:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            posicao     <= 8'd80;
            ruido_usado <= 1'b0;
            falha_usada <= 2'b00;
            pedido      <= 1'b1;                    // roda uma vez ao ligar
        end else begin
            if (apertou[3])      posicao <= somar(posicao, -9'sd10);
            else if (apertou[2]) posicao <= somar(posicao, -9'sd1);
            else if (apertou[1]) posicao <= somar(posicao, 9'sd1);
            else if (apertou[0]) posicao <= somar(posicao, 9'sd10);
            if (iniciar) begin
                ruido_usado <= ruido;
                falha_usada <= falha;
                pedido      <= (apertou != 4'd0);       // um aperto neste mesmo ciclo roda de novo
            end else if (apertou != 4'd0 || ruido != ruido_usado || falha != falha_usada) begin
                pedido <= 1'b1;
            end
        end
    end

    leakmap_demo #(.PERIODO_CICLOS(PERIODO_CICLOS)) u_demo (
        .clk(clk), .rst(rst), .posicao_m(posicao), .ruido(ruido), .falha(falha), .iniciar(iniciar),
        .ocupado(ocupado), .pronto(pronto), .detectou_a(det_a), .detectou_b(det_b),
        .chegada_a(), .chegada_b(), .posicao_estimada_m(estimada),
        .saude_a(saude_a), .saude_b(saude_b));

    // --- display ------------------------------------------------------------------------
    wire [3:0] e_c, e_d, e_u, r_c, r_d, r_u;
    leakmap_tres_digitos u_escolhida (.valor(posicao),  .centena(e_c), .dezena(e_d), .unidade(e_u));
    leakmap_tres_digitos u_estimada  (.valor(estimada), .centena(r_c), .dezena(r_d), .unidade(r_u));

    // o autoteste manda: com um sensor acusado, a posicao nao e mostrada
    wire calculando = ocupado || pedido || !pronto;
    wire falha_a = (saude_a != 4'd0), falha_b = (saude_b != 4'd0);
    wire acusou = falha_a || falha_b;
    wire sem_chegadas = !(det_a && det_b);
    wire [3:0] d2 = calculando ? 4'hB : acusou ? 4'hF : sem_chegadas ? 4'hA : r_c;
    wire [3:0] d1 = calculando ? 4'hB : acusou ? (falha_a ? 4'hC : 4'hA) : sem_chegadas ? 4'hA : r_d;
    wire [3:0] d0 = calculando ? 4'hB : acusou ? (falha_b ? 4'hD : 4'hA) : sem_chegadas ? 4'hE : r_u;

    leakmap_sete_segmentos u_h5 (.digito(e_c), .segmentos(HEX5));
    leakmap_sete_segmentos u_h4 (.digito(e_d), .segmentos(HEX4));
    leakmap_sete_segmentos u_h3 (.digito(e_u), .segmentos(HEX3));
    leakmap_sete_segmentos u_h2 (.digito(d2),  .segmentos(HEX2));
    leakmap_sete_segmentos u_h1 (.digito(d1),  .segmentos(HEX1));
    leakmap_sete_segmentos u_h0 (.digito(d0),  .segmentos(HEX0));

    reg [25:0] pisca = 26'd0;
    always @(posedge clk) pisca <= pisca + 26'd1;
    assign LEDR = {!calculando && falha_b, !calculando && falha_a,
                   pronto && det_b, pronto && det_a, ocupado, pisca[25]};
endmodule

`default_nettype wire

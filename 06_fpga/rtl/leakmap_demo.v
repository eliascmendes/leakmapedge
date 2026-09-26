`timescale 1ns / 1ps
// LEAKMAP Edge - demonstracao autonoma: a placa gera os sinais, detecta e localiza.
//
// Sem computador: para a posicao de rompimento `posicao_m` (40 a 160 m), gera
// os codigos dos dois sensores (em 40 m e 160 m), entrega uma amostra a cada
// PERIODO_CICLOS ciclos aos mesmos detectores do cenario B (leakmap_detector),
// marca as chegadas e calcula a posicao, em aritmetica inteira e sem divisao.
// O modelo de referencia e 06_fpga/computador/demo_autonoma.py, que manda em
// caso de duvida; as constantes vem de leakmap_demo_parametros.vh, gravado por
// ele.
//
// O sinal e sintetico e simples: carga constante e, a partir da chegada da
// onda em cada sensor, uma queda em rampa. Com `ruido`, cada canal soma um
// ruido de -3 a +4 codigos tirado de um LFSR de 16 bits.
//
// Autoteste: `falha` estraga um sensor de proposito a partir da amostra
// DEMO_AMOSTRA_FALHA (bit 0: cabo do sensor A rompido, codigo 0; bit 1:
// transmissor B travado, repete o ultimo codigo). Os dois canais passam pelo
// autoteste do cenario B (leakmap_saude.v), e `saude_a`/`saude_b` trazem as
// bandeiras no fim. O congelamento so e conferido com ruido.
//
// PERIODO_CICLOS = 0 entrega a amostra seguinte assim que os detectores
// terminam a anterior (usado nos testes); na placa, o periodo de amostragem.
`default_nettype none

module leakmap_demo #(
    parameter integer PERIODO_CICLOS = 20065
) (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  posicao_m,
    input  wire        ruido,
    input  wire [1:0]  falha,               // bit 0: sensor A rompido; bit 1: sensor B travado
    input  wire        iniciar,             // um ciclo: roda a demonstracao
    output wire        ocupado,
    output reg         pronto,              // ha resultado valido
    output reg         detectou_a,
    output reg         detectou_b,
    output reg  [15:0] chegada_a,
    output reg  [15:0] chegada_b,
    output reg  [7:0]  posicao_estimada_m,
    output reg  [3:0]  saude_a,             // bandeiras do autoteste (leakmap_saude.v)
    output reg  [3:0]  saude_b
);
    `include "leakmap_demo_parametros.vh"

    localparam [2:0] S_OCIOSO = 3'd0, S_PREP = 3'd1, S_PREP_ESPERA = 3'd2, S_GERA = 3'd3,
                     S_AMOSTRA = 3'd4, S_ESPERA = 3'd5, S_FIM = 3'd6;

    reg  [2:0]  estado;
    reg  [7:0]  posicao;
    reg         com_ruido;
    reg  [1:0]  com_falha;
    reg  [15:0] k;                    // indice da amostra
    reg  [15:0] evento_a, evento_b;   // amostra de chegada da onda em cada sensor
    reg  [15:0] lfsr_a, lfsr_b;
    reg  [15:0] codigo_a, codigo_b;
    reg  [31:0] contador;             // ciclos desde a entrega da amostra atual

    assign ocupado = (estado != S_OCIOSO);

    // --- chegada da onda em cada sensor, da distancia ate o vazamento -----------------
    wire [7:0]  dist_a = (posicao >= DEMO_SENSOR_A) ? posicao - DEMO_SENSOR_A[7:0] : DEMO_SENSOR_A[7:0] - posicao;
    wire [7:0]  dist_b = (posicao >= DEMO_SENSOR_B) ? posicao - DEMO_SENSOR_B[7:0] : DEMO_SENSOR_B[7:0] - posicao;
    wire [31:0] atraso_a = (dist_a * DEMO_AMOSTRAS_POR_M + 32768) >> 16;
    wire [31:0] atraso_b = (dist_b * DEMO_AMOSTRAS_POR_M + 32768) >> 16;

    // --- gerador: queda em rampa depois da chegada, mais o ruido ------------------------
    function [15:0] queda;
        input [15:0] indice, evento;
        reg   [15:0] passos;
        begin
            passos = (indice <= evento) ? 16'd0 : indice - evento;
            if (passos > DEMO_RAMPA) passos = DEMO_RAMPA;
            queda = passos * DEMO_PASSO_QUEDA;
        end
    endfunction

    function [15:0] passo_lfsr;
        input [15:0] s;
        passo_lfsr = s[0] ? ((s >> 1) ^ DEMO_POLINOMIO) : (s >> 1);
    endfunction

    wire [15:0] ruido_a = com_ruido ? {13'd0, lfsr_a[2:0]} : 16'd3;   // (0..7) - 3, somado com +DEMO_BASE - 3
    wire [15:0] ruido_b = com_ruido ? {13'd0, lfsr_b[2:0]} : 16'd3;

    // --- detectores, com a configuracao do modelo ---------------------------------------
    wire        preparar = (estado == S_PREP);
    wire        amostra  = (estado == S_AMOSTRA);
    wire        ocupado_a, ocupado_b, det_a, det_b;
    wire [15:0] cheg_a, cheg_b;

    leakmap_detector u_det_a (
        .clk(clk), .rst(rst),
        .cfg_coeficiente(DEMO_CFG_COEF), .cfg_fracao(DEMO_CFG_FRACAO), .cfg_desloca(DEMO_CFG_DESLOCA),
        .cfg_n_curta(DEMO_CFG_N_CURTA), .cfg_n_guarda(DEMO_CFG_N_GUARDA), .cfg_n_longa(DEMO_CFG_N_LONGA),
        .cfg_limiar(DEMO_CFG_LIMIAR), .cfg_k2(DEMO_CFG_K2), .cfg_piso(DEMO_CFG_PISO),
        .cfg_piso_energia(DEMO_CFG_PISO_ENERGIA),
        .preparar(preparar), .amostra(amostra), .codigo(codigo_a), .ocupado(ocupado_a),
        .detectou(det_a), .truncado(), .estouro(),
        .indice_cruzamento(), .indice_chegada(cheg_a), .oportunidades(),
        .s_curta_cruz(), .s_longa_cruz(), .maior_salto());

    leakmap_detector u_det_b (
        .clk(clk), .rst(rst),
        .cfg_coeficiente(DEMO_CFG_COEF), .cfg_fracao(DEMO_CFG_FRACAO), .cfg_desloca(DEMO_CFG_DESLOCA),
        .cfg_n_curta(DEMO_CFG_N_CURTA), .cfg_n_guarda(DEMO_CFG_N_GUARDA), .cfg_n_longa(DEMO_CFG_N_LONGA),
        .cfg_limiar(DEMO_CFG_LIMIAR), .cfg_k2(DEMO_CFG_K2), .cfg_piso(DEMO_CFG_PISO),
        .cfg_piso_energia(DEMO_CFG_PISO_ENERGIA),
        .preparar(preparar), .amostra(amostra), .codigo(codigo_b), .ocupado(ocupado_b),
        .detectou(det_b), .truncado(), .estouro(),
        .indice_cruzamento(), .indice_chegada(cheg_b), .oportunidades(),
        .s_curta_cruz(), .s_longa_cruz(), .maior_salto());

    // --- autoteste dos dois canais ---------------------------------------------------------
    wire [15:0] limite_congelado = com_ruido ? DEMO_SAUDE_CONGELADO : 16'd0;
    wire [3:0]  band_a, band_b;

    leakmap_saude u_saude_a (
        .clk(clk), .rst(rst), .preparar(preparar), .amostra(amostra), .codigo(codigo_a),
        .limite_congelado(limite_congelado), .codigo_minimo(DEMO_SAUDE_MINIMO),
        .codigo_maximo(DEMO_SAUDE_MAXIMO), .limite_salto(DEMO_SAUDE_SALTO),
        .codigo_min(), .codigo_max(), .maior_sequencia(), .maior_variacao(), .no_extremo(),
        .bandeiras(band_a));

    leakmap_saude u_saude_b (
        .clk(clk), .rst(rst), .preparar(preparar), .amostra(amostra), .codigo(codigo_b),
        .limite_congelado(limite_congelado), .codigo_minimo(DEMO_SAUDE_MINIMO),
        .codigo_maximo(DEMO_SAUDE_MAXIMO), .limite_salto(DEMO_SAUDE_SALTO),
        .codigo_min(), .codigo_max(), .maior_sequencia(), .maior_variacao(), .no_extremo(),
        .bandeiras(band_b));

    // --- posicao: x = 100 m + (chegada_A - chegada_B) * c * ts / 2, arredondada ao metro --
    wire signed [17:0] delta   = $signed({2'b00, cheg_a}) - $signed({2'b00, cheg_b});
    wire signed [40:0] produto = delta * $signed({1'b0, DEMO_METROS_POR_AMOS[21:0]}) + 41'sd32768;
    wire signed [40:0] metros  = 41'sd100 + (produto >>> 16);
    wire [7:0] metros_limitados = (metros < 0) ? 8'd0 : (metros > 255) ? 8'd255 : metros[7:0];

    always @(posedge clk) begin
        if (rst) begin
            estado <= S_OCIOSO;
            pronto <= 1'b0;
            detectou_a <= 1'b0;
            detectou_b <= 1'b0;
            chegada_a <= 16'd0;
            chegada_b <= 16'd0;
            posicao_estimada_m <= 8'd0;
            saude_a <= 4'd0;
            saude_b <= 4'd0;
        end else begin
            contador <= contador + 32'd1;
            case (estado)
            S_OCIOSO: if (iniciar) begin
                posicao   <= posicao_m;
                com_ruido <= ruido;
                com_falha <= falha;
                pronto    <= 1'b0;
                estado    <= S_PREP;
            end
            S_PREP: begin
                evento_a <= DEMO_AMOSTRA_EVENTO + atraso_a[15:0];
                evento_b <= DEMO_AMOSTRA_EVENTO + atraso_b[15:0];
                estado   <= S_PREP_ESPERA;
            end
            S_PREP_ESPERA: if (!ocupado_a && !ocupado_b) begin
                k      <= 16'd0;
                lfsr_a <= DEMO_SEMENTE_A;
                lfsr_b <= DEMO_SEMENTE_B;
                estado <= S_GERA;
            end
            S_GERA: begin
                if (com_falha[0] && k >= DEMO_AMOSTRA_FALHA)
                    codigo_a <= 16'd0;                           // cabo rompido
                else
                    codigo_a <= DEMO_BASE[15:0] - 16'd3 - queda(k, evento_a) + ruido_a;
                if (!(com_falha[1] && k > DEMO_AMOSTRA_FALHA))   // travado: fica o ultimo codigo
                    codigo_b <= DEMO_BASE[15:0] - 16'd3 - queda(k, evento_b) + ruido_b;
                contador <= 32'd0;
                estado   <= S_AMOSTRA;
            end
            S_AMOSTRA: estado <= S_ESPERA;               // `amostra` alto: os dois canais juntos
            // `contador` vale 0 no ciclo seguinte a S_GERA; saindo quando ele chega a
            // PERIODO - 2, a proxima S_GERA cai exatamente PERIODO ciclos depois da anterior
            S_ESPERA:
                if (!ocupado_a && !ocupado_b && (PERIODO_CICLOS == 0 || contador + 32'd2 >= PERIODO_CICLOS)) begin
                    lfsr_a <= passo_lfsr(lfsr_a);
                    lfsr_b <= passo_lfsr(lfsr_b);
                    if (k + 16'd1 == DEMO_N_AMOSTRAS) begin
                        estado <= S_FIM;
                    end else begin
                        k      <= k + 16'd1;
                        estado <= S_GERA;
                    end
                end
            S_FIM: begin
                detectou_a <= det_a;
                detectou_b <= det_b;
                chegada_a  <= det_a ? cheg_a : 16'd0;
                chegada_b  <= det_b ? cheg_b : 16'd0;
                posicao_estimada_m <= (det_a && det_b) ? metros_limitados : 8'd0;
                saude_a    <= band_a;
                saude_b    <= band_b;
                pronto     <= 1'b1;
                estado     <= S_OCIOSO;
            end
            default: estado <= S_OCIOSO;
            endcase
        end
    end
endmodule

`default_nettype wire

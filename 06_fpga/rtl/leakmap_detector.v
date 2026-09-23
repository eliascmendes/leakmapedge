`timescale 1ns / 1ps
// LEAKMAP Edge - detector de um canal em aritmetica inteira (etapas A-11, A-12 e B-09).
//
// Implementa, amostra a amostra, o mesmo algoritmo de
// 06_fpga/computador/placa_referencia.py (classe DetectorInteiro), que por sua
// vez reproduz 04_detector/detector_ponto_fixo.py. A especificacao esta em
// 06_fpga/ESPECIFICACAO.md, secao 7.
//
// Por amostra:
//   y  = (A * (y + ((x - x_anterior) << F))) >>> F      (y = 0 na primeira)
//   ye = y >>> E ;  q = ye * ye
//   s_curta = soma de q nas ultimas nc amostras
//   s_longa = soma de q de n-nc-ng-nl+1 ate n-nc-ng
//   dispara se s_curta*nl >= max(s_longa, nl*PE)*(L*nc)  e  s_curta >= nc*P*P
// No primeiro disparo, retrocede ate a amostra que sai da faixa de ruido,
// no maximo nc+ng amostras, e mede o maior salto de y nesse trecho.
//
// Memorias: anel de q com 2^BITS_JANELA posicoes (precisa de nc+ng+nl+1) e
// anel de y com 2^BITS_HIST posicoes (precisa de nc+ng+2).
//
// Estouro: qualquer soma acima de 64 bits, comparacao acima de 64 bits, |ye|
// acima de 32 bits ou salto acima de 32 bits liga `estouro`; a placa entao
// recusa o resultado (situacao 3), como a referencia.
`default_nettype none

module leakmap_detector #(
    parameter integer BITS_JANELA = 6,
    parameter integer BITS_HIST   = 4
) (
    input  wire        clk,
    input  wire        rst,
    // configuracao, estavel durante a execucao
    input  wire [31:0] cfg_coeficiente,
    input  wire [7:0]  cfg_fracao,
    input  wire [7:0]  cfg_desloca,
    input  wire [7:0]  cfg_n_curta,
    input  wire [7:0]  cfg_n_guarda,
    input  wire [7:0]  cfg_n_longa,
    input  wire [15:0] cfg_limiar,
    input  wire [15:0] cfg_k2,
    input  wire [31:0] cfg_piso,
    input  wire [31:0] cfg_piso_energia,
    // controle
    input  wire        preparar,      // um ciclo: zera o canal e calcula constantes
    input  wire        amostra,       // um ciclo: processa `codigo`
    input  wire [15:0] codigo,
    output wire        ocupado,
    // resultado
    output reg         detectou,
    output reg         truncado,
    output reg         estouro,
    output reg  [15:0] indice_cruzamento,
    output reg  [15:0] indice_chegada,
    output reg  [15:0] oportunidades,
    output reg  [63:0] s_curta_cruz,
    output reg  [63:0] s_longa_cruz,
    output reg  [31:0] maior_salto
);
    localparam [4:0]
        E_LIVRE      = 5'd0,
        E_MULT       = 5'd1,
        E_PREP_LIME  = 5'd2,
        E_PREP_PP    = 5'd3,
        E_PREP_LIMA  = 5'd4,
        E_PREP_FIM   = 5'd5,
        E_Y          = 5'd6,
        E_Y_FIM      = 5'd7,
        E_Q          = 5'd8,
        E_GRAVA      = 5'd9,
        E_CURTA      = 5'd10,
        E_LONGA_SOMA = 5'd11,
        E_LONGA_SUB  = 5'd12,
        E_VALIDA     = 5'd13,
        E_D_DIR      = 5'd14,
        E_D_DECIDE   = 5'd15,
        E_R_KREF     = 5'd16,
        E_R_PASSO    = 5'd17,
        E_R_TESTE    = 5'd18,
        E_T_I        = 5'd19,
        E_T_I1       = 5'd20,
        E_T_FIM      = 5'd21,
        E_SALTO      = 5'd22,
        E_SALTO_FIM  = 5'd23,
        E_FIM        = 5'd24;

    localparam integer TAM_JANELA = 1 << BITS_JANELA;
    localparam integer TAM_HIST   = 1 << BITS_HIST;

    reg [4:0] estado, retorno;

    // --- multiplicador compartilhado ---------------------------------------
    reg         mul_ini;
    reg  [63:0] mul_a;
    reg  [31:0] mul_b;
    wire [95:0] mul_p;
    wire        mul_pronto;
    wire        mul_ocupado;

    leakmap_multiplicador #(.WA(64), .WB(32)) u_mult (
        .clk(clk), .rst(rst), .iniciar(mul_ini), .a(mul_a), .b(mul_b),
        .produto(mul_p), .pronto(mul_pronto), .ocupado(mul_ocupado));

    // --- estado do canal ---------------------------------------------------------
    reg  [15:0]        n;
    reg  [15:0]        x;
    reg  [15:0]        x_anterior;
    reg  signed [63:0] y;
    reg  [63:0]        s_curta;
    reg  [63:0]        s_longa;
    reg  [65:0]        s_longa_parcial;
    reg  [63:0]        q;
    reg  [63:0]        referencia;
    reg  [31:0]        lnc;           // L * nc
    reg  [63:0]        lim_e;         // nl * PE
    reg  [95:0]        lim_a;         // nc * P * P
    reg  [95:0]        kref;          // K2 * referencia
    reg  [95:0]        esquerda;
    reg  [15:0]        i;
    reg  [15:0]        limite;
    reg  [15:0]        k;
    reg  [64:0]        maior;
    reg                sinal_negativo;

    reg  [63:0]        q_mem [0:TAM_JANELA-1];
    reg  signed [63:0] y_mem [0:TAM_HIST-1];

    // --- combinacional ----------------------------------------------------------------
    wire [8:0]  recuo      = cfg_n_curta + cfg_n_guarda;
    wire [9:0]  recuo_nl   = recuo + cfg_n_longa;

    wire signed [16:0] diferenca   = $signed({1'b0, x}) - $signed({1'b0, x_anterior});
    wire signed [66:0] diferenca_e = diferenca;
    wire signed [66:0] diferenca_d = diferenca_e <<< cfg_fracao;
    wire signed [66:0] y_e         = y;
    wire signed [66:0] soma        = y_e + diferenca_d;
    wire [66:0]        soma_mag    = soma[66] ? (~soma + 67'd1) : soma;

    wire signed [96:0] produto_s   = sinal_negativo ? -$signed({1'b0, mul_p}) : $signed({1'b0, mul_p});
    wire signed [96:0] produto_d   = produto_s >>> cfg_fracao;

    wire signed [63:0] ye          = y >>> cfg_desloca;
    wire [63:0]        ye_mag      = ye[63] ? (~ye + 64'd1) : ye;

    wire [BITS_JANELA-1:0] idx_curta = n[BITS_JANELA-1:0] - cfg_n_curta[BITS_JANELA-1:0];
    wire [BITS_JANELA-1:0] idx_longa_ent = n[BITS_JANELA-1:0] - recuo[BITS_JANELA-1:0];
    wire [BITS_JANELA-1:0] idx_longa_sai = n[BITS_JANELA-1:0] - recuo_nl[BITS_JANELA-1:0];

    wire [65:0] curta_nova = {2'b00, s_curta} + {2'b00, q}
                             - ((n >= cfg_n_curta) ? {2'b00, q_mem[idx_curta]} : 66'd0);

    wire [65:0] longa_nova = (n >= recuo_nl) ? (s_longa_parcial - {2'b00, q_mem[idx_longa_sai]})
                                             : s_longa_parcial;

    wire [63:0] s_efetiva  = (s_longa > lim_e) ? s_longa : lim_e;

    wire [BITS_JANELA-1:0] idx_i   = i[BITS_JANELA-1:0];
    wire [BITS_JANELA-1:0] idx_im1 = i[BITS_JANELA-1:0] - 1'b1;

    wire signed [64:0] passo_y = $signed({y_mem[k[BITS_HIST-1:0] + 1'b1][63], y_mem[k[BITS_HIST-1:0] + 1'b1]})
                               - $signed({y_mem[k[BITS_HIST-1:0]][63], y_mem[k[BITS_HIST-1:0]]});
    wire [64:0] passo_mag = passo_y[64] ? (~passo_y + 65'd1) : passo_y;

    assign ocupado = (estado != E_LIVRE) || preparar || amostra;

    // inicia uma multiplicacao e volta para `volta` com o produto em mul_p
    task multiplicar;
        input [63:0] a;
        input [31:0] b;
        input [4:0]  volta;
        begin
            mul_a   <= a;
            mul_b   <= b;
            mul_ini <= 1'b1;
            retorno <= volta;
            estado  <= E_MULT;
        end
    endtask

    always @(posedge clk) begin
        if (rst) begin
            estado            <= E_LIVRE;
            mul_ini           <= 1'b0;
            n                 <= 16'd0;
            detectou          <= 1'b0;
            truncado          <= 1'b0;
            estouro           <= 1'b0;
            indice_cruzamento <= 16'd0;
            indice_chegada    <= 16'd0;
            oportunidades     <= 16'd0;
            s_curta_cruz      <= 64'd0;
            s_longa_cruz      <= 64'd0;
            maior_salto       <= 32'd0;
        end else begin
            case (estado)
            E_LIVRE: begin
                if (preparar) begin
                    n                 <= 16'd0;
                    y                 <= 64'sd0;
                    s_curta           <= 64'd0;
                    s_longa           <= 64'd0;
                    oportunidades     <= 16'd0;
                    detectou          <= 1'b0;
                    truncado          <= 1'b0;
                    estouro           <= 1'b0;
                    indice_cruzamento <= 16'd0;
                    indice_chegada    <= 16'd0;
                    s_curta_cruz      <= 64'd0;
                    s_longa_cruz      <= 64'd0;
                    maior_salto       <= 32'd0;
                    multiplicar({48'd0, cfg_limiar}, {24'd0, cfg_n_curta}, E_PREP_LIME);
                end else if (amostra) begin
                    x <= codigo;
                    if (n == 16'd0) begin
                        y      <= 64'sd0;
                        estado <= E_Q;
                    end else begin
                        estado <= E_Y;
                    end
                end
            end

            E_MULT: begin
                mul_ini <= 1'b0;
                if (mul_pronto)
                    estado <= retorno;
            end

            // --- constantes do ensaio ---------------------------------------------
            E_PREP_LIME: begin
                lnc <= mul_p[31:0];
                multiplicar({32'd0, cfg_piso_energia}, {24'd0, cfg_n_longa}, E_PREP_PP);
            end
            E_PREP_PP: begin
                lim_e <= mul_p[63:0];
                multiplicar({32'd0, cfg_piso}, cfg_piso, E_PREP_LIMA);
            end
            E_PREP_LIMA: begin
                multiplicar(mul_p[63:0], {24'd0, cfg_n_curta}, E_PREP_FIM);
            end
            E_PREP_FIM: begin
                lim_a  <= mul_p;
                estado <= E_LIVRE;
            end

            // --- passa-altas ------------------------------------------------------------
            E_Y: begin
                sinal_negativo <= soma[66];
                if (soma_mag[66:64] != 3'd0)
                    estouro <= 1'b1;
                multiplicar(soma_mag[63:0], cfg_coeficiente, E_Y_FIM);
            end
            E_Y_FIM: begin
                y      <= produto_d[63:0];
                estado <= E_Q;
            end

            // --- energia ---------------------------------------------------------------------
            E_Q: begin
                if (ye_mag[63:32] != 32'd0)
                    estouro <= 1'b1;
                multiplicar({32'd0, ye_mag[31:0]}, ye_mag[31:0], E_GRAVA);
            end
            E_GRAVA: begin
                q                            <= mul_p[63:0];
                q_mem[n[BITS_JANELA-1:0]]    <= mul_p[63:0];
                y_mem[n[BITS_HIST-1:0]]      <= y;
                estado                       <= E_CURTA;
            end
            E_CURTA: begin
                if (curta_nova[65:64] != 2'd0)
                    estouro <= 1'b1;
                s_curta <= curta_nova[63:0];
                estado  <= E_LONGA_SOMA;
            end
            E_LONGA_SOMA: begin
                s_longa_parcial <= (n >= recuo) ? ({2'b00, s_longa} + {2'b00, q_mem[idx_longa_ent]})
                                                : {2'b00, s_longa};
                estado <= E_LONGA_SUB;
            end
            E_LONGA_SUB: begin
                if (longa_nova[65:64] != 2'd0)
                    estouro <= 1'b1;
                s_longa <= longa_nova[63:0];
                estado  <= E_VALIDA;
            end

            // --- decisao ----------------------------------------------------------------------
            E_VALIDA: begin
                if ({6'd0, n} + 16'd1 >= recuo_nl) begin
                    oportunidades <= oportunidades + 16'd1;
                    if (!detectou && !estouro)
                        multiplicar(s_curta, {24'd0, cfg_n_longa}, E_D_DIR);
                    else
                        estado <= E_FIM;
                end else begin
                    estado <= E_FIM;
                end
            end
            E_D_DIR: begin
                esquerda <= mul_p;
                multiplicar(s_efetiva, lnc, E_D_DECIDE);
            end
            E_D_DECIDE: begin
                if (esquerda[95:64] != 32'd0 || mul_p[95:64] != 32'd0) begin
                    estouro <= 1'b1;
                    estado  <= E_FIM;
                end else if (esquerda >= mul_p && {32'd0, s_curta} >= lim_a) begin
                    referencia <= s_longa;
                    i          <= n;
                    limite     <= (n > recuo) ? (n - recuo) : 16'd0;
                    multiplicar(s_longa, {16'd0, cfg_k2}, E_R_KREF);
                end else begin
                    estado <= E_FIM;
                end
            end

            // --- retrocesso (A-12) ------------------------------------------------------------
            E_R_KREF: begin
                kref   <= mul_p;
                estado <= E_R_PASSO;
            end
            E_R_PASSO: begin
                if (i > limite)
                    multiplicar(q_mem[idx_im1], {24'd0, cfg_n_longa}, E_R_TESTE);
                else
                    estado <= E_T_I;
            end
            E_R_TESTE: begin
                if (mul_p > kref) begin
                    i      <= i - 16'd1;
                    estado <= E_R_PASSO;
                end else begin
                    estado <= E_T_I;
                end
            end
            E_T_I: begin
                if (i == limite) begin
                    multiplicar(q_mem[idx_i], {24'd0, cfg_n_longa}, E_T_I1);
                end else begin
                    truncado <= 1'b0;
                    k        <= i;
                    maior    <= 65'd0;
                    estado   <= E_SALTO;
                end
            end
            E_T_I1: begin
                if (mul_p > kref && i != 16'd0) begin
                    multiplicar(q_mem[idx_im1], {24'd0, cfg_n_longa}, E_T_FIM);
                end else begin
                    truncado <= 1'b0;
                    k        <= i;
                    maior    <= 65'd0;
                    estado   <= E_SALTO;
                end
            end
            E_T_FIM: begin
                truncado <= (mul_p > kref);
                k        <= i;
                maior    <= 65'd0;
                estado   <= E_SALTO;
            end
            E_SALTO: begin
                if (k < n) begin
                    if (passo_mag > maior)
                        maior <= passo_mag;
                    k <= k + 16'd1;
                end else begin
                    estado <= E_SALTO_FIM;
                end
            end
            E_SALTO_FIM: begin
                if (maior[64:32] != 33'd0)
                    estouro <= 1'b1;
                detectou          <= 1'b1;
                indice_cruzamento <= n;
                indice_chegada    <= i;
                s_curta_cruz      <= s_curta;
                s_longa_cruz      <= referencia;
                maior_salto       <= maior[31:0];
                estado            <= E_FIM;
            end

            E_FIM: begin
                n          <= n + 16'd1;
                x_anterior <= x;
                estado     <= E_LIVRE;
            end

            default: estado <= E_LIVRE;
            endcase
        end
    end
endmodule

`default_nettype wire

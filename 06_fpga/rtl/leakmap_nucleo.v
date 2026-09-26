`timescale 1ns / 1ps
// LEAKMAP Edge - nucleo da placa no cenario B (etapas B-04 a B-10).
//
// Recebe e devolve bytes; nao sabe nada de UART nem de pinos, entao e o mesmo
// em qualquer placa. Implementa 06_fpga/ESPECIFICACAO.md, secoes 4 a 7, e o
// comportamento de 06_fpga/computador/placa_referencia.py (classe
// PlacaReferencia), que e o que manda em caso de duvida.
//
//   - le quadros A5 5A | tipo | tamanho | carga | CRC-16 e confere o CRC;
//   - CONFIGURAR: guarda parametros, zera contadores e memoria, devolve tudo;
//   - AMOSTRAS: confere identificador, sequencia e posicao, grava na memoria;
//   - EXECUTAR: reproduz a memoria com um indice comum aos dois canais,
//     alimentando os dois detectores na mesma amostra, e monta o resultado;
//   - PEDIR_RESULTADO reenvia o resultado guardado; CONFIRMAR o descarta;
//   - EXECUTAR_TEMPO_REAL: a mesma execucao, mas entregando aos detectores uma
//     amostra a cada `periodo` ciclos, marcados pelo proprio relogio, como um
//     conversor entregaria no ritmo da amostragem. O resultado e identico;
//   - PEDIR_TEMPOS devolve TEMPOS: os ciclos de relogio que a ultima execucao
//     levou, contados pelo proprio circuito (execucao inteira, cada amostra,
//     instante e latencia da declaracao em cada canal, amostras atrasadas);
//   - PEDIR_SAUDE devolve SAUDE: o autoteste que cada canal fez, amostra a
//     amostra, na ultima execucao (leakmap_saude.v), julgado com os limites
//     que vieram no pedido: canal congelado, saturado, fora da faixa, salto.
//
// Interface de bytes: um byte entra quando rx_valido e rx_pronto estao altos
// no mesmo ciclo; um byte sai quando tx_valido e tx_pronto estao altos.
// Enquanto trata uma mensagem ou transmite a resposta, rx_pronto fica baixo.
`default_nettype none

module leakmap_nucleo #(
    parameter integer FREQUENCIA_HZ = 100_000_000,   // so informado em TEMPOS
    parameter integer MAX_AMOSTRAS  = 4096,
    parameter integer BITS_ENDERECO = 12,
    parameter integer MAX_CARGA     = 160
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] rx_dado,
    input  wire       rx_valido,
    output wire       rx_pronto,
    output wire [7:0] tx_dado,
    output wire       tx_valido,
    input  wire       tx_pronto,
    output wire       ocupado,
    output wire       resultado_pendente
);
    // --- tipos e situacoes ------------------------------------------------------
    localparam [7:0] T_CONFIGURAR = 8'h01, T_AMOSTRAS = 8'h02, T_EXECUTAR = 8'h03,
                     T_CONFIRMAR  = 8'h04, T_PEDIR    = 8'h05,
                     T_EXEC_TR    = 8'h07, T_PEDIR_TEMPOS = 8'h08, T_PEDIR_SAUDE = 8'h09,
                     T_LIDA       = 8'h81, T_RECIBO   = 8'h82, T_RESULTADO = 8'h83,
                     T_TEMPOS     = 8'h87, T_SAUDE    = 8'h88;
    localparam [7:0] B_OK = 8'd0, B_CRC = 8'd1, B_SEQUENCIA = 8'd2, B_OUTRO = 8'd3,
                     B_MEMORIA = 8'd4, B_MAL_FORMADO = 8'd5;
    localparam [7:0] R_CONCLUIDO = 8'd0, R_FALTANDO = 8'd1, R_SEM_CONFIG = 8'd2, R_ESTOURO = 8'd3;

    // --- estados --------------------------------------------------------------------
    localparam [4:0]
        S_SINC1 = 5'd0,  S_SINC2 = 5'd1,  S_TIPO = 5'd2,   S_TAM0 = 5'd3,  S_TAM1 = 5'd4,
        S_CARGA = 5'd5,  S_CRC0  = 5'd6,  S_CRC1 = 5'd7,   S_TRATAR = 5'd8,
        S_AMOS  = 5'd9,  S_GRAVA = 5'd10, S_EXEC = 5'd11,  S_PREP = 5'd12,  S_PREP_ESPERA = 5'd13,
        S_LE    = 5'd14, S_LE2   = 5'd15, S_AMOSTRA = 5'd16, S_ESPERA = 5'd17,
        S_MONTA = 5'd18, S_TX    = 5'd19;

    reg [4:0] estado;

    // --- CRC-16/CCITT-FALSE, um byte por vez ----------------------------------------------
    function [15:0] crc_byte;
        input [15:0] crc;
        input [7:0]  dado;
        integer j;
        reg [15:0] c;
        begin
            c = crc ^ {dado, 8'h00};
            for (j = 0; j < 8; j = j + 1)
                c = c[15] ? ((c << 1) ^ 16'h1021) : (c << 1);
            crc_byte = c;
        end
    endfunction

    // --- recepcao -------------------------------------------------------------------------------
    reg  [7:0]  tipo;
    reg  [15:0] tamanho;
    reg  [15:0] contagem;
    reg  [15:0] crc_rx;
    reg  [7:0]  crc_lido0;
    reg  [7:0]  carga [0:MAX_CARGA-1];

    wire recebendo = (estado <= S_CRC1);
    assign rx_pronto = recebendo;
    wire byte_chegou = rx_valido && recebendo;

    // --- configuracao guardada ---------------------------------------------------------------
    reg  [7:0]  cfg [0:30];            // os 31 bytes de CONFIGURAR, devolvidos como vieram
    reg         configurado;
    wire [15:0] cfg_n_amostras = {cfg[30], cfg[29]};

    reg  [15:0] falhas_crc;
    reg  [15:0] descontinuidades;
    reg  [15:0] blocos_recebidos;
    reg  [15:0] sequencia_esperada;
    reg  [15:0] amostras_gravadas;

    // campos da carga recebida
    wire [15:0] carga_u16_8  = {carga[9],  carga[8]};
    wire [15:0] carga_u16_10 = {carga[11], carga[10]};
    wire [7:0]  n_pares      = carga[12];
    wire [7:0]  canais       = carga[13];
    wire        id_confere   = (carga[0] == cfg[0]) && (carga[1] == cfg[1]) && (carga[2] == cfg[2])
                            && (carga[3] == cfg[3]) && (carga[4] == cfg[4]) && (carga[5] == cfg[5])
                            && (carga[6] == cfg[6]) && (carga[7] == cfg[7]);

    // --- memoria das amostras (via 1) ------------------------------------------------------
    reg  [15:0] mem_a [0:MAX_AMOSTRAS-1];
    reg  [15:0] mem_b [0:MAX_AMOSTRAS-1];
    reg         mem_escreve;
    reg  [BITS_ENDERECO-1:0] mem_end_escrita;
    reg  [15:0] mem_dado_a, mem_dado_b;
    reg  [BITS_ENDERECO-1:0] mem_end_leitura;
    reg  [15:0] lido_a, lido_b;

    always @(posedge clk) begin
        if (mem_escreve) begin
            mem_a[mem_end_escrita] <= mem_dado_a;
            mem_b[mem_end_escrita] <= mem_dado_b;
        end
        lido_a <= mem_a[mem_end_leitura];
        lido_b <= mem_b[mem_end_leitura];
    end

    // --- detectores, um por canal, alimentados pelo mesmo indice ---------------------------
    wire preparar_det = (estado == S_PREP);
    wire amostra_det  = (estado == S_AMOSTRA);
    wire ocupado_a, ocupado_b;
    wire det_a, det_b, trunc_a, trunc_b, estouro_a, estouro_b;
    wire [15:0] cruz_a, cruz_b, cheg_a, cheg_b, oport_a, oport_b;
    wire [63:0] sc_a, sc_b, sl_a, sl_b;
    wire [31:0] salto_a, salto_b;

    wire [31:0] cfg_coef   = {cfg[11], cfg[10], cfg[9], cfg[8]};
    wire [15:0] cfg_limiar = {cfg[18], cfg[17]};
    wire [15:0] cfg_k2     = {cfg[20], cfg[19]};
    wire [31:0] cfg_piso   = {cfg[24], cfg[23], cfg[22], cfg[21]};
    wire [31:0] cfg_pe     = {cfg[28], cfg[27], cfg[26], cfg[25]};

    leakmap_detector u_det_a (
        .clk(clk), .rst(rst),
        .cfg_coeficiente(cfg_coef), .cfg_fracao(cfg[12]), .cfg_desloca(cfg[13]),
        .cfg_n_curta(cfg[14]), .cfg_n_guarda(cfg[15]), .cfg_n_longa(cfg[16]),
        .cfg_limiar(cfg_limiar), .cfg_k2(cfg_k2), .cfg_piso(cfg_piso), .cfg_piso_energia(cfg_pe),
        .preparar(preparar_det), .amostra(amostra_det), .codigo(lido_a), .ocupado(ocupado_a),
        .detectou(det_a), .truncado(trunc_a), .estouro(estouro_a),
        .indice_cruzamento(cruz_a), .indice_chegada(cheg_a), .oportunidades(oport_a),
        .s_curta_cruz(sc_a), .s_longa_cruz(sl_a), .maior_salto(salto_a));

    leakmap_detector u_det_b (
        .clk(clk), .rst(rst),
        .cfg_coeficiente(cfg_coef), .cfg_fracao(cfg[12]), .cfg_desloca(cfg[13]),
        .cfg_n_curta(cfg[14]), .cfg_n_guarda(cfg[15]), .cfg_n_longa(cfg[16]),
        .cfg_limiar(cfg_limiar), .cfg_k2(cfg_k2), .cfg_piso(cfg_piso), .cfg_piso_energia(cfg_pe),
        .preparar(preparar_det), .amostra(amostra_det), .codigo(lido_b), .ocupado(ocupado_b),
        .detectou(det_b), .truncado(trunc_b), .estouro(estouro_b),
        .indice_cruzamento(cruz_b), .indice_chegada(cheg_b), .oportunidades(oport_b),
        .s_curta_cruz(sc_b), .s_longa_cruz(sl_b), .maior_salto(salto_b));

    // --- autoteste dos canais: os limites sao os do PEDIR_SAUDE, lidos da carga -----------
    wire [15:0] lim_congelado = {carga[9],  carga[8]};
    wire [15:0] lim_minimo    = {carga[11], carga[10]};
    wire [15:0] lim_maximo    = {carga[13], carga[12]};
    wire [15:0] lim_salto     = {carga[15], carga[14]};
    wire [15:0] sau_min_a, sau_max_a, sau_seq_a, sau_var_a, sau_ext_a;
    wire [15:0] sau_min_b, sau_max_b, sau_seq_b, sau_var_b, sau_ext_b;
    wire [3:0]  sau_band_a, sau_band_b;

    leakmap_saude u_saude_a (
        .clk(clk), .rst(rst), .preparar(preparar_det), .amostra(amostra_det), .codigo(lido_a),
        .limite_congelado(lim_congelado), .codigo_minimo(lim_minimo), .codigo_maximo(lim_maximo),
        .limite_salto(lim_salto),
        .codigo_min(sau_min_a), .codigo_max(sau_max_a), .maior_sequencia(sau_seq_a),
        .maior_variacao(sau_var_a), .no_extremo(sau_ext_a), .bandeiras(sau_band_a));

    leakmap_saude u_saude_b (
        .clk(clk), .rst(rst), .preparar(preparar_det), .amostra(amostra_det), .codigo(lido_b),
        .limite_congelado(lim_congelado), .codigo_minimo(lim_minimo), .codigo_maximo(lim_maximo),
        .limite_salto(lim_salto),
        .codigo_min(sau_min_b), .codigo_max(sau_max_b), .maior_sequencia(sau_seq_b),
        .maior_variacao(sau_var_b), .no_extremo(sau_ext_b), .bandeiras(sau_band_b));

    // --- resposta e resultado ------------------------------------------------------------
    reg  [7:0]  resp [0:38];           // CONFIGURACAO_LIDA (39), BLOCO_RECEBIDO (11) ou SAUDE (39)
    reg  [7:0]  res  [0:70];           // RESULTADO (71), guardado para reenvio
    reg  [7:0]  tem  [0:42];           // TEMPOS (43) da ultima execucao
    reg         pendente;
    reg  [1:0]  fonte_tx;              // 0: `resp`; 1: `res`; 2: `tem`
    reg  [7:0]  tx_tipo;
    reg  [15:0] tx_tamanho;
    reg  [15:0] tx_indice;
    reg  [15:0] crc_tx;
    reg  [7:0]  situacao;
    reg  [15:0] indice_exec;
    reg  [7:0]  k_par;

    assign ocupado = !recebendo;
    assign resultado_pendente = pendente;

    wire [7:0]  tx_carga = (fonte_tx == 2'd1) ? res[tx_indice - 16'd5] :
                           (fonte_tx == 2'd2) ? tem[tx_indice - 16'd5] : resp[tx_indice - 16'd5];

    // --- tempos contados pelo circuito ---------------------------------------------------
    // `ciclo` conta desde a entrada em S_EXEC. No modo de tempo real a amostra k
    // e entregue no ciclo entrega(0) + k * periodo; se o circuito chega depois
    // da hora de uma amostra, ela conta como atrasada.
    reg         contando;
    reg         modo_tr;
    reg  [31:0] periodo;
    reg  [31:0] ciclo;
    reg  [31:0] proxima;               // hora de entrega da proxima amostra
    reg  [31:0] entrega;               // hora em que a amostra atual foi entregue
    reg  [15:0] amostra_min, amostra_max, atrasadas;
    reg  [31:0] decl_a, decl_b;        // ciclo em que o canal declarou o evento
    reg  [15:0] lat_a, lat_b;          // ciclos da entrega da amostra do cruzamento a declaracao
    wire [31:0] duracao = ciclo - entrega;
    wire [15:0] duracao16 = (duracao > 32'd65535) ? 16'hFFFF : duracao[15:0];
    wire [31:0] periodo_rx = {carga[15], carga[14], carga[13], carga[12]};
    localparam [31:0] FREQ32 = FREQUENCIA_HZ;
    assign tx_dado = (tx_indice == 16'd0) ? 8'hA5 :
                     (tx_indice == 16'd1) ? 8'h5A :
                     (tx_indice == 16'd2) ? tx_tipo :
                     (tx_indice == 16'd3) ? tx_tamanho[7:0] :
                     (tx_indice == 16'd4) ? tx_tamanho[15:8] :
                     (tx_indice <  tx_tamanho + 16'd5) ? tx_carga :
                     (tx_indice == tx_tamanho + 16'd5) ? crc_tx[7:0] : crc_tx[15:8];
    assign tx_valido = (estado == S_TX);

    // recibo de bloco: identificador (da carga ou zerado), sequencia e situacao
    task recibo;
        input        com_id;
        input [15:0] seq;
        input [7:0]  sit;
        integer j;
        begin
            for (j = 0; j < 8; j = j + 1)
                resp[j] <= com_id ? carga[j] : 8'h00;
            resp[8]  <= seq[7:0];
            resp[9]  <= seq[15:8];
            resp[10] <= sit;
            tx_tipo         <= T_RECIBO;
            tx_tamanho      <= 16'd11;
            fonte_tx        <= 2'd0;
            tx_indice       <= 16'd0;
            crc_tx          <= 16'hFFFF;
            estado          <= S_TX;
        end
    endtask

    task enviar_resultado;
        begin
            tx_tipo         <= T_RESULTADO;
            tx_tamanho      <= 16'd71;
            fonte_tx        <= 2'd1;
            tx_indice       <= 16'd0;
            crc_tx          <= 16'hFFFF;
            estado          <= S_TX;
        end
    endtask

    // um canal do resultado a partir da posicao `base`
    task canal_no_resultado;
        input integer base;
        input         valido;
        input         det, trunc;
        input [15:0]  cruz, cheg, oport;
        input [63:0]  sc, sl;
        input [31:0]  salto;
        integer j;
        begin
            res[base]     <= valido ? {6'd0, trunc, det} : 8'd0;
            res[base + 1] <= valido ? cruz[7:0]   : 8'd0;
            res[base + 2] <= valido ? cruz[15:8]  : 8'd0;
            res[base + 3] <= valido ? cheg[7:0]   : 8'd0;
            res[base + 4] <= valido ? cheg[15:8]  : 8'd0;
            res[base + 5] <= valido ? oport[7:0]  : 8'd0;
            res[base + 6] <= valido ? oport[15:8] : 8'd0;
            for (j = 0; j < 8; j = j + 1) begin
                res[base + 7 + j]  <= valido ? sc[8*j +: 8] : 8'd0;
                res[base + 15 + j] <= valido ? sl[8*j +: 8] : 8'd0;
            end
            for (j = 0; j < 4; j = j + 1)
                res[base + 23 + j] <= valido ? salto[8*j +: 8] : 8'd0;
        end
    endtask

    // um canal do SAUDE a partir da posicao `base`; zerado sem execucao concluida
    task canal_na_saude;
        input integer base;
        input         valido;
        input [3:0]   band;
        input [15:0]  cmin, cmax, cseq, cvar, cext;
        begin
            resp[base]      <= valido ? {4'd0, band} : 8'd0;
            resp[base + 1]  <= valido ? cmin[7:0]  : 8'd0;
            resp[base + 2]  <= valido ? cmin[15:8] : 8'd0;
            resp[base + 3]  <= valido ? cmax[7:0]  : 8'd0;
            resp[base + 4]  <= valido ? cmax[15:8] : 8'd0;
            resp[base + 5]  <= valido ? cseq[7:0]  : 8'd0;
            resp[base + 6]  <= valido ? cseq[15:8] : 8'd0;
            resp[base + 7]  <= valido ? cvar[7:0]  : 8'd0;
            resp[base + 8]  <= valido ? cvar[15:8] : 8'd0;
            resp[base + 9]  <= valido ? cext[7:0]  : 8'd0;
            resp[base + 10] <= valido ? cext[15:8] : 8'd0;
        end
    endtask

    task enviar_tempos;
        begin
            tx_tipo    <= T_TEMPOS;
            tx_tamanho <= 16'd43;
            fonte_tx   <= 2'd2;
            tx_indice  <= 16'd0;
            crc_tx     <= 16'hFFFF;
            estado     <= S_TX;
        end
    endtask

    // comeca a contar uma execucao: `tr` = tempo real, `per` = periodo em ciclos
    task comecar_execucao;
        input        tr;
        input [31:0] per;
        begin
            contando    <= 1'b1;
            ciclo       <= 32'd0;
            modo_tr     <= tr;
            periodo     <= per;
            proxima     <= 32'd0;
            entrega     <= 32'd0;
            amostra_min <= 16'hFFFF;
            amostra_max <= 16'd0;
            atrasadas   <= 16'd0;
            decl_a      <= 32'hFFFFFFFF;
            decl_b      <= 32'hFFFFFFFF;
            lat_a       <= 16'hFFFF;
            lat_b       <= 16'hFFFF;
            estado      <= S_EXEC;
        end
    endtask

    integer j;

    always @(posedge clk) begin
        mem_escreve <= 1'b0;
        if (rst) begin
            estado             <= S_SINC1;
            configurado        <= 1'b0;
            pendente           <= 1'b0;
            falhas_crc         <= 16'd0;
            descontinuidades   <= 16'd0;
            blocos_recebidos   <= 16'd0;
            sequencia_esperada <= 16'd0;
            amostras_gravadas  <= 16'd0;
            tx_indice          <= 16'd0;
            fonte_tx           <= 2'd0;
            contando           <= 1'b0;
            for (j = 0; j < 31; j = j + 1)
                cfg[j] <= 8'd0;
            // TEMPOS antes de qualquer execucao: situacao 0xFF, so a frequencia
            for (j = 0; j < 43; j = j + 1)
                tem[j] <= 8'd0;
            tem[8] <= 8'hFF;
            for (j = 0; j < 4; j = j + 1)
                tem[10 + j] <= FREQ32[8*j +: 8];
            tem[20] <= 8'd1;
        end else begin
            if (contando)
                ciclo <= ciclo + 32'd1;
            case (estado)
            // --- leitura do quadro ----------------------------------------------------
            S_SINC1: if (byte_chegou && rx_dado == 8'hA5) estado <= S_SINC2;
            S_SINC2: if (byte_chegou) begin
                if (rx_dado == 8'h5A) begin
                    crc_rx <= 16'hFFFF;
                    estado <= S_TIPO;
                end else if (rx_dado != 8'hA5) begin
                    estado <= S_SINC1;
                end
            end
            S_TIPO: if (byte_chegou) begin
                tipo   <= rx_dado;
                crc_rx <= crc_byte(crc_rx, rx_dado);
                estado <= S_TAM0;
            end
            S_TAM0: if (byte_chegou) begin
                tamanho[7:0] <= rx_dado;
                crc_rx       <= crc_byte(crc_rx, rx_dado);
                estado       <= S_TAM1;
            end
            S_TAM1: if (byte_chegou) begin
                tamanho[15:8] <= rx_dado;
                crc_rx        <= crc_byte(crc_rx, rx_dado);
                contagem      <= 16'd0;
                if ({rx_dado, tamanho[7:0]} > 16'd1024) begin
                    // cabecalho absurdo: descarta e conta como falha de CRC
                    falhas_crc <= falhas_crc + 16'd1;
                    recibo(1'b0, 16'hFFFF, B_CRC);
                end else if ({rx_dado, tamanho[7:0]} == 16'd0) begin
                    estado <= S_CRC0;
                end else begin
                    estado <= S_CARGA;
                end
            end
            S_CARGA: if (byte_chegou) begin
                if (contagem < MAX_CARGA)
                    carga[contagem] <= rx_dado;
                crc_rx   <= crc_byte(crc_rx, rx_dado);
                contagem <= contagem + 16'd1;
                if (contagem + 16'd1 == tamanho)
                    estado <= S_CRC0;
            end
            S_CRC0: if (byte_chegou) begin
                crc_lido0 <= rx_dado;
                estado    <= S_CRC1;
            end
            S_CRC1: if (byte_chegou) begin
                if ({rx_dado, crc_lido0} == crc_rx) begin
                    estado <= S_TRATAR;
                end else begin
                    falhas_crc <= falhas_crc + 16'd1;
                    recibo(1'b0, 16'hFFFF, B_CRC);
                end
            end

            // --- tratamento ---------------------------------------------------------------
            S_TRATAR: begin
                case (tipo)
                T_CONFIGURAR:
                    if (tamanho != 16'd31) begin
                        recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    end else begin
                        for (j = 0; j < 31; j = j + 1) begin
                            cfg[j]  <= carga[j];
                            resp[j] <= carga[j];
                        end
                        for (j = 31; j < 39; j = j + 1)
                            resp[j] <= 8'd0;          // contadores recem-zerados
                        configurado        <= ({carga[30], carga[29]} <= MAX_AMOSTRAS);
                        falhas_crc         <= 16'd0;
                        descontinuidades   <= 16'd0;
                        blocos_recebidos   <= 16'd0;
                        sequencia_esperada <= 16'd0;
                        amostras_gravadas  <= 16'd0;
                        pendente           <= 1'b0;
                        tx_tipo            <= T_LIDA;
                        tx_tamanho         <= 16'd39;
                        fonte_tx           <= 2'd0;
                        tx_indice          <= 16'd0;
                        crc_tx             <= 16'hFFFF;
                        estado             <= S_TX;
                    end
                T_AMOSTRAS: estado <= S_AMOS;
                T_EXECUTAR:
                    if (tamanho != 16'd12) recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    else                   comecar_execucao(1'b0, 32'd0);
                T_EXEC_TR:
                    if (tamanho != 16'd16 || periodo_rx == 32'd0)
                        recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    else
                        comecar_execucao(1'b1, periodo_rx);
                T_PEDIR_TEMPOS:
                    if (tamanho != 16'd8) recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    else                  enviar_tempos;
                T_PEDIR_SAUDE:
                    if (tamanho != 16'd16) begin
                        recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    end else begin
                        // id e situacao da ultima execucao, os limites como vieram, e os canais
                        for (j = 0; j < 9; j = j + 1)
                            resp[j] <= tem[j];
                        for (j = 0; j < 8; j = j + 1)
                            resp[9 + j] <= carga[8 + j];
                        canal_na_saude(17, tem[8] == R_CONCLUIDO, sau_band_a,
                                       sau_min_a, sau_max_a, sau_seq_a, sau_var_a, sau_ext_a);
                        canal_na_saude(28, tem[8] == R_CONCLUIDO, sau_band_b,
                                       sau_min_b, sau_max_b, sau_seq_b, sau_var_b, sau_ext_b);
                        tx_tipo    <= T_SAUDE;
                        tx_tamanho <= 16'd39;
                        fonte_tx   <= 2'd0;
                        tx_indice  <= 16'd0;
                        crc_tx     <= 16'hFFFF;
                        estado     <= S_TX;
                    end
                T_CONFIRMAR:
                    if (tamanho != 16'd8) begin
                        recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    end else begin
                        if (pendente && id_confere)
                            pendente <= 1'b0;
                        estado <= S_SINC1;
                    end
                T_PEDIR:
                    if (tamanho != 16'd8)  recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                    else if (pendente)     enviar_resultado;
                    else                   estado <= S_SINC1;
                default: estado <= S_SINC1;
                endcase
            end

            // --- B-04 e B-06: bloco de amostras ------------------------------------------
            S_AMOS: begin
                if (tamanho < 16'd14 || canais != 8'h03
                    || tamanho != 16'd14 + {6'd0, n_pares, 2'b00}
                    || n_pares == 8'd0 || n_pares > 8'd32)
                    recibo(1'b0, 16'hFFFF, B_MAL_FORMADO);
                else if (!configurado || !id_confere)
                    recibo(1'b1, carga_u16_8, B_OUTRO);
                else if (carga_u16_8 < sequencia_esperada)
                    recibo(1'b1, carga_u16_8, B_OK);               // repetido: ja gravado
                else if (carga_u16_8 != sequencia_esperada) begin
                    descontinuidades <= descontinuidades + 16'd1;
                    recibo(1'b1, carga_u16_8, B_SEQUENCIA);
                end else if ({1'b0, carga_u16_10} + {9'd0, n_pares} > {1'b0, cfg_n_amostras})
                    recibo(1'b1, carga_u16_8, B_MEMORIA);
                else if (carga_u16_10 != amostras_gravadas)
                    recibo(1'b1, carga_u16_8, B_MAL_FORMADO);
                else begin
                    k_par  <= 8'd0;
                    estado <= S_GRAVA;
                end
            end
            S_GRAVA: begin
                mem_escreve     <= 1'b1;
                mem_end_escrita <= carga_u16_10[BITS_ENDERECO-1:0] + k_par;
                mem_dado_a      <= {carga[15 + 4*k_par], carga[14 + 4*k_par]};
                mem_dado_b      <= {carga[17 + 4*k_par], carga[16 + 4*k_par]};
                if (k_par + 8'd1 == n_pares) begin
                    amostras_gravadas  <= amostras_gravadas + {8'd0, n_pares};
                    sequencia_esperada <= sequencia_esperada + 16'd1;
                    blocos_recebidos   <= blocos_recebidos + 16'd1;
                    recibo(1'b1, carga_u16_8, B_OK);
                end else begin
                    k_par <= k_par + 8'd1;
                end
            end

            // --- B-08 e B-09: execucao com indice comum ------------------------------------
            S_EXEC: begin
                if (!configurado || !id_confere) begin
                    situacao <= R_SEM_CONFIG;
                    estado   <= S_MONTA;
                end else if (carga_u16_10 != cfg_n_amostras || carga_u16_8 != blocos_recebidos
                             || amostras_gravadas != cfg_n_amostras) begin
                    situacao <= R_FALTANDO;
                    estado   <= S_MONTA;
                end else begin
                    estado <= S_PREP;
                end
            end
            S_PREP: estado <= S_PREP_ESPERA;               // preparar_det alto neste ciclo
            S_PREP_ESPERA:
                if (!ocupado_a && !ocupado_b) begin
                    indice_exec <= 16'd0;
                    if (cfg_n_amostras == 16'd0) begin
                        situacao <= R_CONCLUIDO;
                        estado   <= S_MONTA;
                    end else begin
                        estado <= S_LE;
                    end
                end
            S_LE:
                // tempo real: a amostra k espera a sua hora; a primeira marca o comeco
                if (!(modo_tr && indice_exec != 16'd0 && ciclo < proxima)) begin
                    if (modo_tr && indice_exec != 16'd0 && ciclo > proxima)
                        atrasadas <= atrasadas + 16'd1;
                    proxima         <= ((indice_exec == 16'd0) ? ciclo : proxima) + periodo;
                    entrega         <= ciclo;
                    mem_end_leitura <= indice_exec[BITS_ENDERECO-1:0];
                    estado          <= S_LE2;
                end
            S_LE2:    estado <= S_AMOSTRA;                 // memoria sincrona: um ciclo
            S_AMOSTRA: estado <= S_ESPERA;                 // amostra_det alto: os dois canais juntos
            S_ESPERA:
                if (!ocupado_a && !ocupado_b) begin
                    if (duracao16 < amostra_min) amostra_min <= duracao16;
                    if (duracao16 > amostra_max) amostra_max <= duracao16;
                    if (det_a && decl_a == 32'hFFFFFFFF) begin
                        decl_a <= ciclo;
                        lat_a  <= duracao16;
                    end
                    if (det_b && decl_b == 32'hFFFFFFFF) begin
                        decl_b <= ciclo;
                        lat_b  <= duracao16;
                    end
                    if (indice_exec + 16'd1 == cfg_n_amostras) begin
                        situacao <= (estouro_a || estouro_b) ? R_ESTOURO : R_CONCLUIDO;
                        estado   <= S_MONTA;
                    end else begin
                        indice_exec <= indice_exec + 16'd1;
                        estado      <= S_LE;
                    end
                end

            // --- B-10: resultado ------------------------------------------------------------
            S_MONTA: begin
                for (j = 0; j < 8; j = j + 1)
                    res[j] <= carga[j];
                res[8]  <= situacao;
                res[9]  <= (situacao == R_CONCLUIDO) ? cfg_n_amostras[7:0]  : 8'd0;
                res[10] <= (situacao == R_CONCLUIDO) ? cfg_n_amostras[15:8] : 8'd0;
                res[11] <= falhas_crc[7:0];
                res[12] <= falhas_crc[15:8];
                res[13] <= descontinuidades[7:0];
                res[14] <= descontinuidades[15:8];
                res[15] <= 8'd0;                            // eventos de buffer: nao ha na via 1
                res[16] <= 8'd0;
                canal_no_resultado(17, situacao == R_CONCLUIDO, det_a, trunc_a,
                                   cruz_a, cheg_a, oport_a, sc_a, sl_a, salto_a);
                canal_no_resultado(44, situacao == R_CONCLUIDO, det_b, trunc_b,
                                   cruz_b, cheg_b, oport_b, sc_b, sl_b, salto_b);
                // TEMPOS desta execucao
                contando <= 1'b0;
                for (j = 0; j < 8; j = j + 1)
                    tem[j] <= carga[j];
                tem[8]  <= situacao;
                tem[9]  <= {7'd0, modo_tr};
                for (j = 0; j < 4; j = j + 1) begin
                    tem[10 + j] <= FREQ32[8*j +: 8];
                    tem[14 + j] <= periodo[8*j +: 8];
                    tem[21 + j] <= ciclo[8*j +: 8];
                    tem[31 + j] <= decl_a[8*j +: 8];
                    tem[37 + j] <= decl_b[8*j +: 8];
                end
                tem[18] <= (situacao == R_CONCLUIDO) ? cfg_n_amostras[7:0]  : 8'd0;
                tem[19] <= (situacao == R_CONCLUIDO) ? cfg_n_amostras[15:8] : 8'd0;
                tem[20] <= 8'd1;                            // ciclos contados pelo circuito
                tem[25] <= amostra_min[7:0];
                tem[26] <= amostra_min[15:8];
                tem[27] <= amostra_max[7:0];
                tem[28] <= amostra_max[15:8];
                tem[29] <= atrasadas[7:0];
                tem[30] <= atrasadas[15:8];
                tem[35] <= lat_a[7:0];
                tem[36] <= lat_a[15:8];
                tem[41] <= lat_b[7:0];
                tem[42] <= lat_b[15:8];
                pendente <= 1'b1;
                enviar_resultado;
            end

            // --- transmissao ---------------------------------------------------------------------
            S_TX: if (tx_pronto) begin
                if (tx_indice >= 16'd2 && tx_indice < tx_tamanho + 16'd5)
                    crc_tx <= crc_byte(crc_tx, tx_dado);
                if (tx_indice == tx_tamanho + 16'd6) begin
                    tx_indice <= 16'd0;
                    estado    <= S_SINC1;
                end else begin
                    tx_indice <= tx_indice + 16'd1;
                end
            end

            default: estado <= S_SINC1;
            endcase
        end
    end
endmodule

`default_nettype wire

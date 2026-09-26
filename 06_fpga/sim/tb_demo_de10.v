// LEAKMAP Edge - testbench do topo da demonstracao na DE10-Standard.
//
// Simula a placa inteira como ela vai ser gravada (placas/de10_standard/demo/
// leakmap_demo_de10.v), com o filtro dos botoes e o periodo de amostragem
// encurtados para a simulacao ser rapida. Aperta os botoes e as chaves de ruido
// e de sensor estragado como uma pessoa faria e le os displays de 7 segmentos
// de volta. Confere: a posicao escolhida em HEX5..HEX3; em HEX2..HEX0, a
// posicao calculada igual ao modelo (06_fpga/computador/demo_autonoma.py, pelo
// esperado +esperado=ARQ), ou "F A"/"F b"/"FAb" quando o autoteste acusa um
// sensor, ou "E" sem as duas chegadas; os LEDs das chegadas e do autoteste; e o
// ritmo de entrega das amostras.
`timescale 1ns / 1ps
`default_nettype none

module tb_demo_de10;
    localparam integer PERIODO = 150;
    // digitos lidos do display
    localparam integer APAGADO = 10, TRACO = 11, LETRA_A = 12, LETRA_B = 13, LETRA_E = 14, LETRA_F = 15;

    reg        clk = 1'b0;
    always #10 clk = ~clk;
    reg  [3:0] key = 4'hF;
    reg  [3:0] sw  = 4'b0000;
    wire [6:0] h0, h1, h2, h3, h4, h5;
    wire [5:0] ledr;

    leakmap_demo_de10 #(.PERIODO_CICLOS(PERIODO), .CICLOS_DEBOUNCE(20)) dut (
        .CLOCK_50(clk), .KEY(key), .SW(sw),
        .HEX0(h0), .HEX1(h1), .HEX2(h2), .HEX3(h3), .HEX4(h4), .HEX5(h5), .LEDR(ledr));

    // --- display de volta em digito: 0-9, e as constantes acima -----------------------
    function integer digito;
        input [6:0] s;
        case (~s)
            7'b0111111: digito = 0;   7'b0000110: digito = 1;   7'b1011011: digito = 2;
            7'b1001111: digito = 3;   7'b1100110: digito = 4;   7'b1101101: digito = 5;
            7'b1111101: digito = 6;   7'b0000111: digito = 7;   7'b1111111: digito = 8;
            7'b1101111: digito = 9;   7'b0000000: digito = APAGADO;  7'b1000000: digito = TRACO;
            7'b1110111: digito = LETRA_A;  7'b1111100: digito = LETRA_B;
            7'b1111001: digito = LETRA_E;  7'b1110001: digito = LETRA_F;
            default:    digito = -1;
        endcase
    endfunction

    function integer numero;             // tres digitos, com os apagados valendo zero
        input integer c, d, u;
        numero = ((c == APAGADO) ? 0 : c) * 100 + ((d == APAGADO) ? 0 : d) * 10 + u;
    endfunction

    // --- esperado do modelo, por [falha][ruido][posicao] --------------------------------
    integer esperado_estimada [0:3][0:1][0:255];
    integer esperado_chegadas [0:3][0:1][0:255];   // detectou_A * 2 + detectou_B
    integer esperado_saude    [0:3][0:1][0:255];   // saude_A * 16 + saude_B
    reg [8*300-1:0] arquivo;
    integer fd, lidos, e_pos, e_ruido, e_falha, e_da, e_ca, e_db, e_cb, e_est, e_sa, e_sb, erros, conferidos;

    // --- ritmo: ciclos entre duas entregas de amostra ----------------------------------
    integer ultima_entrega = -1, ciclo = 0, fora_do_ritmo = 0, entregas = 0;
    always @(posedge clk) begin
        ciclo <= ciclo + 1;
        if (dut.u_demo.estado == 3'd4) begin                // S_AMOSTRA
            if (ultima_entrega >= 0 && dut.u_demo.k != 0 && ciclo - ultima_entrega != PERIODO)
                fora_do_ritmo <= fora_do_ritmo + 1;
            ultima_entrega <= ciclo;
            entregas <= entregas + 1;
        end
    end

    task esperar_resultado;
        integer limite;
        begin
            limite = 0;
            repeat (50) @(posedge clk);
            while ((digito(h0) == TRACO || ledr[1]) && limite < 5_000_000) begin
                @(posedge clk);
                limite = limite + 1;
            end
            repeat (5) @(posedge clk);
        end
    endtask

    task apertar;
        input integer botao;
        begin
            key[botao] = 1'b0;
            repeat (60) @(posedge clk);
            key[botao] = 1'b1;
            repeat (60) @(posedge clk);
        end
    endtask

    // o que HEX2..HEX0 e os LEDs tem de mostrar, a partir do esperado do modelo
    task conferir;
        input integer escolhida, com_ruido, falha;
        integer mostrada, d2, d1, d0, e2, e1, e0, sa, sb, da, db, est;
        begin
            esperar_resultado;
            mostrada = numero(digito(h5), digito(h4), digito(h3));
            d2 = digito(h2); d1 = digito(h1); d0 = digito(h0);
            est = esperado_estimada[falha][com_ruido][escolhida];
            sa  = esperado_saude[falha][com_ruido][escolhida] / 16;
            sb  = esperado_saude[falha][com_ruido][escolhida] % 16;
            da  = esperado_chegadas[falha][com_ruido][escolhida] / 2;
            db  = esperado_chegadas[falha][com_ruido][escolhida] % 2;
            if (sa != 0 || sb != 0) begin
                e2 = LETRA_F; e1 = (sa != 0) ? LETRA_A : APAGADO; e0 = (sb != 0) ? LETRA_B : APAGADO;
            end else if (!(da && db)) begin
                e2 = APAGADO; e1 = APAGADO; e0 = LETRA_E;
            end else begin
                e2 = (est >= 100) ? est / 100 : APAGADO;
                e1 = (est >= 10) ? (est / 10) % 10 : APAGADO;
                e0 = est % 10;
            end
            conferidos = conferidos + 1;
            $display("  escolhida %0d m (display %0d), ruido %0d, falha %0d: display %0d %0d %0d, esperado %0d %0d %0d, LEDs %b",
                     escolhida, mostrada, com_ruido, falha, d2, d1, d0, e2, e1, e0, ledr[5:2]);
            if (mostrada != escolhida || d2 != e2 || d1 != e1 || d0 != e0
                || ledr[2] !== da[0] || ledr[3] !== db[0] || ledr[4] !== (sa != 0) || ledr[5] !== (sb != 0))
                erros = erros + 1;
        end
    endtask

    initial begin
        if (!$value$plusargs("esperado=%s", arquivo)) arquivo = "vetores/demo_esperado.txt";
        fd = $fopen(arquivo, "r");
        if (fd == 0) begin $display("ERRO: nao abriu %0s", arquivo); $finish; end
        while (!$feof(fd)) begin
            lidos = $fscanf(fd, "%d %d %d %d %d %d %d %d %d %d\n",
                            e_pos, e_ruido, e_falha, e_da, e_ca, e_db, e_cb, e_est, e_sa, e_sb);
            if (lidos == 10) begin
                esperado_estimada[e_falha][e_ruido][e_pos] = e_est;
                esperado_chegadas[e_falha][e_ruido][e_pos] = e_da * 2 + e_db;
                esperado_saude[e_falha][e_ruido][e_pos]    = e_sa * 16 + e_sb;
            end
        end
        $fclose(fd);
        erros = 0;
        conferidos = 0;

        conferir(80, 0, 0);                     // ao ligar, roda em 80 m
        apertar(0); conferir(90, 0, 0);         // KEY0: +10
        apertar(3); apertar(3); conferir(70, 0, 0);
        apertar(2); conferir(69, 0, 0);         // KEY2: -1
        apertar(1); apertar(1); conferir(71, 0, 0);
        sw[1] = 1'b1; conferir(71, 1, 0);       // SW1: com ruido
        repeat (12) apertar(0); conferir(160, 1, 0);   // para no limite de 160 m
        repeat (13) apertar(3); conferir(40, 1, 0);    // e no de 40 m

        // autoteste: sensores estragados de proposito, em 80 m
        repeat (4) apertar(0);
        sw[2] = 1'b1; conferir(80, 1, 1);       // SW2: cabo do sensor A rompido -> "F A"
        sw[3] = 1'b1; conferir(80, 1, 3);       // e o B travado -> "FAb"
        sw[2] = 1'b0; conferir(80, 1, 2);       // so o B travado -> "F b"
        sw[1] = 1'b0; conferir(80, 0, 2);       // sem ruido o travado nao se distingue: sem a chegada, "E"
        sw[3] = 1'b0; conferir(80, 0, 0);       // sensores bons de novo: a posicao volta

        if (erros == 0 && fora_do_ritmo == 0)
            $display("RESULTADO demo_de10 PASSOU conferidos=%0d entregas=%0d, uma a cada %0d ciclos",
                     conferidos, entregas, PERIODO);
        else
            $display("RESULTADO demo_de10 FALHOU erros=%0d fora_do_ritmo=%0d", erros, fora_do_ritmo);
        $finish;
    end
endmodule

`default_nettype wire

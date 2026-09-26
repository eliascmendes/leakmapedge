// LEAKMAP Edge - testbench da demonstracao autonoma (rtl/leakmap_demo.v).
//
// Le o esperado gravado por 06_fpga/computador/demo_autonoma.py --vetores: uma
// linha por caso, "posicao ruido falha detectou_A chegada_A detectou_B chegada_B
// posicao_estimada saude_A saude_B". Para cada caso roda a demonstracao e exige
// os mesmos numeros: o gerador de sinais, os sensores estragados de proposito,
// os detectores, o autoteste e a conta da posicao do Verilog iguais aos do
// modelo em Python. Roda sem o ritmo da amostragem
// (PERIODO_CICLOS = 0), para ser rapido; o ritmo e conferido em tb_demo_de10.v.
// Uso: vvp tb_demo.vvp +esperado=ARQ
`timescale 1ns / 1ps
`default_nettype none

module tb_demo;
    reg clk = 1'b0;
    always #10 clk = ~clk;
    reg rst = 1'b1;

    reg  [7:0] posicao;
    reg        ruido, iniciar;
    reg  [1:0] falha;
    wire [3:0] saude_a, saude_b;
    wire       ocupado, pronto, det_a, det_b;
    wire [15:0] cheg_a, cheg_b;
    wire [7:0]  estimada;

    leakmap_demo #(.PERIODO_CICLOS(0)) dut (
        .clk(clk), .rst(rst), .posicao_m(posicao), .ruido(ruido), .falha(falha), .iniciar(iniciar),
        .ocupado(ocupado), .pronto(pronto), .detectou_a(det_a), .detectou_b(det_b),
        .chegada_a(cheg_a), .chegada_b(cheg_b), .posicao_estimada_m(estimada),
        .saude_a(saude_a), .saude_b(saude_b));

    reg [8*300-1:0] arquivo;
    integer fd, lidos, casos, erros;
    integer e_pos, e_ruido, e_falha, e_det_a, e_cheg_a, e_det_b, e_cheg_b, e_est, e_saude_a, e_saude_b;
    integer com_falha;

    initial begin
        if (!$value$plusargs("esperado=%s", arquivo)) arquivo = "vetores/demo_esperado.txt";
        fd = $fopen(arquivo, "r");
        if (fd == 0) begin $display("ERRO: nao abriu %0s", arquivo); $finish; end
        iniciar = 1'b0;
        posicao = 8'd80;
        ruido = 1'b0;
        falha = 2'b00;
        repeat (4) @(posedge clk);
        rst = 1'b0;
        casos = 0;
        erros = 0;
        com_falha = 0;
        while (!$feof(fd)) begin
            lidos = $fscanf(fd, "%d %d %d %d %d %d %d %d %d %d\n", e_pos, e_ruido, e_falha, e_det_a, e_cheg_a,
                            e_det_b, e_cheg_b, e_est, e_saude_a, e_saude_b);
            if (lidos == 10) begin
                @(negedge clk);
                posicao = e_pos;
                ruido   = e_ruido;
                falha   = e_falha;
                iniciar = 1'b1;
                @(negedge clk);
                iniciar = 1'b0;
                @(posedge clk);
                while (ocupado) @(posedge clk);
                casos = casos + 1;
                if (e_falha != 0) com_falha = com_falha + 1;
                if (!pronto || det_a !== e_det_a[0] || det_b !== e_det_b[0] || cheg_a !== e_cheg_a[15:0]
                    || cheg_b !== e_cheg_b[15:0] || estimada !== e_est[7:0]
                    || saude_a !== e_saude_a[3:0] || saude_b !== e_saude_b[3:0]) begin
                    erros = erros + 1;
                    $display("  %0d m, ruido %0d, falha %0d: Verilog A %b/%0d B %b/%0d -> %0d m, saude %0d %0d; modelo A %0d/%0d B %0d/%0d -> %0d m, saude %0d %0d",
                             e_pos, e_ruido, e_falha, det_a, cheg_a, det_b, cheg_b, estimada, saude_a, saude_b,
                             e_det_a, e_cheg_a, e_det_b, e_cheg_b, e_est, e_saude_a, e_saude_b);
                end
            end
        end
        $fclose(fd);
        if (erros == 0 && casos > 0)
            $display("RESULTADO demo PASSOU casos=%0d, %0d com sensor estragado de proposito", casos, com_falha);
        else
            $display("RESULTADO demo FALHOU casos=%0d erros=%0d", casos, erros);
        $finish;
    end
endmodule

`default_nettype wire

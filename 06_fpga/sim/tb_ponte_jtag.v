// LEAKMAP Edge - o nucleo atras da ponte JTAG, conversando pela entrada e saida padrao.
//
// Faz no simulador o papel do quartus_stp com 06_fpga/computador/ponte_jtag.tcl:
// recebe os mesmos comandos e responde as mesmas linhas, mas em vez do cabo
// USB-Blaster e da FPGA, desloca os bits no proprio Verilog da ponte e do
// nucleo. Assim o TransporteJtag do computador e testado de ponta a ponta sem
// placa.
//
//   entrada  "IR <valor>"                -> "@@ OK"
//   entrada  "DR <comprimento> <hex>"    -> "@@ DR <hex capturado>"
//   entrada  "FIM"                       -> encerra
//
// O primeiro bit deslocado e o bit 0 do valor, como no JTAG. O relogio do
// JTAG (tck, 74 ns) e o da placa (clk, 20 ns) nao tem relacao de fase, para
// exercitar a travessia das filas. Enquanto o testbench espera um comando, o
// tempo simulado fica parado: a placa so anda quando o computador desloca
// bits, o que e o caso mais lento para ela.
//
// Com +invertido, o valor e deslocado a partir do bit mais significativo,
// como faria um cabo que le a cadeia na outra ordem. O TransporteJtag tem de
// perceber isso sozinho, pela marca do registro de estado.
//
// Com +atraso=N, os bits que o computador manda chegam N bordas depois do
// comeco do deslocamento, e os primeiros N sao zero; o tdo continua alinhado.
// E o que o hub JTAG da Intel faz na DE10-Standard (N = 7, medido na placa em
// 25/09/2026). O TransporteJtag mede N pela passagem da ponte e compensa.
`timescale 1ns / 1ps
`default_nettype none

module tb_ponte_jtag;
    localparam integer ENTRADA = 32'h8000_0000;
    localparam integer SAIDA   = 32'h8000_0001;
    localparam integer MAXIMO  = 2048;          // uma mensagem inteira num deslocamento

    reg clk = 1'b0;
    always #10 clk = ~clk;
    reg rst = 1'b1;

    reg        tck = 1'b0, tdi = 1'b0, cdr = 1'b0, sdr = 1'b0;
    reg  [1:0] ir = 2'd0;
    wire       tdo;

    wire [7:0] rx_dado, tx_dado;
    wire       rx_valido, rx_pronto, tx_valido, tx_pronto;

    leakmap_ponte_jtag u_ponte (
        .tck(tck), .tdi(tdi), .tdo(tdo), .ir_in(ir), .captura_dr(cdr), .desloca_dr(sdr),
        .clk(clk), .rx_dado(rx_dado), .rx_valido(rx_valido), .rx_pronto(rx_pronto),
        .tx_dado(tx_dado), .tx_valido(tx_valido), .tx_pronto(tx_pronto), .transbordou());

    leakmap_nucleo u_nucleo (
        .clk(clk), .rst(rst),
        .rx_dado(rx_dado), .rx_valido(rx_valido), .rx_pronto(rx_pronto),
        .tx_dado(tx_dado), .tx_valido(tx_valido), .tx_pronto(tx_pronto),
        .ocupado(), .resultado_pendente());

    task pulso;
        begin
            #37 tck = 1'b1;
            #37 tck = 1'b0;
        end
    endtask

    reg [8*8-1:0]    comando;
    reg [MAXIMO-1:0] valor, capturado;
    integer          comprimento, i, k, lidos, atraso, origem;
    reg              invertido;

    initial begin
        invertido = $test$plusargs("invertido");
        if (!$value$plusargs("atraso=%d", atraso)) atraso = 0;
        repeat (8) @(posedge clk);
        rst = 1'b0;
        repeat (300) @(posedge clk);            // reinicio do nucleo
        $fwrite(SAIDA, "@@ PRONTO simulacao do Verilog da ponte JTAG\n");
        $fflush();
        forever begin
            lidos = $fscanf(ENTRADA, "%s", comando);
            if (lidos != 1) $finish;
            if (comando == "IR") begin
                lidos = $fscanf(ENTRADA, "%d", comprimento);
                ir = comprimento[1:0];
                repeat (20) pulso;              // o deslocamento da instrucao tambem anda o tck
                $fwrite(SAIDA, "@@ OK\n");
            end else if (comando == "DR") begin
                lidos = $fscanf(ENTRADA, "%d", comprimento);
                lidos = $fscanf(ENTRADA, "%h", valor);
                capturado = {MAXIMO{1'b0}};
                cdr = 1'b1;
                pulso;
                cdr = 1'b0;
                sdr = 1'b1;
                for (i = 0; i < comprimento; i = i + 1) begin
                    k = invertido ? comprimento - 1 - i : i;
                    origem = i - atraso;
                    tdi = (origem < 0) ? 1'b0 : valor[invertido ? comprimento - 1 - origem : origem];
                    capturado[k] = tdo;
                    pulso;
                end
                sdr = 1'b0;
                repeat (4) pulso;               // saida e atualizacao do registro
                $fwrite(SAIDA, "@@ DR %h\n", capturado);
            end else if (comando == "FIM") begin
                $finish;
            end else begin
                $fwrite(SAIDA, "@@ ERRO comando desconhecido\n");
            end
            $fflush();
        end
    end
endmodule

`default_nettype wire

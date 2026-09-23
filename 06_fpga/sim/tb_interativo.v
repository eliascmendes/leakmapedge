// LEAKMAP Edge - o nucleo da placa conversando pela entrada e saida padrao.
//
// E o motor `verilog` de 06_fpga/computador/placa_simulada.py: o mesmo
// Verilog que vai para a FPGA, rodando no Icarus, atras de uma porta serial
// simulada. Troca texto com o programa que o chamou, uma linha por evento:
//
//   entrada  "hh"            um byte vindo do computador, em hexadecimal
//   saida    "PRONTO c"      o nucleo esta livre e espera o proximo byte;
//                            c e o ciclo de relogio atual
//   saida    "BYTE hh c"     um byte que o nucleo devolveu, no ciclo c
//
// O nucleo so pede byte novo depois de tratar a mensagem e mandar a resposta
// inteira, entao tudo o que vem antes de um PRONTO pertence a resposta das
// mensagens ja enviadas. Termina quando a entrada padrao fecha.
`timescale 1ns / 1ps
`default_nettype none

module tb_interativo;
    localparam integer ENTRADA = 32'h8000_0000;   // entrada padrao
    localparam integer SAIDA   = 32'h8000_0001;   // saida padrao

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1;

    reg  [7:0] rx_dado = 8'd0;
    reg        rx_valido = 1'b0;
    wire       rx_pronto;
    wire       tx_valido;
    wire [7:0] tx_dado;

    leakmap_nucleo dut (
        .clk(clk), .rst(rst),
        .rx_dado(rx_dado), .rx_valido(rx_valido), .rx_pronto(rx_pronto),
        .tx_dado(tx_dado), .tx_valido(tx_valido), .tx_pronto(1'b1),
        .ocupado(), .resultado_pendente());

    integer ciclo = 0;
    integer lidos;
    reg [7:0] valor;

    always @(posedge clk) begin
        ciclo <= ciclo + 1;
        if (tx_valido) begin
            $fwrite(SAIDA, "BYTE %02h %0d\n", tx_dado, ciclo);
        end
    end

    initial begin
        repeat (4) @(posedge clk);
        rst = 1'b0;
        forever begin
            // espera o nucleo ficar livre para receber
            @(negedge clk);
            while (!(rx_pronto && !tx_valido)) @(negedge clk);
            $fwrite(SAIDA, "PRONTO %0d\n", ciclo);
            $fflush();                      // sem argumento: no Windows e o que esvazia a saida padrao
            // sem espaco no fim do formato: senao o scanf espera o byte seguinte
            lidos = $fscanf(ENTRADA, "%h", valor);
            if (lidos != 1) $finish;
            rx_dado   = valor;
            rx_valido = 1'b1;
            @(posedge clk);                 // o nucleo consome o byte nesta borda
            #1 rx_valido = 1'b0;
        end
    end
endmodule

`default_nettype wire

// LEAKMAP Edge - testbench do modulo de topo, com a serial de verdade.
//
// Manda os bytes de um ensaio curto bit a bit pelo pino uart_rx, le a
// resposta bit a bit no pino uart_tx e compara com o modelo Python da placa.
// A serial roda com poucos ciclos por bit para a simulacao ser rapida; o
// circuito e o mesmo que vai para a placa, so muda o parametro.
`timescale 1ns / 1ps
`default_nettype none

module tb_topo;
    localparam integer FREQ = 1_000_000;
    localparam integer BAUD = 62_500;
    localparam integer CPB  = FREQ / BAUD;          // 16 ciclos por bit
    localparam integer MAX_BYTES = 16384;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg  uart_rx = 1'b1;
    wire uart_tx;
    wire led_vivo, led_ocupado, led_resultado, led_erro;

    leakmap_topo #(.FREQUENCIA_HZ(FREQ), .BAUD(BAUD)) dut (
        .clk(clk), .reinicio(1'b0), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .led_vivo(led_vivo), .led_ocupado(led_ocupado),
        .led_resultado(led_resultado), .led_erro(led_erro));

    reg [7:0] entrada  [0:MAX_BYTES-1];
    reg [7:0] esperado [0:MAX_BYTES-1];
    reg [7:0] obtido   [0:MAX_BYTES-1];
    integer n_entrada, n_esperado, n_obtido, i, b, fd, lidos, erros, silencio;
    reg [7:0] valor;
    reg [8*200-1:0] arq_entrada, arq_esperado;
    reg enviando_tudo;

    // --- receptor do lado do computador -------------------------------------------
    reg [7:0] rx_byte;
    initial begin
        n_obtido = 0;
        forever begin
            @(negedge uart_tx);
            repeat (CPB / 2) @(posedge clk);            // meio do bit de partida
            for (b = 0; b < 8; b = b + 1) begin
                repeat (CPB) @(posedge clk);
                rx_byte[b] = uart_tx;
            end
            repeat (CPB) @(posedge clk);                // bit de parada
            obtido[n_obtido] = rx_byte;
            n_obtido = n_obtido + 1;
        end
    end

    task enviar_byte;
        input [7:0] dado;
        integer k;
        begin
            uart_rx = 1'b0;
            repeat (CPB) @(posedge clk);
            for (k = 0; k < 8; k = k + 1) begin
                uart_rx = dado[k];
                repeat (CPB) @(posedge clk);
            end
            uart_rx = 1'b1;
            repeat (2 * CPB) @(posedge clk);
        end
    endtask

    initial begin
        if (!$value$plusargs("entrada=%s", arq_entrada))  arq_entrada  = "vetores/ensaio_MX-005.entrada.hex";
        if (!$value$plusargs("esperado=%s", arq_esperado)) arq_esperado = "vetores/ensaio_MX-005.saida.hex";

        n_entrada = 0;
        fd = $fopen(arq_entrada, "r");
        if (fd == 0) begin $display("ERRO: nao abriu %0s", arq_entrada); $finish; end
        while (!$feof(fd)) begin
            lidos = $fscanf(fd, "%h\n", valor);
            if (lidos == 1) begin entrada[n_entrada] = valor; n_entrada = n_entrada + 1; end
        end
        $fclose(fd);
        n_esperado = 0;
        fd = $fopen(arq_esperado, "r");
        if (fd == 0) begin $display("ERRO: nao abriu %0s", arq_esperado); $finish; end
        while (!$feof(fd)) begin
            lidos = $fscanf(fd, "%h\n", valor);
            if (lidos == 1) begin esperado[n_esperado] = valor; n_esperado = n_esperado + 1; end
        end
        $fclose(fd);

        repeat (400) @(posedge clk);                    // reinicio de energizacao
        for (i = 0; i < n_entrada; i = i + 1)
            enviar_byte(entrada[i]);

        // espera a linha de saida ficar em silencio
        silencio = 0;
        while (silencio < 40 * CPB) begin
            @(posedge clk);
            if (uart_tx && !led_ocupado) silencio = silencio + 1;
            else silencio = 0;
        end

        erros = 0;
        for (i = 0; i < n_esperado && i < n_obtido; i = i + 1)
            if (obtido[i] !== esperado[i]) erros = erros + 1;
        if (led_erro)
            $display("RESULTADO topo_com_serial FALHOU a fila de entrada transbordou");
        else if (n_obtido != n_esperado || erros != 0)
            $display("RESULTADO topo_com_serial FALHOU obtidos=%0d esperados=%0d divergentes=%0d",
                     n_obtido, n_esperado, erros);
        else
            $display("RESULTADO topo_com_serial PASSOU bytes=%0d pela serial", n_obtido);
        $finish;
    end
endmodule

`default_nettype wire

// LEAKMAP Edge - testbench do nucleo contra o modelo Python da placa.
//
// Le dois arquivos gravados por 06_fpga/computador/gerar_vetores.py: os bytes
// que o computador envia e os bytes que placa_referencia.py devolveu. Alimenta
// o nucleo com o primeiro, respeitando rx_pronto, e exige o segundo byte a
// byte. Uso:  vvp tb_nucleo.vvp +caso=NOME +entrada=ARQ +esperado=ARQ [+obtido=ARQ]
//
// Com +obtido, grava cada byte que o Verilog devolveu, numa linha:
//   byte  bytes_de_entrada_consumidos  ciclo_do_byte  ciclo_da_ultima_entrada
// e o que 06_fpga/sim/prova_cenario_b.py le para decodificar a resposta do
// proprio Verilog, sem passar pelo modelo Python da placa.
`timescale 1ns / 1ps
`default_nettype none

module tb_nucleo;
    localparam integer MAX_BYTES = 65536;
    localparam integer LIMITE_CICLOS = 60_000_000;

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1;

    reg [7:0] entrada  [0:MAX_BYTES-1];
    reg [7:0] esperado [0:MAX_BYTES-1];
    reg [7:0] obtido   [0:MAX_BYTES-1];
    integer n_entrada, n_esperado, n_obtido, posicao, ciclos, ociosos, erros, primeiro, i, fd, lidos;
    integer relogio, ultima_entrada, fd_obtido;
    reg [8*400-1:0] caso, arq_entrada, arq_esperado, arq_obtido;
    reg [7:0] valor;

    wire       rx_pronto;
    wire       tx_valido;
    wire [7:0] tx_dado;
    wire       rx_valido = !rst && (posicao < n_entrada);
    wire [7:0] rx_dado   = entrada[posicao];

    leakmap_nucleo dut (
        .clk(clk), .rst(rst),
        .rx_dado(rx_dado), .rx_valido(rx_valido), .rx_pronto(rx_pronto),
        .tx_dado(tx_dado), .tx_valido(tx_valido), .tx_pronto(1'b1),
        .ocupado(), .resultado_pendente());

    always @(posedge clk) begin
        if (!rst) begin
            relogio <= relogio + 1;
            if (rx_valido && rx_pronto) begin
                posicao <= posicao + 1;
                ultima_entrada <= relogio;
            end
            if (tx_valido) begin
                obtido[n_obtido] <= tx_dado;
                n_obtido <= n_obtido + 1;
                if (fd_obtido != 0)
                    $fwrite(fd_obtido, "%02h %0d %0d %0d\n", tx_dado, posicao, relogio, ultima_entrada);
            end
        end
    end

    initial begin
        if (!$value$plusargs("caso=%s", caso)) caso = "sem_nome";
        if (!$value$plusargs("entrada=%s", arq_entrada) || !$value$plusargs("esperado=%s", arq_esperado)) begin
            $display("ERRO: informe +entrada= e +esperado=");
            $finish;
        end

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

        fd_obtido = 0;
        if ($value$plusargs("obtido=%s", arq_obtido)) begin
            fd_obtido = $fopen(arq_obtido, "w");
            if (fd_obtido == 0) begin $display("ERRO: nao abriu %0s", arq_obtido); $finish; end
        end

        posicao = 0;
        n_obtido = 0;
        relogio = 0;
        ultima_entrada = 0;
        repeat (4) @(posedge clk);
        rst = 1'b0;

        // termina quando toda a entrada foi consumida e o nucleo ficou livre
        ciclos = 0;
        ociosos = 0;
        while (ociosos < 200 && ciclos < LIMITE_CICLOS) begin
            @(posedge clk);
            ciclos = ciclos + 1;
            if (posicao >= n_entrada && rx_pronto && !tx_valido) ociosos = ociosos + 1;
            else ociosos = 0;
        end

        erros = 0;
        primeiro = -1;
        for (i = 0; i < n_esperado && i < n_obtido; i = i + 1)
            if (obtido[i] !== esperado[i]) begin
                if (primeiro < 0) primeiro = i;
                erros = erros + 1;
            end

        if (ciclos >= LIMITE_CICLOS)
            $display("RESULTADO %0s FALHOU tempo esgotado depois de %0d ciclos", caso, ciclos);
        else if (n_obtido != n_esperado || erros != 0) begin
            $display("RESULTADO %0s FALHOU obtidos=%0d esperados=%0d divergentes=%0d primeiro=%0d",
                     caso, n_obtido, n_esperado, erros, primeiro);
            if (primeiro >= 0)
                $display("  byte %0d: obtido %02h, esperado %02h", primeiro, obtido[primeiro], esperado[primeiro]);
        end else
            $display("RESULTADO %0s PASSOU bytes=%0d ciclos=%0d", caso, n_obtido, ciclos);
        if (fd_obtido != 0) $fclose(fd_obtido);
        $finish;
    end
endmodule

`default_nettype wire

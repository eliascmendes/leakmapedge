// LEAKMAP Edge - testbench completo da placa pelo cabo de gravacao (JTAG).
//
// Simula o topo que vai para a DE10-Standard, 06_fpga/placas/intel/
// leakmap_topo_jtag.v, sem nenhuma alteracao: reinicio na energizacao, ponte
// JTAG, nucleo, os dois detectores e os LEDs. So o sld_virtual_jtag da Intel e
// trocado pelo modelo 06_fpga/sim/modelos/sld_virtual_jtag.v, que desloca os
// bits como o cabo USB-Blaster faria.
//
// O testbench faz o papel do computador: le o roteiro gravado por
// 06_fpga/computador/gerar_roteiro_jtag.py e, mensagem a mensagem, manda os
// bytes pela instrucao ESCREVER, busca a resposta pela instrucao LER e exige
// os mesmos bytes que o modelo Python da placa respondeu. Como o computador,
// mede antes o atraso do tdi pela passagem da ponte (instrucao 0) e compensa:
// na DE10-Standard o hub JTAG da Intel entrega o tdi 7 bits atrasado, e o
// modelo faz o mesmo. Tambem confere:
//   - a marca "LK", a versao e a bandeira de transbordo no registro ESTADO;
//   - que nada chega alem da resposta esperada;
//   - o LED led_resultado depois de cada mensagem (resultado esperando
//     confirmacao) e o led_ocupado apagado quando a placa terminou;
//   - o LED led_erro apagado no fim.
// Para cada RESULTADO, mostra o ensaio e as chegadas nos dois canais.
//
// Roda no Questa (06_fpga/sim/questa/rodar.do) e no Icarus Verilog
// (06_fpga/sim/rodar_simulacao.py). Uso: +roteiro=<arquivo .hex>; sem ele,
// roteiro_jtag.hex na pasta de onde a simulacao roda. Termina com
//   RESULTADO tb_leakmap_jtag PASSOU ...   ou   ... FALHOU ...
`timescale 1ns / 1ps
`default_nettype none

module tb_leakmap_jtag;
    localparam integer MAXIMO       = 2048;     // igual ao modelo do JTAG
    localparam integer TAM_ROTEIRO  = 32768;    // igual a TAMANHO de gerar_roteiro_jtag.py
    localparam integer LER_MAX      = 64;       // igual a leakmap_ponte_jtag
    localparam integer LEITURAS_MAX = 4000;     // por resposta (~150 ms simulados)
    localparam [1:0]   IR_ESCREVER  = 2'd1, IR_LER = 2'd2, IR_ESTADO = 2'd3;

    // --- a placa ------------------------------------------------------------------
    reg  clk = 1'b0;
    always #10 clk = ~clk;                      // CLOCK_50
    reg  reinicio = 1'b0;                       // chave SW0 para baixo
    wire led_vivo, led_ocupado, led_resultado, led_erro;

    leakmap_topo_jtag dut (
        .clk(clk), .reinicio(reinicio),
        .led_vivo(led_vivo), .led_ocupado(led_ocupado),
        .led_resultado(led_resultado), .led_erro(led_erro));

    // --- o roteiro ------------------------------------------------------------------
    reg [7:0]        roteiro [0:TAM_ROTEIRO-1];
    reg [8*256-1:0]  arquivo;
    integer          p;                         // posicao de leitura no roteiro
    reg [MAXIMO-1:0] entrada, saida;
    reg [7:0]        recebidos [0:4095];
    integer          n_recebidos, n_casos, n_mensagens, caso, msg, n_env, n_resp, k, j;
    integer          erros, erros_antes, total_mensagens, total_bytes, resultados;
    integer          atraso, enchimento;         // atraso do tdi medido, e o que o completa em bytes
    reg [7:0]        tamanho_nome, bandeiras;
    reg [31:0]       estado;

    task ler16;
        output integer v;
        begin
            v = roteiro[p] + 256 * roteiro[p + 1];
            p = p + 2;
        end
    endtask

    task ler_estado;
        output [31:0] v;
        begin
            dut.u_jtag.ir_scan(IR_ESTADO);
            dut.u_jtag.dr_scan(32, {MAXIMO{1'b0}}, saida);
            v = saida[31:0];
        end
    endtask

    // atraso do tdi: a instrucao 0 da ponte e uma passagem de um bit, entao o
    // padrao volta deslocado de 1 + atraso (como TransporteJtag._medir_atraso)
    task medir_atraso;
        integer d;
        begin
            dut.u_jtag.ir_scan(2'd0);
            entrada = {MAXIMO{1'b0}};
            entrada[31:0] = 32'hA5C30F81;
            dut.u_jtag.dr_scan(64, entrada, saida);
            atraso = -1;
            for (d = 32; d >= 1; d = d - 1)
                if (saida[d +: 32] == 32'hA5C30F81) atraso = d - 1;
            enchimento = (atraso < 0) ? 0 : (8 - atraso % 8) % 8;
        end
    endtask

    // manda n bytes do roteiro, a partir de p, numa mensagem so: primeiro os
    // bits de atraso e de enchimento, que viram bytes de lixo que o nucleo
    // ignora, e logo depois a mensagem, alinhada em bytes
    task enviar;
        input integer n;
        begin
            dut.u_jtag.ir_scan(IR_ESCREVER);
            entrada = {MAXIMO{1'b0}};
            for (j = 0; j < n; j = j + 1)
                entrada[enchimento + 8*j +: 8] = roteiro[p + j];
            dut.u_jtag.dr_scan(8 * n + enchimento + atraso, entrada, saida);
            p = p + n;
        end
    endtask

    // uma leitura: o primeiro byte e a quantidade, depois os bytes
    task uma_leitura;
        integer n;
        begin
            dut.u_jtag.dr_scan(8 + 8 * LER_MAX, {MAXIMO{1'b0}}, saida);
            n = saida[7:0];
            for (j = 0; j < n; j = j + 1) begin
                recebidos[n_recebidos] = saida[8 + 8*j +: 8];
                n_recebidos = n_recebidos + 1;
            end
        end
    endtask

    // busca a resposta ate juntar `esperados` bytes; depois confere que nada mais chega
    task receber;
        input integer esperados;
        integer leituras;
        begin
            dut.u_jtag.ir_scan(IR_LER);
            n_recebidos = 0;
            leituras = 0;
            while (n_recebidos < esperados && leituras < LEITURAS_MAX) begin
                uma_leitura;
                leituras = leituras + 1;
            end
            repeat (2) uma_leitura;
        end
    endtask

    task mostrar_nome;
        integer c;
        begin
            for (c = 0; c < tamanho_nome; c = c + 1)
                $write("%c", roteiro[p + c]);
        end
    endtask

    task mostrar_resultado;
        integer c;
        begin
            // RESULTADO: A5 5A 83 tamanho(2) | id(8) situacao(1) n_amostras(2) contadores(6) | canal A(27) | canal B(27)
            $write("    RESULTADO ");
            for (c = 5; c < 13; c = c + 1)
                if (recebidos[c] != 8'h00) $write("%c", recebidos[c]);
            $write(": situacao %0d, amostras %0d", recebidos[13], recebidos[14] + 256 * recebidos[15]);
            if (recebidos[22][0]) $write(", chegada A na amostra %0d", recebidos[25] + 256 * recebidos[26]);
            else                  $write(", canal A sem chegada");
            if (recebidos[49][0]) $write(", chegada B na amostra %0d", recebidos[52] + 256 * recebidos[53]);
            else                  $write(", canal B sem chegada");
            $write("\n");
        end
    endtask

    // TEMPOS: A5 5A 87 tamanho(2) | id(8) situacao modo frequencia(4) periodo(4) n(2)
    //        contado ciclos(4) min(2) max(2) atrasadas(2) declA(4) latA(2) declB(4) latB(2)
    function integer u16;
        input integer i;
        u16 = recebidos[i] + 256 * recebidos[i + 1];
    endfunction
    function integer u32;
        input integer i;
        u32 = recebidos[i] + 256 * recebidos[i + 1] + 65536 * recebidos[i + 2] + 16777216 * recebidos[i + 3];
    endfunction

    task mostrar_tempos;
        begin
            $write("    TEMPOS contados pelo circuito: %0s, execucao de %0d ciclos, %0d a %0d ciclos por amostra",
                   recebidos[14] ? "tempo real" : "lote", u32(26), u16(30), u16(32));
            if (recebidos[14]) $write(", uma amostra a cada %0d ciclos, %0d atrasadas", u32(19), u16(34));
            if (u32(36) != 32'hFFFFFFFF) $write(", declaracao A %0d ciclos depois da entrega", u16(40));
            if (u32(42) != 32'hFFFFFFFF) $write(", B %0d", u16(46));
            $write("\n");
            if (recebidos[25] != 8'd1) begin
                $display("    TEMPOS sem a marca de contado pelo circuito");
                erros = erros + 1;
            end
            if (recebidos[14] && u16(34) != 0) begin
                $display("    tempo real com amostras atrasadas");
                erros = erros + 1;
            end
        end
    endtask

    initial begin
        if (!$value$plusargs("roteiro=%s", arquivo)) arquivo = "roteiro_jtag.hex";
        $readmemh(arquivo, roteiro);
        erros = 0;
        total_mensagens = 0;
        total_bytes = 0;
        resultados = 0;

        // reinicio na energizacao do topo: 256 ciclos de relogio
        repeat (400) @(posedge clk);

        ler_estado(estado);
        $display("ESTADO da ponte: 0x%08h (marca \"%s\", versao %0d, transbordo %0d)", estado,
                 estado[31:16], estado[15:8], estado[0]);
        if (estado[31:16] !== 16'h4C4B || estado[15:8] !== 8'd1 || estado[0] !== 1'b0)
            erros = erros + 1;

        medir_atraso;
        $display("atraso do tdi medido pela passagem da ponte: %0d bits (enchimento %0d)", atraso, enchimento);
        if (atraso < 0) begin
            $display("a passagem da ponte nao devolveu o padrao");
            erros = erros + 1;
        end

        p = 0;
        ler16(n_casos);
        for (caso = 0; caso < n_casos; caso = caso + 1) begin
            tamanho_nome = roteiro[p];
            p = p + 1;
            $write("CASO %0d: ", caso + 1);
            mostrar_nome;
            $write("\n");
            p = p + tamanho_nome;
            ler16(n_mensagens);
            erros_antes = erros;
            for (msg = 0; msg < n_mensagens; msg = msg + 1) begin
                ler16(n_env);
                enviar(n_env);
                ler16(n_resp);
                receber(n_resp);
                if (n_recebidos != n_resp) begin
                    $display("    mensagem %0d: chegaram %0d bytes, esperados %0d", msg + 1, n_recebidos, n_resp);
                    erros = erros + 1;
                end
                // bandeiras depois da resposta; com o bit 1, segue a mascara
                bandeiras = roteiro[p + n_resp];
                for (k = 0; k < n_resp && k < n_recebidos; k = k + 1)
                    if ((!bandeiras[1] || roteiro[p + n_resp + 1 + k] != 8'h00)
                        && recebidos[k] !== roteiro[p + k]) begin
                        if (erros == erros_antes)
                            $display("    mensagem %0d, byte %0d: chegou %02h, esperado %02h",
                                     msg + 1, k, recebidos[k], roteiro[p + k]);
                        erros = erros + 1;
                    end
                if (n_resp >= 71 && roteiro[p + 2] == 8'h83) begin
                    mostrar_resultado;
                    resultados = resultados + 1;
                end
                if (n_resp >= 50 && roteiro[p + 2] == 8'h87)
                    mostrar_tempos;
                p = p + n_resp + 1 + (bandeiras[1] ? n_resp : 0);
                if (led_resultado !== bandeiras[0]) begin
                    $display("    mensagem %0d: led_resultado = %b, esperado %b", msg + 1, led_resultado, bandeiras[0]);
                    erros = erros + 1;
                end
                if (led_ocupado !== 1'b0) begin
                    $display("    mensagem %0d: led_ocupado aceso depois da resposta", msg + 1);
                    erros = erros + 1;
                end
                total_mensagens = total_mensagens + 1;
                total_bytes = total_bytes + n_env + n_resp;
            end
            if (erros == erros_antes) $display("    %0d mensagens, iguais ao modelo", n_mensagens);
            else                      $display("    %0d mensagens, COM DIFERENCAS", n_mensagens);
        end

        ler_estado(estado);
        if (estado[0] !== 1'b0 || led_erro !== 1'b0) begin
            $display("a fila de entrada transbordou");
            erros = erros + 1;
        end

        if (erros == 0)
            $display("RESULTADO tb_leakmap_jtag PASSOU casos=%0d mensagens=%0d bytes=%0d resultados=%0d tempo_simulado=%0.1f ms",
                     n_casos, total_mensagens, total_bytes, resultados, $time / 1.0e6);
        else
            $display("RESULTADO tb_leakmap_jtag FALHOU erros=%0d casos=%0d mensagens=%0d",
                     erros, n_casos, total_mensagens);
        $finish;
    end
endmodule

`default_nettype wire

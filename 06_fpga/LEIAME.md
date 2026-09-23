# FPGA — cenário B

Reprodução de sinais digitais em FPGA física: os ensaios já verificados no
cenário A são convertidos em inteiros, carregados na placa, e a placa faz a
detecção e a marcação das chegadas nos dois canais. O computador calcula a
posição e compara com o software.

O cenário valida o processamento digital na placa. Não valida sensor físico,
transmissor, entrada analógica, conversor analógico-digital real nem
instalação industrial.

## O que já existe

| Caminho | Conteúdo |
|---|---|
| [`ESPECIFICACAO.md`](ESPECIFICACAO.md) | Contrato entre computador e FPGA: representação, quadros, mensagens, comportamento da placa e o detector inteiro em pseudocódigo |
| [`rtl/`](rtl) | O Verilog da placa, em Verilog 2005 puro, sem nada de fabricante |
| [`sim/`](sim) | Testbenches, o script que roda todos os casos e o de síntese de conferência |
| [`computador/`](computador) | Todo o lado do computador, etapas B-01 a B-14, com testes |
| [`sintese/`](sintese) | Estatísticas de síntese do Yosys para Xilinx série 7 e Cyclone V |
| [`resultados/`](resultados) | Dimensionamento e resultados do cenário B, sempre com a origem no nome do arquivo |

## Verilog

| Arquivo | O que faz |
|---|---|
| `leakmap_topo.v` | Topo: serial, fila de entrada, núcleo e LEDs. Frequência do relógio e velocidade da serial são parâmetros |
| `leakmap_nucleo.v` | Lê quadros e confere CRC, guarda a configuração, grava as amostras, executa com índice comum aos dois canais e devolve o resultado |
| `leakmap_detector.v` | Detector de um canal em aritmética inteira: passa-altas, somas de energia, limiar, retrocesso e maior salto |
| `leakmap_multiplicador.v` | Multiplicador sequencial de soma e deslocamento, compartilhado pelo detector |
| `leakmap_uart.v` | Serial 8N1 de recepção e transmissão, e a fila de bytes |

Escolhas de projeto que tornam o mesmo Verilog válido em qualquer placa:

- **Sem multiplicador combinacional grande.** As multiplicações de até 64 × 32
  bits são feitas uma de cada vez por um multiplicador sequencial. Não
  dependem de bloco DSP de fabricante e fecham tempo com folga. O maior caso
  da matriz leva cerca de 52 mil ciclos, meio milissegundo a 100 MHz.
- **Memórias escritas no padrão que as duas ferramentas reconhecem.** As
  amostras viram blocos de memória dedicados no Vivado e no Quartus.
- **Reinício interno na energização.** Não depende de botão da placa.

## Verificação

`sim/rodar_simulacao.py` gera os vetores a partir do modelo Python da placa,
compila o Verilog no Icarus Verilog e exige, byte a byte, a mesma resposta:

- os 45 ensaios da matriz, com a conversa completa do computador;
- sinais sintéticos com retrocesso longo, retrocesso truncado e atraso
  conhecido de 40 amostras entre canais;
- casos de protocolo: bloco corrompido e reenviado, lacuna de sequência,
  mensagens mal formadas, cabeçalho absurdo, tipo desconhecido, execução sem
  configuração, ensaio acima da capacidade, pedido de resultado repetido e
  três ensaios seguidos na mesma placa;
- o sistema completo, com a serial de verdade no caminho.

**Situação: 57 de 57 casos idênticos ao modelo.** O teste foi conferido
estragando o Verilog de propósito: trocar `>` por `>=` no retrocesso derruba
15 casos, e deixar de contar uma descontinuidade derruba o caso da lacuna.

## Síntese de conferência

`sim/sintetizar_yosys.py` sintetiza o mesmo Verilog com o Yosys, sem ferramenta
de fabricante:

| Recurso | Xilinx série 7 (Spartan-7) | Cyclone V |
|---|---|---|
| Lógica | cerca de 7 900 LUTs | cerca de 7 800 ALUTs, mais 2 950 aritméticas |
| Flip-flops | cerca de 5 900 | cerca de 5 900 |
| Blocos de memória | 4 RAMB36 e 1 RAMB18 | 17 M10K |

Cabe com folga numa Spartan-7 XC7S25 (14 600 LUTs) ou maior e numa Cyclone V.
Não cabe na XC7S6. São estimativas: os números finais, e o fechamento de
tempo, vêm do Vivado ou do Quartus na placa escolhida.

## Lado do computador

| Arquivo | Etapa | O que faz |
|---|---|---|
| `selo.py` | B-01 | Selo de verificação (SHA-256) e seletor que recusa ensaio sem selo ou alterado |
| `representacao.py` | B-02, B-03 | Especificação em 16 bits, conversão e inversa, tabela de bordas, contador de saturação |
| `protocolo.py` | B-04, B-06, B-07, B-10 | Quadros com CRC-16, blocos numerados, configuração, recibos e resultado |
| `dimensionamento.py` | B-05 | Conta de memória e da serial contra cada placa candidata; decide a via 1 |
| `preparo.py` | B-02, B-07 | Conversão do ensaio e parâmetros inteiros da placa |
| `hospedeiro.py` | B-06, B-07, B-10 | Conversa com a placa: configura e confere, carrega com reenvio, executa e confirma |
| `transporte.py` | — | Em memória (referência) ou porta serial (FPGA) |
| `placa_referencia.py` | B-06 a B-10 | Modelo do que a FPGA faz, amostra a amostra, só com inteiros |
| `registro_b.py` | B-11 | Δt pelos índices, decisão e posição com o código do cenário A, campo `origem` |
| `comparador.py` | B-13 | Divergência com o software em amostras e em metros, com a causa apontada |
| `executar_cenario_b.py` | B-01 a B-14 | Roda tudo e fecha o relatório, com as tentativas gravadas antes da execução |
| `gerar_vetores.py` | — | Grava os bytes de cada caso para o testbench do Verilog |

Resultado com a referência Python da placa (arquivos com `referencia` no nome,
que **não são resultado de FPGA**): 45 ensaios concluídos; 43 idênticos ao
software e 2 com o cruzamento do limiar uma amostra depois, mesma chegada e
mesma posição, por causa da conversão para inteiros; contra a verdade, os
mesmos números do cenário A.

## Como rodar

```bash
python 06_fpga/computador/executar_cenario_b.py
python -m unittest discover -s 06_fpga/computador/testes -p "teste_*.py"
python 06_fpga/sim/rodar_simulacao.py
python 06_fpga/sim/sintetizar_yosys.py
```

A simulação precisa do Icarus Verilog; a síntese, do Yosys ou do pacote
`yowasp-yosys`. Com a FPGA na porta serial (precisa de `pip install pyserial`):

```bash
python 06_fpga/computador/executar_cenario_b.py --serial COM5
```

## O que falta

- O arquivo de pinos e relógio da placa escolhida (XDC no Vivado, QSF no
  Quartus), ligando `clk`, `reinicio`, `uart_rx`, `uart_tx` e os LEDs, e o
  parâmetro `FREQUENCIA_HZ` do topo com o relógio da placa.
- Síntese, fechamento de tempo e gravação na placa.
- A tela do modo FPGA no painel, com o rótulo de origem (B-12).

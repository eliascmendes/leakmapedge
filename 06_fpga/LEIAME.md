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
| [`placas/`](placas) | Projeto do Quartus da DE10-Standard e o topo para placas Intel que conversa pelo cabo de gravação, com o [roteiro do laboratório](placas/de10_standard/ROTEIRO.md) |
| [`sintese/`](sintese) | Estatísticas de síntese do Yosys para Xilinx série 7 e Cyclone V |
| [`resultados/`](resultados) | Dimensionamento e resultados do cenário B, sempre com a origem no nome do arquivo |

## Verilog

| Arquivo | O que faz |
|---|---|
| `leakmap_topo.v` | Topo: serial, fila de entrada, núcleo e LEDs. Frequência do relógio e velocidade da serial são parâmetros |
| `leakmap_nucleo.v` | Lê quadros e confere CRC, guarda a configuração, grava as amostras, executa com índice comum aos dois canais e devolve o resultado |
| `leakmap_detector.v` | Detector de um canal em aritmética inteira: passa-altas, somas de energia, limiar, retrocesso e maior salto |
| `leakmap_multiplicador.v` | Multiplicador sequencial de soma e deslocamento, compartilhado pelo detector |
| `leakmap_saude.v` | Autoteste de um canal, amostra a amostra: congelado, saturado, fora da faixa, salto |
| `leakmap_uart.v` | Serial 8N1 de recepção e transmissão, e a fila de bytes |
| `leakmap_ponte_jtag.v` | Ponte entre o JTAG virtual e o núcleo, para conversar pelo cabo de gravação; filas entre os dois relógios com ponteiros em código Gray |
| `leakmap_demo.v` | Demonstração autônoma: gera os sinais dos dois sensores na própria placa, entrega as amostras aos mesmos detectores e calcula a posição |
| `leakmap_sete_segmentos.v` | Decodificador dos displays de 7 segmentos, para a demonstração |

Escolhas de projeto que tornam o mesmo Verilog válido em qualquer placa:

- **Sem multiplicador combinacional grande.** As multiplicações de até 64 × 32
  bits são feitas uma de cada vez por um multiplicador sequencial. Não
  dependem de bloco DSP de fabricante e fecham tempo com folga. O ensaio mais
  longo da matriz é processado em 32 335 ciclos: 646,7 µs na DE10-Standard, a
  50 MHz, contados pelo próprio circuito.
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
  configuração, ensaio acima da capacidade, pedido de resultado repetido, o
  mesmo ensaio duas vezes seguidas e três ensaios seguidos na mesma placa;
- o sistema completo, com a serial de verdade no caminho;
- o autoteste dos canais: a mensagem SAUDE em todos os ensaios da matriz e em
  canais estragados de propósito (congelado, cabo rompido, pico isolado);
- a demonstração autônoma, contra o modelo em 242 posições e em 18 casos com
  sensor estragado, e o topo dela na DE10-Standard, com botões e displays;
- o topo da DE10-Standard pelo cabo de gravação, `placas/intel/leakmap_topo_jtag.v`
  sem alteração, com um modelo no lugar do `sld_virtual_jtag` da Intel:
  [`sim/tb_leakmap_jtag.v`](sim/tb_leakmap_jtag.v), 9 casos e 109 mensagens,
  conferindo também os LEDs e o registro de estado da ponte. O mesmo
  testbench roda no Questa que vem com o Quartus; ver
  [`sim/questa/LEIAME.md`](sim/questa/LEIAME.md).

**Situação: 71 de 71 casos idênticos ao modelo.** O teste foi conferido
estragando o Verilog de propósito: trocar `>` por `>=` no retrocesso derruba
15 casos, e deixar de contar uma descontinuidade derruba o caso da lacuna.

## Prova do cenário B antes da placa

O testbench grava a resposta que o próprio Verilog devolveu.
`sim/prova_cenario_b.py` decodifica essa resposta e confere os critérios do
cenário B sem passar pelo modelo Python da placa:

| Critério | O que foi conferido | Resultado |
|---|---|---|
| B-09 | Índice de cruzamento e de chegada, bandeira de truncado e oportunidades de decisão iguais aos de `04_detector/detector_ponto_fixo.py`, rodado sobre o sinal original | 90 de 90 canais, e 4 de 4 sinais sintéticos de retrocesso |
| B-08 | Canal B igual ao A atrasado 40 amostras; todas as amostras reproduzidas com um índice só | 40 amostras de diferença na chegada e no cruzamento |
| B-07 | Configuração lida de volta igual à enviada; o mesmo ensaio duas vezes, e com outro no meio | 45 de 45 configurações; resultados idênticos byte a byte |
| B-06 | Bloco corrompido no enlace recusado pelo CRC, reenviado e aceito; bloco fora de sequência recusado | Resultado igual ao do ensaio sem corrupção; execução com lacuna recusada |

Depois, o computador do cenário B roda os 45 ensaios lendo a resposta do
Verilog, com a origem `simulacao_do_verilog`, e o avaliador independente
compara com a verdade. Resultado: 30 detecções, nenhum falso alarme, erro
mediano de 0,241 m, os mesmos números do cenário A. Os arquivos ficam em
`resultados/` com `simulacao` no nome, separados dos da referência e dos da
placa.

A prova também foi conferida estragando de propósito um índice de chegada na
resposta gravada: o B-09 cai para 89 de 90 e o script falha.

O processamento na placa, do fim da mensagem EXECUTAR ao começo do
RESULTADO, leva de mediana 16 103 ciclos e no máximo 32 338 ciclos (MX-039, 500
amostras) na simulação. Na DE10-Standard, o próprio circuito conta 32 335
ciclos para a mesma execução (os 3 de diferença são a leitura e a resposta da
mensagem, fora da execução): 646,7 µs a 50 MHz, para um ensaio que cobre 0,2 s
de sinal.

## Tempo na placa: contagem de ciclos, tempo real e comparação com a CPU

A vantagem própria da FPGA é o tempo: latência fixa, igual em todas as
execuções. Três partes medem isso na própria placa.

**Contagem de ciclos (TEMPOS).** O núcleo conta, em cada execução, os ciclos
da execução inteira, os ciclos de cada amostra (menor e maior), e, em cada
canal, o ciclo em que declarou o evento e a latência da declaração: da entrega
da amostra do cruzamento ao evento declarado. O computador pede esses números
com PEDIR_TEMPOS depois de cada ensaio. Na simulação, o contador confere com a
contagem do próprio simulador (critério Tempos de `sim/prova_cenario_b.py`); na
placa, deu os mesmos números da simulação.

**Tempo real (EXECUTAR_TEMPO_REAL).** A mesma execução, mas a placa entrega ao
detector uma amostra a cada período de amostragem, marcado pelo próprio
relógio, como um conversor entregaria. O resultado é idêntico ao da execução
em lote. Na DE10-Standard, os 45 ensaios em tempo real: 45 concluídos, os
mesmos resultados, nenhuma amostra atrasada, a execução levando exatamente a
duração do sinal (de 40,1 ms a 200,3 ms) e a declaração saindo de 1,78 a
2,04 µs depois da amostra do cruzamento.

```bash
python 06_fpga/computador/executar_cenario_b.py --jtag --tempo-real
```

**FPGA × notebook** ([`computador/comparar_latencia.py`](computador/comparar_latencia.py)).
O mesmo detector em aritmética inteira, nos 30 ensaios com evento, 10 vezes
cada, uma amostra por período de amostragem. No notebook, em Python, com espera
ativa pela hora de cada amostra (o melhor caso para a CPU):

| | FPGA (DE10-Standard, 50 MHz) | Notebook (Python) |
|---|---|---|
| Declaração depois da amostra do cruzamento, mediana | 1,94 µs | 14,5 µs |
| Pior caso | 2,04 µs | 45,6 µs |
| Repetições do mesmo ensaio | mesmo número de ciclos em 30 de 30 ensaios | desvio de 4,9 µs |
| Amostras processadas depois da hora | 0 | uma com 860 µs de atraso, em 60 180 |

Um detector em C no notebook seria mais rápido que em Python; o que a tabela
mostra de próprio da FPGA é a variação: a placa faz a mesma conta sempre no
mesmo número de ciclos, e nunca perde a hora de uma amostra. Resultado em
[`resultados/leakmap_latencia_fpga_e_cpu_v1.json`](resultados/leakmap_latencia_fpga_e_cpu_v1.json).

```bash
python 06_fpga/computador/comparar_latencia.py --jtag
```

## Autoteste dos canais na placa

Um canal que falha em silêncio é pior que um canal que não existe: um
transmissor travado ou um cabo rompido pode virar uma "chegada" e uma posição
errada. Por isso a placa acompanha cada canal, amostra a amostra, no mesmo
ciclo em que o detector recebe a amostra
([`rtl/leakmap_saude.v`](rtl/leakmap_saude.v)), e acusa quatro falhas:

| Falha | Como a placa vê |
|---|---|
| Congelado | o mesmo código muitas amostras seguidas (32 amostras, 12,8 ms) |
| Saturado | amostra no extremo da palavra, 0 ou 65 535 |
| Fora da faixa | código fora da faixa de medição do transmissor |
| Salto | variação entre duas amostras seguidas maior que meia faixa, que nenhuma onda faz |

O computador pede o autoteste depois de cada ensaio (PEDIR_SAUDE), com os
limites do transmissor declarado no ensaio, e grava o resultado no registro
(`autoteste_na_placa`) e no relatório (`autoteste_dos_canais`). Detalhes da
mensagem em [`ESPECIFICACAO.md`](ESPECIFICACAO.md).

Na simulação do Verilog: os 90 canais da matriz saem saudáveis, com as
estatísticas iguais às contadas direto nas amostras; e cada canal estragado de
propósito é acusado com a falha certa, e só ela (critério Autoteste de
`sim/prova_cenario_b.py`):

| Canal estragado de propósito | A placa acusa |
|---|---|
| Canal B congelado a partir da amostra 60 (MX-013) | congelado |
| Canal A cai a código 0 na amostra 100, cabo rompido (MX-013) | congelado, saturado, fora da faixa |
| Uma amostra isolada do canal B cai mais que meia faixa (MX-021) | salto |

O mesmo canal congelado, julgado com os limites abertos, não é acusado: quem
decide o que é falha é o transmissor declarado, não um número fixo no
circuito.

Na placa, o autoteste ainda não rodou: o `leakmap.sof` gravado na
DE10-Standard em 25/09/2026 é anterior a ele. Com o projeto recompilado, o
teste é o passo B.6 do
[roteiro de testes](placas/de10_standard/ROTEIRO_DE_TESTES.txt).

## Demonstração autônoma na placa

Um segundo projeto da DE10-Standard, sem computador: escolhe-se nos botões
onde a linha rompe, e a placa gera os sinais dos dois sensores, entrega uma
amostra a cada período de amostragem aos mesmos detectores do cenário B
(`rtl/leakmap_detector.v`), marca as chegadas e mostra a posição calculada
nos displays. Serve para mostrar a placa funcionando sozinha, de mão em mão.

| Na placa | Função |
|---|---|
| KEY3, KEY2, KEY1, KEY0 | −10 m, −1 m, +1 m, +10 m na posição do rompimento, de 40 m a 160 m |
| SW1 | para cima: ruído nos dois sinais |
| SW2 | para cima: estraga o sensor A, cabo rompido (código 0) |
| SW3 | para cima: estraga o sensor B, transmissor travado (repete o último código) |
| SW0 | reinício; para baixo em uso |
| HEX5..HEX3 | posição escolhida, em metros |
| HEX2..HEX0 | posição que a placa calculou; `---` enquanto calcula, `E` sem as duas chegadas, `F A`, `F b` ou `FAb` quando o autoteste acusa o sensor A, o B ou os dois |
| LEDR0 · LEDR1 · LEDR2 · LEDR3 | pisca · calculando · chegada no sensor A · chegada no sensor B |
| LEDR4 · LEDR5 | autoteste acusou o sensor A · o sensor B |

Os sensores ficam em 40 m e 160 m. O sinal é sintético: pressão constante e,
a partir da chegada da onda em cada sensor, uma queda em rampa; com ruído, cada
canal soma de −3 a +4 códigos de um LFSR de 16 bits. São 512 amostras por
sensor, entregues no período de amostragem dos ensaios (20 065 ciclos a
50 MHz): cada cálculo leva cerca de 0,2 s, o tempo de o sinal passar.

Com SW2 ou SW3, o sensor estraga na amostra 100, antes da onda chegar. O
cabo rompido mostra por que o autoteste importa: a queda até 0 parece uma
chegada, e sem autoteste a placa calcularia 38 m para um rompimento em 60 m.
Com o autoteste, ela mostra `F A` no lugar da posição. O transmissor travado
só é distinguível com ruído (SW1 para cima): sem ruído o sinal é ideal e fica
constante de verdade, e a placa mostra só que falta a chegada no B (`E`).

O modelo de referência é [`computador/demo_autonoma.py`](computador/demo_autonoma.py):
gera as constantes do Verilog (`rtl/leakmap_demo_parametros.vh`, com os
parâmetros do detector em inteiros) e a resposta esperada. Em simulação, o
Verilog dá a mesma chegada e a mesma posição que o modelo nas 242 combinações
de 40 m a 160 m, com e sem ruído, e a posição calculada acerta a escolhida em
todas; e o mesmo autoteste nos 18 casos com sensor estragado
([`sim/tb_demo.v`](sim/tb_demo.v)). O topo da placa também é simulado
inteiro ([`sim/tb_demo_de10.v`](sim/tb_demo_de10.v)): aperta os botões, lê os
displays de volta, inclusive `F A`, `F b` e `FAb` com as chaves SW2 e SW3, e
confere uma amostra exatamente a cada período.

**Na DE10-Standard (25/09/2026):** compilada no Quartus (37% da lógica, folga
de tempo de +4,187 ns a 50 MHz), gravada e rodando: ao ligar, a placa mostrou
80 m escolhido e 80 m calculado, sozinha, sem computador. Os botões, as chaves
de ruído e de sensor estragado e o autoteste ainda não foram testados na
placa; o passo a passo está em
[`placas/de10_standard/ROTEIRO_DE_TESTES.txt`](placas/de10_standard/ROTEIRO_DE_TESTES.txt).

Para gravar, a partir da raiz do repositório:

```bash
python 06_fpga/placas/preparar_quartus.py --placa de10_standard/demo
```

O projeto é copiado para `leakmap_quartus/de10_standard/demo`, na pasta do
usuário (o Quartus não aceita caminho com acento). Abrir `leakmap_demo_de10.qpf` no Quartus, compilar e gravar
`output_files/leakmap_demo_de10.sof` pelo Programmer, como no
[roteiro do laboratório](placas/de10_standard/ROTEIRO.md). A gravação troca o
circuito da placa: para voltar ao cenário B pelo cabo, gravar de novo o
`leakmap.sof`.

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
| `transporte.py` | — | Em memória (referência), resposta gravada do Verilog no simulador (para se a conversa sair do que foi simulado), porta serial ou cabo de gravação pelo JTAG (FPGA) |
| `ponte_jtag.tcl` | — | Roda no `quartus_stp` e leva os deslocamentos do JTAG virtual entre o computador e a placa |
| `placa_referencia.py` | B-06 a B-10 | Modelo do que a FPGA faz, amostra a amostra, só com inteiros |
| `registro_b.py` | B-11 | Δt pelos índices, decisão e posição com o código do cenário A, campo `origem` |
| `comparador.py` | B-13 | Divergência com o software em amostras e em metros, com a causa apontada |
| `executar_cenario_b.py` | B-01 a B-14 | Roda tudo e fecha o relatório, com as tentativas gravadas antes da execução e uma linha por ensaio na hora em que o resultado chega |
| `placa_simulada.py` | — | Programa que fala o protocolo serial da FPGA, para testar o computador de ponta a ponta sem hardware |
| `gerar_vetores.py` | — | Grava os bytes de cada caso para o testbench do Verilog |

Resultado com a referência Python da placa (arquivos com `referencia` no nome,
que **não são resultado de FPGA**): 45 ensaios concluídos; 43 idênticos ao
software e 2 com o cruzamento do limiar uma amostra depois, mesma chegada e
mesma posição, por causa da conversão para inteiros; contra a verdade, os
mesmos números do cenário A.

## Placa simulada

`computador/placa_simulada.py` é um programa que fica do outro lado do fio no
lugar da FPGA e fala o mesmo protocolo. O computador conversa com ela pelo
mesmo código da porta serial, só com outro endereço. Assim o receptor, o
cálculo de posição e o avaliador são testados de ponta a ponta sem hardware,
e a tela do modo FPGA (B-12) vai ser testada do mesmo jeito. No dia, basta
trocar o endereço da placa simulada pela porta da placa real.

Dois motores podem responder:

- `referencia`: o modelo Python da placa;
- `verilog`: o próprio Verilog da placa, rodando ciclo a ciclo no Icarus
  Verilog atrás da porta, por [`sim/tb_interativo.v`](sim/tb_interativo.v).

O enlace pode ser piorado de propósito, para exercitar o receptor: bits
trocados nos dois sentidos, mensagens RESULTADO perdidas e o tempo de fio da
serial a 115 200 bits/s.

A placa simulada responde à mensagem IDENTIFICAR, que a FPGA ignora. Por isso
o computador grava os resultados dela com a origem `placa_simulada` e nunca
como resultado de FPGA. Essas rodadas são teste do computador e ficam fora do
repositório.

Os testes de ponta a ponta
([`computador/testes/teste_placa_simulada.py`](computador/testes/teste_placa_simulada.py))
rodam a matriz inteira pela serial:

- sem ruído, os 45 ensaios chegam com o mesmo resultado da referência, e o
  avaliador independente dá os números do cenário A;
- com cerca de um bit trocado a cada 3 300 bytes, nos dois sentidos, e 20% dos
  resultados perdidos, o computador reenvia blocos e pede resultados de novo.
  Nenhum resultado errado passa em silêncio: cada ensaio chega igual ao da
  referência ou sai marcado como falha, com o motivo. Com 6 tentativas, os 45
  concluem;
- com o Verilog atrás da porta e ruído no enlace, os ensaios testados chegam
  iguais aos da referência;
- quem não responde a IDENTIFICAR fica como `fpga`.

Esses testes mostraram três pontos fracos do receptor, já corrigidos: um
recibo atrasado de bloco já confirmado derrubava o ensaio; um EXECUTAR
corrompido nunca era reenviado; e respostas fora de hora se acumulavam na
fila. Agora o computador descarta e conta as respostas fora de hora, e manda
EXECUTAR de novo quando a placa acusa CRC inválido.

## Pelo cabo de gravação, sem adaptador

A serial pede um adaptador USB-serial ligado nos pinos da placa. Para não
depender dele, o computador também conversa com a FPGA pelo próprio cabo que a
grava (USB-Blaster), pelo JTAG virtual da Intel. As mensagens são as mesmas;
só o fio muda.

- [`rtl/leakmap_ponte_jtag.v`](rtl/leakmap_ponte_jtag.v): a ponte, em
  Verilog puro. Recebe os sinais do JTAG virtual e entrega ao núcleo a mesma
  interface de bytes da serial.
- [`placas/intel/leakmap_topo_jtag.v`](placas/intel/leakmap_topo_jtag.v): o
  topo para placas Intel, com o `sld_virtual_jtag`. É o único arquivo do
  projeto com módulo de fabricante.
- [`computador/ponte_jtag.tcl`](computador/ponte_jtag.tcl) roda no
  `quartus_stp` e abre uma porta TCP local; o `TransporteJtag` conecta nela.
  TCP e não a entrada e saída padrão, porque o `quartus_stp` só entrega o que
  escreve quando termina.
- [`placas/de10_standard/`](placas/de10_standard): o projeto do Quartus da
  DE10-Standard. [`placas/preparar_quartus.py`](placas/preparar_quartus.py)
  copia o projeto para uma pasta sem acento, porque o Quartus não aceita
  acento no caminho, e compila.

Ao conectar, o computador lê o registro de estado da ponte e confere a marca
"LK": uma placa sem o projeto gravado para com mensagem clara, e a mesma
leitura descobre a ordem em que o cabo desloca os bits. Depois mede o atraso
do tdi pela passagem da ponte (instrução 0). Na DE10-Standard, o hub JTAG da
Intel entrega ao circuito os bits que o computador manda 7 bordas depois do
começo do deslocamento, enquanto o tdo sai alinhado. O computador compensa:
cada mensagem vai num deslocamento só, precedida de bits de enchimento que
formam um byte de lixo, e o núcleo o ignora porque só começa a ler uma
mensagem no `A5 5A`.

**Na placa, em 25/09/2026:** DE10-Standard (`5CSXFC6D6F31C6N`), pelo cabo de
gravação, os 45 ensaios da matriz. 45 concluídos, sem nenhum reenvio nem falha
de CRC, e os registros iguais, um a um, aos do Verilog simulado. Contra o
software: mesma chegada nos 90 canais e mesma posição nos 45 ensaios; em
MX-021 e MX-022 o cruzamento do limiar sai uma amostra depois, como a
simulação já mostrava. Contra a verdade: 30 detecções, nenhum falso alarme,
erro mediano de 0,241 m e máximo de 1,046 m, os números do cenário A.
Resultados em `resultados/` com `fpga` no nome.

Os testes ([`computador/testes/teste_ponte_jtag.py`](computador/testes/teste_ponte_jtag.py))
ligam o computador inteiro do cenário B ao Verilog da ponte e do núcleo no
Icarus, por [`sim/tb_ponte_jtag.v`](sim/tb_ponte_jtag.v), que fala as mesmas
linhas do `quartus_stp`. Os ensaios chegam iguais aos da referência, inclusive
com o cabo deslocando os bits na ordem inversa. Com o Quartus instalado, o
teste também conversa com o `quartus_stp` de verdade pela porta local.

O passo a passo do dia está em [`placas/de10_standard/ROTEIRO.md`](placas/de10_standard/ROTEIRO.md).

## Como rodar

```bash
python 06_fpga/computador/executar_cenario_b.py
python -m unittest discover -s 06_fpga/computador/testes -p "teste_*.py"
python 06_fpga/sim/rodar_simulacao.py      # simula e, com tudo igual, roda a prova
python 06_fpga/sim/sintetizar_yosys.py
```

A simulação precisa do Icarus Verilog; a síntese, do Yosys ou do pacote
`yowasp-yosys`. A porta serial precisa de `pip install pyserial`.

Com a placa simulada, em dois terminais:

```bash
python 06_fpga/computador/placa_simulada.py --motor verilog
python 06_fpga/computador/executar_cenario_b.py --serial socket://127.0.0.1:5555
```

A placa simulada aceita `--ruido 1e-4`, `--perder-resultado 0.1`,
`--semente 7` e `--baud 0` (sem o tempo de fio). Com a FPGA gravada, pelo
cabo de gravação ou pela porta serial:

```bash
python 06_fpga/computador/executar_cenario_b.py --jtag
python 06_fpga/computador/executar_cenario_b.py --serial COM5
```

## O que falta

- Para outra placa: o arquivo de pinos dela (QSF no Quartus, XDC no Vivado).
  Numa placa Xilinx, o topo pelo cabo de gravação usaria o `BSCANE2` no
  lugar do `sld_virtual_jtag`, com as instruções USER no papel do `ir_in` da
  ponte; o computador precisaria de outro script no lugar do `quartus_stp`.

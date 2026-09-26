# LEAKMAP Edge

**Detecção e localização de vazamentos de granéis líquidos no cais, pela diferença de tempo de chegada da onda de pressão, com a marcação de tempo feita em FPGA.**

Equipe **TACHYON** · São Luís, MA
Hackathon do Complexo Portuário do Itaqui · Edital nº 01/2026 (EMAP, ICT Guará, FAPEMA) · Desafio 2

---

## Por que este projeto existe

Nos berços 104 e 108 do Complexo Portuário do Itaqui, granéis líquidos, entre eles produtos químicos e inflamáveis, passam por tubulações e juntas sujeitas a rompimento. Hoje não existe sistema que detecte esse rompimento na hora: a identificação depende da observação visual do operador. Esse processo é lento, sujeito a falha humana e arriscado, e deixa o vazamento se alastrar antes de ser percebido.

O cais é compartilhado por várias empresas. Um único rompimento não afeta só uma operação: afeta a segurança das pessoas, o meio ambiente e a continuidade de todo o ecossistema portuário.

O volume de um derramamento não depende só do tempo até alguém notar o vazamento. Depende do tempo até contê-lo, e conter exige saber **onde** a linha rompeu, para isolar o trecho certo e fechar a válvula certa. Essa informação não existe hoje na operação. O LEAKMAP Edge entrega a posição junto com o alarme.

## Como funciona

Quando uma linha pressurizada rompe, a pressão cai de repente no ponto da falha. Essa queda viaja pelo líquido nos dois sentidos, a cerca de 1 200 m/s, como um som dentro do tubo. Com um transmissor de pressão em cada extremidade do trecho, a onda chega primeiro ao sensor mais próximo do rompimento. A diferença entre os dois instantes de chegada diz onde a falha está. É o mesmo raciocínio de estimar a distância de um raio contando os segundos entre o clarão e o trovão.

Sendo `L` a distância entre os sensores, `c` a velocidade da onda e `Δt = tA − tB`, a posição medida a partir do sensor A é:

```
x = (L + c · Δt) / 2
```

A técnica, chamada de onda de pressão negativa, é consolidada na indústria de dutos para vazamentos em longas distâncias. O LEAKMAP Edge traz essa técnica para a escala do cais, usando o sinal de pressão que já existe, sem instrumentação dentro do tubo.

## Por que FPGA

Com a onda a 1 200 m/s, cada milissegundo de erro na comparação dos tempos vira 0,6 m de erro de posição. O que decide a precisão não é a velocidade do processador: é os dois canais serem lidos **pelo mesmo relógio** e carimbados por um contador de hardware, sem sistema operacional no caminho.

Uma **FPGA** (*Field-Programmable Gate Array*, matriz de portas lógicas programável em campo) é um chip cujos circuitos são configurados para uma tarefa específica. Um processador comum executa instruções uma depois da outra e divide o tempo com rede e sistema operacional. A FPGA vira o próprio circuito da tarefa: cada etapa roda em hardware próprio, em paralelo, com latência fixa e conhecida. É por isso que ela garante a base de tempo comum aos dois sensores, e é esse o diferencial técnico do projeto.

## O que já está pronto

A cadeia completa roda em software, em simulação, e é a referência contra a qual a placa será comparada, amostra a amostra.

| Etapa | O que faz | Onde está |
|---|---|---|
| A-01 a A-08 | Modelo hidráulico do trecho de 200 m e simulação transiente pelo método das características (TSNet) | [`02_bancada`](02_bancada) |
| A-09 | Modelo dos transmissores: banda, atraso de canal, jitter, ruído, offset, saturação e conversor A/D | [`04_detector/modelo_sensor.py`](04_detector/modelo_sensor.py) |
| A-10 | Frequência de amostragem escolhida por critério de resolução e pacote do ensaio | [`04_detector/amostragem.py`](04_detector/amostragem.py) |
| A-11 a A-15 | Detector: passa-altas, razão de energia curta/longa, marcação da chegada, decisão de evidência e registro do resultado | [`04_detector/detector.py`](04_detector/detector.py) |
| A-14 | Cálculo da posição e propagação de erro | [`04_detector/posicao.py`](04_detector/posicao.py) |
| A-17 | Avaliador independente, em processo separado, que nunca importa código do detector | [`05_avaliacao/avaliador.py`](05_avaliacao/avaliador.py) |
| Porte para hardware | Detector reescrito em aritmética inteira, pronto para virar circuito | [`04_detector/detector_ponto_fixo.py`](04_detector/detector_ponto_fixo.py) |
| Simulador no painel | O detector adaptado para o navegador, conferido contra o Python | [`web`](web) |
| Cenário B, lado do computador | Selo, conversão em inteiros, protocolo com a placa, modelo de referência da FPGA, comparação e relatório | [`06_fpga/computador`](06_fpga/computador) |
| Cenário B, pelo cabo de gravação | O computador conversa com a FPGA pelo mesmo cabo USB que a grava, pelo JTAG virtual, sem adaptador nem fio nos pinos. Rodou na DE10-Standard: 45 de 45 ensaios, mesma chegada que o software nos 90 canais. Projeto do Quartus e [roteiro do laboratório](06_fpga/placas/de10_standard/ROTEIRO.md) | [`06_fpga/placas`](06_fpga/placas) |
| Cenário B, tempo na placa | A própria placa conta os ciclos de cada execução e processa em tempo real, uma amostra por período de amostragem. Na DE10-Standard: declaração do evento de 1,78 a 2,04 µs depois da amostra do cruzamento, mesmo número de ciclos em todas as repetições e nenhuma amostra atrasada; o mesmo detector num notebook leva 14,5 µs de mediana e 45,6 µs no pior caso | [`06_fpga/computador/comparar_latencia.py`](06_fpga/computador/comparar_latencia.py) |
| Autoteste dos canais na placa | A placa acompanha cada canal amostra a amostra e acusa canal congelado, saturado, fora da faixa do transmissor ou com salto impossível, com os limites do transmissor declarado. Em simulação do Verilog: os 90 canais da matriz saudáveis e cada canal estragado de propósito acusado com a falha certa; na placa, ainda não testado | [`06_fpga/rtl/leakmap_saude.v`](06_fpga/rtl/leakmap_saude.v) |
| Demonstração autônoma na placa | A DE10-Standard sozinha, sem computador: escolhe-se nos botões onde a linha rompe, a placa gera os sinais dos dois sensores, detecta, marca as chegadas e mostra nos displays a posição calculada. Nas chaves, um sensor estragado de propósito aparece como falha acusada, não como posição errada. Gravada e rodando na DE10-Standard: ao ligar, 80 m escolhido e 80 m calculado | [`06_fpga/placas/de10_standard/demo`](06_fpga/placas/de10_standard/demo) |
| Cenário B, placa simulada | Programa que fala o protocolo serial da FPGA, com o próprio Verilog da placa atrás da porta. Testa o computador de ponta a ponta, inclusive com ruído no enlace; no dia, só muda o endereço da porta | [`06_fpga/computador/placa_simulada.py`](06_fpga/computador/placa_simulada.py) |
| Cenário B, Verilog da placa | Detector e protocolo em Verilog puro, sintetizável para Spartan-7 e Cyclone V. Em simulação, marca o mesmo índice de chegada da referência em ponto fixo nos 90 canais da matriz e devolve exato um atraso imposto de 40 amostras | [`06_fpga/rtl`](06_fpga/rtl) |

### Resultados em simulação

Matriz de 45 ensaios: cinco posições de rompimento, três níveis de qualidade de transmissor, duas velocidades de onda declaradas e quinze corridas sem evento.

| Indicador | Resultado |
|---|---|
| Eventos localizados | 30 de 30 |
| Erro de localização mediano | 0,24 m em 200 m de linha |
| Erro de localização máximo | 1,05 m |
| Falsos alarmes | 0 em 13 860 oportunidades de decisão |
| Tempo do rompimento à declaração do evento | 31 ms em média |
| Porte em aritmética inteira contra o software | mesma marca de chegada em 90 de 90 canais |
| Cenário B, Verilog da placa simulado ciclo a ciclo, contra o software | mesma marca de chegada em 90 de 90 canais e mesma posição em 45 de 45 ensaios |

Os números estão em [`05_avaliacao/leakmap_avaliacao_matriz_v1.json`](05_avaliacao/leakmap_avaliacao_matriz_v1.json) e a leitura detalhada, linha por linha da matriz, em [`05_avaliacao/LEIAME.md`](05_avaliacao/LEIAME.md).

## Estrutura do repositório

| Pasta | Conteúdo |
|---|---|
| [`01_documentacao`](01_documentacao) | Fluxogramas com a especificação das etapas A-01 a A-17 |
| [`02_bancada`](02_bancada) | Modelo hidráulico, código de simulação e ambiente |
| [`03_ensaios`](03_ensaios) | Dados de cada rodada, separados por quem pode lê-los |
| [`04_detector`](04_detector) | Modelo de sensor, amostragem, detector, posição e porte em ponto fixo |
| [`05_avaliacao`](05_avaliacao) | Avaliador independente e métricas |
| [`06_fpga`](06_fpga) | Cenário B: especificação, Verilog da placa, simulação e o lado do computador |
| [`web`](web) | Simulador interativo do painel: adaptação do detector para o navegador e teste de paridade com o Python |
| [`leakmap_painel.html`](leakmap_painel.html) | Painel de apresentação do projeto |

Uma regra organiza os dados: o detector só lê `parametros`, `amostras` e `pacotes`. A posição real do vazamento fica em `03_ensaios/verdade_do_cenario` e só o avaliador a abre. Assim nenhum limiar é ajustado olhando a resposta.

## Como rodar

A trilha de detecção e avaliação precisa apenas de Python 3 e NumPy:

```bash
pip install numpy pyserial
python rodar_software.py
```

O comando gera os ensaios com o modelo de sensor, roda o detector, compara o porte em ponto fixo, executa o avaliador em processo separado, roda o cenário B contra o modelo de referência da placa e termina com os 120 testes automatizados em Python, inclusive os de ponta a ponta pela serial contra a placa simulada. Com o Icarus Verilog instalado, simula também o Verilog da placa e confere os critérios do cenário B. Com o Node instalado, roda também o teste de paridade do simulador do painel contra o Python; o GitHub Actions executa a trilha inteira a cada envio.

A simulação hidráulica das etapas A-01 a A-08 usa TSNet e wntr; o ambiente está descrito em [`02_bancada/ambiente`](02_bancada/ambiente). Os sinais que ela produziu já estão versionados em `03_ensaios/amostras`, então a trilha acima roda sem ela.

Para ver o painel, abra `leakmap_painel.html` no navegador. O arquivo `vercel.json` publica esse mesmo painel na Vercel.

### Simulador no painel

No painel, a seção "Experimente" deixa qualquer pessoa escolher onde a linha rompe, trocar o transmissor, errar a velocidade da onda e rodar vários cenários de uma vez. O detector que responde ali é uma adaptação para o navegador do Python de `04_detector`, que continua sendo a implementação de referência. A adaptação é conferida contra um gabarito gravado pelo próprio Python: mesma classe, mesmas marcas de chegada e mesma posição nos 45 ensaios da matriz. Detalhes em [`web/LEIAME.md`](web/LEIAME.md).

### Tela do cenário B no painel

A seção "Cenário B · reprodução de sinais digitais em FPGA física" mostra, ensaio a ensaio, o resultado da placa ao lado do resultado do software: as amostras dos dois canais que a placa recebeu, a marca de chegada da placa e a do software, a diferença de tempo e a posição. Um rótulo fixo diz sempre quem processou o resultado mostrado. Com os resultados gravados pela DE10-Standard, a tela abre no resultado processado na FPGA, com o rótulo "Processado na FPGA · reprodução de sinais digitais", e mostra a latência da placa ao lado da do notebook; a simulação do Verilog ciclo a ciclo continua disponível, com o próprio rótulo.

## Roteiro

**No hackathon**, a equipe aperfeiçoa a cadeia que já funciona:

1. Levar a demonstração autônoma à banca: a DE10-Standard localizando, sozinha, o rompimento escolhido nos botões.
2. Ajustar o modelo de sensores aos parâmetros dos transmissores instalados.
3. Estender o cálculo de posição à topologia real da linha, com três berços e manifold.
4. Empacotar o ambiente da simulação hidráulica para que qualquer máquina refaça os ensaios do zero.

**Na visão do produto**, descrita na proposta:

- classificar manobras normais pela física (polaridade da onda e origem coincidindo com bomba ou válvula cadastrada), para que partida de bomba e fechamento de válvula não gerem alarme;
- confirmar o alarme com sensores de vapor químico e inflamável, uma segunda física independente;
- autoteste contínuo dos canais em campo, para que o monitoramento nunca falhe em silêncio, a partir do autoteste que a placa já faz em cada execução;
- gêmeo hidráulico da linha saudável, para cobrir também o furo lento, que não gera onda;
- piloto em um trecho instrumentado do cais, com calibração da velocidade de onda por transientes provocados em posições conhecidas.

O nó LEAKMAP Edge é uma instância da plataforma reconfigurável **Itaqui Edge** da equipe: aquisição sincronizada, processamento em FPGA e telemetria. A mesma plataforma escala para outros berços e trechos do cais e atende outros desafios do porto trocando os sensores e a configuração da placa.

## Equipe

**TACHYON**, de São Luís, MA, reúne projeto de hardware digital (HDL, FPGA e aquisição de sinais) e engenharia de software (backend, dados e produto) no mesmo time.

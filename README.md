# LEAKMAP Edge

> **Projeto arquivado em 29/09/2026.** O LEAKMAP Edge foi desenvolvido para o Hackathon do Complexo Portuário do Itaqui e está encerrado. O código, as simulações e os resultados ficam aqui como registro do que foi feito. Não há desenvolvimento ativo, e issues e pull requests não serão acompanhados. A seção [Estado final](#estado-final) separa o que rodou na placa física do que ficou só em simulação.

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

A mesma onda também diz **quanto** vaza. O furo tira de uma vez uma vazão ΔQ da linha, e a altura da frente de onda é proporcional a ela (Joukowsky: ΔH = c·ΔQ / 2gA). Com a altura medida nos sensores, a física da linha estima a vazão do vazamento e o tamanho equivalente do furo, além da posição.

## Por que FPGA

Com a onda a 1 200 m/s, cada milissegundo de erro na comparação dos tempos vira 0,6 m de erro de posição. O que decide a precisão não é a velocidade do processador: é os dois canais serem lidos **pelo mesmo relógio** e carimbados por um contador de hardware, sem sistema operacional no caminho.

Uma **FPGA** (*Field-Programmable Gate Array*, matriz de portas lógicas programável em campo) é um chip cujos circuitos são configurados para uma tarefa específica. Um processador comum executa instruções uma depois da outra e divide o tempo com rede e sistema operacional. A FPGA vira o próprio circuito da tarefa: cada etapa roda em hardware próprio, em paralelo, com latência fixa e conhecida. É por isso que ela garante a base de tempo comum aos dois sensores, e é esse o diferencial técnico do projeto.

## Estado final

**Rodou na placa física** (Terasic DE10-Standard, Cyclone V a 50 MHz):

- os 45 ensaios da matriz reproduzidos na placa pelo cabo de gravação (JTAG virtual): 45 de 45 concluídos, com a mesma marca de chegada que o software nos 90 canais;
- a execução em tempo real, com uma amostra por período de amostragem: nenhuma amostra atrasada, e a declaração do evento de 1,78 a 2,04 µs depois da amostra do cruzamento;
- a comparação com um notebook rodando o mesmo detector, detalhada em [Resultados gerais](#resultados-gerais);
- a demonstração autônoma: a placa sozinha gera os sinais, detecta e mostra a posição nos displays.

**Rodou só em simulação:**

- toda a hidráulica, pelo TSNet (método das características);
- os sinais dos transmissores, gerados por um modelo de sensor;
- o autoteste dos canais e a medição do degrau da onda, que estão no Verilog e foram verificados no Icarus Verilog byte a byte contra o modelo de referência, mas não chegaram a ser gravados na placa. Falta recompilar o projeto no Quartus; o passo está no [roteiro de testes](06_fpga/placas/de10_standard/ROTEIRO_DE_TESTES.txt);
- a bancada virtual do backend, que faz o papel da linha e dos sensores.

**Não chegou a existir:**

- dados reais da instalação. Comprimentos, diâmetro, produto e posição de válvulas e bombas são premissas declaradas;
- bancada hidráulica física e piloto em campo;
- ligação com o sistema de controle da planta.

## Resultados gerais

| Onde | Indicador | Resultado |
|---|---|---|
| Matriz de 45 ensaios (linha de 200 m) | Eventos localizados | 30 de 30 |
| | Erro de localização mediano / máximo | 0,24 m / 1,05 m |
| | Falsos alarmes | 0 em 13 860 oportunidades de decisão |
| | Tempo do rompimento à declaração | 31 ms em média |
| Linha do cais (8", diesel, sensores a 700 m) | Transmissor rápido | 14 de 14 localizados, erro mediano de 0,11 a 0,18 m |
| | Transmissor inteligente | o erro cresce com a atualização da saída: 0,2 m com 1 ms, 1 a 1,6 m com 10 ms, 6 a 14 m com 50 ms |
| | Manobras que viraram alarme (4 manobras, 6 transmissores) | 1 de 24 com classificação e cadastro, contra 14 de 24 sem |
| Rede do cais (tronco e três ramais, quatro sensores) | Transmissor rápido | 14 de 14 localizados, todos no ramal certo, erro mediano de 0,10 a 0,15 m; nenhum falso alarme |
| Física da linha | Coeficiente de emissor do furo | erro mediano de +0,2 % (de -1,0 a +1,3 %) com transmissor de até 10 ms |
| | Diâmetro equivalente do furo | 23,8 mm, para 23,8 mm reais |
| | Incerteza de posição que cobre o erro (2σ), transmissor de 10 / 50 / 100 ms | 100 / 100 / 60 %, contra 40 / 0 / 0 % antes |
| | Velocidade da onda calibrada pelos eventos | 1 226,2 m/s, para 1 226,6 reais |
| | Menor vazamento detectável no cais | cerca de 3,2 L/min |
| Previsão do golpe de aríete | Erro no tamanho do golpe, 48 casos | de -16 % a +11 % (a fórmula aproximada sozinha: de -41 % a +49 %) |
| FPGA, na DE10-Standard | Ensaios concluídos, iguais ao software | 45 de 45, mesma chegada em 90 de 90 canais |
| | Declaração do evento depois da amostra do cruzamento | 1,94 µs de mediana, 2,04 µs no pior caso, o mesmo número de ciclos em todas as repetições |
| | O mesmo detector num notebook | 14,5 e 19,2 µs de mediana em duas medições; uma amostra chegou a atrasar quase 3 ms |
| FPGA, Verilog simulado ciclo a ciclo | Casos idênticos ao modelo de referência, byte a byte | 72 de 72 |
| Software | Testes automatizados da trilha | 218, todos passando, mais a paridade do painel com o Python |

Os números detalhados estão em [`05_avaliacao/LEIAME.md`](05_avaliacao/LEIAME.md) e [`06_fpga/LEIAME.md`](06_fpga/LEIAME.md), com os arquivos de resultado em JSON ao lado.

## Últimas atualizações

**29/09/2026. Física da linha e degrau da onda na FPGA.**

- [`04_detector/fisica.py`](04_detector/fisica.py) acrescenta princípios de mecânica dos fluidos ao detector:
  - Darcy-Weisbach com o atrito de Swamee-Jain, para a vazão de regime;
  - a atenuação da onda por atrito, teórica e medida pela razão das amplitudes;
  - Joukowsky e a lei do orifício, para a vazão e o tamanho do furo;
  - a propagação de incerteza com o período de atualização do transmissor;
  - a calibração da velocidade da onda pelos próprios eventos, com descarte robusto;
  - a correção pela advecção do escoamento;
  - o menor vazamento detectável.
- A decisão e a posição publicadas não mudaram: continuam iguais no Python, no painel e na FPGA. A física roda ao lado e grava o próprio bloco em cada registro. A avaliação contra a verdade está em [`05_avaliacao/avaliar_fisica.py`](05_avaliacao/avaliar_fisica.py).
- A FPGA ganhou a mensagem DEGRAU: numa passada pela memória, a placa soma as amostras antes e depois da chegada de cada canal, e o computador tira dali a altura da frente de onda, a entrada da Joukowsky. Nos 60 canais da matriz com evento, as somas do Verilog são iguais às feitas direto nas amostras.

**27/09/2026. Golpe de aríete e backend.**

- Previsão do golpe antes de fechar uma válvula: o pico, o nível e o tempo mínimo de manobra seguro.
- Alerta de sobrepressão com os mesmos sensores.
- Backend da bancada virtual com webhook, histórico em PostgreSQL e manobras nas três linhas.

**25 e 26/09/2026. A placa e a operação.**

- Os 45 ensaios rodando na DE10-Standard.
- O tempo contado pela própria placa e a comparação com o notebook.
- A demonstração autônoma e o autoteste dos canais.
- A escala de alerta com webhook.
- O cadastro de equipamentos.
- A rede do cais com manifold.
- O refino da posição por correlação cruzada.

## O que o projeto entregou

| Etapa | O que faz | Onde está |
|---|---|---|
| A-01 a A-08 | Modelo hidráulico do trecho de 200 m e simulação transiente pelo método das características (TSNet) | [`02_bancada`](02_bancada) |
| A-09 | Modelo dos transmissores: banda, atraso de canal, jitter, ruído, offset, saturação e conversor A/D | [`04_detector/modelo_sensor.py`](04_detector/modelo_sensor.py) |
| A-10 | Frequência de amostragem escolhida por critério de resolução e pacote do ensaio | [`04_detector/amostragem.py`](04_detector/amostragem.py) |
| A-11 a A-15 | Detector: passa-altas, razão de energia curta/longa, marcação da chegada, decisão de evidência e registro do resultado | [`04_detector/detector.py`](04_detector/detector.py) |
| A-14 | Cálculo da posição e propagação de erro | [`04_detector/posicao.py`](04_detector/posicao.py) |
| A-17 | Avaliador independente, em processo separado, que nunca importa código do detector | [`05_avaliacao/avaliador.py`](05_avaliacao/avaliador.py) |
| Física da linha | Vazão de regime (Darcy-Weisbach), vazão e furo do vazamento (Joukowsky e orifício), atenuação por atrito, incerteza de posição com o período do transmissor, velocidade da onda calibrada pelos eventos, advecção e menor vazamento detectável | [`04_detector/fisica.py`](04_detector/fisica.py) |
| Refino da posição | Diferença de tempo em fração de amostra por correlação cruzada, ao lado da posição publicada | [`04_detector/refino.py`](04_detector/refino.py) |
| Porte para hardware | Detector reescrito em aritmética inteira, pronto para virar circuito | [`04_detector/detector_ponto_fixo.py`](04_detector/detector_ponto_fixo.py) |
| Linha de produto do cais | Simulação no TSNet de uma linha de 8" com diesel e sensores a 700 m um do outro, com o mesmo detector e seis tipos de transmissor. Premissas declaradas no lugar do dado da instalação real | [`02_bancada/codigo/linha_cais.py`](02_bancada/codigo/linha_cais.py) |
| Manobra × vazamento | Classificação pela física: vazamento é queda de pressão nos dois sensores, dentro do trecho; onda de alta é manobra; diferença de tempo no limite físico é origem fora do trecho, com o lado. As manobras que derrubam a pressão (abrir a válvula de um ramal, parar a bomba) têm a mesma onda de um vazamento: para elas, o cadastro de válvulas e bombas com o registro de operação do sistema de controle | [`04_detector/detector.py`](04_detector/detector.py), [`07_servico/cadastro.py`](07_servico/cadastro.py) |
| Rede do cais com manifold | Tronco e três ramais até os berços 104, 106 e 108, com quatro sensores. A posição sai do ponto da rede cujos tempos de chegada pela tubulação batem com os medidos, e o detector diz em que ramal está o vazamento | [`04_detector/rede.py`](04_detector/rede.py) |
| Escala de alerta e integração | Suspeita, provável e confirmado, com o estado do monitoramento; cada evento sai num JSON padronizado, por webhook configurável, para qualquer automação da empresa | [`07_servico`](07_servico) |
| Alerta de sobrepressão | Os mesmos sensores acompanham o pico de pressão contra o limite da linha e avisam em atenção (80 %) e alarme (95 %) quando uma manobra rápida chega perto do que o componente mais fraco aguenta | [`07_servico/sobrepressao.py`](07_servico/sobrepressao.py) |
| Previsão do golpe antes da manobra | Antes de fechar uma válvula, o pico previsto, o nível e o tempo mínimo de manobra para ficar seguro, pela física do golpe de aríete e pelo estudo de transitórios de cada válvula no TSNet | [`07_servico/previsao_de_golpe.py`](07_servico/previsao_de_golpe.py) |
| Bancada virtual | O backend faz o papel da linha e dos sensores: vazamento em qualquer ponto, manobras nas três linhas, sensor com defeito e gás, com o detector rodando ao vivo e o evento entregue por WebSocket e webhook e guardado em PostgreSQL. Conferido contra o TSNet: a chegada da onda erra no máximo 0,4 ms e o detector dá a mesma classe nos 36 pontos simulados | [`08_backend`](08_backend) |
| Simulador no painel | O detector adaptado para o navegador, conferido contra o Python | [`web`](web) |
| Cenário B, lado do computador | Selo, conversão em inteiros, protocolo com a placa, modelo de referência da FPGA, comparação e relatório | [`06_fpga/computador`](06_fpga/computador) |
| Cenário B, Verilog da placa | Detector, autoteste, degrau da onda e protocolo em Verilog puro, sintetizável para Spartan-7 e Cyclone V, verificado byte a byte contra o modelo de referência | [`06_fpga/rtl`](06_fpga/rtl) |
| Cenário B, pelo cabo de gravação | O computador conversa com a FPGA pelo mesmo cabo USB que a grava, pelo JTAG virtual, sem adaptador nem fio nos pinos. Projeto do Quartus e [roteiro do laboratório](06_fpga/placas/de10_standard/ROTEIRO.md) | [`06_fpga/placas`](06_fpga/placas) |
| Cenário B, tempo na placa | A própria placa conta os ciclos de cada execução e processa em tempo real, uma amostra por período de amostragem; comparação com o mesmo detector num notebook | [`06_fpga/computador/comparar_latencia.py`](06_fpga/computador/comparar_latencia.py) |
| Autoteste dos canais na placa | A placa acompanha cada canal amostra a amostra e acusa canal congelado, saturado, fora da faixa do transmissor ou com salto impossível, com os limites do transmissor declarado | [`06_fpga/rtl/leakmap_saude.v`](06_fpga/rtl/leakmap_saude.v) |
| Degrau da onda na placa | A placa soma, na própria memória, as janelas antes e depois da chegada de cada canal; o computador tira dali a altura da frente de onda para a vazão do furo | [`06_fpga/rtl/leakmap_nucleo.v`](06_fpga/rtl/leakmap_nucleo.v) |
| Demonstração autônoma na placa | A DE10-Standard sozinha, sem computador: escolhe-se nos botões onde a linha rompe, a placa gera os sinais dos dois sensores, detecta, marca as chegadas e mostra nos displays a posição calculada. Nas chaves, um sensor estragado de propósito aparece como falha acusada, não como posição errada | [`06_fpga/placas/de10_standard/demo`](06_fpga/placas/de10_standard/demo) |
| Cenário B, placa simulada | Programa que fala o protocolo serial da FPGA, com o próprio Verilog da placa atrás da porta, para testar o computador de ponta a ponta, inclusive com ruído no enlace | [`06_fpga/computador/placa_simulada.py`](06_fpga/computador/placa_simulada.py) |

## Estrutura do repositório

| Pasta | Conteúdo |
|---|---|
| [`01_documentacao`](01_documentacao) | Fluxogramas com a especificação das etapas A-01 a A-17 e o guia do backend para o front-end |
| [`02_bancada`](02_bancada) | Modelo hidráulico, código de simulação e ambiente do TSNet |
| [`03_ensaios`](03_ensaios) | Dados de cada rodada, separados por quem pode lê-los |
| [`04_detector`](04_detector) | Modelo de sensor, amostragem, detector, posição, física da linha e porte em ponto fixo |
| [`05_avaliacao`](05_avaliacao) | Avaliador independente e métricas |
| [`06_fpga`](06_fpga) | Cenário B: especificação, Verilog da placa, simulação, projetos do Quartus e o lado do computador |
| [`07_servico`](07_servico) | Escala de alerta, evento padronizado, cadastro de equipamentos, sobrepressão, previsão do golpe e saída por webhook |
| [`08_backend`](08_backend) | Backend da bancada virtual: a linha, os sensores e o detector ao vivo, com REST e WebSocket |
| [`web`](web) | Simulador interativo do painel: adaptação do detector para o navegador e teste de paridade com o Python |
| [`leakmap_painel.html`](leakmap_painel.html) | Painel de apresentação do projeto |

Uma regra organiza os dados: o detector só lê `parametros`, `amostras` e `pacotes`. A posição real do vazamento fica em `03_ensaios/verdade_do_cenario` e só o avaliador a abre. Assim nenhum limiar é ajustado olhando a resposta.

## Como rodar

A trilha de detecção e avaliação precisa apenas de Python 3 e NumPy:

```bash
pip install numpy pyserial
python rodar_software.py
```

O comando faz, nesta ordem:

1. gera os ensaios com o modelo de sensor e roda o detector;
2. compara o porte em ponto fixo;
3. executa o avaliador em processo separado;
4. roda o cenário B contra o modelo de referência da placa;
5. roda o detector e a avaliação da linha e da rede do cais, e a avaliação da física da linha;
6. termina com os 218 testes automatizados em Python.

Ferramentas opcionais acrescentam etapas:

- com o Icarus Verilog instalado, simula também o Verilog da placa e confere os critérios do cenário B;
- com o Node instalado, roda o teste de paridade do simulador do painel contra o Python.

O GitHub Actions executa a trilha inteira a cada envio.

A simulação hidráulica das etapas A-01 a A-08 usa TSNet e wntr, que pedem Python 3.11 ou 3.12. Os sinais que ela produziu já estão versionados em `03_ensaios/amostras`, então a trilha acima roda sem ela. Para refazer as simulações do zero, um comando cria o ambiente com as versões congeladas e confere que ele reproduz os sinais gravados:

```bash
bash 02_bancada/ambiente/preparar_ambiente.sh
```

No Windows, `powershell -ExecutionPolicy Bypass -File 02_bancada\ambiente\preparar_ambiente.ps1`. Detalhes em [`02_bancada/ambiente`](02_bancada/ambiente).

Para ver o painel, abra `leakmap_painel.html` no navegador. O arquivo `vercel.json` publica esse mesmo painel na Vercel. Com o projeto arquivado, os serviços publicados (painel e backend) podem ser desligados a qualquer momento; o painel local e a trilha acima continuam funcionando.

### Simulador no painel

No painel, a seção "Experimente" deixa qualquer pessoa escolher onde a linha rompe, trocar o transmissor, errar a velocidade da onda e rodar vários cenários de uma vez. O detector que responde ali é uma adaptação para o navegador do Python de `04_detector`, que continua sendo a implementação de referência. A adaptação é conferida contra um gabarito gravado pelo próprio Python: mesma classe, mesmas marcas de chegada e mesma posição nos 45 ensaios da matriz. Detalhes em [`web/LEIAME.md`](web/LEIAME.md).

### Tela do cenário B no painel

A seção "Cenário B · reprodução de sinais digitais em FPGA física" mostra, ensaio a ensaio, o resultado da placa ao lado do resultado do software: as amostras dos dois canais que a placa recebeu, a marca de chegada da placa e a do software, a diferença de tempo e a posição. Um rótulo fixo diz sempre quem processou o resultado mostrado. Com os resultados gravados pela DE10-Standard, a tela abre no resultado processado na FPGA, com o rótulo "Processado na FPGA · reprodução de sinais digitais", e mostra a latência da placa ao lado da do notebook; a simulação do Verilog ciclo a ciclo continua disponível, com o próprio rótulo.

## O que ficaria para a continuação

Se o projeto for retomado, estes são os próximos passos, na ordem em que mais mudam o resultado:

1. **Dados da planta.** Trocar as premissas pelos comprimentos, pela espessura do isométrico e pela posição de cada válvula e bomba, na linha e na rede com manifold que já estão simuladas.
2. **Transmissor instalado.** Ajustar o modelo de sensores à folha de dados do transmissor. O tempo de atualização da saída decide se o sistema localiza por metro ou por berço, e a incerteza de posição já leva isso em conta.
3. **Recompilar a placa.** Gravar na DE10-Standard o Verilog com o autoteste e o degrau da onda, e rodar o passo B.6 do [roteiro de testes](06_fpga/placas/de10_standard/ROTEIRO_DE_TESTES.txt).
4. **Amostrar mais rápido.** A 10 mil amostras por segundo, uma amostra vale 6 cm. O refino por correlação cruzada ajuda pouco a 2,5 mil por segundo, porque a frente dura poucas amostras.
5. **Integração com o controle da planta.** Ler o registro de operação das válvulas e bombas, que separa manobra de vazamento, e devolver o alarme por contato seco ou Modbus.
6. **Piloto em campo.** Instrumentar um trecho do cais e calibrar a velocidade da onda por transientes provocados em posições conhecidas; a calibração pelos próprios eventos já está implementada.

Na visão do produto ficaram também:

- a confirmação do alarme por sensores de vapor químico e inflamável, uma segunda física independente;
- um gêmeo hidráulico da linha saudável, para cobrir o furo lento, que não gera onda;
- a plataforma reconfigurável **Itaqui Edge** da equipe, da qual o LEAKMAP Edge é uma instância: aquisição sincronizada, processamento em FPGA e telemetria, para outros berços e outros desafios do porto.

## Equipe

**TACHYON**, de São Luís, MA, reúne projeto de hardware digital (HDL, FPGA e aquisição de sinais) e engenharia de software (backend, dados e produto) no mesmo time.

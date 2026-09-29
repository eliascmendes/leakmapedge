# Avaliacao

Etapa A-17. O avaliador mede o desempenho do produto sem que o produto tenha
tido acesso a resposta.

## Independencia

`avaliador.py` e um processo separado. Le dois arquivos ja gravados e nada
mais:

- `04_detector/resultados/leakmap_resultado_matriz_v1.json`, a saida de A-15;
- `03_ensaios/verdade_do_cenario/leakmap_verdade_matriz_v1.json`.

Cruza os dois pelo identificador do ensaio. Nao importa nem chama nenhum
modulo de `04_detector`. A funcao `conferir_independencia` verifica isso em
tempo de execucao e derruba a execucao se algum modulo do detector estiver
carregado, e `testes/teste_avaliador.py` roda o avaliador em outro processo,
sem `04_detector` no caminho de busca, e confere que a tabela sai igual.

## Arquivos

| Arquivo | Conteudo |
|---|---|
| `avaliador.py` | A-17, o avaliador independente |
| `gerar_verdade_matriz.py` | Monta a verdade do cenario da matriz a partir do plano e da verdade v1 |
| `leakmap_avaliacao_matriz_v1.json` | Resultado da matriz de ensaios |
| `leakmap_avaliacao_v1.json` | Rodada v1 de referencia, mantida para conferencia de regressao |
| `avaliar_linha_cais.py`, `leakmap_avaliacao_linha_cais_v1.json` | Linha do cais: seis transmissores, manobras, com e sem classificacao e cadastro |
| `avaliar_rede_cais.py`, `leakmap_avaliacao_rede_cais_v1.json` | Rede do cais com manifold e tres ramais, erro medido pela tubulacao |
| `avaliar_fisica.py`, `leakmap_avaliacao_fisica_v1.json` | Fisica da linha (`04_detector/fisica.py`) contra a verdade: vazao e furo, cobertura da incerteza, velocidade calibrada, menor vazamento detectavel, adveccao |
| `testes/teste_avaliador.py` | Testes de A-17 e os criterios de A-12 e A-14 que precisam da posicao real |

Os testes que precisam da posicao real do vazamento ficam aqui, e nao em
`04_detector/testes`, justamente porque abrem a verdade do cenario.

## Rodada da matriz de ensaios

45 ensaios: cinco posicoes (60, 80, 100, 120 e 140 m) x tres niveis de ruido
x duas velocidades de onda declaradas, mais quinze ensaios sem evento.

| Linha | n | Erro medio | Erro maximo |
|---|---|---|---|
| `evento/sem_ruido/casada` | 5 | 0,000 m | 0,000 m |
| `evento/baixo/casada` | 5 | 0,000 m | 0,000 m |
| `evento/alto/casada` | 5 | 0,241 m | 0,241 m |
| `evento/sem_ruido/desviada` | 5 | 0,480 m | 0,800 m |
| `evento/baixo/desviada` | 5 | 0,480 m | 0,800 m |
| `evento/alto/desviada` | 5 | 0,529 m | 1,046 m |

Geral: 30 eventos, 30 localizados, nenhuma nao deteccao, nenhum inconclusivo,
nenhuma falha de execucao. Erro medio 0,288 m, mediano 0,241 m, maximo
1,046 m. Tempo de deteccao medio 31,4 ms, maximo 52,7 ms, contado do instante
de abertura do vazamento. Em 28 dos 30 casos o erro ficou dentro da incerteza
que o proprio detector declarou.

Falso alarme: zero em 15 ensaios sem evento e em 13 860 oportunidades de
decisao. Com zero ocorrencias, o limite superior de 95% de confianca pela
regra de tres e 2,2e-4 por oportunidade.

## Como ler os numeros

A linha `sem_ruido/casada` reproduz o baseline v1, com erro exatamente zero
nos cinco eventos. Isso continua sendo consequencia do alinhamento da malha do
MOC, em que cada sub-trecho de 20 m recebeu 166 segmentos e o tempo de
transito entre nos vizinhos e um numero inteiro de passos de tempo. Serve de
conferencia de regressao, nao de medida de desempenho.

As demais linhas e que medem alguma coisa:

- `alto/casada` da 0,241 m em todos os cinco eventos, que e exatamente uma
  amostra. A configuracao `alto` tem 0,4 ms de diferenca de atraso entre os
  canais, quase um periodo de amostragem, e esse desvio entra direto em
  `delta_t`. E um erro sistematico de instrumentacao, corrigivel por
  calibracao dos dois canais.
- As linhas `desviada` declaram ao detector um `c` 2% acima do real. O erro
  cresce com `|delta_t|` e some no meio do trecho, que e o que a propagacao
  `dx = delta_t * dc / 2` preve: em 100 m, equidistante dos sensores, o erro e
  zero mesmo com `c` errado.

O eixo de velocidade varia o `c` declarado ao detector, nao o `c` com que o
solucionador gerou os sinais. Refazer a simulacao com outro `c` exige TSNet,
que depende do wntr e nao compila no ambiente atual. O que o eixo mede e `c`
assumido diferente de `c` real, que e o modo de erro que existe em campo. O
que ele nao cobre e a mudanca de forma de onda que outro `c` produziria.

## Linha de produto do cais (simulacao com premissas)

`avaliar_linha_cais.py` avalia, do mesmo jeito independente, uma linha de
produto do cais simulada no TSNet (`02_bancada/codigo/linha_cais.py` e
`manobras_cais.py`): 8" em aco carbono com diesel, onda a ~1.227 m/s, sensores
a 700 m um do outro, vazamentos grandes (~23% da vazao) e pequenos (~5%) em
sete posicoes, um vazamento fora do trecho e quatro manobras. Comprimentos,
espessura e vazao sao premissas, gravadas junto com os sinais, ate chegar o
dado da instalacao real.

O mesmo detector, com seis configuracoes de transmissor (0 a 15 bar, 16 bits):

| Transmissor | Vazamento grande: localizados, erro mediano / maximo | Pequeno | Falsos alarmes (5 sem evento) |
|---|---|---|---|
| ideal (hidraulica pura) | 7/7, 0,11 / 0,25 m | 7/7, 0,11 / 0,25 m | 0 |
| rapido dedicado | 7/7, 0,18 / 0,25 m | 7/7, 0,11 / 0,25 m | 0 |
| inteligente, saida a cada 1 ms | 7/7, 0,18 / 0,56 m | 7/7, 0,25 / 0,39 m | 0 |
| inteligente, 10 ms | 7/7, 1,58 / 3,02 m | 7/7, 0,88 / 2,74 m | 0 |
| inteligente, 50 ms | 7/7, 13,73 / 21,18 m | 5/7, 5,73 / 23,71 m | 0 |
| inteligente, 100 ms | 5/7, 51,32 / 300,81 m | 4/7, 18,65 / 271,62 m | 0 |

Todos os 84 vazamentos dentro do trecho foram detectados; os 7 que nao foram
localizados (transmissor de 50 e 100 ms) sairam com a posicao retida, como
suspeita, porque a saida em degraus deixou a diferenca de tempo fora do que o
trecho permite.

Leitura:

- O que decide a precisao e o tempo de atualizacao da saida do transmissor,
  nao o ruido: cada transmissor atualiza no proprio relogio, e o erro de
  posicao chega a c x T / 2 (0,6 m com 1 ms, 6 m com 10 ms, 31 m com 50 ms).
  Com 100 ms aparecem erros bem maiores que esse limite (ate 301 m): a saida
  em degraus confunde a marcacao da chegada.
- Com transmissor rapido, o erro fica no tamanho de uma amostra (0,25 m), o
  mesmo da matriz.

Atrito: a simulacao usa o atrito de Darcy-Weisbach do aco comercial
(rugosidade 0,046 mm) com a viscosidade do diesel, e parte em equilibrio. A
versao anterior passava 0,02 a `set_roughness`, que o TSNet le como
rugosidade de 20 mm, e o regime nao ficava em equilibrio
(`02_bancada/ambiente/LEIAME.md`, armadilha 7). Com a correcao, a carga ao
longo da linha subiu e os mesmos coeficientes de vazamento passaram de ~18% e
~4% para ~23% e ~5% da vazao. Os erros de posicao praticamente nao mudaram;
um vazamento a mais, com transmissor de 100 ms, saiu sem localizacao.

### Manobras: polaridade, origem e cadastro

As quatro manobras, cada uma com os seis transmissores:

| Manobra | Onda | Onde nasce |
|---|---|---|
| fim de carregamento no navio do 108 | alta | fora do trecho, lado B |
| fechamento no ramal do berco 106 | alta | dentro do trecho, 450 m |
| abertura no ramal do berco 106 | queda | dentro do trecho, 450 m |
| parada da bomba | queda, lenta (a bomba perde rotacao em 2 s) | fora do trecho, lado A |

O nivel da escala de alerta em cada modo (24 ensaios de manobra):

| | Sem classificacao | Com classificacao | Com classificacao e cadastro |
|---|---|---|---|
| Alarme de vazamento, com posicao (provavel) | 14 | 6 | 1 |
| Suspeita, sem posicao | 10 | 6 | 0 |
| Registro, sem alarme | 0 | 12 | 23 |

- A **classificacao por polaridade e origem** resolve as duas manobras de
  alta (12 de 12 viram registro). A abertura no 106 e uma onda de queda que
  nasce em 450 m, a mesma assinatura de um vazamento ali: continua alarmando
  nos 6 transmissores.
- A **parada da bomba** sai como suspeita, sem posicao: a frente e lenta, a
  marca no sensor B sai tarde, e a diferenca de tempo passa de L/c (0,574 s
  contra 0,571 s) alem da tolerancia.
- O **cadastro de equipamentos com o registro de operacao**
  (`07_servico/cadastro.py`) resolve as duas: a origem coincide com a valvula
  XV-106 ou fica do lado da bomba B-01, e o sistema de controle registrou a
  operacao no mesmo instante. Sobra 1 caso, a abertura no 106 com transmissor
  de 100 ms: a posicao saiu longe da valvula, a coincidencia nao fecha e o
  alerta continua. E o lado seguro da regra.

Vazamentos, nos tres modos: os mesmos 84 detectados e 77 localizados, com os
mesmos erros. Nos ensaios de vazamento nao ha operacao registrada, entao o
cadastro nao rebaixou nenhum: os vazamentos em 450 m saem com a anotacao
"coincide com XV-106, sem operacao registrada: conferir" e continuam
provaveis.

Vazamento fora do trecho (-150 m, antes do sensor A):

| | Sem classificacao | Com classificacao |
|---|---|---|
| Apontado como "fora do trecho, lado A" | 0 de 12 | 8 de 12 |
| Localizado dentro do trecho, perto de A | 8 de 12 | 4 de 12 |

Os 4 que ainda saem localizados sao de transmissor inteligente (a 0,4 m do
sensor A com 1 ms; 6 e 10 m com 50 ms; 31 m com 100 ms): o erro de tempo
empurra a posicao para dentro do trecho. Com transmissor rapido, os 4 casos
saem como "fora do trecho, lado A".

## Rede do cais com manifold e tres ramais (simulacao com premissas)

`avaliar_rede_cais.py` avalia a localizacao em rede (`04_detector/rede.py`)
sobre a rede simulada em `02_bancada/codigo/rede_cais.py`: tronco de 300 m do
sensor A ate o manifold e tres ramais de 250, 400 e 550 m ate os sensores dos
bercos 104, 106 e 108, com os tres navios carregando. Quatro sensores. Sete
vazamentos dentro da rede (um no tronco e dois em cada ramal, um deles a 30 m
do manifold) e um antes do sensor A, em dois tamanhos, com os mesmos seis
transmissores. O erro e medido pela tubulacao.

Com mais de dois sensores, a posicao sai do ponto da rede cujos tempos de
chegada pela tubulacao batem com os medidos, e o detector diz tambem em que
trecho o vazamento esta. O periodo de atualizacao de cada transmissor
inteligente entra declarado, como dado de folha de dados.

| Transmissor | Localizados, no trecho certo | Erro mediano, grande · pequeno | Pior caso | Falsos alarmes (5 sem evento) |
|---|---|---|---|---|
| rapido dedicado | 14 de 14, 14 | 0,10 · 0,15 m | 0,25 m | 0 |
| inteligente, 1 ms | 14 de 14, 14 | 0,20 · 0,15 m | 0,40 m | 0 |
| inteligente, 10 ms | 14 de 14, 14 | 2,35 · 2,40 m | 4,80 m | 0 |
| inteligente, 50 ms | 13 de 14, 13 | 8,35 · 8,40 m | 18,75 m | 0 |
| inteligente, 100 ms | 13 de 14, 13 | 11,10 · 22,15 m | 29,40 m | 0 |
| ideal (hidraulica pura) | 14 de 14, 14 | 0,25 · 0,25 m | 1,55 m | 0 |

Leitura:

- Todos os 82 vazamentos localizados cairam no trecho certo. Os 2 que nao
  foram localizados sao o vazamento a 30 m do manifold, com transmissor de 50
  e 100 ms: com esse erro de tempo, o tronco perto do manifold explica as
  chegadas tao bem quanto o ramal, e o detector retem a posicao como ambigua
  em vez de escolher.
- Com transmissor lento, os quatro sensores ajudam: o erro mediano com 50 ms
  fica em 8 m (14 m na linha reta de dois sensores) e o pior caso com 100 ms
  em 29 m (301 m na linha reta). As chegadas a mais amarram a posicao.
- Sem o periodo de atualizacao declarado, a mesma rede localiza 8 de 14 com
  10 ms e nenhum com 50 ou 100 ms: a redundancia denuncia chegadas que nao
  batem, e o detector retem a posicao. Declarar o periodo e o que torna
  possivel usar o transmissor inteligente que ja esta instalado.
- O caso ideal, sem nenhum ruido, erra mais que o transmissor rapido (ate
  1,55 m): as retiradas dos navios nao ficam em equilibrio perfeito no
  TSNet, e um degrau de 0,1 mm antes da frente, invisivel com o ruido de
  qualquer instrumento, puxa a marca de chegada algumas amostras para tras.
  E um artefato da simulacao sem ruido, nao do detector.

Vazamento antes do sensor A (-150 m): sai como "fora da rede, lado A" em 7
de 12; nos outros 5, a posicao sai no tronco, perto de A (1,3 m no caso
ideal, pelo mesmo artefato; 1,5 a 33 m com transmissor inteligente de 10 a
100 ms), como na linha reta.

## Refino da posicao por correlacao cruzada

`04_detector/refino.py` compara a frente de onda dos dois canais em volta das
marcas de chegada, pela correlacao normalizada, e interpola o pico por uma
parabola: a diferenca de tempo sai em fracao de amostra. Fica ao lado da
posicao publicada, sem substitui-la; o avaliador mede os dois. Erro de
localizacao, mediano / maximo, so marcas e com o refino:

| Caso | So marcas | Com o refino |
|---|---|---|
| Linha do cais, ideal | 0,11 / 0,25 m | 0,09 / 0,19 m |
| Linha do cais, transmissor rapido, grande | 0,18 / 0,25 m | 0,12 / 0,26 m |
| Linha do cais, transmissor rapido, pequeno | 0,11 / 0,25 m | 0,11 / 0,26 m |
| Linha do cais, inteligente 1 ms, grande | 0,18 / 0,56 m | 0,08 / 0,35 m |
| Linha do cais, inteligente 1 ms, pequeno | 0,25 / 0,39 m | 0,08 / 0,30 m |
| Linha do cais, inteligente 10 ms ou mais | 0,9 a 51 m | igual ou ate 4% pior |
| Matriz de 200 m, ruido baixo e sem ruido | 0,00 m | 0,00 a 0,06 m |

Leitura: o refino ajuda quando a frente e limpa e a marca erra por fracao de
amostra, como com o transmissor de 1 ms; com transmissor lento o erro vem da
saida em degraus, e a correlacao nao tem o que corrigir. Na matriz as marcas
ja acertam exatamente, pela forma como os eventos foram simulados. A 2,5 mil
amostras por segundo a frente dura poucas amostras: o ganho grande de
resolucao viria de amostrar mais rapido (a 10 mil por segundo, uma amostra
vale 6 cm), nao do refino.

## Fisica da linha: quanto vaza, com que incerteza, e o menor vazamento

`avaliar_fisica.py` mede `04_detector/fisica.py` contra a verdade do
simulador. Os principios e as equacoes estao em `04_detector/LEIAME.md`.

**Quanto vaza.** A verdade grava o coeficiente de emissor do furo, `C` em
`Q = C sqrt(h)`. A fisica o recupera pela Joukowsky e pelo orificio:

| Caso | Erro do coeficiente, mediana (faixa) |
|---|---|
| Linha do cais, ideal, rapido, 1 ms e 10 ms | +0,2 % (-1,0 a +1,3 %) |
| Linha do cais, inteligente 50 ms | +0,7 % |
| Linha do cais, inteligente 100 ms | +1,1 % (-3,3 a +2,0 %) |
| Matriz, velocidade casada | -0,1 a -0,4 % (ate -1,4 %) |
| Matriz, velocidade declarada 2 % acima | cerca de -2 %: o erro de `c` entra direto na Joukowsky |

Furo equivalente do vazamento grande do cais: 23,8 mm, para 23,8 mm reais.
Vazao de regime pela perda de carga (Darcy-Weisbach): 0,0471 a 0,0473 m3/s,
para 0,0471 reais.

**Incerteza que cobre o erro.** Fracao dos eventos com erro de posicao dentro
de 2 sigma, com a incerteza de hoje (so as marcas) e com a completa (mais o
periodo de atualizacao do transmissor e a incerteza de `c`):

| Transmissor | Hoje | Completa |
|---|---|---|
| ideal, rapido, 1 ms | 100 % | 100 % |
| inteligente 10 ms | 40 % | 100 % |
| inteligente 50 ms | 0 % | 100 % |
| inteligente 100 ms | 0 % | 60 % |

**Velocidade de onda calibrada pelos eventos** (real 1226,6 m/s no cais):
1226,2 com o transmissor rapido, 1226,3 com 1 ms, 1224,2 com 10 ms, 1235 +-
16 com 50 ms e 1230 +- 46 com 100 ms. Na matriz, validacao cruzada deixando um
fora: com a velocidade declarada 2 % acima, o erro de posicao cai de 0,48 m
(maximo 0,80) para zero sem ruido e com ruido baixo, e de 0,53 m (maximo 1,05)
para 0,32 m (maximo 0,42) com ruido alto. Com a velocidade ja certa e ruido
alto, calibrar piora de 0,24 m para 0,32 m. Por isso a posicao calibrada fica
ao lado da publicada e nao a substitui.

**Menor vazamento detectavel no cais**, com o ruido do transmissor rapido:
0,104 m de degrau, cerca de 3,2 L/min, pela teoria (limiar 12 na razao de
energia, fator 0,75 da janela curta depois do passa-altas); 0,10 a 0,12 m,
3,2 a 3,8 L/min, na simulacao com a onda de um vazamento real escalada, 6
sementes de ruido.

**Adveccao.** O escoamento de 1,46 m/s arrasta a onda: a posicao pela
formula simples fica 0,42 m para o lado de A, o vies `-L V / 2c`. O TSNet
despreza a adveccao, entao a correcao fica opcional e nao entra na avaliacao
dos numeros publicados.

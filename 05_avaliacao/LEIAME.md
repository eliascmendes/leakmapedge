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
a 700 m um do outro, vazamentos grandes (~18% da vazao) e pequenos (~4%) em
sete posicoes, um vazamento fora do trecho e duas manobras. Comprimentos,
espessura e vazao sao premissas, gravadas junto com os sinais, ate chegar o
dado da instalacao real.

O mesmo detector, com seis configuracoes de transmissor (0 a 15 bar, 16 bits):

| Transmissor | Vazamento grande: detectados, erro mediano / maximo | Pequeno | Falsos alarmes (5 sem evento) |
|---|---|---|---|
| ideal (hidraulica pura) | 7/7, 0,11 / 0,25 m | 7/7, 0,11 / 0,25 m | 0 |
| rapido dedicado | 7/7, 0,11 / 0,25 m | 7/7, 0,14 / 0,32 m | 0 |
| inteligente, saida a cada 1 ms | 7/7, 0,18 / 0,56 m | 7/7, 0,25 / 0,39 m | 0 |
| inteligente, 10 ms | 7/7, 1,58 / 3,02 m | 7/7, 0,88 / 2,74 m | 0 |
| inteligente, 50 ms | 7/7, 13,73 / 21,18 m | 7/7, 5,73 / 23,71 m | 0 |
| inteligente, 100 ms | 7/7, 50,61 / 300,81 m | 7/7, 18,65 / 271,62 m | 0 |

Leitura:

- O que decide a precisao e o tempo de atualizacao da saida do transmissor,
  nao o ruido: cada transmissor atualiza no proprio relogio, e o erro de
  posicao chega a c x T / 2 (0,6 m com 1 ms, 6 m com 10 ms, 31 m com 50 ms).
  Com 100 ms aparecem erros bem maiores que esse limite (ate 301 m): a saida
  em degraus confunde a marcacao da chegada.
- Com transmissor rapido, o erro fica no tamanho de uma amostra (0,25 m), o
  mesmo da matriz.

Classificacao por polaridade e origem, com e sem ela (o detector de antes):

| | Sem classificacao | Com classificacao |
|---|---|---|
| Manobras que viram alarme de vazamento (2 manobras x 6 transmissores) | 9 de 12 (6 com posicao) | 0 de 12 |
| Vazamento fora do trecho apontado como "fora do trecho, lado A" | 0 de 12 | 7 de 12 |
| Vazamentos dentro do trecho detectados e localizados | 84 de 84 | 84 de 84, os mesmos erros |

Os 5 vazamentos fora do trecho que nao saem como "fora" sao todos de
transmissor inteligente: 4 saem localizados perto do sensor A (a 0,4 m com
1 ms; 6 e 10 m com 50 ms; 31 m com 100 ms), porque o erro de tempo empurra a
posicao para dentro do trecho, e 1 sai sem localizacao (100 ms). Com
transmissor rapido, os 4 casos (ideal e rapido, grande e pequeno) saem como
"fora do trecho, lado A".

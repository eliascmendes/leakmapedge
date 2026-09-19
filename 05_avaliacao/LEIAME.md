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

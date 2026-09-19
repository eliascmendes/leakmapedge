# Ensaios

Uma subpasta por tipo de acesso. Esta separacao nao e cosmetica, ela vem da
regra de separacao da arquitetura v1.0.

| Subpasta | Quem pode ler | Conteudo |
|---|---|---|
| `parametros` | Detector e avaliador | Geometria, posicao dos sensores, `c`, passo de tempo |
| `amostras` | Detector e avaliador | Series dos canais A e B, mesma base de tempo |
| `pacotes` | Detector e avaliador | Pacote do ensaio da etapa A-10, ja decimado |
| `matriz` | Detector e avaliador | Plano da matriz de ensaios |
| `verdade_do_cenario` | Somente avaliador | Posicao real do vazamento, tipo de evento |

Os ensaios da rodada de referencia sao identificados por `EV-nn` e os da
matriz por `MX-nnn`. O detector recebe o identificador, os parametros e as
amostras. Nunca a posicao real.

## Arquivos

| Arquivo | Etapa | Conteudo |
|---|---|---|
| `amostras/leakmap_amostras_v1.json` | A-08 | Sinal limpo do solucionador, cinco eventos |
| `amostras/leakmap_amostras_ruido_v1.json` | A-09 | O mesmo sinal com o modelo de sensor aplicado, tres niveis |
| `pacotes/leakmap_pacote_matriz_v1.json` | A-10 | Os 45 ensaios da matriz, decimados, prontos para o detector |
| `matriz/leakmap_matriz_v1.json` | — | Plano da matriz |
| `verdade_do_cenario/leakmap_verdade_v1.json` | — | Verdade da rodada de referencia |
| `verdade_do_cenario/leakmap_verdade_matriz_v1.json` | — | Verdade da matriz |

Arquivo de ensaio nunca e sobrescrito: cada rodada nova recebe sufixo de
versao proprio.

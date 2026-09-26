# Codigo da bancada

Scripts de simulacao. Manter deterministico: toda rodada precisa registrar
semente, versoes e parametros efetivos lidos de volta do solucionador.

Ler de volta sempre, nunca assumir:

    tm.time_step        # passo de tempo efetivo
    pipe.wavev          # velocidade de onda ajustada por trecho

Na rodada v1 o solicitado foi 1e-4 s e 1200 m/s; o efetivo saiu
1.003264e-4 s e 1200.899544 m/s.

## Scripts

| Script | O que simula |
|---|---|
| `build_model.py`, `simular.py`, `rodar_tudo.py` | O trecho reto de 200 m da matriz de ensaios (rodada v1) |
| `velocidade_de_onda.py` | Velocidade da onda por produto e por linha, pela formula de Korteweg, com valores tipicos de produto e de tubo |
| `linha_cais.py` | Uma linha de produto do cais: 8" em aco carbono com diesel, sensores a 700 m um do outro, vazamentos grandes e pequenos em sete posicoes e um fora do trecho. Premissas no lugar do que falta da instalacao real, gravadas junto com os sinais |
| `manobras_cais.py` | Manobras na mesma linha: fim de carregamento no navio (fora do trecho) e fechamento no ramal de um berco intermediario (dentro do trecho) |

Os dois ultimos precisam do ambiente com TSNet (`../ambiente/LEIAME.md`) e
levam cerca de 1 minuto por simulacao:

    python linha_cais.py          # regime e 16 vazamentos, ~17 min
    python manobras_cais.py       # 2 manobras, ~2 min

Os sinais ficam em `03_ensaios/amostras` e as posicoes em
`03_ensaios/verdade_do_cenario`, separados como na matriz. O detector e o
avaliador leem esses arquivos gravados, entao a trilha de
`rodar_software.py` roda sem o TSNet.

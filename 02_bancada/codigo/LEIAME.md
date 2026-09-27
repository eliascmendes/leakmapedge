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
| `manobras_cais.py` | Manobras na mesma linha, agora com uma bomba de verdade no modelo: fim de carregamento no navio (fora do trecho), fechamento e abertura no ramal de um berco intermediario (dentro do trecho) e parada da bomba (fora do trecho, lado A). Grava tambem o registro de operacao que o sistema de controle daria |
| `manobras_rede.py` | Manobras na rede, com bomba no modelo: abertura e fechamento da válvula de cada navio (fim dos ramais) e parada da bomba |
| `manobras_trecho_200.py` | Manobras no trecho de 200 m: duas tomadas de ação rápida (20 ms), uma entre os sensores e uma depois do sensor B |
| `golpe_por_tempo_de_manobra.py` | O golpe de ariete de cada fechamento com varios tempos de manobra e cortando metade ou toda a vazao, mais casos de conferencia fora da grade: o estudo de transitorios que a previsao do pico antes da manobra usa (`07_servico/previsao_de_golpe.py`). Passo de 2 ms, que basta para o pico |
| `rede_cais.py` | A rede com manifold: tronco de 300 m do sensor A ao manifold e tres ramais (250, 400 e 550 m) ate os sensores dos bercos 104, 106 e 108, com vazamentos no tronco, em cada ramal e antes do sensor A |

Os tres ultimos precisam do ambiente com TSNet (`../ambiente/LEIAME.md`) e
levam cerca de 1 minuto por simulacao:

    python linha_cais.py          # regime e 16 vazamentos, ~17 min
    python manobras_cais.py       # 4 manobras, ~5 min
    python rede_cais.py           # regime e 16 vazamentos na rede, ~35 min
    python manobras_rede.py       # 7 manobras na rede, ~17 min
    python manobras_trecho_200.py # 4 manobras no trecho de 200 m, ~3 min
    python golpe_por_tempo_de_manobra.py  # 48 fechamentos, ~10 min

Os sinais ficam em `03_ensaios/amostras` e as posicoes em
`03_ensaios/verdade_do_cenario`, separados como na matriz. O detector e o
avaliador leem esses arquivos gravados, entao a trilha de
`rodar_software.py` roda sem o TSNet.

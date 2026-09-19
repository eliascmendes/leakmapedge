# Amostras

Series dos canais A e B na mesma base de tempo. Carga em metros e pressao
em bar.

Pode ir para o detector.

## `leakmap_amostras_v1.json`

Baseline limpo, direto do solucionador: sem ruido, sem quantizacao e sem
atraso de sensor. Nao usar esta rodada sozinha para calibrar limiar de
deteccao, o sinal esta bom demais.

## `leakmap_amostras_ruido_v1.json`

O mesmo sinal com o modelo de sensor da etapa A-09 aplicado, em tres niveis
(`sem_ruido`, `baixo` e `alto`). Cada ensaio registra a lista de efeitos
aplicados e seus parametros, entao qualquer resultado pode ser reproduzido a
partir do sinal limpo. Continua na base de tempo do solucionador; a decimacao
e a montagem do pacote acontecem em A-10, em `03_ensaios/pacotes`.

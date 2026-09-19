# Plano da matriz de ensaios

Diz de qual ensaio de origem cada linha da matriz veio e com que configuracao
de sensor e de velocidade declarada.

E o contrato entre quem gera os ensaios e quem avalia: o avaliador usa este
plano para saber que ensaio `MX-nnn` corresponde a que `EV-nn`, e so entao
abre a verdade do cenario.

Nao contem a posicao real do vazamento. O detector nao le este arquivo; ele le
apenas o pacote em `03_ensaios/pacotes`.

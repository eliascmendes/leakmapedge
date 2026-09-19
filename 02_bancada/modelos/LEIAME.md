# Modelos

Arquivos de rede EPANET (.inp) e o codigo que os gera.

Convencao adotada na rodada v1: nos internos em todas as posicoes candidatas
(40, 60, 80, 100, 120, 140, 160), identicos em todos os cenarios. So muda qual
no sofre o evento. Isso mantem a geometria constante entre rodadas e faz os seis
sub-trechos entre os sensores receberem a mesma velocidade ajustada, o que
elimina a ambiguidade de qual `c` entra na formula.

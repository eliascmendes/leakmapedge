# Pacotes de ensaio

Saida da etapa A-10. E o unico arquivo que o detector le.

Pode ir para o detector.

Formato `pacote-v1`. Cabecalho com a escolha de frequencia de amostragem e a
conta que a justifica, unidades, escala do instrumento e o atraso de grupo do
antisserrilhamento. Depois, um registro por ensaio com `id`, `n_pontos`,
`indice` (comum aos dois canais), `tempo_s`, `canal_A_carga_m`,
`canal_B_carga_m`, `parametros_do_detector` e `efeitos_de_sensor_aplicados`.

Nao contem a posicao real do vazamento, em nenhum campo.

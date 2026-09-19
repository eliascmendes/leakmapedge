# Detector

Modelo de sensor, amostragem, deteccao, marcacao de tempos de chegada e
estimador de posicao. Etapas A-09 a A-15 do fluxograma.

Nada aqui le `03_ensaios/verdade_do_cenario`. O erro de localizacao e
calculado em outro processo, por `05_avaliacao/avaliador.py`.

## Modulos

| Arquivo | Etapa | O que faz |
|---|---|---|
| `modelo_sensor.py` | A-09 | Banda, atraso comum, diferenca de atraso, jitter, offset, ruido, saturacao e quantizacao, cada um ligavel sozinho |
| `amostragem.py` | A-10 | Escolha da frequencia por criterio, decimacao e montagem do pacote do ensaio |
| `detector.py` | A-11 a A-15 | Passa-altas, razao de energia, marcacao com retrocesso, decisao de evidencia e registro de resultado |
| `posicao.py` | A-14 | `x = (L + c * delta_t) / 2` e a propagacao de erro, como funcao isolada |
| `matriz.py` | — | Definicao da matriz de ensaios: posicao x ruido x velocidade |
| `gerar_ensaios.py` | A-09, A-10 | Aplica o modelo de sensor e grava as amostras e o pacote |
| `rodar_detector.py` | A-11 a A-15 | Roda o detector sobre o pacote e grava um registro por ensaio |
| `detector_ponto_fixo.py` | bonus | Porte de referencia em aritmetica inteira de A-11 e A-12 |

## Cadeia de deteccao

1. **Passa-altas** de primeira ordem em 20 Hz, para remover o nivel de regime
   e a deriva lenta.
2. **Razao de energia**: energia media em janela curta de 6 amostras contra
   uma janela longa de referencia de 30 amostras, separadas por 3 amostras de
   guarda para que a frente de onda nao contamine a propria referencia.
3. **Declaracao de evento** quando as duas condicoes valem ao mesmo tempo:
   a razao atinge 12, e o valor eficaz da janela curta fica acima do piso de
   amplitude. O piso e parametro explicito e nunca fica abaixo da resolucao
   declarada do sensor. E ele que impede o detector de disparar sobre o ruido
   numerico do simulador, que fica na ordem de 1e-7 m de carga.
4. **Marcacao de chegada (A-12)**: do cruzamento do limiar, retrocede ate a
   amostra que sai da faixa de 3 sigma do ruido de referencia, o que desfaz o
   atraso introduzido pela janela de energia. Cada marca sai com incerteza
   composta de tres termos: quantizacao temporal, ruido dividido pela
   inclinacao no ponto de chegada, e ambiguidade de uma amostra do retrocesso.
5. **Decisao de evidencia (A-13)**: exige os dois canais validos e nao
   saturados, razao acima do limiar nos dois, e `delta_t` dentro de `-L/c` a
   `+L/c`. Fora disso o registro sai como inconclusivo, com o motivo. Nunca
   sai posicao fora do trecho. `delta_t` igual a zero e resultado valido, nao
   caso inconclusivo: significa evento equidistante dos sensores.
6. **Posicao (A-14)**: `x = (L + c * delta_t) / 2`, medida a partir do sensor
   A. Posicao absoluta no trecho = 40 m + x.

Nao ha CUSUM. O CUSUM interno do TSNet foi o substituto provisorio do baseline
v1, usado para fechar a cadeia A-01 a A-08 antes de existir detector de
produto. A cadeia acima e a especificada em A-11 e nao depende do TSNet.

## Classes de saida

Todo ensaio executado produz exatamente um registro, inclusive os que nao
detectaram nada: `localizado`, `detectado_sem_localizacao`, `sem_deteccao` e
`falha_execucao`.

## Amostragem

A frequencia sai de criterio, nao de costume. A resolucao de posicao e
`c * Ts / 2`. Partindo do requisito de localizar dentro de 0,5 m e de um fator
de seguranca 2, a resolucao de projeto e 0,25 m, o que pede pelo menos
2401,8 Hz. Decimando o passo do solucionador por 4 chega-se a 2491,9 Hz e a
uma resolucao de 0,2410 m. A conta inteira fica gravada no pacote do ensaio.

## Porte em ponto fixo

`detector_ponto_fixo.py` repete A-11 e A-12 so com inteiros: estado do filtro
em Q16, comparacao de razao por multiplicacao cruzada em vez de divisao, e
faixa de ruido comparada em energia em vez de raiz quadrada. Nos 90 canais da
matriz ele reproduz a versao em ponto flutuante exatamente: mesma deteccao,
mesmo indice de cruzamento e mesma marca de chegada. A maior largura de
palavra observada foi 57 bits, registrada por estagio em
`resultados/leakmap_ponto_fixo_v1.json` para dimensionar o registrador quando
houver Verilog.

## Adaptacao para o painel

O simulador do painel usa `web/leakmap_detector.js`, uma adaptacao destes
modulos para o navegador. Os modulos daqui continuam sendo a referencia: o
JavaScript e conferido contra o gabarito que `web/gerar_gabarito.py` grava a
partir deste Python. Mudanca de algoritmo comeca aqui; ver `web/LEIAME.md`.

## Como rodar

```
python 04_detector/gerar_ensaios.py     # A-09 e A-10
python 04_detector/rodar_detector.py    # A-11 a A-15
python -m unittest discover -s 04_detector/testes -p "teste_*.py"
```

Ou a trilha inteira, incluindo o avaliador: `python rodar_software.py`.

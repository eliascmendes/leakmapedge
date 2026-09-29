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
| `refino.py` | — | Refino da diferenca de tempo por correlacao cruzada, gravado ao lado da posicao |
| `fisica.py` | — | Mecanica dos fluidos da linha: escoamento de regime, vazao e furo do vazamento, incerteza de posicao, calibracao da velocidade de onda e menor vazamento detectavel |
| `linha_cais.py` | A-09 a A-15 | Linha do cais: seis transmissores, com e sem a classificacao por polaridade e origem |
| `rede.py` | A-14 em rede | Localizacao numa rede em arvore com N sensores: o trecho e o ponto cujos tempos pela tubulacao batem com as chegadas |
| `rede_cais.py` | A-09 a A-15 | Rede do cais com manifold e tres ramais, quatro sensores, seis transmissores |

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

## Fisica da linha (fisica.py)

O detector acha a frente de onda e a posicao. `fisica.py` usa a mesma frente,
e os niveis de regime antes dela, para dizer quanto vaza, por que furo, com
que incerteza, e qual e o menor vazamento que a linha consegue ver. Roda ao
lado do detector: nao muda a decisao nem a posicao publicadas, que continuam
iguais no Python, no painel e na FPGA. Grava o bloco `fisica` e a
`incerteza_fisica` em cada registro localizado.

| Principio | Equacao | O que da |
|---|---|---|
| Darcy-Weisbach, atrito de Swamee-Jain | `h_f = f (L/D) V^2 / 2g` | Velocidade e vazao de regime pela perda de carga medida entre os sensores (valida para Re >= 4000 e e/D <= 0,05; fora disso o registro diz) |
| Atenuacao por atrito | `alpha = f V / (2 D c)` | Quanto a frente perde ate cada sensor; tambem medida pela razao das duas amplitudes, `ln(dH_A/dH_B) / (d_B - d_A)`, quando o furo nao esta perto do meio |
| Joukowsky | `dQ = 2 g A dH / c` | Vazao do vazamento pelo degrau da onda no furo (metade do deficit para cada lado) |
| Orificio (Torricelli, Cd = 0,61) | `Q = C_e sqrt(h)`, `Q = Cd a sqrt(2 g h)` | Coeficiente de emissor e diametro equivalente do furo; vazao na pressao de regime |
| Linha piezometrica | linear entre os sensores | Carga de regime no ponto do furo |
| Janelas do degrau | antes: -30 a -3 ms; depois: +4 ms (+ periodo do transmissor) ate 3 ms antes da primeira reflexao, `2 d / c` | Degrau limpo, sem a subida da frente e sem a onda refletida |
| Propagacao de incerteza | `u_x^2 = (c u_dt / 2)^2 + (dt u_c / 2)^2`, com `T^2/6` do periodo de atualizacao em `u_dt` | Incerteza de posicao que cobre o erro real, inclusive com transmissor lento |
| Minimos quadrados na lentidao | `s = 1/c`, `dt = s (2x - L)`, corte robusto por MAD a 3 sigma | Velocidade de onda calibrada pelos proprios eventos, e a posicao refeita com ela |
| Adveccao | `x = [dt (c^2 - V^2) + L (c - V)] / 2c` | Correcao do escoamento sobre a onda (vies de `-L V / 2c`, 0,42 m no cais), opcional |
| Limiar em carga e vazao | `dH_min = sqrt(R / k) sigma`, `k ~ 0,75` | Menor degrau e menor vazao que o detector declara com o ruido do transmissor |

Resultados contra a verdade do simulador em
`../05_avaliacao/leakmap_avaliacao_fisica_v1.json`
(`python 05_avaliacao/avaliar_fisica.py`):

- linha do cais, vazamento grande: coeficiente de emissor com erro mediano de
  +0,2 % (de -1,0 % a +1,3 %) do transmissor ideal ao de 10 ms, +1,1 % com
  100 ms; furo de 23,8 mm para 23,8 mm reais; vazao de regime de 0,0471 a
  0,0473 m3/s para 0,0471 reais;
- incerteza de posicao que cobre o erro a 2 sigma: com transmissor de 10 ms
  passa de 40 % para 100 % dos eventos; de 50 ms, de 0 % para 100 %; de 100
  ms, de 0 % para 60 %;
- velocidade de onda calibrada: 1226,2 m/s para 1226,6 reais com transmissor
  rapido; na matriz com velocidade declarada 2 % acima da real, o erro de
  posicao cai de 0,48 m (maximo 0,80) para zero sem ruido, e de 0,53 m para
  0,32 m com ruido alto. Com a velocidade ja certa e ruido alto, calibrar
  piora (0,24 m para 0,32 m): so vale quando ha motivo para duvidar de `c`;
- menor vazamento detectavel no cais: 0,104 m de degrau, cerca de 3,2 L/min,
  pela teoria; 0,10 a 0,12 m (3,2 a 3,8 L/min) na simulacao.

Na FPGA, a mensagem DEGRAU faz na propria placa as somas das janelas antes e
depois da chegada, e o computador tira delas o degrau da Joukowsky; ver
`../06_fpga/LEIAME.md`.

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

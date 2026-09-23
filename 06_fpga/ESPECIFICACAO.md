# Especificação do cenário B — contrato entre o computador e a FPGA

Este documento é o que o Verilog precisa implementar. O lado do computador já
existe e está testado em [`computador/`](computador). O comportamento esperado
da placa, byte a byte e amostra a amostra, está escrito em Python em
[`computador/placa_referencia.py`](computador/placa_referencia.py): em caso de
dúvida, **o modelo de referência manda**.

**Nome correto do que é feito aqui:** reprodução de sinais digitais em FPGA
física. O cenário valida o processamento digital na placa, detecção e marcação
das chegadas, nas condições ensaiadas. Não valida sensor físico, resposta de
transmissor, entrada analógica, conversor analógico-digital real nem
instalação industrial.

## 1. Divisão de trabalho

| Na FPGA | No computador |
|---|---|
| Conferência de CRC e de sequência de cada bloco | Seleção do ensaio pelo selo (B-01) |
| Memória das amostras (via 1) | Conversão para inteiros (B-02, B-03) |
| Reprodução por índice comum aos dois canais (B-08) | Empacotamento em blocos (B-04) |
| Passa-altas, somas de energia, limiar e marcação da chegada (B-09) | Diferença temporal, decisão de evidência e posição (B-11) |
| Resultado repetido até ser confirmado (B-10) | Comparação com o software e relatório (B-13, B-14) |

## 2. Via 1: o ensaio inteiro na memória da placa

O maior ensaio da matriz tem 500 amostras por canal: 500 × 2 × 16 bits =
16 000 bits, mais 5 384 bits de janelas e histórico do detector, somando
20,9 kbit. A menor placa candidata tem 180 kbit de memória em bloco. A
temporização do sinal vem do índice da memória, nunca do instante em que um
byte chega pela serial. A conta completa está em
[`resultados/leakmap_dimensionamento_v1.json`](resultados/leakmap_dimensionamento_v1.json).

Pela via 2, a serial a 115 200 bits/s não fecharia: seriam 11 603 bytes/s
com cabeçalho e CRC, contra 11 520 disponíveis.

**Capacidade mínima exigida da placa:** 4 096 amostras por canal. Acima
disso, a placa de referência devolve a configuração, mas recusa todos os
blocos (situação 3), e o ensaio não é executado.

## 3. Representação das amostras (B-03)

| Item | Valor |
|---|---|
| Palavra | 16 bits sem sinal, 0 a 65 535 |
| Referência | código 0 = 0 m de carga |
| Degrau | resolução declarada do transmissor do ensaio; 1 mm quando não há conversor declarado |
| Fora da faixa | satura no extremo e incrementa um contador (feito no computador) |

A placa recebe os códigos prontos. O degrau não entra na conta da placa: ele
já está embutido nos parâmetros inteiros da configuração.

## 4. Quadro

Tudo em little-endian.

```
A5 5A | tipo (1 byte) | tamanho (2 bytes) | carga útil | CRC-16 (2 bytes)
```

- CRC-16/CCITT-FALSE: polinômio 0x1021, valor inicial 0xFFFF, sem reflexão,
  sem xor final. Cobre tipo, tamanho e carga útil. Vetor de conferência:
  `"123456789"` → `0x29B1`.
- Identificador do ensaio: 8 bytes ASCII, completados com zero. Viaja em
  todas as mensagens.
- Quadro com CRC errado: a placa **não** processa, incrementa `falhas_de_crc`
  e responde `BLOCO_RECEBIDO` com identificador vazio, sequência `0xFFFF` e
  situação 1.
- Cabeçalho com tamanho acima de 1 024 bytes: a placa descarta os 5 bytes do
  cabeçalho, conta como falha de CRC, responde como acima e volta a procurar
  `A5 5A` a partir do byte seguinte.
- Mensagem com carga útil de tamanho diferente do exato (CONFIGURAR 31,
  EXECUTAR 12, CONFIRMAR e PEDIR 8, AMOSTRAS 14 + 4·n): `BLOCO_RECEBIDO` com
  identificador vazio, sequência `0xFFFF` e situação 5.
- Tipo desconhecido: ignorado, sem resposta.

## 5. Mensagens

### Computador → placa

| Tipo | Nome | Carga útil (bytes) |
|---|---|---|
| `0x01` | CONFIGURAR (31) | id (8), coeficiente_do_filtro u32, fracao u8, desloca_energia u8, n_curta u8, n_guarda u8, n_longa u8, limiar_de_razao u16, k2_faixa_de_ruido u16, piso_em_ye u32, piso_energia_por_amostra u32, n_amostras u16 |
| `0x02` | AMOSTRAS (14 + 4·n) | id (8), sequencia u16, indice_inicial u16, n_pares u8 (1 a 32), canais u8 = `0x03`, depois n pares (A u16, B u16) |
| `0x03` | EXECUTAR (12) | id (8), n_blocos u16, n_amostras u16 |
| `0x04` | CONFIRMAR_RESULTADO (8) | id (8) |
| `0x05` | PEDIR_RESULTADO (8) | id (8) |

### Placa → computador

| Tipo | Nome | Carga útil (bytes) |
|---|---|---|
| `0x81` | CONFIGURACAO_LIDA (39) | os mesmos 31 bytes de CONFIGURAR, depois falhas_de_crc u16, descontinuidades_de_sequencia u16, eventos_de_buffer u16, blocos_recebidos u16 |
| `0x82` | BLOCO_RECEBIDO (11) | id (8), sequencia u16, situacao u8 |
| `0x83` | RESULTADO (71) | id (8), situacao u8, n_amostras_reproduzidas u16, falhas_de_crc u16, descontinuidades u16, eventos_de_buffer u16, depois canal A (27) e canal B (27) |

Cada canal no RESULTADO: bandeiras u8 (bit 0 detectado, bit 1 retrocesso
truncado), indice_de_cruzamento u16, indice_de_chegada u16,
n_oportunidades_de_decisao u16, s_curta_no_cruzamento u64,
s_longa_no_cruzamento u64, maior_salto_q u32.

Situação do bloco: 0 ok, 1 CRC inválido, 2 fora de sequência, 3 de outro
ensaio ou sem configuração, 4 fora da memória, 5 mal formado.

Situação do resultado: 0 concluído, 1 recusado por amostras faltando, 2
recusado por falta de configuração, 3 recusado por estouro de largura.

### Identificação da placa simulada

| Tipo | Nome | Carga útil (bytes) |
|---|---|---|
| `0x06` | IDENTIFICAR (0) | nenhuma |
| `0x86` | IDENTIDADE (até 96) | texto UTF-8 que descreve a placa simulada e o motor dela |

Só a placa simulada ([`computador/placa_simulada.py`](computador/placa_simulada.py))
responde a IDENTIFICAR. A FPGA ignora, como faz com todo tipo que não conhece, e
o Verilog não muda. O computador manda IDENTIFICAR antes do primeiro ensaio:
com resposta, grava os resultados com a origem `placa_simulada`; em silêncio,
com a origem `fpga`. Assim resultado de placa simulada nunca sai como
resultado de FPGA.

## 6. Comportamento da placa

1. **CONFIGURAR:** apaga a memória, zera todos os contadores, a sequência
   esperada e o resultado pendente; guarda os parâmetros e responde
   CONFIGURACAO_LIDA com os parâmetros **efetivamente guardados** e os
   contadores. O computador confere tudo antes de seguir (B-07).
2. **AMOSTRAS:**
   - identificador diferente do configurado → situação 3;
   - sequência menor que a esperada → situação 0, sem regravar (é reenvio);
   - sequência maior → incrementa `descontinuidades_de_sequencia`, situação 2,
     não grava;
   - bloco que passa do fim da memória → situação 4;
   - bloco que não começa exatamente onde o anterior terminou
     (`indice_inicial` diferente do total de amostras gravadas) → situação 5;
     é assim que a placa sabe, só contando, que não ficou lacuna na memória;
   - caso contrário grava, incrementa a sequência esperada, `blocos_recebidos`
     e o total de amostras gravadas, e responde situação 0.
3. **EXECUTAR:** só executa se `n_amostras` e `n_blocos` batem com o que foi
   configurado e recebido e se o total de amostras gravadas é igual ao
   configurado. Senão, RESULTADO com situação 1. Nunca processa em silêncio
   um ensaio incompleto.
4. **Reprodução (B-08):** um único contador de índice percorre a memória, e
   os dois canais recebem a amostra do mesmo índice no mesmo ciclo.
5. **RESULTADO:** enviado ao fim e guardado. PEDIR_RESULTADO reenvia o
   guardado. CONFIRMAR_RESULTADO o descarta.

## 7. Detector em aritmética inteira (B-09)

Parâmetros vindos da configuração: `A` (coeficiente), `F` (fracao = 16),
`E` (desloca_energia = 8), `nc` = 6, `ng` = 3, `nl` = 30, `L` (limiar = 12),
`K2` (= 9), `P` (piso_em_ye), `PE` (piso_energia_por_amostra). Para cada
canal, a cada índice `n`:

```
se n == 0:  y = 0
senão:      y = (A * (y + ((x[n] - x[n-1]) << F))) >>> F      // deslocamento aritmético
ye = y >>> E
q  = ye * ye
s_curta = soma de q nas últimas nc amostras (n-nc+1 .. n)
s_longa = soma de q de (n-nc-ng-nl+1) até (n-nc-ng)
valido  = n >= nc + ng + nl - 1                  // conta n_oportunidades_de_decisao
s_ef    = s_longa se s_longa > nl*PE, senão nl*PE
dispara = valido e (s_curta*nl >= s_ef*(L*nc)) e (s_curta >= nc*P*P)
```

No **primeiro** disparo, `cruz = n`:

```
ref = s_longa (sem o piso)
fora(i) = ye[i]^2 * nl > K2 * ref
limite = max(0, cruz - (nc + ng))
i = cruz
enquanto i > limite e fora(i-1): i = i - 1
chegada = i
truncado = (i == limite) e fora(i) e (i > 0) e fora(i-1)
maior_salto_q = maior |y[k+1] - y[k]| para k de chegada até cruz-1   (0 se chegada == cruz)
```

Depois do disparo o canal continua contando `n_oportunidades_de_decisao` até
o fim da memória, mas não dispara de novo.

**Memória por canal:** os últimos `nc+ng+nl+1` = 40 valores de `q`, e os
últimos `nc+ng+2` = 11 valores de `ye` e de `y` (histórico anterior ao
disparo).

**Larguras medidas nos 90 canais da matriz** (bits, com sinal onde cabe), em
[`../04_detector/resultados/leakmap_ponto_fixo_v1.json`](../04_detector/resultados/leakmap_ponto_fixo_v1.json):

| Estágio | Bits |
|---|---|
| código de entrada | 17 |
| coeficiente do filtro | 17 |
| y (Q16) | 33 |
| ye | 25 |
| q = ye² | 48 |
| s_curta | 50 |
| s_longa | 51 |
| s_curta·nl | 55 |
| s_ef·(L·nc) | 57 |

Com registradores de 64 bits para somas e comparações há folga. A placa de
referência recusa o resultado (situação 3) se algum estágio passar de 64 bits
ou se `maior_salto_q` passar de 32 bits.

Valores de configuração da matriz: `A` = 62 390 em todos os ensaios; `P` =
6 252, 4 097 ou 256 e `PE` = 3 257 292, 1 398 784 ou 5 461, conforme o degrau
de 1 mm, 16 bits ou 12 bits.

## 8. Critério de aceitação do Verilog

**Situação:** o Verilog em [`rtl/`](rtl) cumpre os cinco critérios abaixo em
simulação (Icarus Verilog), nos 57 casos gerados por
[`computador/gerar_vetores.py`](computador/gerar_vetores.py) e no sistema
completo com a serial. A resposta do próprio Verilog também é decodificada e
conferida direto contra `04_detector/detector_ponto_fixo.py`, sem passar pelo
modelo da placa, em [`sim/prova_cenario_b.py`](sim/prova_cenario_b.py): 90 de
90 canais com o mesmo índice. A placa confirma o que a simulação já mostra.

1. Para cada um dos 45 ensaios da matriz e para os casos sintéticos de
   retrocesso longo e truncado de
   [`computador/testes/teste_cenario_b.py`](computador/testes/teste_cenario_b.py),
   o índice de cruzamento, o índice de chegada, a bandeira de truncado e
   `n_oportunidades_de_decisao` são iguais aos de `placa_referencia.py`.
2. A mensagem RESULTADO é igual, byte a byte, à que o modelo de referência
   produz para o mesmo ensaio.
3. Um bloco corrompido de propósito é recusado e reenviado, e o resultado
   final é o mesmo do ensaio limpo.
4. O mesmo ensaio executado duas vezes seguidas dá exatamente o mesmo
   resultado.
5. Com o canal B igual ao A atrasado 40 amostras, a diferença entre os
   índices de chegada devolvidos é exatamente 40.

Com a placa ligada, basta rodar:

```bash
python 06_fpga/computador/executar_cenario_b.py --serial COM5
```

O relatório sai com origem `fpga`, lado a lado com o da referência.

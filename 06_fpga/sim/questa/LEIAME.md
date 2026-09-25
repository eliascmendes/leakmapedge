# Testbench completo da placa pelo JTAG, no Questa

O testbench [`../tb_leakmap_jtag.v`](../tb_leakmap_jtag.v) simula o topo que
vai para a DE10-Standard,
[`placas/intel/leakmap_topo_jtag.v`](../../placas/intel/leakmap_topo_jtag.v),
**sem nenhuma alteração**: reinício na energização, ponte JTAG, núcleo, os dois
detectores e os LEDs. Só o `sld_virtual_jtag` da Intel é trocado pelo modelo
[`../modelos/sld_virtual_jtag.v`](../modelos/sld_virtual_jtag.v), que tem o
mesmo nome e as mesmas portas e desloca os bits como o cabo USB-Blaster faria.

O testbench faz o papel do computador: manda cada mensagem pela instrução
ESCREVER, busca a resposta pela instrução LER e exige os mesmos bytes que o
modelo Python da placa respondeu. O roteiro,
[`roteiro_jtag.hex`](roteiro_jtag.hex), é gravado por
[`computador/gerar_roteiro_jtag.py`](../../computador/gerar_roteiro_jtag.py) e
fica no git, então o Questa roda sem Python.

## O que ele confere

| Caso | O que mostra |
|---|---|
| MX-001, MX-013, MX-021, MX-030 | Vazamento localizado com cada transmissor, com c casada e desviada |
| MX-039 | O ensaio mais longo (500 amostras), sem evento: nenhuma chegada |
| B-06 | Bloco corrompido no caminho, recusado pelo CRC e reenviado |
| B-07 | O mesmo ensaio duas vezes, com resultado idêntico |
| B-08 | Canal B atrasado 40 amostras: as chegadas saem com exatamente 40 amostras de diferença |
| Protocolo | IDENTIFICAR sem resposta; resultado pedido de novo antes e depois da confirmação |

Em todas as 109 mensagens também confere que nada chega além da resposta, o
LED `led_resultado` (resultado esperando confirmação) e o `led_ocupado` apagado
quando a placa terminou. No começo e no fim lê o registro ESTADO da ponte: a
marca "LK", a versão e a bandeira de transbordo, que tem de ficar em 0.

## Como rodar no Questa

O Questa Starter vem com o Quartus Prime Lite e precisa da licença gratuita da
Intel. O Quartus em si não simula: ele chama o Questa.

1. Abra o **Questa - Altera FPGA Starter Edition** (menu Iniciar).
2. **File > Change Directory** e escolha esta pasta, `06_fpga/sim/questa`.
3. No Transcript, digite:

   ```
   do rodar.do
   ```

4. Abre a janela de forma de onda com os sinais principais (LEDs, JTAG, bytes
   da ponte, estado do núcleo e as chegadas dos dois detectores) e a
   simulação roda até o fim, cerca de 22 ms simulados.
5. O resultado sai no Transcript: um bloco por caso, cada RESULTADO com as
   chegadas nos dois canais, e no fim:

   ```
   RESULTADO tb_leakmap_jtag PASSOU casos=9 mensagens=109 bytes=13845 resultados=12 tempo_simulado=22.3 ms
   ```

O Questa não consegue gravar a biblioteca de trabalho num caminho com acento,
como "Área de Trabalho". Por isso o `rodar.do` copia os arquivos para
`%TEMP%\leakmap_questa` e compila lá; nada muda no repositório.

Sem janela, pelo terminal:

```bash
python 06_fpga/sim/rodar_questa.py
```

## Também no Icarus

O mesmo testbench roda no Icarus Verilog dentro de
`python 06_fpga/sim/rodar_simulacao.py`, que também confere que o roteiro no
git é o que o modelo da placa gera hoje. É o que o GitHub Actions roda a cada
envio.

## O que ele não cobre

O `sld_virtual_jtag` de verdade e o hub JTAG da FPGA são da Intel e só
existem na placa. A compilação no Quartus os confere (síntese, fechamento de
tempo do relógio do JTAG) e o primeiro teste na placa confirma o resto.

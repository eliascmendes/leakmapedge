# Roteiro do laboratório: cenário B na DE10-Standard

Tudo pelo cabo USB que grava a placa, sem adaptador serial e sem fio nos
pinos. O computador conversa com a FPGA pelo JTAG virtual, através do
`quartus_stp`, que vem com o Quartus Prime Lite.

## Antes de ir

1. Tenha o projeto do Quartus compilado, numa pasta **sem acento** no caminho
   (o Quartus não aceita "Área de Trabalho"). Ele usa o topo
   `leakmap_topo_jtag`, com os arquivos `rtl/leakmap_multiplicador.v`,
   `rtl/leakmap_detector.v`, `rtl/leakmap_nucleo.v`,
   `rtl/leakmap_ponte_jtag.v` e `placas/intel/leakmap_topo_jtag.v`, mais os
   pinos e o `.sdc` de `placas/de10_standard`. Quem ainda não tem projeto pode
   montar e compilar um com:

   ```bash
   python 06_fpga/placas/preparar_quartus.py --compilar
   ```

   O arquivo para gravar é o `.sof` da pasta `output_files` do projeto.

2. Confira que o caminho pelo JTAG passa nos testes, sem placa:

   ```bash
   python -m unittest discover -s 06_fpga/computador/testes -p "teste_ponte_jtag.py"
   ```

3. Leve o notebook com o Quartus instalado e peça no laboratório a fonte da
   placa e o cabo USB do USB-Blaster.

## No laboratório

1. **Confira a placa.** O chip grande tem de dizer `5CSXFC6D6F31C6` (o `N` do
   fim não importa). Se for outro código, pare: a pinagem deste projeto é só
   da DE10-Standard.
2. **Chave SW0 para baixo.** Para cima, a placa fica reiniciando.
3. **Ligue a fonte e o cabo USB** no conector do USB-Blaster da placa. No
   Gerenciador de Dispositivos, o cabo aparece como "USB-Blaster II". Se
   aparecer com triângulo amarelo, instale o driver da pasta
   `E:\altera\25.1std\quartus\drivers\usb-blaster-ii`.
4. **Grave o `.sof`.** No Quartus: Tools > Programmer > Hardware Setup >
   escolha o cabo (algo como `DE-SoC [USB-1]`) > Auto Detect. Aparecem dois
   dispositivos: o `SOCVHPS` (o processador ARM) e o `5CSXFC6D6`. Clique no
   `5CSXFC6D6` > Change File > o `.sof` do projeto > marque Program/Configure >
   Start. A barra tem de chegar a 100% (Successful). Feche o Programmer.
5. **O LEDR0 começa a piscar**, mais ou menos a cada 1,3 segundo. Se não
   piscar, a gravação não entrou.
6. **Teste um ensaio:**

   ```bash
   python 06_fpga/computador/executar_cenario_b.py --jtag --ensaios MX-001
   ```

   O esperado é algo como:

   ```
   placa pelo JTAG: DE-SoC [USB-1] | @2: 5CSXFC6D6(.|ES)/5CSXFC6D6F31C6 (0x...)
   MX-001  localizado       60.00 m  +- 0.49 m
   origem: fpga
   tentados 1 | concluidos 1 | nao concluidos 0
   iguais ao software: 1 de 1 | maior divergencia: 0 amostra(s), 0.000 m
   ```

7. **Rode os 45 ensaios:**

   ```bash
   python 06_fpga/computador/executar_cenario_b.py --jtag
   ```

   Os resultados ficam em `06_fpga/resultados`, com `fpga` no nome.
8. **Leve o resultado para o site:**

   ```bash
   python web/gerar_dados_fpga.py
   ```

   A tela do cenário B passa a abrir no resultado da FPGA, com o rótulo
   "Processado na FPGA · reprodução de sinais digitais".

Enquanto roda, os LEDs ajudam: LEDR1 acende quando a placa está trabalhando,
LEDR2 quando há resultado esperando o computador buscar, LEDR3 se a fila de
entrada transbordou (não deve acontecer).

## Se algo der errado

| Mensagem ou sintoma | O que fazer |
|---|---|
| `nenhum cabo JTAG encontrado` | Placa ligada? Cabo no conector do USB-Blaster? Driver instalado? No Programmer, Hardware Setup tem de mostrar o cabo. |
| `a FPGA respondeu 0x... em vez da marca do LEAKMAP` | O `.sof` não está gravado: a gravação some quando a placa desliga. Grave de novo (passo 4). |
| `quartus_stp nao encontrado` | O Quartus está em outra pasta: defina a variável `QUARTUS_ROOTDIR` com a pasta `...\quartus`. |
| Trava ou diz que o cabo está ocupado | Feche o Programmer do Quartus e rode de novo. |
| Mais de um cabo ligado | Informe qual: `--cabo "DE-SoC [USB-1]"`. |
| `a placa nao confirmou a configuracao` | Confira a SW0 para baixo e o LEDR0 piscando; grave de novo. |
| Algum ensaio diferente do software | Não apague nada: o relatório em `06_fpga/resultados` diz qual ensaio, em que canal e quanto. |

A primeira conversa confere sozinha a ordem em que o cabo desloca os bits, e
uma placa sem o projeto gravado para com mensagem clara, antes de mandar
qualquer ensaio.

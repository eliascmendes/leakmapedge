# FPGA — cenário B

Reprodução de sinais digitais em FPGA física: os ensaios já verificados no
cenário A são convertidos em inteiros, carregados na placa, e a placa faz a
detecção e a marcação das chegadas nos dois canais. O computador calcula a
posição e compara com o software.

O cenário valida o processamento digital na placa. Não valida sensor físico,
transmissor, entrada analógica, conversor analógico-digital real nem
instalação industrial.

## O que já existe

| Caminho | Conteúdo |
|---|---|
| [`ESPECIFICACAO.md`](ESPECIFICACAO.md) | Contrato entre computador e FPGA: representação, quadros, mensagens, comportamento da placa e o detector inteiro em pseudocódigo, com as larguras de registrador |
| [`computador/`](computador) | Todo o lado do computador, etapas B-01 a B-14, com testes |
| [`resultados/`](resultados) | Dimensionamento e resultados do cenário B, sempre com a origem no nome do arquivo |

## Lado do computador

| Arquivo | Etapa | O que faz |
|---|---|---|
| `selo.py` | B-01 | Selo de verificação (SHA-256) e seletor que recusa ensaio sem selo ou alterado |
| `representacao.py` | B-02, B-03 | Especificação em 16 bits, conversão e inversa, tabela de bordas, contador de saturação |
| `protocolo.py` | B-04, B-06, B-07, B-10 | Quadros com CRC-16, blocos numerados, configuração, recibos e resultado |
| `dimensionamento.py` | B-05 | Conta de memória e da serial contra cada placa candidata; decide a via 1 |
| `preparo.py` | B-02, B-07 | Conversão do ensaio e parâmetros inteiros da placa |
| `hospedeiro.py` | B-06, B-07, B-10 | Conversa com a placa: configura e confere, carrega com reenvio, executa e confirma |
| `transporte.py` | — | Em memória (referência) ou porta serial (FPGA) |
| `placa_referencia.py` | B-06 a B-10 | Modelo do que a FPGA faz, amostra a amostra, só com inteiros. É a especificação executável do Verilog |
| `registro_b.py` | B-11 | Δt pelos índices, decisão e posição com o código do cenário A, campo `origem` |
| `comparador.py` | B-13 | Divergência com o software em amostras e em metros, com a causa apontada |
| `executar_cenario_b.py` | B-01 a B-14 | Roda tudo e fecha o relatório, com as tentativas gravadas antes da execução |

## Resultado com a referência Python da placa

Enquanto não há placa, o cenário roda contra `placa_referencia.py`. Os
arquivos saem com `referencia` no nome e `origem:
referencia_python_da_placa` em cada registro: **não são resultado de FPGA**.

- 45 ensaios tentados, 45 concluídos.
- 43 idênticos ao software. Nos outros dois (MX-021 e MX-022, transmissor
  modesto), só o índice de cruzamento do limiar no canal B muda em uma
  amostra; as marcas de chegada e a posição são as mesmas. Causa apontada: a
  conversão para inteiros, porque o sinal de 12 bits, depois da média da
  decimação, fica entre dois códigos.
- Contra a verdade, pelo avaliador independente: os mesmos números do
  cenário A.

## Como rodar

```bash
python 06_fpga/computador/selo.py
python 06_fpga/computador/dimensionamento.py
python 06_fpga/computador/executar_cenario_b.py
python -m unittest discover -s 06_fpga/computador/testes -p "teste_*.py"
```

Com a FPGA na porta serial (precisa de `pip install pyserial`):

```bash
python 06_fpga/computador/executar_cenario_b.py --serial COM5
```

## O que falta

- O Verilog, seguindo [`ESPECIFICACAO.md`](ESPECIFICACAO.md).
- O arquivo de pinos e relógio da placa escolhida.
- A tela do modo FPGA no painel, com o rótulo de origem (B-12).

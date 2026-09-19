# LEAKMAP Edge

Deteccao e localizacao de vazamentos de graneis liquidos por diferenca de tempo
de chegada, com processamento em FPGA sobre a plataforma Itaqui Edge.
TACHYON, Hackathon do Complexo Portuario do Itaqui, Desafio 2.

## Regra que organiza estas pastas

A arquitetura v1.0 separa o que o detector pode ler do que nunca pode ler.
Essa separacao esta materializada em `03_ensaios`:

- `parametros` e `amostras` podem ir para o detector.
- `verdade_do_cenario` e de uso exclusivo do avaliador.

Quem mexer aqui precisa respeitar isso, senao o ajuste de limiares passa a ser
feito sobre a resposta e a avaliacao perde o valor.

## Mapa

| Pasta | Conteudo |
|---|---|
| `01_documentacao` | Proposta, arquitetura, fluxogramas, edital |
| `02_bancada` | Modelo hidraulico, codigo de simulacao, ambiente |
| `03_ensaios` | Saidas de cada rodada, ja separadas por acesso |
| `04_detector` | Modelo de sensor, amostragem, deteccao, estimador de posicao |
| `05_avaliacao` | Metricas, erro de localizacao, falsos alarmes |
| `06_fpga` | Verilog, sintese, integracao Itaqui Edge |

## Trilha de software

As etapas A-01 a A-08 (modelo hidraulico e simulacao) dependem do TSNet e
produziram `03_ensaios/amostras/leakmap_amostras_v1.json`. Dali em diante a
trilha roda so com NumPy:

```
python rodar_software.py
```

Isso executa A-09 e A-10 (modelo de sensor e pacote do ensaio), A-11 a A-15
(detector), o porte de referencia em ponto fixo, a montagem da verdade do
cenario da matriz e A-17 (avaliacao independente), e no fim roda os testes dos
dois lados. O avaliador roda em processo separado de proposito: e o criterio
de conclusao de A-17.

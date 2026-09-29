# LEAKMAP Edge

Deteccao e localizacao de vazamentos de graneis liquidos por diferenca de tempo
de chegada, com processamento em FPGA sobre a plataforma Itaqui Edge.
TACHYON, Hackathon do Complexo Portuario do Itaqui, Desafio 2.

**Projeto arquivado em 29/09/2026.** Sem desenvolvimento ativo. A visao geral,
o estado final e os resultados estao no `README.md`.

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
| `01_documentacao` | Fluxogramas das etapas A-01 a A-17, guia do backend para o front-end |
| `02_bancada` | Modelo hidraulico, codigo de simulacao, ambiente do TSNet |
| `03_ensaios` | Saidas de cada rodada, ja separadas por acesso |
| `04_detector` | Modelo de sensor, amostragem, deteccao, estimador de posicao, fisica da linha |
| `05_avaliacao` | Metricas, erro de localizacao, falsos alarmes, avaliacao da fisica |
| `06_fpga` | Especificacao, Verilog, simulacao, projetos do Quartus, lado do computador |
| `07_servico` | Escala de alerta, evento, cadastro, sobrepressao, previsao do golpe, webhook |
| `08_backend` | Bancada virtual: a linha, os sensores e o detector ao vivo |
| `web` | Simulador do painel e paridade do JavaScript com o Python |

## Trilha de software

As etapas A-01 a A-08 (modelo hidraulico e simulacao) dependem do TSNet e
produziram os sinais em `03_ensaios/amostras`. Dali em diante a trilha roda so
com NumPy:

```
python rodar_software.py
```

Isso executa A-09 e A-10 (modelo de sensor e pacote do ensaio), A-11 a A-15
(detector), o porte de referencia em ponto fixo, a montagem da verdade do
cenario da matriz e A-17 (avaliacao independente). Depois roda o cenario B
contra o modelo da placa, a linha e a rede do cais e a avaliacao da fisica da
linha, e no fim os 218 testes. Com o Icarus Verilog, simula tambem o Verilog
da placa. O avaliador roda em processo separado de proposito: e o criterio de
conclusao de A-17.

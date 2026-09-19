# Front-end

Simulador interativo do painel (`leakmap_painel.html`, seção "Experimente").

## O Python continua sendo a referência

O algoritmo do LEAKMAP vive em `04_detector`, em Python. Nada aqui o
substitui. O arquivo `leakmap_detector.js` é uma **adaptação** desse Python
para rodar no navegador, função por função e na mesma ordem de operações, e
só existe para o painel. Ele nunca gera número do repositório.

| Arquivo | Papel |
|---|---|
| `leakmap_detector.js` | Adaptação de `modelo_sensor.py`, `amostragem.py`, `detector.py`, `posicao.py` e das configurações de `matriz.py` |
| `simulador.js` | Só a tela: controles, desenho do trecho, gráfico e modo de vários cenários |
| `leakmap_dados_web.js` | Sinais, parâmetros e posições reais usados pelo simulador, gerados de `03_ensaios` |
| `gerar_gabarito.py` | Roda o Python e grava o gabarito que o JavaScript tem de reproduzir |
| `gerar_dados_web.py` | Gera `leakmap_dados_web.js` a partir dos arquivos versionados |
| `gabarito/leakmap_gabarito_js_v1.json` | Saídas do Python: modelo de sensor, cadeia completa e os 45 ensaios da matriz |
| `testes/teste_paridade.js` | Confere o JavaScript contra o gabarito do Python |

## Como a paridade é garantida

1. `gerar_gabarito.py` roda o próprio Python de `04_detector` e grava as
   entradas e as saídas: cada efeito do modelo de sensor isolado, a cadeia
   completa A-09 → A-14 nos cinco eventos e o registro de resultado dos 45
   ensaios da matriz, com os sinais intermediários de alguns canais amostra a
   amostra.
2. `testes/teste_paridade.js` exige do JavaScript:
   - índices, classes, motivos e booleanos exatamente iguais;
   - números em ponto flutuante com diferença relativa de no máximo 1e-9.

   Na versão atual a maior diferença observada é 1,1 × 10⁻¹⁶, um bit de
   arredondamento.
3. `rodar_software.py` regenera o gabarito e roda o teste de paridade junto
   com os testes Python. O GitHub Actions faz o mesmo a cada envio. Se o
   Python mudar e o JavaScript não acompanhar, a trilha falha.

Toda mudança de algoritmo segue esta ordem: primeiro o Python, depois
`gerar_gabarito.py`, e só então o ajuste do JavaScript até o teste passar.

## A única diferença deliberada: o sorteio do ruído

O gerador de números aleatórios do NumPy não tem equivalente em JavaScript.
Por isso os efeitos `ruido` e `erro_de_sincronizacao` recebem os sorteios
gaussianos de fora:

- nos testes, os mesmos sorteios que o Python usou, gravados no gabarito, e o
  resultado tem de ser idêntico;
- no painel, a primeira realização de ruído de cada cenário usa os sorteios
  que o Python usou na matriz de ensaios, então repete exatamente o número
  publicado em `05_avaliacao`;
- a partir do botão "Nova realização do ruído", o navegador sorteia com o
  próprio gerador, com a mesma estatística. O teste de paridade confere média
  e desvio-padrão desse gerador.

## Separação entre detector e avaliação

Na tela, a função que roda o detector recebe só os sinais e os parâmetros que
um detector instalado conheceria. A posição real do vazamento entra apenas na
função que calcula o erro depois da resposta, repetindo a regra de
`03_ensaios`: o detector nunca vê a resposta.

## Como rodar

```bash
python web/gerar_gabarito.py
python web/gerar_dados_web.py
node --test web/testes/teste_paridade.js
```

Ou a trilha inteira: `python rodar_software.py`.

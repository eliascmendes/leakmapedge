# Resultados do detector

Saida das etapas A-15 e do porte em ponto fixo. Gerados por
`rodar_detector.py` e `detector_ponto_fixo.py`.

| Arquivo | Conteudo |
|---|---|
| `leakmap_resultado_matriz_v1.json` | Um registro por ensaio: classe, marcas de chegada, delta_t, posicao quando houver, indicadores de qualidade e motivo |
| `leakmap_ponto_fixo_v1.json` | Comparacao canal a canal entre o porte inteiro e o de ponto flutuante, com as larguras de palavra observadas por estagio |

Nenhum destes arquivos contem a posicao real do vazamento nem erro de
localizacao. Quem cruza com a verdade do cenario e o avaliador, em
`05_avaliacao/avaliador.py`, que roda como processo separado.

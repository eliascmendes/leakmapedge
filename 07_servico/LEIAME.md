# Serviço local: escala de alerta e integração

O LEAKMAP não depende de nenhuma ferramenta externa para alarmar: a decisão sai
do detector, no nó, mesmo sem rede. Para quem quiser receber os eventos (a
automação da empresa, um n8n, um Node-RED, o histórico), o serviço entrega cada
evento num formato fixo, por webhook.

| Arquivo | O que faz |
|---|---|
| [`alerta.py`](alerta.py) | Escala de alerta e montagem do evento padronizado |
| [`integracao.py`](integracao.py) | Saída por webhook (HTTP POST com JSON), desligada por padrão, com fila local para o que não conseguiu sair |
| [`integracao.exemplo.json`](integracao.exemplo.json) | Configuração de exemplo; copie para `integracao.json` para ligar |
| [`receptor_teste.py`](receptor_teste.py) | Receptor mínimo, para testar a integração sem instalar nada |
| [`testes/`](testes) | Escala, evento e webhook de ponta a ponta com o receptor |

## Escala de alerta

| Nível | Quando | O que o sistema faz |
|---|---|---|
| `registro` | manobra reconhecida: onda de alta, ou alta de um lado e queda do outro | guarda no histórico; nunca alarma |
| `suspeita` | evento num canal só, ou origem no sensor ou fora do trecho | registra e observa |
| `provavel` | queda de pressão nos dois canais, com posição possível dentro do trecho | alerta, já com a posição |
| `confirmado` | provável e o sensor de gás acusou vapor na região | alarme grave |

Cada evento leva também o estado do **monitoramento**: `normal`, `degradado`
(com o motivo, vindo do autoteste dos canais) ou `sem_autoteste`.

## O evento (`leakmap.evento`, versão 1)

```json
{
  "tipo": "leakmap.evento",
  "versao": "1",
  "id": "9b7c...",
  "instante_utc": "2026-09-26T14:03:11.402+00:00",
  "linha": "L-01",
  "sensores": {"A": {"nome": "inicio do trecho", "posicao_m": 0.0},
               "B": {"nome": "berco 108", "posicao_m": 700.0}},
  "nivel": "provavel",
  "classificacao": "vazamento",
  "posicao_m": 252.4,
  "incerteza_m": 0.4,
  "lado": null,
  "motivo": "evidencia suficiente",
  "canais": {"A": {"detectou": true, "polaridade": "queda", "instante_de_chegada_s": 0.305},
             "B": {"detectou": true, "polaridade": "queda", "instante_de_chegada_s": 0.466}},
  "confirmacao_por_gas": null,
  "saude": {"monitoramento": "normal", "motivos": []},
  "origem_do_processamento": "notebook",
  "id_do_ensaio": "LQ-017"
}
```

| Campo | Significado |
|---|---|
| `nivel` | `registro`, `suspeita`, `provavel` ou `confirmado` |
| `classificacao` | `vazamento`, `manobra`, `fora_do_trecho` ou `evento_sem_localizacao` |
| `posicao_m`, `incerteza_m` | só para vazamento localizado; medida na linha, na mesma referência dos sensores |
| `lado` | para `fora_do_trecho`: o lado (`A` ou `B`) de onde a onda veio |
| `canais.*.polaridade` | `queda` ou `alta`: a frente de onda em cada sensor |
| `saude` | estado do monitoramento, com os motivos da degradação |
| `origem_do_processamento` | `fpga`, `simulacao_do_verilog`, `notebook` ou `software` |

A versão só muda se um campo existente mudar de sentido; campos novos podem
entrar sem mudar a versão.

## Ligar o webhook

```bash
copy 07_servico\integracao.exemplo.json 07_servico\integracao.json
```

Em `integracao.json`: `"ligado": true`, a `url` do destino e os `niveis` que
devem sair. Um envio que falha nunca atrasa nem derruba a detecção: o evento
vai para `07_servico/pendentes.jsonl` e sai de novo em `integracao.reenviar()`.

Para testar sem nada instalado, num terminal:

```bash
python 07_servico/receptor_teste.py
```

## Para o piloto: o sistema de controle da planta

Para o alarme chegar também ao sistema de controle (CLP ou SCADA), dois
caminhos usuais, a combinar com a equipe de automação do terminal:

- **contato seco de alarme**, uma saída digital por nível (provável e
  confirmado), o caminho mais simples e o mais robusto;
- **Modbus TCP**, com um mapa de registradores: nível, posição em decímetros,
  estado do monitoramento, contador de eventos.

Nenhum dos dois está implementado: dependem do sistema instalado.

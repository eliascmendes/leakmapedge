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
| [`cadastro.py`](cadastro.py) | Confronta o evento com o cadastro de válvulas e bombas e com o registro de operação |
| [`cadastro.exemplo.json`](cadastro.exemplo.json) | Cadastro de exemplo da linha simulada do cais |
| [`cadastro_linha_cais.py`](cadastro_linha_cais.py) | Aplica o cadastro aos ensaios da linha do cais e grava `resultados/` |
| [`sobrepressao.py`](sobrepressao.py) | Alerta de sobrepressão (golpe de aríete): recurso complementar, à parte da detecção de vazamento |
| [`previsao_de_golpe.py`](previsao_de_golpe.py) | Previsão do pico de pressão antes da manobra, com o tempo mínimo seguro de fechamento |
| [`testes/`](testes) | Escala, evento, cadastro, sobrepressão, previsão do golpe e webhook de ponta a ponta com o receptor |

## Escala de alerta

| Nível | Quando | O que o sistema faz |
|---|---|---|
| `registro` | manobra reconhecida: onda de alta, ou alta de um lado e queda do outro | guarda no histórico; nunca alarma |
| `suspeita` | evento num canal só, ou origem no sensor ou fora do trecho | registra e observa |
| `provavel` | queda de pressão nos dois canais, com posição possível dentro do trecho | alerta, já com a posição |
| `confirmado` | provável e o sensor de gás acusou vapor na região | alarme grave |

Cada evento leva também o estado do **monitoramento**: `normal`, `degradado`
(com o motivo, vindo do autoteste dos canais) ou `sem_autoteste`.

## Cadastro de equipamentos e registro de operação

A classificação por polaridade separa sozinha as manobras que **sobem** a
pressão (fechar uma válvula, partir uma bomba). As que **derrubam** a pressão
(abrir a válvula de um ramal para começar um carregamento, parar uma bomba)
geram a mesma onda de um vazamento. Nem a polaridade nem a posição separam as
duas coisas. O que separa é saber que o equipamento foi operado naquele
instante.

`cadastro.py` aplica uma regra conservadora:

| A origem do evento… | Registro de operação do equipamento, compatível com a onda, na janela do evento | Resultado |
|---|---|---|
| coincide com uma válvula ou bomba do cadastro | sim | `manobra` (nível `registro`), com o equipamento e a operação no motivo |
| coincide com uma válvula ou bomba do cadastro | não | o alerta continua como estava, com a anotação "coincide com X, sem operação registrada: conferir" |
| não coincide com nenhum equipamento | — | nada muda |

As regras de coincidência e de compatibilidade são estas:

- **Posição.** A posição estimada está a menos de `max(15 m, 3 × incerteza
  declarada)` do equipamento. Num evento fora do trecho, só o lado é
  conhecido, e vale qualquer equipamento além do sensor daquele lado (por
  exemplo, a bomba antes do sensor A).
- **Tempo.** A operação foi registrada de 5 s antes a 2 s depois do evento.
- **Onda.** Abrir e parar geram queda; fechar e partir geram alta. Uma operação
  incompatível com a polaridade medida não explica o evento.

**Só o registro de operação rebaixa um alerta.** A coincidência de posição
sozinha nunca rebaixa.

O risco que fica é o de um vazamento na própria válvula, no mesmo instante em
que ela é operada: esse sai como manobra registrada. É o preço da regra, e por
isso o evento continua no histórico, com o equipamento e a operação.

Numa **rede com manifold**, cada equipamento diz também o trecho, a distância
é medida pela tubulação (`GeometriaDaRede`) e "além do sensor" quer dizer mais
longe do manifold que ele, no mesmo ramal. Sem posição nem limite físico
passado, o lado é o do sensor que viu a onda primeiro (com folga de 2 ms).

**Uma operação registrada explica um evento só**: quem aplica a conferência
marca a operação como `usada`, e ela não serve para outro evento, mesmo dentro
da janela de tempo.

O **cadastro** (nome, tipo e posição de cada equipamento, na referência dos
sensores) vem do isométrico da linha. O **registro de operação** vem do sistema
de controle da planta (os eventos de abrir, fechar, partir e parar) ou de um
lançamento do operador. No evento, a conferência sai no campo `cadastro`.

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
| `cadastro` | conferência com o cadastro: `decisao` (`manobra_registrada`, `conferir` ou `sem_equipamento`), `equipamento`, `operacao`, `texto`; `null` quando não houve conferência |

A versão só muda se um campo existente mudar de sentido; campos novos podem
entrar sem mudar a versão.

## Alerta de sobrepressão (`leakmap.sobrepressao`, versão 1)

Recurso complementar, que entra agora: a detecção e a localização de
vazamento continuam sendo o centro do LEAKMAP e não mudaram. Os mesmos
sensores de pressão mostram também os picos de golpe de aríete (fechar uma
válvula ou partir uma bomba de repente), que com o tempo causam o próximo
vazamento nos elos fracos da linha: mangotes, braços de carregamento, flanges.

`sobrepressao.py` compara o pico de cada sensor com o **limite** da linha, a
pressão máxima admissível do componente mais fraco (premissa até chegar o
dado da planta):

| Nível | Quando |
|---|---|
| `atencao` | o pico passou de 80% do limite |
| `alarme` | o pico passou de 95% do limite |

- O episódio começa quando algum sensor passa do nível de atenção; o evento
  sai 1 s depois (para pegar o pico inteiro), de novo com o mesmo `id` e a
  `revisao` seguinte se subir para alarme, e quando acabar (todos os sensores
  abaixo do nível de atenção, com 0,3 bar de folga, por 1 s).
- A causa provável é a operação registrada mais perto do pico (de 5 s antes a
  1 s depois), no mesmo registro de operação do cadastro. Sem operação, a
  explicação pede para conferir a linha.
- Sensores reprovados no autoteste ficam de fora.
- A pressão só é medida onde há sensor: entre eles o pico pode ser maior. Um
  pico acima da faixa do transmissor fica cortado, e o evento avisa
  (`pico_pode_ser_maior`).
- O alerta avisa quando o pico acontece; a previsão, abaixo, responde antes.

Campos principais do evento: `id`, `revisao`, `nivel`, `em_curso`,
`limite_bar`, `origem_do_limite`, `pico_bar`, `fracao_do_limite`,
`sensor_do_pico`, `instante_do_pico_s`, `picos_por_sensor_bar`, `duracao_s`,
`causa_provavel`, `pico_pode_ser_maior`, `explicacao`. Pelo webhook, sai com
os níveis próprios, sem passar pelo filtro de níveis de vazamento (ver o
backend, `08_backend/repasse.py`).

## Previsão do golpe antes da manobra (`leakmap.previsao_de_golpe`, versão 1)

Recurso complementar, como o alerta. [`previsao_de_golpe.py`](previsao_de_golpe.py)
responde, antes de o operador mexer numa válvula: o pico previsto, o nível
(atenção, alarme) e o tempo mínimo de manobra para o pico ficar abaixo de 80%
do limite.

- **Tamanho do golpe (Joukowsky):** `dH = c / (g A n) * (Q0 - Q1)`, com `n` =
  1 no fim da linha e 2 no meio; a válvula que fica parcialmente aberta é um
  orifício, `Q1 = (1 - f) Q0 raiz(1 + dH/H0)`. Resolvido por bisseção.
- **Alívio pelo tempo de manobra:** pelo estudo de transitórios da válvula
  (tabela tempo → fração do golpe máximo, simulada uma vez por válvula, como
  se faz na planta); além da tabela, cai com 1/t. Sem estudo, Michaud,
  `(2L/c) / t`, marcado como estimativa.
- Abrir uma válvula ou parar uma bomba derruba a pressão: sem risco. Partida
  de bomba: sem previsão (curva da bomba e jeito de partir fora do cadastro).

Conferência contra o TSNet (`08_backend/validar_previsao_de_golpe.py`):

| Casos | Erro da subida prevista |
|---|---|
| 41 da tabela do estudo (a parte física e a interpolação) | de -6,1% a +10,7% |
| 7 de conferência, fora da tabela (30% e 75% da vazão, tempos no meio e além da tabela) | de -16,1% a +2,1% |
| Só a fórmula de Michaud, sem estudo (os 48) | de -40,8% a +48,7% |

`MARGEM` = 20%: a faixa publicada contém todos os casos, e o tempo mínimo
seguro usa o lado de cima dela. Tudo é premissa até chegarem a vazão de cada
válvula, o diâmetro, o limite e o estudo de transitórios da linha real.

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

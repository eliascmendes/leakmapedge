# Backend da bancada virtual

A equipe não tem bancada física: este backend faz o papel da linha, dos
sensores de pressão e do detector. O front-end (a bancada visual da
demonstração e o dashboard do operador) conversa com ele por REST e WebSocket,
como se houvesse uma tubulação de verdade do outro lado.

Tudo o que sai daqui é simulação e vem marcado com `"modo": "simulacao"`.

O contrato para a equipe de front está em
[`01_documentacao/LEAKMAP_backend_guia_para_o_front_end.txt`](../01_documentacao/LEAKMAP_backend_guia_para_o_front_end.txt)
(parte A: o que o backend entrega; parte B: a referência técnica). Com o
backend no ar, a referência viva é o `/docs`.

## Rodar

```bash
pip install -r 08_backend/requirements.txt
uvicorn --app-dir 08_backend app:app --port 8000
```

- Documentação interativa: http://localhost:8000/docs
- Página de teste, com todas as ações e mensagens: http://localhost:8000/teste
- Cliente de linha de comando: `python 08_backend/cliente.py --vazamento principal 320 grande`

| Variável de ambiente | Para quê |
|---|---|
| `LEAKMAP_CHAVE` | chave exigida nos comandos, no cabeçalho `X-LEAKMAP-Chave`. Sem ela, os comandos ficam abertos: só para uso local |
| `LEAKMAP_ORIGENS` | endereços do front liberados no CORS, separados por vírgula (padrão `*`) |
| `LEAKMAP_BANCO` | histórico: endereço `postgresql://...` (sobrevive a reinícios) ou arquivo SQLite. Sem ela, vale `DATABASE_URL`; sem as duas, SQLite em memória |
| `LEAKMAP_WEBHOOK_URL` | liga o repasse dos eventos por webhook para esta URL |
| `LEAKMAP_WEBHOOK_NIVEIS` | níveis que saem pelo webhook, separados por vírgula (padrão `suspeita,provavel,confirmado`) |
| `LEAKMAP_WEBHOOK_CABECALHOS` | cabeçalhos extras do webhook, em JSON (ex.: um token de autorização) |
| `LEAKMAP_LINHA` | linha ativa ao iniciar: `trecho_200`, `cais` ou `rede` (padrão `cais`) |

## Publicar no Render

O arquivo [`render.yaml`](../render.yaml), na raiz, descreve o serviço. No
Render: *New > Blueprint*, escolher este repositório. O Render gera a chave dos
comandos (`LEAKMAP_CHAVE`); ela fica na aba *Environment* do serviço.

No plano gratuito o serviço dorme depois de uns 15 minutos sem acesso, e o
primeiro acesso leva cerca de 1 minuto: `GET /api/servico` acorda. Sem banco
externo, o histórico some a cada reinício (ver abaixo). Medido no notebook, cada passo de 0,1 s da
bancada gasta de 1,4 a 2,6 ms de processador (mediana): cabe folgado no décimo
de processador do plano gratuito.

### Histórico que sobrevive a reinícios (PostgreSQL)

1. No Render: *New > Postgres* (o plano gratuito serve para a demonstração;
   ele tem prazo de validade, conferir no painel do Render).
2. Na página do banco, copiar a *Internal Database URL*.
3. No serviço `leakmap-bancada`, aba *Environment*: criar `LEAKMAP_BANCO` com
   esse endereço. O serviço reinicia e passa a gravar no banco; as tabelas
   (`eventos` e `sobrepressoes`) são criadas sozinhas.

`GET /api/servico` mostra `"historico": "postgresql"` quando deu certo. Se a
conexão com o banco cair (banco gerenciado derruba conexão parada), o backend
reconecta sozinho.

### Repasse dos eventos por webhook

Com `LEAKMAP_WEBHOOK_URL` definida, cada evento que sai no WebSocket sai também
por HTTP POST, em JSON, para essa URL, pelo mesmo código de
`07_servico/integracao.py`: filtro por nível, três tentativas e fila local
para reenviar a cada minuto o que não saiu. É o ponto de entrada da automação
da empresa (n8n, Node-RED, o sistema de controle). Vai só o evento, sem a
verdade da simulação, com `"modo": "simulacao"`; quando o gás confirma um
alerta, o mesmo evento sai de novo com o mesmo `id` e `"revisao": 2`. O envio
roda à parte: um destino lento ou fora do ar nunca atrasa a bancada.

- `GET /api/integracao`: se está ligado, o destino (só o endereço do
  servidor), os níveis e as contagens (enviados, filtrados, pendentes,
  reenviados).
- `POST /api/integracao/teste` (com a chave): manda na hora um evento de teste,
  marcado `"teste": true`.

Para testar sem nada instalado, `python 07_servico/receptor_teste.py` faz o
papel do destino.

## Como funciona

A cada 0,1 s de relógio, a bancada (`bancada.py`):

1. calcula a carga em cada sensor: o regime da linha mais os eventos abertos
   (`gerador.py`);
2. passa o sinal pelo modelo do transmissor escolhido, o mesmo dos ensaios
   (`04_detector/modelo_sensor.py`, configurações de
   `04_detector/linha_cais.py`);
3. aplica as falhas de sensor pedidas (cabo rompido, sinal travado);
4. procura a chegada de uma onda com o detector (`04_detector/detector.py`).
   Quando o primeiro sensor a vê, espera o maior tempo de percurso entre os
   sensores e fecha o evento com o detector inteiro: `detector.py` na linha
   reta, `rede.py` na rede. Depois vêm o autoteste dos canais (o modelo da
   placa, `06_fpga/computador`), o cadastro com o registro de operação e a
   escala de alerta (`07_servico`).

**Confirmação do degrau.** O detector foi calibrado sobre registros de 0,2 s.
Rodando sem parar, ele toma cerca de 10 mil decisões por segundo, e o ruído do
transmissor passava do limiar num sensor só cerca de uma vez a cada 2,5
minutos (4 em 10 minutos, com o transmissor rápido e com o de 10 ms; nenhuma
virou alarme, porque alarme precisa de dois sensores). Quando só um sensor
dispara, a bancada confere se o nível mudou e ficou mudado; o pico de ruído é
descartado e contado em `deteccoes_descartadas_como_ruido`, no
`/api/servico`. Depois disso: nenhuma detecção falsa em 10 minutos, em todas as
linhas, e os eventos reais num sensor só (cabo rompido, parada de bomba)
continuam saindo. O detector em si não mudou.

### Alerta de sobrepressão (recurso novo)

Complementar à detecção e localização de vazamento, que continua sendo o centro
e não mudou. No mesmo passo de 0,1 s, o monitor de `07_servico/sobrepressao.py`
compara o pico de pressão de cada sensor com o limite da linha, a pressão
máxima admissível do componente mais fraco (mangote, braço de carregamento,
flange): **atenção** a partir de 80% do limite, **alarme** a partir de 95%. O
episódio sai na mensagem `sobrepressao` do WebSocket, 1 s depois de começar,
de novo com o mesmo `id` se subir para alarme e quando acabar; a causa
provável é a operação registrada mais perto do pico. Fica numa tabela própria
do histórico (`sobrepressoes`) e sai também pelo webhook, com
`"tipo": "leakmap.sobrepressao"` e os níveis próprios, sem o filtro de níveis
de vazamento. Sensores reprovados no autoteste ficam de fora.

| Linha | Limite (premissa) | Manobras da bancada que chegam à atenção |
|---|---|---|
| `cais` | 12 bar | fechar XV-108: 10,5 bar em B (88%); partir B-01: 11,3 bar em A (94%) |
| `rede` | 12 bar | partir B-01: 10,3 bar em A (86%) |
| `trecho_200` | 8 bar | fechar XV-100: 6,5 bar em A (82%) |

Os limites são premissas até chegar o dado da planta (`linhas.py`,
`LIMITE_DE_PRESSAO_BAR`) e mudam pela API, até o serviço reiniciar:

- `GET /api/sobrepressao`: limite, estado atual e último episódio;
- `GET /api/sobrepressao/eventos`: histórico das sobrepressões;
- `POST /api/sobrepressao/limite` (com a chave): `{"limite_bar": 10.5, "linha": "cais"}`.

O alerta avisa quando o pico acontece; para saber antes, a previsão abaixo.

### Previsão do golpe antes da manobra (recurso novo)

Também complementar. Antes de o operador fechar uma válvula,
`07_servico/previsao_de_golpe.py` calcula o pico previsto, o nível e o tempo
mínimo de manobra para o pico ficar abaixo de 80% do limite:

1. **o tamanho do golpe**, pela fórmula de Joukowsky, com a válvula como
   orifício (a vazão que resta cresce com a pressão) e a onda saindo para um
   lado (fim da linha) ou para dois (meio da linha);
2. **o alívio pelo tempo de manobra**, pelo estudo de transitórios de cada
   válvula: `02_bancada/codigo/golpe_por_tempo_de_manobra.py` simula no TSNet
   o fechamento com vários tempos e frações da vazão. Sem estudo, vale a
   fórmula de Michaud, marcada como estimativa.

Os dados de cada válvula (vazão, lados, distância até o reservatório, sensor
de referência, manobra padrão) são premissas lidas dos scripts das
simulações (`linhas.py`). Conferência contra o TSNet
(`validar_previsao_de_golpe.py`):

| Casos | Erro da subida prevista |
|---|---|
| 41 da tabela do estudo (a parte física e a interpolação) | de -6,1% a +10,7% |
| 7 de conferência, fora da tabela (30% e 75% da vazão, tempos no meio e além da tabela) | de -16,1% a +2,1% |
| Só a fórmula de Michaud, sem estudo (os 48) | de -40,8% a +48,7% |

A faixa publicada usa margem de 20% e contém todos os casos. Nas manobras que
a bancada executa, a previsão bate com o que o alerta mede: XV-108 no cais,
10,56 bar previstos e 10,55 medidos; XV-100 no trecho de 200 m, 6,54 e 6,55.

- `GET /api/sobrepressao/previsao?equipamento=XV-108&acao=fechar&tempo_de_manobra_s=2`
  (aberta; não mexe na bancada), com a curva pico × tempo de manobra;
- a resposta de `POST /api/bancada/equipamento` traz `previsao_do_golpe`, a
  previsão da manobra que a bancada vai fazer.

Partida de bomba sem previsão: depende da curva da bomba e do jeito de
partir. A bancada executa sempre a manobra padrão; outros tempos e frações
são "e se".

**Chegada pelo nível.** Quando só um sensor declara, o cadastro toma o lado
dele, supondo que o outro ainda não tinha visto a onda. Com a frente lenta da
parada da bomba, o que não declarou pode ser o mais perto: na linha do cais, 4
paradas em 50 saíam como "suspeita do lado B, conferir XV-108", com a queda
tendo passado pelo sensor A 0,57 s antes. A bancada agora olha o nível dos
outros sensores: se algum mostra o mesmo degrau começando antes da chegada
declarada por pelo menos 80% do percurso entre os dois, e já mudou pelo menos
metade do degrau do que declarou, a onda veio de além dele, e o lado é o dele
(anotado no `motivo`). Resultado: nenhuma parada do lado errado em 100 (linha
do cais e rede, a partir do regime e logo depois de outras manobras); em 206
cenários de vazamento, manobra e falha de sensor, com o transmissor rápido e o
de 100 ms, só a partida da bomba sem registro mudou, para o lado certo (A). O
detector não muda.

O backend não reescreve nenhuma dessas partes: importa (`projeto.py`). O
detector só recebe o sinal dos sensores; a posição real vai à parte, no campo
`verdade`, só para o perfil de demonstração.

### De onde vem o sinal

Cada simulação gravada do TSNet vira um molde: a variação de carga em cada
sensor desde o evento (`linhas.py`). Para um vazamento em qualquer ponto, o
gerador pega a simulação mais próxima (mesmo trecho, mesmo tamanho, mesmo lado
do sensor A), desloca a onda de cada sensor para a chegada cair onde a
distância pela tubulação manda e corrige a amplitude pelas simulações vizinhas.
No ponto simulado, o sinal é o do próprio TSNet (fonte `tsnet`); fora dele,
fonte `gerador`.

Conferência (`validar_gerador.py`): cada um dos 36 pontos simulados foi gerado
a partir dos vizinhos, sem a própria simulação, e comparado com o TSNet.

| Medida | Resultado |
|---|---|
| Diferença de chegada da onda | até 0,4 ms, uma amostra do detector |
| Amplitude da frente | 0,99 a 1,02 do TSNet no trecho de 200 m e na linha do cais; 0,97 a 1,04 na rede |
| Classe dada pelo detector | a mesma nos 36 casos |
| Erro de posição do detector | 0 a 0,30 m sobre o sinal gerado, 0 a 0,30 m sobre o do TSNet |

Resultado completo em `resultados/leakmap_validacao_do_gerador_v1.json`.

### Limites

- As reflexões que vêm depois da primeira chegada seguem a forma do ponto
  simulado mais próximo: ficam deslocadas de até o dobro da distância até ele,
  dividido pela velocidade da onda. A chegada, que é o que o detector usa, é
  exata.
- Depois que a simulação de um vazamento acaba, o sinal segura o último
  valor: o vazamento fica aberto até reparar. No trecho de 200 m a simulação
  gravada é curta (0,1 s), e o nível que fica é o do meio do transitório.
- As simulações de manobra acabam (1,2 s) no meio do transitório. Segurar o
  último valor deixaria o golpe de aríete na linha para sempre (e o alerta de
  sobrepressão aceso); por isso, depois do fim da simulação, a variação da
  manobra decai para o regime com constante de tempo de 2 s
  (`RELAXACAO_DA_MANOBRA_S`, em `gerador.py`), e a manobra sai da conta
  quando o efeito já sumiu. É uma aproximação: o regime novo depois da
  manobra (um pouco acima ou abaixo do de antes) não está nas simulações.
  Duas manobras seguidas se somam enquanto a primeira decai. Com menos de
  uns 4 s entre elas, a frente lenta da segunda (a parada da bomba, sobretudo)
  pode não ser marcada: o decaimento da primeira ainda enche a janela longa
  do detector. Na linha real o transitório demora ainda mais para assentar;
  `conferir_servico.py` espera 4 s entre as manobras (`ASSENTAR_S`).
- Manobras nas três linhas, pelas simulações de manobra de cada uma: na
  linha do cais, a bomba e as válvulas XV-104, XV-106 e XV-108 (a XV-104 usa
  as simulações da XV-106, deslocadas para 200 m); na rede, a bomba e as
  válvulas dos navios no fim de cada ramal, XV-104, XV-106 e XV-108; no trecho
  de 200 m, duas tomadas de ação rápida, XV-100 (entre os sensores) e XV-190
  (depois do sensor B). O sentido contrário de uma manobra que não foi
  simulada (reabrir a válvula do navio, partir a bomba) é a mesma onda com o
  sinal trocado.
- No trecho de 200 m, as tomadas fecham e abrem em 20 ms. Com 0,3 s, como nas
  outras linhas, a onda num trecho curto entre dois reservatórios vira uma
  rampa lenta que as reflexões desfazem, sem frente para o detector marcar.
- Na rede, a abertura da válvula de um navio (fora da rede monitorada, 20 m
  depois do sensor do berço) às vezes sai sem posição e sem lado, porque a
  rampa de 0,3 s é marcada em pontos diferentes em cada sensor. O cadastro
  toma o lado do sensor que viu a onda primeiro; com o registro de operação,
  sai como manobra registrada; sem ele, como suspeita, com a anotação para
  conferir.
- Cada operação registrada explica um evento só: depois de usada, não serve
  para outro, mesmo dentro da janela de 5 s.
- A parada da bomba tem frente lenta (a bomba desacelera): a razão de energia
  do detector fica entre 10 e 24 em todos os sensores, com limiar 12. Em 50
  paradas a partir do regime, com o transmissor rápido, 1 na linha do cais e
  4 na rede não foram marcadas por sensor nenhum: não sai evento (nunca um
  alarme; a operação estava registrada). O detector não foi recalibrado para
  isso, e a conferência do serviço aceita a parada não marcada.
- Vários eventos ao mesmo tempo se somam (superposição linear).

## Arquivos

| Arquivo | O que faz |
|---|---|
| `projeto.py` | Importa os módulos do projeto (detector, autoteste, alerta, cadastro, premissas) |
| `linhas.py` | As três linhas e os moldes do TSNet |
| `gerador.py` | Sinal de qualquer ponto a partir das simulações do TSNet |
| `bancada.py` | Estado da bancada, modelo do transmissor, falhas e detector em fluxo |
| `explicacao.py` | Texto do evento para a tela |
| `historico.py` | Histórico dos eventos, em PostgreSQL ou SQLite |
| `repasse.py` | Repasse dos eventos por webhook |
| `app.py` | API REST e WebSocket |
| `pagina_teste.html` | Página de teste (`/teste`) |
| `cliente.py` | Cliente de linha de comando; grava sessões |
| `validar_gerador.py` | Conferência do gerador contra o TSNet |
| `validar_previsao_de_golpe.py` | Conferência da previsão do golpe contra o TSNet (grava `resultados/leakmap_validacao_da_previsao_de_golpe_v1.json`) |
| `conferir_servico.py` | Conferência de um serviço no ar (Render ou local): 79 conferências com resultado esperado |
| `exemplos/` | Sessões gravadas do WebSocket, uma mensagem por linha: vazamento na linha do cais, abertura de válvula sem registro de operação, vazamento na rede |
| `testes/` | Gerador, bancada ao vivo, manobras nas três linhas, sobrepressão, fluxo contra lote, REST, WebSocket, webhook de ponta a ponta e histórico em SQLite e PostgreSQL |

Testes: `python -m unittest discover -s 08_backend/testes -p "teste_*.py"`
(47 testes; os 6 do PostgreSQL rodam quando `LEAKMAP_BANCO_DE_TESTE` aponta
para um banco descartável, como no GitHub Actions, job `backend-da-bancada`,
que sobe um PostgreSQL para eles).

## Conferir o serviço no ar

```bash
python 08_backend/conferir_servico.py --endereco https://leakmap-bancada.onrender.com --chave <chave>
```

Roda 79 conferências com resultado esperado conhecido: consultas, chave,
erros de validação, WebSocket (taxa, pressão de regime contra o TSNet, perfil
do operador), vazamentos na linha do cais, na rede e no trecho de 200 m,
manobras com e sem registro de operação nas três linhas, autoteste, gás,
transmissor lento, histórico, webhook, sobrepressão (atenção no fechamento
da XV-108, o mesmo episódio encerrando, alarme com o limite em 10,5 bar, e a
previsão antes da manobra com o pico medido dentro da faixa prevista) e
20 s de regime sem falso alarme. No fim devolve a bancada ao estado inicial. Como o serviço é compartilhado, não começa se houver alguém
conectado ao WebSocket, a menos que se use `--forcar`. `--relatorio
arquivo.json` grava o resultado; `--grupos manobras,sobrepressao` roda só
os grupos pedidos.

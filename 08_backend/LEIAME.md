# Backend da bancada virtual

A equipe não tem bancada física: este backend faz o papel da linha, dos
sensores de pressão e do detector. O front-end (a bancada visual da
demonstração e o dashboard do operador) conversa com ele por REST e WebSocket,
como se houvesse uma tubulação de verdade do outro lado.

Tudo o que sai daqui é simulação e vem marcado com `"modo": "simulacao"`.

O contrato para a equipe de front está em
[`01_documentacao/LEAKMAP_backend_guia_para_o_front_end.txt`](../01_documentacao/LEAKMAP_backend_guia_para_o_front_end.txt)
(seção 15: o que mudou na implementação). Com o backend no ar, a referência
viva é o `/docs`.

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
| `LEAKMAP_BANCO` | arquivo SQLite do histórico (padrão: em memória) |
| `LEAKMAP_LINHA` | linha ativa ao iniciar: `trecho_200`, `cais` ou `rede` (padrão `cais`) |

## Publicar no Render

O arquivo [`render.yaml`](../render.yaml), na raiz, descreve o serviço. No
Render: *New > Blueprint*, escolher este repositório. O Render gera a chave dos
comandos (`LEAKMAP_CHAVE`); ela fica na aba *Environment* do serviço.

No plano gratuito o serviço dorme depois de uns 15 minutos sem acesso, e o
primeiro acesso leva cerca de 1 minuto: `GET /api/servico` acorda. O
histórico some a cada reinício. Medido no notebook, cada passo de 0,1 s da
bancada gasta de 1,4 a 2,6 ms de processador (mediana): cabe folgado no décimo
de processador do plano gratuito.

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
- Depois que a simulação acaba, o sinal segura o último valor: o vazamento
  fica aberto até reparar. No trecho de 200 m a simulação gravada é curta
  (0,1 s), e o nível que fica é o do meio do transitório.
- Manobras só na linha do cais, com as quatro manobras simuladas. O sentido
  contrário de uma manobra (reabrir a válvula do navio, partir a bomba) é a
  mesma onda com o sinal trocado; a XV-104 usa as simulações da XV-106,
  deslocadas para 200 m.
- Vários eventos ao mesmo tempo se somam (superposição linear).
- Histórico só em SQLite.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `projeto.py` | Importa os módulos do projeto (detector, autoteste, alerta, cadastro, premissas) |
| `linhas.py` | As três linhas e os moldes do TSNet |
| `gerador.py` | Sinal de qualquer ponto a partir das simulações do TSNet |
| `bancada.py` | Estado da bancada, modelo do transmissor, falhas e detector em fluxo |
| `explicacao.py` | Texto do evento para a tela |
| `historico.py` | Histórico dos eventos em SQLite |
| `app.py` | API REST e WebSocket |
| `pagina_teste.html` | Página de teste (`/teste`) |
| `cliente.py` | Cliente de linha de comando; grava sessões |
| `validar_gerador.py` | Conferência do gerador contra o TSNet |
| `conferir_servico.py` | Conferência de um serviço no ar (Render ou local): 63 conferências com resultado esperado |
| `exemplos/` | Sessões gravadas do WebSocket, uma mensagem por linha: vazamento na linha do cais, abertura de válvula sem registro de operação, vazamento na rede |
| `testes/` | Gerador, bancada ao vivo, fluxo contra lote, REST e WebSocket |

Testes: `python -m unittest discover -s 08_backend/testes -p "teste_*.py"`
(19 testes; rodam também no GitHub Actions, no job `backend-da-bancada`).

## Conferir o serviço no ar

```bash
python 08_backend/conferir_servico.py --endereco https://leakmap-bancada.onrender.com --chave <chave>
```

Roda 63 conferências com resultado esperado conhecido: consultas, chave,
erros de validação, WebSocket (taxa, pressão de regime contra o TSNet, perfil
do operador), vazamentos na linha do cais, na rede e no trecho de 200 m,
manobras com e sem registro de operação, autoteste, gás, transmissor lento,
histórico e 20 s de regime sem falso alarme. No fim devolve a bancada ao
estado inicial. Como o serviço é compartilhado, não começa se houver alguém
conectado ao WebSocket, a menos que se use `--forcar`. `--relatorio
arquivo.json` grava o resultado.

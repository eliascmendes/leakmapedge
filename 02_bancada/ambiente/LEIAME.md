# Ambiente do TSNet

O detector, o avaliador e o painel rodam no Python do sistema, so com NumPy.
O TSNet so e preciso para refazer as simulacoes hidraulicas do zero
(`02_bancada/codigo`). Ele pede versoes antigas: Python 3.11 ou 3.12, NumPy
1.26 e wntr 1.3.2.

## Numa maquina nova: um comando

Windows, no PowerShell, a partir da raiz do repositorio:

    powershell -ExecutionPolicy Bypass -File 02_bancada\ambiente\preparar_ambiente.ps1

Linux ou macOS:

    bash 02_bancada/ambiente/preparar_ambiente.sh

O script acha um Python 3.11 ou 3.12 (o lancador `py` ou o `uv` no Windows;
`python3.11`, `python3.12`, `python3` ou o `uv` no Linux), cria o ambiente
virtual `leakmap_env` na pasta do usuario, instala as versoes congeladas e
termina rodando a conferencia. Com `-Completo` (Windows) ou `--completo`
(Linux, como segundo argumento, depois do destino), confere tambem a linha e a
rede do cais, cerca de 3 minutos a mais.

| Arquivo | O que e |
|---|---|
| `requirements-congelado.txt` | Todas as versoes, congeladas do ambiente conferido |
| `requirements.txt` | So as tres que importam (numpy, wntr, tsnet) |
| `preparar_ambiente.ps1`, `preparar_ambiente.sh` | Criam o ambiente e rodam a conferencia |
| `conferir_ambiente.py` | Refaz simulacoes gravadas e compara ponto a ponto; sai com 0 quando confere |

A conferencia compara a carga nos sensores e a base de tempo com o que esta
gravado em `03_ensaios/amostras`: o evento EV-01 da matriz de 200 m e, com a
opcao completa, o vazamento LC-05 da linha do cais e o RC-01 da rede. A
tolerancia e 1e-4 m de carga; a diferenca medida e de 5e-6 m, o
arredondamento do arquivo de rede.

Conferido em 26/09/2026 no Windows 11 com Python 3.11.16, num ambiente criado
do zero pelo script. O GitHub Actions faz o mesmo no Linux a cada envio (job
`ambiente-do-tsnet` em `.github/workflows/testes.yml`).

## Armadilhas conhecidas

1. NumPy 2.x quebra o TSNet. Instalar numpy e wntr antes do tsnet impede a
   subida de versao.
2. A wheel se identifica como 0.3.1 mas `tsnet.__version__` devolve `0.2.2`.
   Os autores nao atualizaram a string interna. Nao confie no atributo.
3. `MOCSimulator` falha com
   `AttributeError: 'Pipe' object has no attribute 'initial_head'`
   se `tsnet.simulation.Initializer(tm, 0, 'DD')` nao for chamado antes.
   Isso nao esta claro na documentacao.
4. O TSNet reescreve o coeficiente Darcy-Weisbach para 0.03 quando o valor
   derivado fica alto. Desloca o nivel de carga de regime, nao os tempos
   de chegada.
5. Na regra de manobra de valvula (`valve_closure`, `valve_opening`), a
   abertura final `se` e uma FRACAO de 0 a 1, embora a documentacao diga
   "percentage": o TSNet multiplica por 100 depois. Passar 85 quer dizer
   8500%, e a valvula muda de estado de uma vez no instante zero.
6. Rede com valvula parte fora de equilibrio: o EPANET e o TSNet discordam da
   perda da valvula aberta, e o TSNet avisa "Initial condition discrepancy of
   pressure". A diferenca vira uma onda falsa no inicio da simulacao. Para
   manobra, use retirada de vazao no no com `add_demand_pulse` (reduzir a
   retirada e o mesmo que fechar a valvula daquele ramal), que parte em
   equilibrio.
7. `set_roughness` troca a RUGOSIDADE do modelo (em metros, no wntr), nao o
   fator de atrito. Passar 0.02 pensando em f = 0,02 da 20 mm de rugosidade:
   o EPANET calcula o regime com f perto de 0,1, o TSNet corta para 0,03
   (armadilha 4), e o regime nao fica em equilibrio no transiente. Numa rede
   so com reservatorios isso quase nao aparece na carga; com bomba, a carga
   da descarga escorrega desde o instante zero. Para a linha do cais: nao
   chame `set_roughness`, e ponha a rugosidade real no `.inp` em metros
   (aco comercial: 0.046e-3). O trecho de 200 m da matriz (rodada v1) usa
   `set_roughness(0.02)` e ficou como esta, para nao mudar a referencia.

## Instalacao a mao

Se preferir nao usar o script: um Python 3.11 ou 3.12, num ambiente virtual
fora de caminho com acento (o NumPy 1.26 e o wntr 1.3.2 nao tem pacote pronto
para Python 3.13 ou 3.14):

    py -3.11 -m venv C:\Users\<usuario>\leakmap_env
    C:\Users\<usuario>\leakmap_env\Scripts\python -m pip install -r 02_bancada\ambiente\requirements-congelado.txt
    C:\Users\<usuario>\leakmap_env\Scripts\python 02_bancada\ambiente\conferir_ambiente.py

Sem o arquivo congelado, instale numpy e wntr ANTES do tsnet (armadilha 1).

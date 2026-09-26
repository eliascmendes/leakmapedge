# Ambiente

Combinacao validada em 18/09/2026, instalada sem ajuste:

    python -m venv leakmap_env
    pip install numpy==1.26.4 wntr==1.3.2
    pip install tsnet

Resultado: numpy 1.26.4, wntr 1.3.2, tsnet 0.3.1 (wheel), pandas 3.0.6.

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

## No Windows

O NumPy 1.26 e o wntr 1.3.2 nao tem pacote pronto para Python 3.13 ou 3.14.
Use um Python 3.11 ou 3.12 so para a bancada, num ambiente virtual fora de
caminho com acento:

    py -3.11 -m venv C:\Users\<usuario>\leakmap_env
    C:\Users\<usuario>\leakmap_env\Scripts\python -m pip install numpy==1.26.4 wntr==1.3.2
    C:\Users\<usuario>\leakmap_env\Scripts\python -m pip install tsnet

Conferido em 26/09/2026 com Python 3.11.16: o ambiente reproduz os sinais
gravados de `03_ensaios/amostras/leakmap_amostras_v1.json` com diferenca
maxima de 5e-6 m de carga (arredondamento do arquivo de rede) e o mesmo passo
de tempo efetivo. O resto do projeto continua no Python do sistema; so as
simulacoes do TSNet usam este ambiente.

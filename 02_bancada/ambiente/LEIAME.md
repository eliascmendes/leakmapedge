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

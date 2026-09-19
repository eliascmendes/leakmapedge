# Codigo da bancada

Scripts de simulacao. Manter deterministico: toda rodada precisa registrar
semente, versoes e parametros efetivos lidos de volta do solucionador.

Ler de volta sempre, nunca assumir:

    tm.time_step        # passo de tempo efetivo
    pipe.wavev          # velocidade de onda ajustada por trecho

Na rodada v1 o solicitado foi 1e-4 s e 1200 m/s; o efetivo saiu
1.003264e-4 s e 1200.899544 m/s.

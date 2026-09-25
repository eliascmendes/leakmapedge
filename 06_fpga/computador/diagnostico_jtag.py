"""LEAKMAP - diagnostico da conversa com a FPGA pelo cabo de gravacao (JTAG).

Mostra, passo a passo, o que a placa devolve:
  1. o registro de estado da ponte (marca "LK", versao, transbordo) e a ordem
     dos bits que o computador detectou;
  2. uma leitura com nada enviado (tem de vir vazia);
  3. uma mensagem mal formada, que a placa sempre responde (recibo com
     situacao 5), e os bytes crus que voltaram;
  4. se nada voltou, a mesma mensagem com os bits na ordem inversa;
  5. o estado da ponte de novo.

Uso, com a placa gravada e o Programmer fechado:
  python 06_fpga/computador/diagnostico_jtag.py
"""
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import protocolo as PR  # noqa: E402
import transporte as TR  # noqa: E402


def ler_por(t, segundos):
    dados, fim = b'', time.monotonic() + segundos
    while time.monotonic() < fim:
        dados += t.receber(0.2)
    return dados


def estado(t):
    t._ir(t.IR_ESTADO)
    v = t._dr(32, 0)
    return v, 'marca %s, versao %d, transbordo %d' % (
        'LK ok' if v >> 16 == t.MARCA else 'ERRADA', (v >> 8) & 0xFF, v & 1)


def mostrar(dados):
    print('  bytes que voltaram (%d): %s' % (len(dados), dados.hex(' ') or '(nenhum)'))
    for situacao, tipo, carga in PR.LeitorDeQuadros().alimentar(dados):
        texto = '%s tipo 0x%02x' % (situacao, tipo)
        if situacao == 'ok' and tipo == PR.BLOCO_RECEBIDO:
            texto += ' -> recibo %r' % (PR.ler_bloco_recebido(carga),)
        print('  quadro: ' + texto)


def main():
    t = TR.TransporteJtag()
    try:
        print('1. placa: %s' % t.descricao)
        v, texto = estado(t)
        print('   estado 0x%08x (%s); bits na ordem inversa: %s' % (v, texto, t.invertido))

        t._ir(t.IR_LER)
        v = t._dr(8 + 8 * t.LER_MAX, 0)
        print('2. leitura sem nada enviado: n = %d, cru = 0x%x' % (v & 0xFF, v))

        mal_formada = PR.montar_quadro(PR.CONFIGURAR, b'\x00' * 30)
        print('3. mensagem mal formada (%d bytes): %s' % (len(mal_formada), mal_formada.hex(' ')))
        t.enviar(mal_formada)
        dados = ler_por(t, 2.0)
        mostrar(dados)

        if not dados:
            print('4. nada voltou; tentando a escrita com os bits na ordem inversa')
            t.invertido = not t.invertido
            t.enviar(mal_formada)
            t.invertido = not t.invertido
            dados = ler_por(t, 2.0)
            mostrar(dados)

        v, texto = estado(t)
        print('5. estado 0x%08x (%s)' % (v, texto))
    finally:
        t.fechar()


if __name__ == '__main__':
    main()

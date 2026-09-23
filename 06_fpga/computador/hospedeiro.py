"""LEAKMAP - lado do computador na conversa com a placa (cenario B).

Conduz um ensaio do comeco ao fim, na via 1 (ensaio inteiro na memoria da
placa, ver dimensionamento.py):

  1. CONFIGURAR e conferir a leitura de volta: parametros iguais aos
     enviados e contadores zerados, obrigatoriamente, antes de cada
     execucao (B-07);
  2. carregar os blocos, um a um, reenviando o bloco cujo CRC a placa
     rejeitou (B-04, B-06);
  3. EXECUTAR e esperar o resultado; sem resposta, pedir de novo; ao
     receber, confirmar. Sem resultado depois das tentativas, o ensaio sai
     marcado como sem resultado, nunca some (B-10).

A temporizacao do sinal nao depende de nada disso: vem do indice das
amostras dentro da placa. Os tempos medidos aqui sao so de comunicacao.
"""
import time

import protocolo as PR


class FalhaNaPlaca(RuntimeError):
    pass


class Hospedeiro:

    def __init__(self, transporte, tentativas=3, tempo_limite_s=2.0):
        self.transporte = transporte
        self.tentativas = tentativas
        self.tempo_limite_s = tempo_limite_s
        self.leitor = PR.LeitorDeQuadros()
        self.pendentes = []
        self._zerar_eventos()

    def _zerar_eventos(self):
        self.eventos = {'reenvios_de_bloco': 0, 'reenvios_de_configuracao': 0,
                        'pedidos_de_resultado': 0, 'quadros_com_crc_invalido_recebidos': 0}

    # --- recepcao ------------------------------------------------------------------
    def _esperar(self, tipos):
        """Proximo quadro valido de um dos tipos, ou um recibo de CRC invalido."""
        fim = time.monotonic() + self.tempo_limite_s
        while True:
            for k, (situacao, tipo, carga) in enumerate(self.pendentes):
                if situacao != 'ok':
                    self.eventos['quadros_com_crc_invalido_recebidos'] += 1
                    del self.pendentes[k]
                    break
                if tipo in tipos:
                    del self.pendentes[k]
                    return tipo, carga
            else:
                restante = fim - time.monotonic()
                if restante <= 0:
                    return None, None
                self.pendentes.extend(self.leitor.alimentar(self.transporte.receber(restante)))
                sincrono = getattr(self.transporte, 'sincrono', False)
                if not self.pendentes and (sincrono or time.monotonic() >= fim):
                    return None, None
                continue

    # --- B-07 -----------------------------------------------------------------------
    def configurar(self, identificador, parametros, n_amostras):
        quadro = PR.montar_quadro(PR.CONFIGURAR, PR.carga_configurar(identificador, parametros, n_amostras))
        for tentativa in range(self.tentativas):
            if tentativa:
                self.eventos['reenvios_de_configuracao'] += 1
            self.transporte.enviar(quadro)
            tipo, carga = self._esperar({PR.CONFIGURACAO_LIDA, PR.BLOCO_RECEBIDO})
            if tipo != PR.CONFIGURACAO_LIDA:
                continue
            ident, lidos, contadores = PR.ler_configuracao_lida(carga)
            esperado = dict(parametros, n_amostras=n_amostras)
            divergentes = [c for c in PR.CAMPOS_DE_CONFIGURACAO if lidos[c] != int(esperado[c])]
            if ident != identificador or divergentes:
                raise FalhaNaPlaca('leitura de volta nao confere: id %r, campos %r'
                                   % (ident, divergentes))
            if any(contadores.values()):
                raise FalhaNaPlaca('contadores nao foram zerados: %r' % contadores)
            return {'parametros_lidos': lidos, 'contadores_lidos': contadores}
        raise FalhaNaPlaca('a placa nao confirmou a configuracao')

    # --- B-04 e B-06 ----------------------------------------------------------------------
    def carregar(self, identificador, blocos):
        for seq, quadro in enumerate(blocos):
            for tentativa in range(self.tentativas):
                if tentativa:
                    self.eventos['reenvios_de_bloco'] += 1
                self.transporte.enviar(quadro)
                tipo, carga = self._esperar({PR.BLOCO_RECEBIDO})
                if tipo is None:
                    continue
                ident, seq_lida, situacao = PR.ler_bloco_recebido(carga)
                if situacao == PR.BLOCO_OK and ident == identificador and seq_lida == seq:
                    break
                if situacao == PR.BLOCO_CRC_INVALIDO:
                    continue
                raise FalhaNaPlaca('bloco %d recusado pela placa (situacao %d)' % (seq, situacao))
            else:
                raise FalhaNaPlaca('bloco %d nao confirmado depois de %d tentativas'
                                   % (seq, self.tentativas))

    # --- B-10 ------------------------------------------------------------------------------
    def executar(self, identificador, n_blocos, n_amostras):
        self.transporte.enviar(PR.montar_quadro(
            PR.EXECUTAR, PR.carga_executar(identificador, n_blocos, n_amostras)))
        for tentativa in range(self.tentativas + 1):
            if tentativa:
                self.eventos['pedidos_de_resultado'] += 1
                self.transporte.enviar(PR.montar_quadro(PR.PEDIR_RESULTADO, PR.carga_so_id(identificador)))
            tipo, carga = self._esperar({PR.RESULTADO})
            if tipo != PR.RESULTADO:
                continue
            resultado = PR.ler_resultado(carga)
            if resultado['id'] != identificador:
                raise FalhaNaPlaca('resultado de outro ensaio: %r' % resultado['id'])
            self.transporte.enviar(PR.montar_quadro(PR.CONFIRMAR_RESULTADO, PR.carga_so_id(identificador)))
            return resultado
        return None

    # --- ensaio completo -----------------------------------------------------------------------
    def rodar(self, identificador, codigos_a, codigos_b, parametros):
        self._zerar_eventos()
        n = len(codigos_a)
        blocos = PR.blocos_do_ensaio(identificador, codigos_a, codigos_b)
        t0 = time.perf_counter()
        configuracao = self.configurar(identificador, parametros, n)
        t1 = time.perf_counter()
        self.carregar(identificador, blocos)
        t2 = time.perf_counter()
        resultado = self.executar(identificador, len(blocos), n)
        t3 = time.perf_counter()
        tempos = {'configuracao_s': t1 - t0, 'carga_s': t2 - t1,
                  'execucao_ate_resultado_s': t3 - t2}
        if getattr(self.transporte, 'sincrono', False):
            tempos = None   # sem enlace de verdade, o tempo medido nao significa nada
        return {
            'resultado': resultado,
            'configuracao': configuracao,
            'n_blocos': len(blocos),
            'bytes_de_amostras_enviados': sum(len(b) for b in blocos),
            'eventos_de_comunicacao': dict(self.eventos),
            'tempos_de_comunicacao': tempos,
        }

"""LEAKMAP - lado do computador na conversa com a placa (cenario B).

Conduz um ensaio do comeco ao fim, na via 1 (ensaio inteiro na memoria da
placa, ver dimensionamento.py):

  1. CONFIGURAR e conferir a leitura de volta: parametros iguais aos
     enviados e contadores zerados, obrigatoriamente, antes de cada
     execucao (B-07);
  2. carregar os blocos, um a um, reenviando o bloco cujo CRC a placa
     rejeitou (B-04, B-06);
  3. EXECUTAR e esperar o resultado; sem resposta, pedir de novo, e se a
     placa acusar CRC invalido, mandar EXECUTAR de novo; ao receber,
     confirmar. Sem resultado depois das tentativas, o ensaio sai marcado
     como sem resultado, nunca some (B-10). Com `periodo_ciclos`, a execucao
     e em tempo real: a placa entrega uma amostra a cada `periodo_ciclos`
     ciclos do proprio relogio;
  4. pedir TEMPOS: os ciclos de relogio que a execucao levou, contados pelo
     circuito. Uma placa que nao responde (projeto antigo) fica sem tempos;
  5. pedir SAUDE, com os limites do transmissor: o autoteste que a placa fez
     em cada canal durante a execucao. Sem resposta, o ensaio fica sem
     autoteste e o computador nao pergunta mais nesta placa.

Num enlace de verdade chegam respostas atrasadas: o recibo de um bloco que
ja foi confirmado, a resposta a uma mensagem reenviada. O computador as
descarta e conta, em vez de tomar uma delas pela resposta da mensagem atual.

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
        self.responde_saude = True
        self._zerar_eventos()

    def _zerar_eventos(self):
        self.eventos = {'reenvios_de_bloco': 0, 'reenvios_de_configuracao': 0,
                        'reenvios_de_execucao': 0, 'pedidos_de_resultado': 0,
                        'quadros_com_crc_invalido_recebidos': 0, 'respostas_fora_de_hora_descartadas': 0}

    # --- recepcao ------------------------------------------------------------------
    def _esperar(self, tipos):
        """Proximo quadro valido de um dos tipos. Os de outros tipos estao fora de hora."""
        fim = time.monotonic() + self.tempo_limite_s
        while True:
            if self.pendentes:
                situacao, tipo, carga = self.pendentes.pop(0)
                if situacao != 'ok':
                    self.eventos['quadros_com_crc_invalido_recebidos'] += 1
                elif tipo in tipos:
                    return tipo, carga
                else:
                    self.eventos['respostas_fora_de_hora_descartadas'] += 1
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
    def _recibo_do_bloco(self, identificador, seq):
        """Situacao do bloco `seq`, ou None sem resposta. Recibo atrasado de bloco anterior e descartado."""
        while True:
            tipo, carga = self._esperar({PR.BLOCO_RECEBIDO})
            if tipo is None:
                return None
            ident, seq_lida, situacao = PR.ler_bloco_recebido(carga)
            if situacao == PR.BLOCO_CRC_INVALIDO:
                return situacao
            if ident == identificador and seq_lida < seq:
                self.eventos['respostas_fora_de_hora_descartadas'] += 1
                continue
            if ident == identificador and seq_lida == seq:
                return situacao
            raise FalhaNaPlaca('recibo inesperado esperando o bloco %d: id %r, sequencia %d, situacao %d'
                               % (seq, ident, seq_lida, situacao))

    def carregar(self, identificador, blocos):
        for seq, quadro in enumerate(blocos):
            for tentativa in range(self.tentativas):
                if tentativa:
                    self.eventos['reenvios_de_bloco'] += 1
                self.transporte.enviar(quadro)
                situacao = self._recibo_do_bloco(identificador, seq)
                if situacao == PR.BLOCO_OK:
                    break
                if situacao in (None, PR.BLOCO_CRC_INVALIDO):
                    continue
                raise FalhaNaPlaca('bloco %d recusado pela placa (situacao %d)' % (seq, situacao))
            else:
                raise FalhaNaPlaca('bloco %d nao confirmado depois de %d tentativas'
                                   % (seq, self.tentativas))

    # --- B-10 ------------------------------------------------------------------------------
    def pedir_tempos(self, identificador=''):
        """TEMPOS da ultima execucao; None se a placa nao responder."""
        self.transporte.enviar(PR.montar_quadro(PR.PEDIR_TEMPOS, PR.carga_so_id(identificador)))
        tipo, carga = self._esperar({PR.TEMPOS})
        return PR.ler_tempos(carga) if tipo == PR.TEMPOS else None

    def pedir_saude(self, identificador, limites):
        """SAUDE da ultima execucao, julgada com `limites`; None se a placa nao responder."""
        self.transporte.enviar(PR.montar_quadro(PR.PEDIR_SAUDE, PR.carga_pedir_saude(identificador, limites)))
        tipo, carga = self._esperar({PR.SAUDE})
        return PR.ler_saude(carga) if tipo == PR.SAUDE else None

    def executar(self, identificador, n_blocos, n_amostras, periodo_ciclos=None):
        if periodo_ciclos:
            executar = PR.montar_quadro(PR.EXECUTAR_TEMPO_REAL, PR.carga_executar_tempo_real(
                identificador, n_blocos, n_amostras, periodo_ciclos))
        else:
            executar = PR.montar_quadro(PR.EXECUTAR, PR.carga_executar(identificador, n_blocos, n_amostras))
        pedir = PR.montar_quadro(PR.PEDIR_RESULTADO, PR.carga_so_id(identificador))
        self.transporte.enviar(executar)
        crc_acusado = False
        for tentativa in range(self.tentativas + 1):
            if tentativa:
                # CRC invalido acusado: o EXECUTAR pode nao ter chegado inteiro, e
                # executar de novo da o mesmo resultado; senao, so pede o resultado
                if crc_acusado:
                    self.eventos['reenvios_de_execucao'] += 1
                    self.transporte.enviar(executar)
                else:
                    self.eventos['pedidos_de_resultado'] += 1
                    self.transporte.enviar(pedir)
            crc_acusado = False
            while True:
                tipo, carga = self._esperar({PR.RESULTADO, PR.BLOCO_RECEBIDO})
                if tipo is None:
                    break
                if tipo == PR.BLOCO_RECEBIDO:
                    if PR.ler_bloco_recebido(carga)[2] == PR.BLOCO_CRC_INVALIDO:
                        crc_acusado = True
                    else:
                        self.eventos['respostas_fora_de_hora_descartadas'] += 1
                    continue
                resultado = PR.ler_resultado(carga)
                if resultado['id'] != identificador:
                    self.eventos['respostas_fora_de_hora_descartadas'] += 1
                    continue
                self.transporte.enviar(PR.montar_quadro(PR.CONFIRMAR_RESULTADO, PR.carga_so_id(identificador)))
                return resultado
        return None

    # --- ensaio completo -----------------------------------------------------------------------
    def rodar(self, identificador, codigos_a, codigos_b, parametros, periodo_ciclos=None,
              medir_tempos=True, limites_de_saude=None):
        self._zerar_eventos()
        n = len(codigos_a)
        blocos = PR.blocos_do_ensaio(identificador, codigos_a, codigos_b)
        t0 = time.perf_counter()
        configuracao = self.configurar(identificador, parametros, n)
        t1 = time.perf_counter()
        self.carregar(identificador, blocos)
        t2 = time.perf_counter()
        resultado = self.executar(identificador, len(blocos), n, periodo_ciclos)
        t3 = time.perf_counter()
        tempos_na_placa = None
        if medir_tempos and resultado is not None:
            tempos_na_placa = self.pedir_tempos(identificador)
        saude = None
        if limites_de_saude and self.responde_saude and resultado is not None:
            saude = self.pedir_saude(identificador, limites_de_saude)
            self.responde_saude = saude is not None
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
            'tempos_na_placa': tempos_na_placa,
            'saude_na_placa': saude,
        }

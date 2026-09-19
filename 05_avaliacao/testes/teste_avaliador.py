"""Testes da etapa A-17 e dos criterios que precisam da verdade do cenario.

Estes testes ficam do lado do avaliador, e nao em 04_detector/testes, porque
usam 03_ensaios/verdade_do_cenario. O detector nunca abre esse arquivo; quem
o abre e o avaliador, que e outro processo.

Ficam aqui tambem os criterios de A-12 e A-14 que so fazem sentido contra a
posicao real do evento:

  A-12  delta_t medido corresponde a diferenca de distancias dividida pela
        velocidade efetiva, dentro de uma amostra;
  A-14  variando a posicao do evento, a posicao estimada acompanha a real de
        forma monotona.

Roda com: python -m unittest discover -s 05_avaliacao/testes -p "teste_*.py"
"""
import json
import os
import subprocess
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import avaliador as AV  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
RESULTADO = os.path.join(RAIZ, '04_detector', 'resultados',
                         'leakmap_resultado_matriz_v1.json')
VERDADE = os.path.join(RAIZ, '03_ensaios', 'verdade_do_cenario',
                       'leakmap_verdade_matriz_v1.json')
PARAMETROS = os.path.join(RAIZ, '03_ensaios', 'parametros',
                          'leakmap_parametros_v1.json')
POSICAO_SENSOR_A_M = 40.0
POSICAO_SENSOR_B_M = 160.0


def ler(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


class Base(unittest.TestCase):

    def setUp(self):
        for caminho in (RESULTADO, VERDADE):
            if not os.path.exists(caminho):
                self.skipTest('%s ainda nao existe; rode o pipeline'
                              % os.path.basename(caminho))
        self.resultado = ler(RESULTADO)
        self.verdade = ler(VERDADE)
        self.por_id = {e['id']: e for e in self.verdade['ensaios']}
        self.registros = {r['id']: r for r in self.resultado['resultados']}
        self.c_real = float(ler(PARAMETROS)['velocidade_de_onda']
                            ['efetiva_ajustada_m_s'])


class A17Independencia(Base):

    def test_avaliador_nao_importa_modulo_do_detector(self):
        # nenhum modulo do detector pode estar carregado neste processo
        AV.conferir_independencia()

    def test_codigo_do_avaliador_nao_menciona_o_detector(self):
        caminho = os.path.join(RAIZ, '05_avaliacao', 'avaliador.py')
        with open(caminho, encoding='utf-8') as f:
            linhas = f.read().splitlines()
        for linha in linhas:
            limpa = linha.strip()
            if limpa.startswith('import ') or limpa.startswith('from '):
                for modulo in AV.MODULOS_DO_DETECTOR:
                    self.assertNotIn(modulo, limpa,
                                     'avaliador importa %s' % modulo)

    def test_roda_como_processo_separado_a_partir_dos_arquivos(self):
        """Criterio de conclusao de A-17, verificado de verdade: o avaliador e
        executado em outro processo, sem 04_detector no caminho de busca, e
        precisa reproduzir a mesma tabela."""
        destino = os.path.join(RAIZ, '05_avaliacao', 'testes',
                               '_saida_de_teste.json')
        ambiente = dict(os.environ)
        ambiente['PYTHONPATH'] = ''
        codigo = (
            'import sys, json; sys.path.insert(0, %r); import avaliador as A;'
            'A.main(%r, %r, %r)' % (os.path.join(RAIZ, '05_avaliacao'),
                                    RESULTADO, VERDADE, destino))
        processo = subprocess.run([sys.executable, '-c', codigo],
                                  capture_output=True, text=True,
                                  env=ambiente, cwd=RAIZ)
        self.assertEqual(processo.returncode, 0, processo.stderr)
        try:
            produzido = ler(destino)
            esperado = AV.avaliar(self.resultado, self.verdade)
            self.assertEqual(produzido['contagens'], esperado['contagens'])
            self.assertEqual(produzido['por_linha_da_matriz'],
                             esperado['por_linha_da_matriz'])
        finally:
            if os.path.exists(destino):
                os.remove(destino)

    def test_para_se_um_modulo_do_detector_estiver_carregado(self):
        marcador = object()
        sys.modules['detector'] = marcador
        try:
            with self.assertRaises(SystemExit):
                AV.conferir_independencia()
        finally:
            del sys.modules['detector']


class A17Metricas(Base):

    def setUp(self):
        super().setUp()
        self.relatorio = AV.avaliar(self.resultado, self.verdade)

    def test_todo_ensaio_tem_exatamente_um_registro(self):
        self.assertEqual(self.relatorio['n_ensaios'],
                         len(self.verdade['ensaios']))
        identificadores = [e['id'] for e in self.relatorio['ensaios']]
        self.assertEqual(len(set(identificadores)), len(identificadores))

    def test_erro_de_localizacao_bate_com_a_conta_direta(self):
        for item in self.relatorio['ensaios']:
            if item['erro_de_localizacao_m'] is None:
                continue
            with self.subTest(ensaio=item['id']):
                self.assertAlmostEqual(
                    item['erro_de_localizacao_m'],
                    abs(item['posicao_estimada_m'] - item['posicao_real_m']),
                    places=9)

    def test_taxa_de_falso_alarme_esta_registrada_com_denominador(self):
        fa = self.relatorio['falso_alarme']
        self.assertGreater(fa['ensaios_sem_evento'], 0)
        self.assertGreater(fa['oportunidades_de_decisao'], 0)
        self.assertIsNotNone(fa['taxa_por_ensaio'])
        self.assertIsNotNone(fa['taxa_por_oportunidade'])

    def test_contagens_somam_o_total(self):
        c = self.relatorio['contagens']
        soma = (c['deteccao'] + c['nao_deteccao'] + c['falso_alarme']
                + c['silencio_correto'] + c['falha_de_execucao'])
        self.assertEqual(soma, self.relatorio['n_ensaios'])

    def test_ensaio_sem_registro_e_recusado(self):
        resultado = json.loads(json.dumps(self.resultado))
        resultado['resultados'].pop()
        with self.assertRaises(SystemExit):
            AV.avaliar(resultado, self.verdade)

    def test_registro_repetido_e_recusado(self):
        resultado = json.loads(json.dumps(self.resultado))
        resultado['resultados'].append(resultado['resultados'][0])
        with self.assertRaises(SystemExit):
            AV.avaliar(resultado, self.verdade)


class A12ContraAPosicaoReal(Base):
    """delta_t medido contra a diferenca de distancias dividida por c."""

    def test_delta_t_bate_dentro_de_uma_amostra(self):
        for identificador, verd in self.por_id.items():
            if not verd['tem_evento']:
                continue
            # o eixo de velocidade desviada muda o c declarado, nao o sinal;
            # a conferencia de A-12 e sobre o tempo medido, entao usa o c real
            registro = self.registros[identificador]
            if registro.get('delta_t_s') is None:
                self.fail('ensaio %s nao produziu delta_t' % identificador)
            pos = float(verd['posicao_real_m'])
            esperado = ((abs(pos - POSICAO_SENSOR_A_M)
                         - abs(POSICAO_SENSOR_B_M - pos)) / self.c_real)
            ts = float(registro['periodo_de_amostragem_s'])
            with self.subTest(ensaio=identificador,
                              linha=verd['linha_da_matriz']):
                self.assertLessEqual(
                    abs(registro['delta_t_s'] - esperado), ts,
                    'delta_t medido %.6e s, esperado %.6e s, diferenca de '
                    'mais de uma amostra (%.6e s)'
                    % (registro['delta_t_s'], esperado, ts))


class A14ContraAPosicaoReal(Base):
    """A posicao estimada acompanha a real de forma monotona."""

    def test_posicao_estimada_e_monotona_em_cada_linha(self):
        linhas = {}
        for identificador, verd in self.por_id.items():
            if not verd['tem_evento']:
                continue
            registro = self.registros[identificador]
            if registro.get('posicao_estimada_m') is None:
                continue
            linhas.setdefault(verd['linha_da_matriz'], []).append(
                (float(verd['posicao_real_m']),
                 float(registro['posicao_estimada_m'])))

        self.assertTrue(linhas)
        for nome, pares in sorted(linhas.items()):
            pares.sort()
            estimadas = [p[1] for p in pares]
            with self.subTest(linha=nome):
                self.assertEqual(len(pares), 5)
                self.assertTrue(np.all(np.diff(estimadas) > 0),
                                'posicao estimada nao monotona em %s: %r'
                                % (nome, estimadas))

    def test_linha_sem_ruido_e_c_casada_reproduz_o_baseline_v1(self):
        """Conferencia de regressao: com todos os efeitos de sensor desligados
        e c igual ao efetivo, o resultado tem de repetir o v1, que deu erro
        zero nos cinco eventos."""
        achou = 0
        for identificador, verd in self.por_id.items():
            if verd['linha_da_matriz'] != 'evento/sem_ruido/casada':
                continue
            achou += 1
            registro = self.registros[identificador]
            erro = abs(float(registro['posicao_estimada_m'])
                       - float(verd['posicao_real_m']))
            with self.subTest(ensaio=identificador):
                self.assertLess(erro, 1e-9,
                                'erro %.6g m na conferencia de regressao'
                                % erro)
        self.assertEqual(achou, 5)


if __name__ == '__main__':
    unittest.main()

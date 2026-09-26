/*
 * LEAKMAP Edge - adaptacao do detector para o front-end.
 *
 * ESTE ARQUIVO NAO E A IMPLEMENTACAO DE REFERENCIA. A referencia e o Python
 * de 04_detector:
 *
 *   modelo_sensor.py  ->  modeloSensor   (A-09)
 *   amostragem.py     ->  amostragem     (A-10)
 *   detector.py       ->  detector       (A-11 a A-15)
 *   posicao.py        ->  posicao        (A-14)
 *   matriz.py         ->  matriz         (configuracoes de sensor da matriz)
 *
 * Cada funcao aqui repete a funcao Python de mesmo nome, inclusive a ordem
 * das operacoes, para que o resultado em ponto flutuante seja o mesmo. O teste
 * web/testes/teste_paridade.js confere isso contra o gabarito que o proprio
 * Python grava em web/gabarito/leakmap_gabarito_js_v1.json.
 *
 * Toda mudanca de algoritmo comeca no Python. Depois: rodar
 * web/gerar_gabarito.py, ajustar este arquivo e rodar o teste de paridade ate
 * passar. Este arquivo nunca gera gabarito nem numero do repositorio.
 *
 * Unica diferenca deliberada: o sorteio do ruido. O gerador do NumPy nao tem
 * equivalente em JavaScript. Os efeitos `ruido` e `erro_de_sincronizacao`
 * recebem os sorteios gaussianos de uma `fonte`: nos testes, os mesmos
 * sorteios que o Python usou, gravados no gabarito; no navegador, um gerador
 * proprio com a mesma estatistica.
 */
(function (raiz, fabrica) {
  "use strict";
  if (typeof module === "object" && module.exports) {
    module.exports = fabrica();
  } else {
    raiz.LEAKMAP = fabrica();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* utilitarios que reproduzem o comportamento do NumPy                 */
  /* ------------------------------------------------------------------ */

  function copiar(x) { return Array.prototype.slice.call(x); }

  /* np.interp com grade xp = 0, 1, ..., n-1 (e a unica usada pelo modelo).
   * Segue o algoritmo de numpy/core/src/multiarray/compiled_base.c. */
  function interpGrade(xv, fp, esquerda, direita) {
    var n = fp.length, saida = new Array(xv.length);
    var lval = (esquerda === undefined) ? fp[0] : esquerda;
    var rval = (direita === undefined) ? fp[n - 1] : direita;
    for (var i = 0; i < xv.length; i++) {
      var x = xv[i];
      if (x !== x) { saida[i] = x; continue; }
      if (x < 0) { saida[i] = lval; continue; }
      if (x > n - 1) { saida[i] = rval; continue; }
      var j = Math.floor(x);
      if (j === n - 1) { saida[i] = fp[j]; continue; }
      if (j === x) { saida[i] = fp[j]; continue; }
      var inclinacao = (fp[j + 1] - fp[j]) / ((j + 1) - j);
      var r = inclinacao * (x - j) + fp[j];
      if (r !== r) {
        r = inclinacao * (x - (j + 1)) + fp[j + 1];
        if (r !== r && fp[j] === fp[j + 1]) { r = fp[j]; }
      }
      saida[i] = r;
    }
    return saida;
  }

  /* np.rint: arredonda para o inteiro mais proximo, empate para o par. */
  function rint(v) {
    var piso = Math.floor(v), resto = v - piso;
    if (resto > 0.5) { return piso + 1; }
    if (resto < 0.5) { return piso; }
    return (piso % 2 === 0) ? piso : piso + 1;
  }

  function mediana(v) {
    var s = copiar(v).sort(function (a, b) { return a - b; });
    var m = s.length >> 1;
    return (s.length % 2) ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  /* formato '%.6e' do Python: expoente com sinal e pelo menos dois digitos */
  function exp6(v) {
    var s = v.toExponential(6), k = s.indexOf("e");
    var sinal = s.charAt(k + 1), digitos = s.slice(k + 2);
    if (digitos.length < 2) { digitos = "0" + digitos; }
    return s.slice(0, k) + "e" + sinal + digitos;
  }

  function mesclar(destino, origem) {
    for (var k in origem) {
      if (Object.prototype.hasOwnProperty.call(origem, k)) { destino[k] = origem[k]; }
    }
    return destino;
  }

  /* ------------------------------------------------------------------ */
  /* A-09  modelo_sensor.py                                              */
  /* ------------------------------------------------------------------ */

  var ORDEM_DOS_EFEITOS = ["banda", "amortecimento", "atualizacao", "atraso_comum", "diferenca_de_atraso",
    "erro_de_sincronizacao", "offset", "ruido", "saturacao", "quantizacao"];

  function configNeutra() {
    return {
      banda: { ligado: false, corte_hz: 400.0, ordem: 1 },
      amortecimento: { ligado: false, constante_de_tempo_s: 0.0 },
      atualizacao: { ligado: false, periodo_s: 0.0, fase_A_s: null, fase_B_s: null, semente: 0 },
      atraso_comum: { ligado: false, atraso_s: 0.0 },
      diferenca_de_atraso: { ligado: false, atraso_s: 0.0 },
      erro_de_sincronizacao: { ligado: false, jitter_s: 0.0, semente: 0 },
      offset: { ligado: false, offset_A_m: 0.0, offset_B_m: 0.0 },
      ruido: { ligado: false, desvio_padrao_m: 0.0, semente: 0 },
      saturacao: { ligado: false, minimo_m: 0.0, maximo_m: 100.0 },
      quantizacao: { ligado: false, bits: 16, fundo_de_escala_min_m: 0.0,
        fundo_de_escala_max_m: 100.0 }
    };
  }

  function degrauDeQuantizacao(bits, vmin, vmax) {
    return (vmax - vmin) / (Math.pow(2, bits) - 1);
  }

  function resolucaoDeclaradaM(cfg) {
    var q = cfg.quantizacao || {};
    if (!q.ligado) { return null; }
    return degrauDeQuantizacao(q.bits, q.fundo_de_escala_min_m, q.fundo_de_escala_max_m);
  }

  function filtrarPassaBaixas(x, corteHz, ts, ordem) {
    var tau = 1.0 / (2.0 * Math.PI * corteHz);
    var alfa = ts / (tau + ts);
    var y = copiar(x);
    for (var o = 0; o < (ordem || 1); o++) {
      var saida = new Array(y.length), acc = y[0];
      for (var n = 0; n < y.length; n++) {
        acc += alfa * (y[n] - acc);
        saida[n] = acc;
      }
      y = saida;
    }
    return y;
  }

  function amortecer(x, constanteDeTempoS, ts) {
    if (constanteDeTempoS <= 0.0) { return copiar(x); }
    return filtrarPassaBaixas(x, 1.0 / (2.0 * Math.PI * constanteDeTempoS), ts, 1);
  }

  /* Saida que so muda nos instantes fase + m * periodo e segura o valor. */
  function atualizar(x, periodoS, faseS, ts) {
    if (periodoS <= ts) { return copiar(x); }
    var y = new Array(x.length);
    for (var n = 0; n < x.length; n++) {
      var m = Math.floor((n * ts - faseS) / periodoS + 1e-9);
      var indice = m < 0 ? 0 : Math.floor((faseS + m * periodoS) / ts + 1e-9);
      y[n] = x[Math.min(Math.max(indice, 0), x.length - 1)];
    }
    return y;
  }

  function atrasar(x, atrasoS, ts) {
    var d = atrasoS / ts;
    if (d === 0.0) { return copiar(x); }
    if (d < 0.0) { throw new Error("atraso negativo nao e representavel: " + atrasoS); }
    var pontos = new Array(x.length);
    for (var i = 0; i < x.length; i++) { pontos[i] = i - d; }
    return interpGrade(pontos, x, x[0]);
  }

  function aplicarJitter(x, jitterS, ts, sorteios) {
    if (jitterS === 0.0) { return copiar(x); }
    var escala = jitterS / ts, pontos = new Array(x.length);
    for (var i = 0; i < x.length; i++) { pontos[i] = i + (0.0 + escala * sorteios[i]); }
    return interpGrade(pontos, x, x[0], x[x.length - 1]);
  }

  function saturar(x, minimo, maximo) {
    return x.map(function (v) { return Math.min(Math.max(v, minimo), maximo); });
  }

  function quantizar(x, bits, vmin, vmax) {
    var passo = degrauDeQuantizacao(bits, vmin, vmax), topo = Math.pow(2, bits) - 1;
    return x.map(function (v) {
      var codigo = rint((v - vmin) / passo);
      codigo = Math.min(Math.max(codigo, 0), topo);
      return vmin + codigo * passo;
    });
  }

  /* `fonte.normais(chave, n)` devolve n sorteios gaussianos padrao.
   * Chaves: ruido_A, ruido_B, jitter_A, jitter_B. */
  function aplicarModelo(canalA, canalB, ts, cfg, fonte) {
    var a = copiar(canalA), b = copiar(canalB), registro = [];
    ORDEM_DOS_EFEITOS.forEach(function (nome) {
      var par = cfg[nome];
      if (!par || !par.ligado) { return; }
      if (nome === "banda") {
        a = filtrarPassaBaixas(a, par.corte_hz, ts, par.ordem || 1);
        b = filtrarPassaBaixas(b, par.corte_hz, ts, par.ordem || 1);
      } else if (nome === "amortecimento") {
        a = amortecer(a, par.constante_de_tempo_s, ts);
        b = amortecer(b, par.constante_de_tempo_s, ts);
      } else if (nome === "atualizacao") {
        /* fase sem valor declarado: sorteada pela fonte, se ela souber sortear
         * uniforme; o Python sorteia com o NumPy, que o navegador nao reproduz */
        var sorteio = fonte && fonte.uniformes ? fonte.uniformes("fase", 2) : [0.0, 0.0];
        var faseA = par.fase_A_s === null || par.fase_A_s === undefined ? sorteio[0] * par.periodo_s : par.fase_A_s;
        var faseB = par.fase_B_s === null || par.fase_B_s === undefined ? sorteio[1] * par.periodo_s : par.fase_B_s;
        a = atualizar(a, par.periodo_s, faseA, ts);
        b = atualizar(b, par.periodo_s, faseB, ts);
        par = mesclar(mesclar({}, par), { fase_A_s: faseA, fase_B_s: faseB });
      } else if (nome === "atraso_comum") {
        a = atrasar(a, par.atraso_s, ts);
        b = atrasar(b, par.atraso_s, ts);
      } else if (nome === "diferenca_de_atraso") {
        b = atrasar(b, par.atraso_s, ts);
      } else if (nome === "erro_de_sincronizacao") {
        if (par.jitter_s !== 0.0) {
          a = aplicarJitter(a, par.jitter_s, ts, fonte.normais("jitter_A", a.length));
          b = aplicarJitter(b, par.jitter_s, ts, fonte.normais("jitter_B", b.length));
        }
      } else if (nome === "offset") {
        var oa = par.offset_A_m || 0.0, ob = par.offset_B_m || 0.0;
        a = a.map(function (v) { return v + oa; });
        b = b.map(function (v) { return v + ob; });
      } else if (nome === "ruido") {
        var sigma = par.desvio_padrao_m;
        var za = fonte.normais("ruido_A", a.length), zb = fonte.normais("ruido_B", b.length);
        a = a.map(function (v, i) { return v + (0.0 + sigma * za[i]); });
        b = b.map(function (v, i) { return v + (0.0 + sigma * zb[i]); });
      } else if (nome === "saturacao") {
        a = saturar(a, par.minimo_m, par.maximo_m);
        b = saturar(b, par.minimo_m, par.maximo_m);
      } else if (nome === "quantizacao") {
        a = quantizar(a, par.bits, par.fundo_de_escala_min_m, par.fundo_de_escala_max_m);
        b = quantizar(b, par.bits, par.fundo_de_escala_min_m, par.fundo_de_escala_max_m);
      }
      var copia = {};
      for (var k in par) { if (k !== "ligado") { copia[k] = par[k]; } }
      registro.push({ efeito: nome, parametros: copia });
    });
    return { a: a, b: b, registro: registro };
  }

  /* Gerador do navegador: mulberry32, normal por Box-Muller. Nao reproduz o
   * NumPy; reproduz a estatistica (media zero, desvio-padrao pedido). */
  function fonteAleatoria(semente) {
    function mulberry32(s) {
      return function () {
        s = (s + 0x6d2b79f5) | 0;
        var t = Math.imul(s ^ (s >>> 15), 1 | s);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((((t ^ (t >>> 14)) >>> 0) + 0.5) / 4294967296);
      };
    }
    var desvios = { ruido_A: 11, ruido_B: 23, jitter_A: 37, jitter_B: 53 };
    return {
      normais: function (chave, n) {
        var u = mulberry32(((semente | 0) * 7919 + (desvios[chave] || 97)) | 0);
        var saida = new Array(n);
        for (var i = 0; i < n; i += 2) {
          var r = Math.sqrt(-2.0 * Math.log(u())), th = 2.0 * Math.PI * u();
          saida[i] = r * Math.cos(th);
          if (i + 1 < n) { saida[i + 1] = r * Math.sin(th); }
        }
        return saida;
      }
    };
  }

  /* fonte que devolve sorteios prontos (usada pelos testes de paridade) */
  function fonteGravada(sorteios) {
    return {
      normais: function (chave, n) {
        var z = sorteios[chave];
        if (!z || z.length !== n) {
          throw new Error("sorteio " + chave + " ausente ou de tamanho errado");
        }
        return z;
      }
    };
  }

  /* ------------------------------------------------------------------ */
  /* matriz.py                                                           */
  /* ------------------------------------------------------------------ */

  var ESCALA_MIN_M = 0.0, ESCALA_MAX_M = 100.0;
  var NIVEIS_DE_RUIDO = ["sem_ruido", "baixo", "alto"];

  function configMatriz(ruido, bits, corte, atrasoComum, skew, jitter, offA, offB, semente) {
    var cfg = configNeutra();
    mesclar(cfg.banda, { ligado: true, corte_hz: corte, ordem: 2 });
    mesclar(cfg.atraso_comum, { ligado: true, atraso_s: atrasoComum });
    mesclar(cfg.diferenca_de_atraso, { ligado: true, atraso_s: skew });
    mesclar(cfg.erro_de_sincronizacao, { ligado: true, jitter_s: jitter, semente: semente });
    mesclar(cfg.offset, { ligado: true, offset_A_m: offA, offset_B_m: offB });
    mesclar(cfg.ruido, { ligado: true, desvio_padrao_m: ruido, semente: semente + 1000 });
    mesclar(cfg.saturacao, { ligado: true, minimo_m: ESCALA_MIN_M, maximo_m: ESCALA_MAX_M });
    mesclar(cfg.quantizacao, { ligado: true, bits: bits, fundo_de_escala_min_m: ESCALA_MIN_M,
      fundo_de_escala_max_m: ESCALA_MAX_M });
    return cfg;
  }

  function configuracoesDeSensor(semente) {
    semente = semente || 0;
    return {
      sem_ruido: configNeutra(),
      baixo: configMatriz(0.02, 16, 800.0, 1.0e-3, 1.0e-4, 5.0e-6, 0.02, -0.03, semente),
      alto: configMatriz(0.20, 12, 250.0, 2.0e-3, 4.0e-4, 3.0e-5, 0.10, -0.15, semente + 500)
    };
  }

  function velocidades(cEfetiva) {
    return {
      casada: { c_m_s: cEfetiva, incerteza_m_s: 0.0, desvio_relativo: 0.0 },
      desviada: { c_m_s: cEfetiva * 1.02, incerteza_m_s: cEfetiva * 0.02, desvio_relativo: 0.02 }
    };
  }

  function sinalSemEvento(h0A, h0B, nPontos, ts, t0) {
    var t = new Array(nPontos), a = new Array(nPontos), b = new Array(nPontos);
    for (var i = 0; i < nPontos; i++) { t[i] = (t0 || 0.0) + i * ts; a[i] = h0A; b[i] = h0B; }
    return { t: t, a: a, b: b };
  }

  /* ------------------------------------------------------------------ */
  /* A-10  amostragem.py                                                 */
  /* ------------------------------------------------------------------ */

  function escolherFrequencia(c, tsSolucionador, requisito, fatorSeguranca) {
    requisito = (requisito === undefined) ? 0.5 : requisito;
    fatorSeguranca = (fatorSeguranca === undefined) ? 2.0 : fatorSeguranca;
    var fsSol = 1.0 / tsSolucionador;
    var resolucaoProjeto = requisito / fatorSeguranca;
    var fsMinima = c / (2.0 * resolucaoProjeto);
    var fator = Math.floor(fsSol / fsMinima);
    if (fator < 1) { throw new Error("nao ha decimacao possivel"); }
    var fs = fsSol / fator, ts = 1.0 / fs;
    return {
      requisito_de_resolucao_m: requisito,
      fator_de_seguranca: fatorSeguranca,
      resolucao_de_projeto_m: resolucaoProjeto,
      velocidade_de_onda_usada_m_s: c,
      frequencia_minima_hz: fsMinima,
      frequencia_do_solucionador_hz: fsSol,
      fator_de_decimacao: fator,
      frequencia_de_amostragem_hz: fs,
      periodo_de_amostragem_s: ts,
      resolucao_de_posicao_m: c * ts / 2.0
    };
  }

  function mediaMovel(x, fator) {
    if (fator <= 1) { return copiar(x); }
    var ext = new Array(fator - 1 + x.length), i, k;
    for (i = 0; i < fator - 1; i++) { ext[i] = x[0]; }
    for (i = 0; i < x.length; i++) { ext[fator - 1 + i] = x[i]; }
    var peso = 1 / fator, saida = new Array(x.length);
    for (i = 0; i < x.length; i++) {
      var soma = 0.0;
      for (k = 0; k < fator; k++) { soma += ext[i + k] * peso; }
      saida[i] = soma;
    }
    return saida;
  }

  function decimar(x, fator, antisserrilhamento) {
    if (fator <= 1) { return copiar(x); }
    var y = (antisserrilhamento === false) ? x : mediaMovel(x, fator), saida = [];
    for (var i = 0; i < y.length; i += fator) { saida.push(y[i]); }
    return saida;
  }

  function montarEnsaio(id, tempo, canalA, canalB, parametros, efeitos, escolha) {
    var fator = escolha.fator_de_decimacao, t = [];
    for (var i = 0; i < tempo.length; i += fator) { t.push(tempo[i]); }
    var a = decimar(canalA, fator), b = decimar(canalB, fator);
    var n = Math.min(t.length, a.length, b.length), indice = [];
    for (i = 0; i < n; i++) { indice.push(i); }
    return {
      id: id, n_pontos: n, indice: indice,
      tempo_s: t.slice(0, n), canal_A_carga_m: a.slice(0, n), canal_B_carga_m: b.slice(0, n),
      parametros_do_detector: parametros, efeitos_de_sensor_aplicados: efeitos
    };
  }

  /* ------------------------------------------------------------------ */
  /* A-14  posicao.py                                                    */
  /* ------------------------------------------------------------------ */

  function limiteFisicoDeDeltaT(l, c) { return l / c; }

  function posicaoAPartirDoSensorA(l, c, dt) { return (l + c * dt) / 2.0; }

  function incertezaDePosicaoM(c, dt, uDt, uC) {
    var termoTempo = c * (uDt || 0.0) / 2.0;
    var termoC = dt * (uC || 0.0) / 2.0;
    return Math.hypot(termoTempo, termoC);
  }

  function localizar(l, c, dt, posA, uDt, uC) {
    var bruto = posicaoAPartirDoSensorA(l, c, dt);
    var limitado = Math.min(Math.max(bruto, 0.0), l);
    return {
      posicao_estimada_rel_sensor_A_m: limitado,
      posicao_estimada_m: posA + limitado,
      posicao_sem_limite_rel_sensor_A_m: bruto,
      posicao_limitada_a_faixa: limitado !== bruto,
      incerteza_de_posicao_m: incertezaDePosicaoM(c, dt, uDt, uC),
      velocidade_de_onda_usada_m_s: c,
      origem_da_velocidade_de_onda: "parametros_do_detector do pacote do ensaio (A-10)"
    };
  }

  /* ------------------------------------------------------------------ */
  /* A-11 a A-15  detector.py                                            */
  /* ------------------------------------------------------------------ */

  var CLASSE_LOCALIZADO = "localizado";
  var CLASSE_SEM_LOCALIZACAO = "detectado_sem_localizacao";
  var CLASSE_SEM_DETECCAO = "sem_deteccao";
  var CLASSE_FALHA = "falha_execucao";
  var CLASSE_MANOBRA = "manobra";
  var CLASSE_FORA_DO_TRECHO = "fora_do_trecho";
  var POLARIDADE_QUEDA = "queda";
  var POLARIDADE_ALTA = "alta";

  function calibracaoPadrao() {
    return {
      n_curta: 6, n_guarda: 3, n_longa: 30,
      corte_passa_altas_hz: 20.0, limiar_de_razao: 12.0,
      piso_de_amplitude_m: 0.01, fator_sobre_a_resolucao: 1.0,
      k_faixa_de_ruido: 3.0
    };
  }

  function pisoDeAmplitude(cal, resolucao) {
    var piso = cal.piso_de_amplitude_m;
    if (resolucao) { piso = Math.max(piso, cal.fator_sobre_a_resolucao * resolucao); }
    return piso;
  }

  function pisoDeEnergia(cal, resolucao) {
    var p = pisoDeAmplitude(cal, resolucao);
    return (p * p) / 12.0;
  }

  function passaAltas(x, corteHz, ts) {
    var tau = 1.0 / (2.0 * Math.PI * corteHz), a = tau / (tau + ts);
    var y = new Array(x.length);
    y[0] = 0.0;
    for (var n = 1; n < x.length; n++) { y[n] = a * (y[n - 1] + x[n] - x[n - 1]); }
    return y;
  }

  function energiaEmJanela(y, nJanela) {
    var acumulado = new Array(y.length + 1), saida = new Array(y.length), i;
    acumulado[0] = 0.0;
    for (i = 0; i < y.length; i++) {
      var q = y[i] * y[i];
      acumulado[i + 1] = (i === 0) ? q : acumulado[i] + q;
    }
    for (i = 0; i < y.length; i++) {
      saida[i] = (i >= nJanela - 1) ? (acumulado[i + 1] - acumulado[i - nJanela + 1]) / nJanela : NaN;
    }
    return saida;
  }

  function razaoDeEnergia(y, cal, pisoEnergia) {
    var eCurta = energiaEmJanela(y, cal.n_curta);
    var eLongaBruta = energiaEmJanela(y, cal.n_longa);
    var recuo = cal.n_curta + cal.n_guarda, eLonga = new Array(y.length), i;
    for (i = 0; i < y.length; i++) { eLonga[i] = (i >= recuo) ? eLongaBruta[i - recuo] : NaN; }
    var razao = new Array(y.length);
    for (i = 0; i < y.length; i++) { razao[i] = eCurta[i] / Math.max(eLonga[i], pisoEnergia); }
    return { razao: razao, eCurta: eCurta, eLonga: eLonga };
  }

  function detectarCanal(sinal, ts, cal, resolucao) {
    var y = passaAltas(sinal, cal.corte_passa_altas_hz, ts);
    var piso = pisoDeAmplitude(cal, resolucao);
    var pisoE = pisoDeEnergia(cal, resolucao);
    var r = razaoDeEnergia(y, cal, pisoE);
    var primeiro = -1, validos = 0, maxima = -Infinity;
    for (var i = 0; i < y.length; i++) {
      var rms = Math.sqrt(r.eCurta[i]);
      var valido = isFinite(r.razao[i]) && isFinite(rms);
      if (!valido) { continue; }
      validos++;
      if (r.razao[i] > maxima) { maxima = r.razao[i]; }
      if (primeiro < 0 && r.razao[i] >= cal.limiar_de_razao && rms >= piso) { primeiro = i; }
    }
    var det = {
      detectado: primeiro >= 0,
      piso_de_amplitude_usado_m: piso,
      piso_de_energia_usado_m2: pisoE,
      n_oportunidades_de_decisao: validos,
      indice_de_cruzamento: primeiro >= 0 ? primeiro : null,
      razao_no_cruzamento: primeiro >= 0 ? r.razao[primeiro] : null,
      razao_maxima: validos ? maxima : null,
      rms_curta_no_cruzamento: primeiro >= 0 ? Math.sqrt(r.eCurta[primeiro]) : null
    };
    return { det: det, y: y, razao: r.razao, eLonga: r.eLonga };
  }

  function marcarChegada(y, eLonga, iCruz, tempo, ts, cal) {
    var nc = cal.n_curta, ng = cal.n_guarda;
    var limite = Math.max(0, iCruz - (nc + ng));
    var sigmaRef = Math.sqrt(eLonga[iCruz]);
    var faixa = cal.k_faixa_de_ruido * sigmaRef;
    var i = iCruz;
    while (i > limite && Math.abs(y[i - 1]) > faixa) { i--; }
    var truncado = (i === limite && Math.abs(y[i]) > faixa && i > 0 && Math.abs(y[i - 1]) > faixa);

    var inclinacao = 0.0;
    if (iCruz - i + 1 > 1) {
      var maior = 0.0;
      for (var k = i; k < iCruz; k++) {
        var d = Math.abs(y[k + 1] - y[k]);
        if (d > maior) { maior = d; }
      }
      inclinacao = maior / ts;
    }
    var uQ = ts / Math.sqrt(12.0);
    var uR = inclinacao > 0.0 ? sigmaRef / inclinacao : ts;
    var uRet = truncado ? (nc + ng) * ts : ts;
    var incerteza = Math.sqrt(uQ * uQ + uR * uR + uRet * uRet);
    /* polaridade da frente: soma do passa-altas da chegada ao cruzamento */
    var variacao = 0.0;
    for (var q = i; q <= iCruz; q++) { variacao += y[q]; }
    return {
      polaridade: variacao < 0.0 ? POLARIDADE_QUEDA : POLARIDADE_ALTA,
      variacao_na_frente_m: variacao,
      indice_de_chegada: i,
      tempo_de_chegada_s: tempo[i],
      amostras_retrocedidas: iCruz - i,
      retrocesso_truncado: truncado,
      sigma_de_referencia_m: sigmaRef,
      faixa_de_ruido_m: faixa,
      inclinacao_m_por_s: inclinacao,
      incerteza_s: incerteza,
      componentes_da_incerteza_s: {
        quantizacao_temporal: uQ,
        ruido_sobre_inclinacao: uR,
        ambiguidade_do_retrocesso: uRet
      }
    };
  }

  function canalSaturado(sinal, escala) {
    if (!escala || Object.keys(escala).length === 0) { return false; }
    var minimo = escala.minimo_m, maximo = escala.maximo_m;
    var passo = escala.resolucao_declarada_m || 0.0, eps = Math.max(passo, 1e-12);
    for (var i = 0; i < sinal.length; i++) {
      if (minimo !== null && minimo !== undefined && sinal[i] <= minimo + eps) { return true; }
      if (maximo !== null && maximo !== undefined && sinal[i] >= maximo - eps) { return true; }
    }
    return false;
  }

  function decidirEvidencia(detA, detB, satA, satB, deltaT, l, c, ts, cal) {
    if (!detA.detectado && !detB.detectado) { return [false, "nenhum canal declarou evento"]; }
    if (!detA.detectado) { return [false, "canal A nao declarou evento"]; }
    if (!detB.detectado) { return [false, "canal B nao declarou evento"]; }
    if (satA && satB) { return [false, "os dois canais encostaram no fundo de escala"]; }
    if (satA) { return [false, "canal A encostou no fundo de escala"]; }
    if (satB) { return [false, "canal B encostou no fundo de escala"]; }
    if (detA.razao_no_cruzamento < cal.limiar_de_razao) {
      return [false, "razao de energia do canal A abaixo do limiar"];
    }
    if (detB.razao_no_cruzamento < cal.limiar_de_razao) {
      return [false, "razao de energia do canal B abaixo do limiar"];
    }
    var limite = limiteFisicoDeDeltaT(l, c);
    if (Math.abs(deltaT) > limite + ts / 2.0) {
      return [false, "diferenca temporal fora da faixa fisica: |" + exp6(deltaT) +
        "| s > L/c = " + exp6(limite) + " s"];
    }
    return [true, "evidencia suficiente"];
  }

  /* Classificacao fisica (secao 5.4 do projeto), igual a de detector.py. */
  function classificarEvento(detA, detB, deltaT, l, c, ts) {
    var pa = detA.polaridade, pb = detB.polaridade;
    if (pa === POLARIDADE_ALTA && pb === POLARIDADE_ALTA) {
      return [CLASSE_MANOBRA, "onda de alta nos dois canais: manobra, nao vazamento", null];
    }
    if (pa !== pb) {
      return [CLASSE_MANOBRA, "polaridades opostas (A " + pa + ", B " + pb + "): manobra entre os sensores", null];
    }
    var limite = limiteFisicoDeDeltaT(l, c);
    if (limite - Math.abs(deltaT) <= ts) {
      var lado = deltaT < 0 ? "A" : "B";
      return [CLASSE_FORA_DO_TRECHO, "diferenca temporal no limite fisico: origem no sensor " + lado +
        " ou fora do trecho, do lado dele", lado];
    }
    return [null, null, null];
  }

  function classificarSemLocalizacao(marcaA, marcaB, deltaT, l, c, ts, uDeltaT) {
    var marcas = [marcaA, marcaB].filter(function (m) { return m !== null; });
    if (marcas.length && marcas.every(function (m) { return m.polaridade === POLARIDADE_ALTA; })) {
      return [CLASSE_MANOBRA, "onda de alta: manobra, nao vazamento", null];
    }
    var tolerancia = Math.max(2.0 * ts, 3.0 * (uDeltaT || 0.0));
    if (marcaA && marcaB && deltaT !== null && marcaA.polaridade === POLARIDADE_QUEDA &&
        marcaB.polaridade === POLARIDADE_QUEDA) {
      var excesso = Math.abs(deltaT) - limiteFisicoDeDeltaT(l, c);
      if (excesso > 0.0 && excesso <= tolerancia) {
        var lado = deltaT < 0 ? "A" : "B";
        return [CLASSE_FORA_DO_TRECHO, "diferenca temporal alem do limite fisico: origem fora do trecho, " +
          "do lado do sensor " + lado, lado];
      }
    }
    return [null, null, null];
  }

  /* Recebe apenas o ensaio (sinais e parametros conhecidos pelo detector) e
   * a escala do instrumento. Nunca recebe a posicao real do vazamento. */
  function processarEnsaio(ensaio, escala, cal, classificar) {
    if (classificar === undefined) { classificar = true; }
    cal = mesclar({}, cal || calibracaoPadrao());
    var registro = { id: ensaio.id, calibracao: cal };
    try {
      var par = ensaio.parametros_do_detector;
      var l = par.distancia_entre_sensores_L_m;
      var c = par.velocidade_de_onda_m_s;
      if (typeof c !== "number") { throw new Error("velocidade_de_onda_m_s ausente"); }
      var uC = par.incerteza_de_velocidade_de_onda_m_s || 0.0;
      var posA = par.posicao_sensor_A_m;
      registro.parametros_do_detector = par;

      var t = ensaio.tempo_s, diffs = [];
      for (var i = 1; i < t.length; i++) { diffs.push(t[i] - t[i - 1]); }
      var ts = mediana(diffs);
      var resolucao = (escala || {}).resolucao_declarada_m;
      if (resolucao === undefined) { resolucao = null; }

      var ra = detectarCanal(ensaio.canal_A_carga_m, ts, cal, resolucao);
      var rb = detectarCanal(ensaio.canal_B_carga_m, ts, cal, resolucao);
      var detA = ra.det, detB = rb.det;
      var satA = canalSaturado(ensaio.canal_A_carga_m, escala);
      var satB = canalSaturado(ensaio.canal_B_carga_m, escala);
      detA.saturado = satA;
      detB.saturado = satB;

      var marcaA = null, marcaB = null;
      if (detA.detectado) {
        marcaA = marcarChegada(ra.y, ra.eLonga, detA.indice_de_cruzamento, t, ts, cal);
        mesclar(detA, marcaA);
      }
      if (detB.detectado) {
        marcaB = marcarChegada(rb.y, rb.eLonga, detB.indice_de_cruzamento, t, ts, cal);
        mesclar(detB, marcaB);
      }
      registro.canal_A = detA;
      registro.canal_B = detB;
      registro.periodo_de_amostragem_s = ts;

      var cruzamentos = [];
      if (detA.detectado) { cruzamentos.push(t[detA.indice_de_cruzamento]); }
      if (detB.detectado) { cruzamentos.push(t[detB.indice_de_cruzamento]); }
      registro.tempo_de_declaracao_s = cruzamentos.length ? Math.min.apply(null, cruzamentos) : null;

      var deltaT = null, uDeltaT = null;
      if (marcaA && marcaB) {
        deltaT = marcaA.tempo_de_chegada_s - marcaB.tempo_de_chegada_s;
        uDeltaT = Math.hypot(marcaA.incerteza_s, marcaB.incerteza_s);
        registro.delta_t_s = deltaT;
        registro.incerteza_de_delta_t_s = uDeltaT;
        registro.delta_t_amostras = marcaA.indice_de_chegada - marcaB.indice_de_chegada;
      }

      var decisao = decidirEvidencia(detA, detB, satA, satB, deltaT !== null ? deltaT : 0.0,
        l, c, ts, cal);
      registro.motivo = decisao[1];
      if (!decisao[0]) {
        registro.classe = (!detA.detectado && !detB.detectado) ? CLASSE_SEM_DETECCAO
          : CLASSE_SEM_LOCALIZACAO;
        if (classificar && registro.classe === CLASSE_SEM_LOCALIZACAO) {
          var cs = classificarSemLocalizacao(marcaA, marcaB, deltaT, l, c, ts, uDeltaT);
          if (cs[0] !== null) {
            registro.classe = cs[0];
            registro.motivo = cs[1];
            registro.lado_da_origem = cs[2];
          }
        }
        return registro;
      }
      registro.classe = CLASSE_LOCALIZADO;
      mesclar(registro, localizar(l, c, deltaT, posA, uDeltaT, uC));
      if (classificar) {
        var ce = classificarEvento(detA, detB, deltaT, l, c, ts);
        if (ce[0] !== null) {
          registro.classe = ce[0];
          registro.motivo = ce[1];
          registro.lado_da_origem = ce[2];
          registro.posicao_da_origem_m = registro.posicao_estimada_m;
          delete registro.posicao_estimada_m;
        }
      }
      return registro;
    } catch (e) {
      registro.classe = CLASSE_FALHA;
      registro.motivo = (e && e.name ? e.name : "Erro") + ": " + (e && e.message ? e.message : e);
      return registro;
    }
  }

  return {
    origem: "Adaptacao de 04_detector (Python). A referencia e o Python.",
    modeloSensor: {
      ORDEM_DOS_EFEITOS: ORDEM_DOS_EFEITOS,
      configNeutra: configNeutra,
      degrauDeQuantizacao: degrauDeQuantizacao,
      resolucaoDeclaradaM: resolucaoDeclaradaM,
      filtrarPassaBaixas: filtrarPassaBaixas,
      amortecer: amortecer,
      atualizar: atualizar,
      atrasar: atrasar,
      aplicarJitter: aplicarJitter,
      saturar: saturar,
      quantizar: quantizar,
      aplicar: aplicarModelo,
      fonteAleatoria: fonteAleatoria,
      fonteGravada: fonteGravada
    },
    matriz: {
      ESCALA_MIN_M: ESCALA_MIN_M,
      ESCALA_MAX_M: ESCALA_MAX_M,
      NIVEIS_DE_RUIDO: NIVEIS_DE_RUIDO,
      configuracoesDeSensor: configuracoesDeSensor,
      velocidades: velocidades,
      sinalSemEvento: sinalSemEvento
    },
    amostragem: {
      escolherFrequencia: escolherFrequencia,
      mediaMovel: mediaMovel,
      decimar: decimar,
      montarEnsaio: montarEnsaio
    },
    posicao: {
      limiteFisicoDeDeltaT: limiteFisicoDeDeltaT,
      posicaoAPartirDoSensorA: posicaoAPartirDoSensorA,
      incertezaDePosicaoM: incertezaDePosicaoM,
      localizar: localizar
    },
    detector: {
      CLASSE_LOCALIZADO: CLASSE_LOCALIZADO,
      CLASSE_SEM_LOCALIZACAO: CLASSE_SEM_LOCALIZACAO,
      CLASSE_SEM_DETECCAO: CLASSE_SEM_DETECCAO,
      CLASSE_FALHA: CLASSE_FALHA,
      CLASSE_MANOBRA: CLASSE_MANOBRA,
      CLASSE_FORA_DO_TRECHO: CLASSE_FORA_DO_TRECHO,
      classificarEvento: classificarEvento,
      classificarSemLocalizacao: classificarSemLocalizacao,
      calibracaoPadrao: calibracaoPadrao,
      pisoDeAmplitude: pisoDeAmplitude,
      pisoDeEnergia: pisoDeEnergia,
      passaAltas: passaAltas,
      energiaEmJanela: energiaEmJanela,
      razaoDeEnergia: razaoDeEnergia,
      detectarCanal: detectarCanal,
      marcarChegada: marcarChegada,
      canalSaturado: canalSaturado,
      decidirEvidencia: decidirEvidencia,
      processarEnsaio: processarEnsaio
    }
  };
});

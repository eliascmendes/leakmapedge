/*
 * LEAKMAP Edge - simulador interativo do painel.
 *
 * So cuida da tela. O algoritmo vem de web/leakmap_detector.js, que e a
 * adaptacao do Python de 04_detector conferida contra o gabarito do Python.
 *
 * Mesma regra de separacao do repositorio: `simular` entrega ao detector
 * apenas os sinais e os parametros que um detector instalado conheceria. A
 * posicao real do vazamento so aparece em `avaliar`, que faz o papel do
 * avaliador (05_avaliacao) e calcula o erro depois que o detector respondeu.
 */
(function () {
  "use strict";

  var L = window.LEAKMAP, D = window.LEAKMAP_DADOS;
  var raiz = document.getElementById("simule");
  if (!L || !D || !raiz) { return; }

  var P = D.parametros;
  var TS = P.passo_do_solucionador_s;
  var C_EF = P.velocidade_de_onda_efetiva_m_s;
  var ESCOLHA = L.amostragem.escolherFrequencia(C_EF, TS);
  var RHO_G = 9810.0;
  var ORDEM_EVENTOS = ["EV-01", "EV-02", "EV-03", "EV-04", "EV-05"];
  var SEMENTES_SEM_EVENTO = [101, 102, 103, 104, 105];
  var N_SEM_EVENTO = 2000;

  var sinais = {}, posicaoReal = {};
  D.sinais.forEach(function (s) { sinais[s.id] = s; });
  D.verdade.forEach(function (v) { posicaoReal[v.id] = v.posicao_real_m; });

  var TRANSMISSORES = {
    ideal: { nivel: "sem_ruido", nome: "Ideal", sub: "sem efeitos de instrumento" },
    bom: { nivel: "baixo", nome: "Bom", sub: "16 bits · 0,02 m de ruído" },
    modesto: { nivel: "alto", nome: "Modesto", sub: "12 bits · 0,20 m de ruído" }
  };
  var CORES_TX = { ideal: "#e9eee7", bom: "#b3f000", modesto: "#2fd6e8" };

  /* ------------------------------------------------------------------ */
  /* formatacao                                                           */
  /* ------------------------------------------------------------------ */

  function fmt(v, casas) {
    var s = Math.abs(v).toFixed(casas).split(".");
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return (v < 0 && Number(v.toFixed(casas)) !== 0 ? "−" : "") + s.join(",");
  }

  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, pai) {
    var ns = /^(svg|line|rect|circle|text|g|path|polyline)$/.test(tag);
    var e = ns ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag);
    for (var k in attrs) {
      if (k === "texto") { e.textContent = attrs[k]; } else { e.setAttribute(k, attrs[k]); }
    }
    if (pai) { pai.appendChild(e); }
    return e;
  }

  /* ------------------------------------------------------------------ */
  /* estado da tela                                                       */
  /* ------------------------------------------------------------------ */

  var estado = {
    evento: "EV-02",
    tx: "bom",
    cPct: 0,
    realizacao: 0,
    ajuste: null,
    caso: null
  };

  /* Casos de "tente quebrar". Os numeros dos textos foram medidos nos cinco
   * pontos de rompimento com este mesmo simulador. */
  var CASOS = {
    faixa: {
      titulo: "Transmissor saturado",
      texto: "Faixa de medida de 30 a 100 m de carga. Na ruptura a pressão cai para 14 a 23 m, " +
        "abaixo do que o instrumento consegue medir. O LEAKMAP detecta o evento, reconhece que os dois " +
        "canais saíram da faixa e retém a posição em vez de publicar uma errada, em qualquer um dos cinco pontos.",
      aplicar: function () {
        estado.tx = "bom"; estado.ajuste = ajustePadrao("bom");
        estado.ajuste.faixa = { on: true, min: 30, max: 100 }; estado.evento = "EV-02";
      }
    },
    skew: {
      titulo: "Canais desencontrados",
      texto: "1,2 ms de atraso entre os dois transmissores. O erro vira um desvio fixo de 0,48 m, sempre " +
        "na direção do sensor A e igual nos cinco pontos. É o tipo de erro que desaparece quando os dois " +
        "canais são lidos pelo mesmo relógio, como na FPGA.",
      aplicar: function () {
        estado.tx = "ideal"; estado.ajuste = ajustePadrao("ideal");
        estado.ajuste.skew = { on: true, val: 1.2 }; estado.evento = "EV-02";
      }
    },
    velocidade: {
      titulo: "Velocidade da onda errada",
      texto: "Velocidade de onda declarada 5% acima da real. O erro é zero no meio do trecho e cresce em " +
        "direção aos sensores, até 2 m nas pontas. Por isso a velocidade de onda da linha é calibrada na instalação.",
      aplicar: function () {
        estado.tx = "bom"; estado.ajuste = ajustePadrao("bom"); estado.cPct = 5; estado.evento = "EV-01";
      }
    }
  };

  function ajustePadrao(tx) {
    var cfg = L.matriz.configuracoesDeSensor(0)[TRANSMISSORES[tx].nivel];
    return {
      ruido: { on: cfg.ruido.ligado, val: cfg.ruido.ligado ? cfg.ruido.desvio_padrao_m : 0.02 },
      bits: { on: cfg.quantizacao.ligado, val: cfg.quantizacao.ligado ? cfg.quantizacao.bits : 16 },
      skew: { on: cfg.diferenca_de_atraso.ligado,
        val: cfg.diferenca_de_atraso.ligado ? cfg.diferenca_de_atraso.atraso_s * 1000 : 0.1 },
      banda: { on: cfg.banda.ligado, val: cfg.banda.ligado ? cfg.banda.corte_hz : 800 },
      faixa: { on: cfg.saturacao.ligado, min: L.matriz.ESCALA_MIN_M, max: L.matriz.ESCALA_MAX_M }
    };
  }

  function igualAoPadrao(tx) {
    return JSON.stringify(estado.ajuste) === JSON.stringify(ajustePadrao(tx));
  }

  /* Configuracao de sensor: parte da configuracao da matriz (mesmas
   * sementes de 04_detector/gerar_ensaios.py) e aplica os ajustes da tela. */
  function montarConfig(eventoId, tx, ajuste) {
    var indice = ORDEM_EVENTOS.indexOf(eventoId);
    var cfg = L.matriz.configuracoesDeSensor(indice * 7)[TRANSMISSORES[tx].nivel];
    var a = ajuste;
    cfg.ruido.ligado = a.ruido.on;
    if (a.ruido.on) { cfg.ruido.desvio_padrao_m = a.ruido.val; }
    cfg.diferenca_de_atraso.ligado = a.skew.on;
    if (a.skew.on) { cfg.diferenca_de_atraso.atraso_s = a.skew.val / 1000; }
    cfg.banda.ligado = a.banda.on;
    if (a.banda.on) { cfg.banda.corte_hz = a.banda.val; cfg.banda.ordem = 2; }
    cfg.saturacao.ligado = a.faixa.on;
    cfg.saturacao.minimo_m = a.faixa.min;
    cfg.saturacao.maximo_m = a.faixa.max;
    cfg.quantizacao.ligado = a.bits.on;
    cfg.quantizacao.bits = a.bits.val;
    cfg.quantizacao.fundo_de_escala_min_m = a.faixa.min;
    cfg.quantizacao.fundo_de_escala_max_m = a.faixa.max;
    return cfg;
  }

  /* Realizacao 0: os mesmos sorteios que o Python usou na matriz, quando
   * existem para este evento e transmissor. Demais: gerador do navegador. */
  function montarFonte(chaveMatriz, realizacao, semente) {
    var gravados = (realizacao === 0 && chaveMatriz) ? D.sorteios_da_matriz[chaveMatriz] : null;
    var aleatoria = L.modeloSensor.fonteAleatoria(semente + realizacao * 1009);
    return {
      normais: function (chave, n) {
        if (gravados && gravados[chave] && gravados[chave].length === n) { return gravados[chave]; }
        return aleatoria.normais(chave, n);
      }
    };
  }

  function parametrosDoDetector(cPct) {
    var fator = cPct === 0 ? 1 : (100 + cPct) / 100;
    return {
      posicao_sensor_A_m: P.posicao_sensor_A_m,
      posicao_sensor_B_m: P.posicao_sensor_B_m,
      distancia_entre_sensores_L_m: P.distancia_entre_sensores_L_m,
      velocidade_de_onda_m_s: C_EF * fator,
      incerteza_de_velocidade_de_onda_m_s: C_EF * (Math.abs(cPct) / 100)
    };
  }

  /* ------------------------------------------------------------------ */
  /* simulacao e avaliacao, separadas                                     */
  /* ------------------------------------------------------------------ */

  /* Recebe sinais limpos do solucionador e devolve o que o detector viu e
   * respondeu. Nao recebe a posicao real. */
  function simular(tempo, canalA, canalB, cfg, fonte, cPct, id) {
    var r = L.modeloSensor.aplicar(canalA, canalB, TS, cfg, fonte);
    var ensaio = L.amostragem.montarEnsaio(id, tempo, r.a, r.b, parametrosDoDetector(cPct), {}, ESCOLHA);
    var escala = {
      minimo_m: cfg.saturacao.minimo_m,
      maximo_m: cfg.saturacao.maximo_m,
      resolucao_declarada_m: L.modeloSensor.resolucaoDeclaradaM(cfg)
    };
    return { ensaio: ensaio, registro: L.detector.processarEnsaio(ensaio, escala) };
  }

  function simularEvento(eventoId, tx, ajuste, cPct, realizacao) {
    var s = sinais[eventoId];
    var cfg = montarConfig(eventoId, tx, ajuste);
    var indice = ORDEM_EVENTOS.indexOf(eventoId);
    var fonte = montarFonte(eventoId + "/" + TRANSMISSORES[tx].nivel, realizacao, 31 * (indice + 1));
    return simular(s.tempo_s, s.canal_A_carga_m, s.canal_B_carga_m, cfg, fonte, cPct, eventoId);
  }

  function simularSemEvento(tx, ajuste, cPct, repeticao, realizacao) {
    var s0 = sinais[ORDEM_EVENTOS[0]];
    var semente = SEMENTES_SEM_EVENTO[repeticao];
    var base = L.matriz.sinalSemEvento(s0.canal_A_carga_m[0], s0.canal_B_carga_m[0], N_SEM_EVENTO, TS);
    var cfg = montarConfig(ORDEM_EVENTOS[0], tx, ajuste);
    if (cfg.ruido.ligado) { cfg.ruido.semente = semente + 1000; }
    var fonte = montarFonte(null, realizacao, semente);
    return simular(base.t, base.a, base.b, cfg, fonte, cPct, "sem-vazamento-" + (repeticao + 1));
  }

  /* Papel do avaliador: so aqui entra a posicao real. */
  function avaliar(registro, posReal) {
    var localizado = registro.classe === L.detector.CLASSE_LOCALIZADO;
    var declarou = localizado || registro.classe === L.detector.CLASSE_SEM_LOCALIZACAO;
    if (posReal === null) {
      return { temEvento: false, falsoAlarme: declarou, erro: null };
    }
    return {
      temEvento: true,
      detectou: declarou,
      localizado: localizado,
      erro: localizado ? Math.abs(registro.posicao_estimada_m - posReal) : null
    };
  }

  /* ------------------------------------------------------------------ */
  /* textos da decisao                                                    */
  /* ------------------------------------------------------------------ */

  function explicar(reg) {
    var m = reg.motivo || "";
    if (reg.classe === L.detector.CLASSE_LOCALIZADO) {
      return "Evidência suficiente nos dois canais: a posição é publicada junto com o alarme.";
    }
    if (/fundo de escala/.test(m)) {
      return "Rompimento detectado, posição retida: " +
        (/os dois/.test(m) ? "os dois transmissores saíram" : "o transmissor " + m.charAt(6) + " saiu") +
        " da faixa de medida, e o LEAKMAP não publica posição sem evidência. Melhor reter do que apontar o lugar errado.";
    }
    if (/nenhum canal/.test(m)) { return "Nenhum canal viu uma onda de rompimento: sem alarme."; }
    if (/nao declarou/.test(m)) {
      return "Rompimento detectado, posição retida: só um dos canais viu a onda, e o LEAKMAP não publica posição sem os dois.";
    }
    if (/faixa fisica/.test(m)) {
      return "Rompimento detectado, posição retida: a diferença de tempo é fisicamente impossível para este trecho.";
    }
    if (/abaixo do limiar/.test(m)) {
      return "Rompimento detectado, posição retida: a onda não se destacou do ruído com margem suficiente.";
    }
    return m;
  }

  function nomeDaClasse(reg) {
    if (reg.classe === L.detector.CLASSE_LOCALIZADO) { return "Localizado"; }
    if (reg.classe === L.detector.CLASSE_SEM_LOCALIZACAO) { return "Posição retida"; }
    if (reg.classe === L.detector.CLASSE_SEM_DETECCAO) { return "Sem alarme"; }
    return "Falha";
  }

  /* ------------------------------------------------------------------ */
  /* desenho do trecho                                                    */
  /* ------------------------------------------------------------------ */

  function desenharTrecho(svg, reg, posReal, aoClicar) {
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    /* desenhado em pixels da largura disponivel, para o texto manter o
     * tamanho em qualquer tela */
    var Wv = Math.max(280, Math.round(svg.getBoundingClientRect().width || 1000));
    var cp = Wv < 560, H = cp ? 150 : 162;
    svg.setAttribute("viewBox", "0 0 " + Wv + " " + H);
    var x0 = cp ? 18 : 40, x1 = Wv - x0, y = cp ? 62 : 68, W = x1 - x0;
    var px = function (m) { return x0 + (m / P.trecho_m) * W; };
    var MONO = "IBM Plex Mono, monospace", DISP = "Archivo, sans-serif";
    function txt(x, yy, cor, fam, tamanho, peso, conteudo, ancora) {
      return el("text", { x: x, y: yy, fill: cor, "font-family": fam, "font-size": tamanho,
        "font-weight": peso, "text-anchor": ancora || "middle", texto: conteudo }, svg);
    }

    el("rect", { x: x0, y: y - 13, width: W, height: 26, fill: "#11171a", stroke: "#1e2724" }, svg);
    [[P.posicao_sensor_A_m, "A"], [P.posicao_sensor_B_m, "B"]].forEach(function (s) {
      var X = px(s[0]);
      el("line", { x1: X, y1: y - 13, x2: X, y2: y - 28, stroke: "#b3f000", "stroke-width": 2 }, svg);
      el("rect", { x: X - 13, y: y - 32, width: 26, height: 4, fill: "#b3f000" }, svg);
      txt(X, y - 40, "#b3f000", DISP, cp ? "13" : "15", "700", "SENSOR " + s[1]);
    });

    /* faixa de incerteza e posicao estimada */
    if (reg && reg.classe === L.detector.CLASSE_LOCALIZADO) {
      var est = reg.posicao_estimada_m, u = Math.max(reg.incerteza_de_posicao_m, 0.4);
      el("rect", { x: px(est - u), y: y - 13, width: Math.max(px(est + u) - px(est - u), 2), height: 26,
        fill: "#b3f000", "fill-opacity": ".16" }, svg);
    }

    /* alvos clicaveis: os cinco pontos com onda simulada */
    ORDEM_EVENTOS.forEach(function (id) {
      var m = posicaoReal[id], X = px(m), ativo = id === estado.evento && posReal !== null;
      var g = el("g", { class: "alvo" + (ativo ? " ativo" : ""), tabindex: "0", role: "button",
        "aria-label": "Rompimento em " + fmt(m, 0) + " metros" }, svg);
      el("rect", { x: X - (cp ? 13 : 20), y: y - 18, width: cp ? 26 : 40, height: 60, fill: "transparent" }, g);
      el("circle", { cx: X, cy: y, r: ativo ? 8 : 6, fill: ativo ? "#f5a524" : "#06080a",
        stroke: ativo ? "#06080a" : "#5b655d", "stroke-width": 2 }, g);
      el("text", { x: X, y: y + 32, fill: ativo ? "#f5a524" : "#828d80", "font-family": MONO,
        "font-size": cp ? "12" : "13", "text-anchor": "middle", texto: fmt(m, 0) + (cp ? "" : " m") }, g);
      if (aoClicar) {
        g.addEventListener("click", function () { aoClicar(id); });
        g.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); aoClicar(id); }
        });
      }
    });

    if (reg && reg.classe === L.detector.CLASSE_LOCALIZADO) {
      var XE = px(reg.posicao_estimada_m);
      el("circle", { cx: XE, cy: y, r: 14, fill: "none", stroke: "#b3f000", "stroke-width": 2.5 }, svg);
      txt(Math.min(Math.max(XE, x0 + 70), x1 - 70), y + 62, "#b3f000", MONO, "13", "600",
        "estimada " + fmt(reg.posicao_estimada_m, 2) + " m");
    } else if (reg) {
      txt((x0 + x1) / 2, y + 62, "#f5a524", MONO, "13", "600",
        reg.classe === L.detector.CLASSE_SEM_DETECCAO ? "sem alarme" : "rompimento detectado · posição retida");
    }
  }

  /* ------------------------------------------------------------------ */
  /* grafico dos dois canais                                              */
  /* ------------------------------------------------------------------ */

  function desenharGrafico(cv, sim, faixa) {
    var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) { return; }
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    var g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);

    var e = sim.ensaio, reg = sim.registro, t = e.tempo_s;
    var A = e.canal_A_carga_m, B = e.canal_B_carga_m, n = t.length;
    var marcas = [];
    ["canal_A", "canal_B"].forEach(function (c) {
      if (reg[c] && reg[c].detectado) { marcas.push(reg[c].indice_de_chegada, reg[c].indice_de_cruzamento); }
    });
    var i0 = 0, i1 = n - 1;
    if (marcas.length) {
      i0 = Math.max(0, Math.min.apply(null, marcas) - 28);
      i1 = Math.min(n - 1, Math.max.apply(null, marcas) + 45);
    }
    var bar = function (v) { return v * RHO_G / 1e5; };
    var lo = Infinity, hi = -Infinity, i;
    for (i = i0; i <= i1; i++) {
      lo = Math.min(lo, bar(A[i]), bar(B[i])); hi = Math.max(hi, bar(A[i]), bar(B[i]));
    }
    var mg = (hi - lo) * 0.1 || 0.1; lo -= mg; hi += mg;
    var padL = 58, padR = 16, padT = 14, padB = 34, pw = w - padL - padR, ph = h - padT - padB;
    var X = function (k) { return padL + ((t[k] - t[i0]) / (t[i1] - t[i0] || 1)) * pw; };
    var Y = function (v) { return padT + ph - ((v - lo) / (hi - lo)) * ph; };

    g.font = '12px "IBM Plex Mono", monospace'; g.lineWidth = 1;
    for (i = 0; i <= 4; i++) {
      var yv = lo + (hi - lo) * i / 4, yy = Y(yv);
      g.strokeStyle = "#161d1b"; g.beginPath(); g.moveTo(padL, yy); g.lineTo(w - padR, yy); g.stroke();
      g.fillStyle = "#5b655d"; g.textAlign = "right"; g.textBaseline = "middle";
      g.fillText(fmt(yv, 2), padL - 8, yy);
    }
    g.textBaseline = "top";
    var divisoes = w < 460 ? 2 : 4;
    for (i = 0; i <= divisoes; i++) {
      var k = Math.round(i0 + (i1 - i0) * i / divisoes), xx = X(k);
      g.fillStyle = "#5b655d"; g.textAlign = i === 0 ? "left" : (i === divisoes ? "right" : "center");
      g.fillText(fmt(t[k] * 1000, 1) + " ms", xx, padT + ph + 9);
    }

    function traco(S, cor) {
      g.strokeStyle = cor; g.lineWidth = 2; g.lineJoin = "round"; g.beginPath();
      for (var k2 = i0; k2 <= i1; k2++) {
        var px = X(k2), py = Y(bar(S[k2]));
        if (k2 === i0) { g.moveTo(px, py); } else { g.lineTo(px, py); }
      }
      g.stroke();
    }
    traco(B, "#2fd6e8"); traco(A, "#b3f000");

    /* limites da faixa de medida, quando aparecem na janela: mostram por que
     * o sinal "achata" num transmissor saturado */
    if (faixa && faixa.on) {
      [faixa.min, faixa.max].forEach(function (limite) {
        var yb = bar(limite);
        if (yb < lo || yb > hi) { return; }
        var yy = Y(yb);
        g.strokeStyle = "#f5a524"; g.lineWidth = 1.5; g.setLineDash([6, 4]);
        g.beginPath(); g.moveTo(padL, yy); g.lineTo(w - padR, yy); g.stroke(); g.setLineDash([]);
        g.fillStyle = "#f5a524"; g.textAlign = "right"; g.textBaseline = "bottom";
        g.fillText("limite do transmissor", w - padR - 4, yy - 3);
      });
    }

    [["canal_A", "#b3f000", "A"], ["canal_B", "#2fd6e8", "B"]].forEach(function (c, j) {
      var d = reg[c[0]];
      if (!d || !d.detectado) { return; }
      var xc = X(d.indice_de_cruzamento), xa = X(d.indice_de_chegada);
      g.strokeStyle = c[1]; g.globalAlpha = 0.45; g.setLineDash([3, 4]);
      g.beginPath(); g.moveTo(xc, padT); g.lineTo(xc, padT + ph); g.stroke();
      g.globalAlpha = 1; g.setLineDash([]); g.lineWidth = 1.5;
      g.beginPath(); g.moveTo(xa, padT); g.lineTo(xa, padT + ph); g.stroke();
      g.fillStyle = c[1]; g.textAlign = "left"; g.textBaseline = "top";
      g.fillText("t" + c[2], xa + 5, padT + 3 + j * 16);
    });
  }

  /* ------------------------------------------------------------------ */
  /* aba: um cenario                                                      */
  /* ------------------------------------------------------------------ */

  var ultimo = null;

  function rodarUm() {
    var sim = simularEvento(estado.evento, estado.tx, estado.ajuste, estado.cPct, estado.realizacao);
    var real = posicaoReal[estado.evento];
    var av = avaliar(sim.registro, real);
    ultimo = sim;
    var reg = sim.registro;

    desenharTrecho($("simSvg"), reg, real, function (id) { estado.evento = id; sincronizar(); });
    desenharGrafico($("simCv"), sim, estado.ajuste.faixa);

    var loc = reg.classe === L.detector.CLASSE_LOCALIZADO;
    var vazio = '<span class="vazio">—</span>';
    $("sEst").innerHTML = loc ? fmt(reg.posicao_estimada_m, 2) + "<small>m</small>" : vazio;
    $("sErro").innerHTML = loc ? fmt(av.erro, 2) + "<small>m</small>" : vazio;
    $("sDt").innerHTML = (reg.delta_t_s !== undefined) ? fmt(reg.delta_t_s * 1000, 2) + "<small>ms</small>" : "—";
    $("sClasse").textContent = nomeDaClasse(reg);
    $("sClasse").className = "val " + (loc ? "ok" : "alerta");
    $("sReal").textContent = "real " + fmt(real, 0) + " m";
    $("sIncerteza").textContent = loc ? "± " + fmt(reg.incerteza_de_posicao_m, 2) + " m declarados" : "";
    $("sMotivo").textContent = explicar(reg);
    $("sMotivo").className = "motivo" + (loc ? "" : " retida");
    $("sClasseSub").textContent = loc ? "posição publicada com o alarme" :
      (reg.classe === L.detector.CLASSE_SEM_LOCALIZACAO ? "rompimento detectado" : "nenhuma onda de rompimento");
    $("bEst").textContent = loc ? fmt(reg.posicao_estimada_m, 2) + " m" : "—";
    $("bErro").textContent = loc ? fmt(av.erro, 2) + " m" : "—";
    $("bClasse").textContent = nomeDaClasse(reg);
    $("bClasse").className = loc ? "ok" : "alerta";

    var partes = [];
    if (reg.canal_A && reg.canal_A.detectado) { partes.push("<b>chegada A</b> " + fmt(reg.canal_A.tempo_de_chegada_s * 1000, 3) + " ms"); }
    if (reg.canal_B && reg.canal_B.detectado) { partes.push("<b>chegada B</b> " + fmt(reg.canal_B.tempo_de_chegada_s * 1000, 3) + " ms"); }
    partes.push("<b>amostragem</b> " + fmt(ESCOLHA.frequencia_de_amostragem_hz, 1) + " Hz");
    partes.push("<b>c declarada</b> " + fmt(parametrosDoDetector(estado.cPct).velocidade_de_onda_m_s, 1) + " m/s");
    partes.push("<b>ruído</b> " + (estado.realizacao === 0 ? "mesmo sorteio da matriz publicada" :
      "sorteio nº " + (estado.realizacao + 1) + " do navegador"));
    $("sReadout").innerHTML = partes.join(" &nbsp;·&nbsp; ");
  }

  /* ------------------------------------------------------------------ */
  /* controles                                                            */
  /* ------------------------------------------------------------------ */

  function sincronizar() {
    Array.prototype.forEach.call(document.querySelectorAll("#simPos button"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.evento === estado.evento));
    });
    var personalizado = !igualAoPadrao(estado.tx);
    Array.prototype.forEach.call(document.querySelectorAll("#simTx button"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.tx === estado.tx && !personalizado));
    });
    $("simTxNota").textContent = (personalizado && !estado.caso) ?
      "Instrumento personalizado a partir do transmissor " + TRANSMISSORES[estado.tx].nome.toLowerCase() + "." : "";

    var caso = estado.caso ? CASOS[estado.caso] : null;
    $("simCaso").hidden = !caso;
    $("simCasoSair2").hidden = !caso;
    if (caso) {
      $("simCasoTitulo").textContent = caso.titulo;
      $("simCasoTexto").textContent = caso.texto;
    }
    Array.prototype.forEach.call(document.querySelectorAll("[data-quebra]"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.quebra === estado.caso));
    });

    $("simC").value = String(estado.cPct);
    var c = parametrosDoDetector(estado.cPct).velocidade_de_onda_m_s;
    $("simCval").textContent = fmt(c, 1) + " m/s · " +
      (estado.cPct === 0 ? "exata" : (estado.cPct > 0 ? "+" : "−") + fmt(Math.abs(estado.cPct), 1) + "% em relação à real");

    var a = estado.ajuste;
    ["ruido", "bits", "skew", "banda"].forEach(function (k) {
      $("aj_" + k + "_on").checked = a[k].on;
      $("aj_" + k).value = String(a[k].val);
      $("aj_" + k).disabled = !a[k].on;
    });
    $("aj_faixa_on").checked = a.faixa.on;
    $("aj_faixa_min").value = String(a.faixa.min);
    $("aj_faixa_max").value = String(a.faixa.max);
    $("aj_faixa_min").disabled = $("aj_faixa_max").disabled = !a.faixa.on;
    rodarUm();
  }

  function numero(v, padrao) { var x = parseFloat(String(v).replace(",", ".")); return isFinite(x) ? x : padrao; }

  function lerAjuste() {
    var a = estado.ajuste;
    a.ruido = { on: $("aj_ruido_on").checked, val: Math.max(0, numero($("aj_ruido").value, a.ruido.val)) };
    a.bits = { on: $("aj_bits_on").checked, val: Math.min(24, Math.max(4, Math.round(numero($("aj_bits").value, a.bits.val)))) };
    a.skew = { on: $("aj_skew_on").checked, val: Math.max(0, numero($("aj_skew").value, a.skew.val)) };
    a.banda = { on: $("aj_banda_on").checked, val: Math.min(1200, Math.max(20, numero($("aj_banda").value, a.banda.val))) };
    var mn = numero($("aj_faixa_min").value, a.faixa.min), mx = numero($("aj_faixa_max").value, a.faixa.max);
    if (mx <= mn) { mx = mn + 1; }
    a.faixa = { on: $("aj_faixa_on").checked, min: mn, max: mx };
  }

  function montarControles() {
    var pos = $("simPos");
    ORDEM_EVENTOS.forEach(function (id) {
      var b = el("button", { type: "button", "data-evento": id, texto: fmt(posicaoReal[id], 0) + " m" }, pos);
      b.addEventListener("click", function () { estado.evento = id; sincronizar(); });
    });
    var tx = $("simTx");
    Object.keys(TRANSMISSORES).forEach(function (k) {
      var b = el("button", { type: "button", "data-tx": k }, tx);
      el("span", { class: "n", texto: TRANSMISSORES[k].nome }, b);
      el("span", { class: "s", texto: TRANSMISSORES[k].sub }, b);
      b.addEventListener("click", function () {
        estado.tx = k; estado.ajuste = ajustePadrao(k); estado.caso = null; sincronizar();
      });
    });
    $("simC").addEventListener("input", function () {
      estado.cPct = numero(this.value, 0); estado.caso = null; sincronizar();
    });
    Array.prototype.forEach.call(document.querySelectorAll("#simAjuste input"), function (inp) {
      inp.addEventListener("change", function () { lerAjuste(); estado.caso = null; sincronizar(); });
    });
    $("simNovo").addEventListener("click", function () { estado.realizacao += 1; sincronizar(); });
    function voltarAoPadrao(manterPonto) {
      if (!manterPonto) { estado.evento = "EV-02"; }
      estado.tx = "bom"; estado.cPct = 0; estado.realizacao = 0; estado.caso = null;
      estado.ajuste = ajustePadrao("bom"); $("simAjuste").open = false; sincronizar();
    }
    $("simReset").addEventListener("click", function () { voltarAoPadrao(false); });
    $("simCasoSair").addEventListener("click", function () { voltarAoPadrao(true); });
    $("simCasoSair2").addEventListener("click", function () { voltarAoPadrao(true); });

    Array.prototype.forEach.call(document.querySelectorAll("[data-quebra]"), function (b) {
      b.addEventListener("click", function () {
        if (estado.caso === b.dataset.quebra) { voltarAoPadrao(true); return; }
        estado.cPct = 0; estado.realizacao = 0;
        CASOS[b.dataset.quebra].aplicar();
        estado.caso = b.dataset.quebra;
        $("simAjuste").open = true;
        sincronizar();
        if (window.matchMedia("(min-width: 861px)").matches) {
          $("simSvg").scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      });
    });

    Array.prototype.forEach.call(document.querySelectorAll(".simtabs button"), function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(document.querySelectorAll(".simtabs button"), function (o) {
          o.setAttribute("aria-selected", String(o === b));
        });
        $("abaUm").hidden = b.dataset.aba !== "um";
        $("abaLote").hidden = b.dataset.aba !== "lote";
        if (b.dataset.aba === "um" && ultimo) { desenharGrafico($("simCv"), ultimo, estado.ajuste.faixa); }
      });
    });

    var lp = $("lotePos");
    ORDEM_EVENTOS.forEach(function (id) {
      var r = el("label", { class: "chk" }, lp);
      el("input", { type: "checkbox", value: id, checked: "checked" }, r);
      el("span", { texto: fmt(posicaoReal[id], 0) + " m" }, r);
    });
    var lt = $("loteTx");
    Object.keys(TRANSMISSORES).forEach(function (k) {
      var r = el("label", { class: "chk" }, lt);
      el("input", { type: "checkbox", value: k, checked: "checked" }, r);
      el("i", { style: "background:" + CORES_TX[k] }, r);
      el("span", { texto: TRANSMISSORES[k].nome }, r);
    });
    $("loteRodar").addEventListener("click", rodarLote);
    $("bVer").addEventListener("click", function () {
      document.querySelector("#abaUm .simres").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  /* ------------------------------------------------------------------ */
  /* aba: varios cenarios                                                 */
  /* ------------------------------------------------------------------ */

  function marcados(id) {
    return Array.prototype.filter.call(document.querySelectorAll("#" + id + " input"), function (i) {
      return i.checked;
    }).map(function (i) { return i.value; });
  }

  function rodarLote() {
    var posicoes = marcados("lotePos"), txs = marcados("loteTx");
    var semEvento = $("loteSem").checked, cPct = estado.cPct;
    var linhas = [], pontos = [], erros = [], localizados = 0, comEvento = 0, falsos = 0, semN = 0;

    txs.forEach(function (tx) {
      var aj = ajustePadrao(tx);
      posicoes.forEach(function (id) {
        var sim = simularEvento(id, tx, aj, cPct, 0);
        var av = avaliar(sim.registro, posicaoReal[id]);
        comEvento++;
        if (av.localizado) { localizados++; erros.push(av.erro); pontos.push([posicaoReal[id], sim.registro.posicao_estimada_m, tx]); }
        linhas.push([TRANSMISSORES[tx].nome, fmt(posicaoReal[id], 0) + " m",
          av.localizado ? fmt(sim.registro.posicao_estimada_m, 2) + " m" : "—",
          av.localizado ? fmt(av.erro, 2) + " m" : "—", nomeDaClasse(sim.registro), av.localizado]);
      });
      if (semEvento) {
        var f = 0;
        for (var r = 0; r < SEMENTES_SEM_EVENTO.length; r++) {
          var s = simularSemEvento(tx, aj, cPct, r, 0);
          semN++;
          if (avaliar(s.registro, null).falsoAlarme) { f++; falsos++; }
        }
        linhas.push([TRANSMISSORES[tx].nome, "sem vazamento (" + SEMENTES_SEM_EVENTO.length + "×)", "—", "—",
          f ? f + " falso(s) alarme(s)" : "nenhum alarme", f === 0]);
      }
    });

    erros.sort(function (a, b) { return a - b; });
    var med = erros.length ? (erros.length % 2 ? erros[erros.length >> 1] :
      (erros[erros.length / 2 - 1] + erros[erros.length / 2]) / 2) : null;
    $("lN").innerHTML = String(comEvento + semN);
    $("lLoc").innerHTML = localizados + "<small>/ " + comEvento + "</small>";
    $("lMed").innerHTML = med === null ? "—" : fmt(med, 2) + "<small>m</small>";
    $("lMax").innerHTML = erros.length ? fmt(erros[erros.length - 1], 2) + "<small>m</small>" : "—";
    $("lFa").innerHTML = semN ? falsos + "<small>/ " + semN + "</small>" : "—";

    var corpo = $("loteTabela");
    while (corpo.firstChild) { corpo.removeChild(corpo.firstChild); }
    linhas.forEach(function (l) {
      var tr = el("tr", {}, corpo);
      l.slice(0, 5).forEach(function (v, j) { el("td", { class: j >= 2 ? "num" : "", texto: v }, tr); });
      tr.lastChild.className = l[5] ? "num ok" : "num alerta";
    });
    desenharDispersao($("loteSvg"), pontos);
    $("loteRes").hidden = false;
  }

  function desenharDispersao(svg, pontos) {
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    var m0 = 50, m1 = 150, x0 = 56, x1 = 384, y0 = 294, y1 = 16;
    var X = function (m) { return x0 + (m - m0) / (m1 - m0) * (x1 - x0); };
    var Y = function (m) { return y0 - (m - m0) / (m1 - m0) * (y0 - y1); };
    var MONO = "IBM Plex Mono, monospace";
    [60, 80, 100, 120, 140].forEach(function (m) {
      el("line", { x1: X(m), y1: y1, x2: X(m), y2: y0, stroke: "#161d1b" }, svg);
      el("line", { x1: x0, y1: Y(m), x2: x1, y2: Y(m), stroke: "#161d1b" }, svg);
      el("text", { x: X(m), y: y0 + 18, fill: "#5b655d", "font-family": MONO, "font-size": "15",
        "text-anchor": "middle", texto: String(m) }, svg);
      el("text", { x: x0 - 8, y: Y(m) + 4, fill: "#5b655d", "font-family": MONO, "font-size": "15",
        "text-anchor": "end", texto: String(m) }, svg);
    });
    el("line", { x1: X(m0), y1: Y(m0), x2: X(m1), y2: Y(m1), stroke: "#7fa800", "stroke-dasharray": "4 4" }, svg);
    el("text", { x: (x0 + x1) / 2, y: y0 + 36, fill: "#828d80", "font-family": MONO, "font-size": "15",
      "text-anchor": "middle", texto: "posição real (m)" }, svg);
    var rot = el("text", { x: 14, y: (y0 + y1) / 2, fill: "#828d80", "font-family": MONO, "font-size": "15",
      "text-anchor": "middle", transform: "rotate(-90 14 " + ((y0 + y1) / 2) + ")", texto: "estimada (m)" }, svg);
    rot.setAttribute("dominant-baseline", "middle");
    var deslocamento = { ideal: -7, bom: 0, modesto: 7 };
    pontos.forEach(function (p) {
      el("circle", { cx: X(p[0]) + deslocamento[p[2]], cy: Y(p[1]), r: 5.5, fill: CORES_TX[p[2]],
        "fill-opacity": ".9", stroke: "#06080a", "stroke-width": 1.5 }, svg);
    });
  }

  /* ------------------------------------------------------------------ */

  estado.ajuste = ajustePadrao(estado.tx);
  montarControles();
  sincronizar();
  var redesenho = null;
  window.addEventListener("resize", function () {
    clearTimeout(redesenho);
    redesenho = setTimeout(function () { if (!$("abaUm").hidden) { rodarUm(); } }, 120);
  });
})();

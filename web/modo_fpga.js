/*
 * LEAKMAP Edge - tela do modo FPGA do painel (cenario B, etapa B-12).
 *
 * Mostra o resultado da placa ao lado do resultado do software, ensaio a
 * ensaio, na mesma tela. Os dados vem de web/leakmap_dados_fpga.js, gravado
 * por web/gerar_dados_fpga.py a partir dos arquivos de 04_detector e de
 * 06_fpga/resultados; nenhum numero daqui e calculado no navegador.
 *
 * O rotulo de origem e parte fixa da tela: diz sempre quem processou o
 * resultado mostrado (software, Verilog da placa simulado ou FPGA), para que
 * um observador externo saiba, olhando a tela, de onde veio o numero.
 */
(function () {
  "use strict";

  var F = window.LEAKMAP_FPGA;
  var raiz = document.getElementById("modo-fpga");
  if (!F || !raiz) { return; }

  var BAR = F.bar_por_metro;
  var CLASSES = {
    localizado: "Vazamento localizado",
    sem_deteccao: "Nenhum evento",
    inconclusivo: "Inconclusivo",
    posicao_retida: "Posição retida",
    falha_execucao: "Sem resultado"
  };
  var LINHAS = {
    "evento/sem_ruido/casada": "Ideal · c casada",
    "evento/sem_ruido/desviada": "Ideal · c desviada",
    "evento/baixo/casada": "Bom · c casada",
    "evento/baixo/desviada": "Bom · c desviada",
    "evento/alto/casada": "Modesto · c casada",
    "evento/alto/desviada": "Modesto · c desviada",
    "sem_evento/sem_ruido": "Sem evento · ideal",
    "sem_evento/baixo": "Sem evento · bom",
    "sem_evento/alto": "Sem evento · modesto"
  };

  var porId = {}, linhas = [], grupos = {};
  F.ensaios.forEach(function (e) {
    porId[e.id] = e;
    if (!grupos[e.linha]) { grupos[e.linha] = []; linhas.push(e.linha); }
    grupos[e.linha].push(e);
  });

  var origem = F.ordem_das_origens[0];
  var atual = porId["MX-013"] ? "MX-013" : F.ensaios[0].id;

  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, pai) {
    var e = document.createElement(tag);
    for (var k in attrs) {
      if (k === "texto") { e.textContent = attrs[k]; }
      else if (k === "html") { e.innerHTML = attrs[k]; }
      else { e.setAttribute(k, attrs[k]); }
    }
    if (pai) { pai.appendChild(e); }
    return e;
  }

  function fmt(v, casas) {
    var s = Math.abs(v).toFixed(casas).split(".");
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return (v < 0 && Number(v.toFixed(casas)) !== 0 ? "−" : "") + s.join(",");
  }

  /* ------------------------------------------------------------------ */
  /* resumo da origem                                                     */
  /* ------------------------------------------------------------------ */

  function montarOrigens() {
    var abas = $("fpgaOrigens");
    abas.innerHTML = "";
    if (F.ordem_das_origens.length < 2) { abas.hidden = true; return; }
    abas.hidden = false;
    F.ordem_das_origens.forEach(function (k) {
      var b = el("button", { type: "button", role: "tab", "aria-selected": String(k === origem),
                             texto: F.origens[k].curto }, abas);
      b.addEventListener("click", function () { origem = k; montarOrigens(); resumo(); mostrar(); });
    });
  }

  function tile(pai, lab, val, unid, acc) {
    var t = el("div", { class: "tile" + (acc ? " acc" : "") }, pai);
    el("div", { class: "lab", texto: lab }, t);
    var v = el("div", { class: "val num" }, t);
    v.appendChild(document.createTextNode(val));
    if (unid) { el("small", { texto: unid }, v); }
  }

  function resumo() {
    var o = F.origens[origem];
    $("fpgaStatus").textContent = o.curto + " · " + o.concluidos + "/" + o.ensaios + " ensaios";
    var t = $("fpgaTiles");
    t.innerHTML = "";
    tile(t, "Chegadas iguais ao software", String(o.chegadas_iguais_ao_software), "/ " + o.canais + " canais", true);
    tile(t, "Posições iguais ao software", String(o.posicoes_iguais_ao_software), "/ " + o.ensaios);
    if (o.erro_mediano_m !== null && o.erro_mediano_m !== undefined) {
      tile(t, "Erro mediano contra a verdade", fmt(o.erro_mediano_m, 3), "m");
    }
    if (o.processamento) {
      tile(t, "Processamento do maior ensaio", fmt(o.processamento.ms_a_100_mhz, 2), "ms a 100 MHz");
    } else if (o.falsos_alarmes !== null && o.falsos_alarmes !== undefined) {
      tile(t, "Falsos alarmes", String(o.falsos_alarmes), "/ " + fmt(o.oportunidades_sem_evento, 0));
    }

    var fontes = $("fpgaFontes");
    fontes.innerHTML = "";
    fontes.appendChild(document.createTextNode("Números lidos dos arquivos gravados: "));
    o.arquivos.forEach(function (arq, i) {
      if (i) { fontes.appendChild(document.createTextNode(" · ")); }
      el("a", { class: "src num", "data-src": arq, href: "#", texto: arq }, fontes);
    });
    fontes.appendChild(document.createTextNode(". Software: "));
    el("a", { class: "src num", "data-src": "04_detector/resultados/leakmap_resultado_matriz_v1.json", href: "#",
              texto: "04_detector/resultados/leakmap_resultado_matriz_v1.json" }, fontes);
    fontes.appendChild(document.createTextNode("."));
    ligarFontes(fontes);
  }

  /* os links de fonte seguem a mesma regra do resto do painel */
  function ligarFontes(pai) {
    var meta = document.querySelector('meta[name="leakmap-repo"]');
    var repo = meta ? (meta.getAttribute("content") || "").trim().replace(/\/+$/, "") : "";
    var ramo = meta ? (meta.getAttribute("data-branch") || "main") : "main";
    pai.querySelectorAll("a.src[data-src]").forEach(function (a) {
      if (!repo) { return; }
      a.href = repo + "/blob/" + ramo + "/" + a.getAttribute("data-src");
      a.target = "_blank";
      a.rel = "noopener";
    });
  }

  /* ------------------------------------------------------------------ */
  /* grade dos 45 ensaios                                                 */
  /* ------------------------------------------------------------------ */

  function igual(e) {
    var s = e.software, p = e.placa[origem];
    if (!p) { return false; }
    var mesmaPos = (s.posicao_m === null && p.posicao_m === null) ||
      (s.posicao_m !== null && p.posicao_m !== null && Math.abs(s.posicao_m - p.posicao_m) < 1e-9);
    return s.classe === p.classe && mesmaPos &&
      s.canal_A.chegada === p.canal_A.chegada && s.canal_B.chegada === p.canal_B.chegada;
  }

  function montarGrade() {
    var g = $("fpgaGrade");
    g.innerHTML = "";
    var cab = el("div", { class: "gcab" }, g);
    el("span", { class: "glin", texto: "Onde a linha rompe" }, cab);
    var eventos = grupos[linhas[0]];
    eventos.forEach(function (e) {
      el("span", { class: "gcol num", texto: fmt(e.posicao_real_m, 0) + " m" }, cab);
    });
    linhas.forEach(function (linha) {
      var fila = el("div", { class: "gfila" + (grupos[linha][0].tem_evento ? "" : " sem") }, g);
      el("span", { class: "glin", texto: LINHAS[linha] || linha }, fila);
      grupos[linha].forEach(function (e) {
        var ok = igual(e);
        var b = el("button", {
          type: "button", class: "gcel num" + (ok ? " ok" : " dif"), "data-id": e.id,
          "aria-pressed": String(e.id === atual),
          "aria-label": e.id + (ok ? ", igual ao software" : ", diferente do software")
        }, fila);
        el("span", { class: "gid", texto: e.id.replace("MX-", "") }, b);
        el("span", { class: "gok", "aria-hidden": "true", texto: ok ? "=" : "≠" }, b);
        b.addEventListener("click", function () { atual = e.id; marcarGrade(); mostrar(); });
      });
    });
  }

  function marcarGrade() {
    $("fpgaGrade").querySelectorAll(".gcel").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-id") === atual));
    });
  }

  /* ------------------------------------------------------------------ */
  /* grafico: a serie que a placa recebeu e as duas marcas de chegada     */
  /* ------------------------------------------------------------------ */

  function desenhar() {
    var cv = $("fpgaCv"), e = porId[atual], s = e.software, p = e.placa[origem];
    var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) { return; }
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    var g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);

    var A = e.codigos_A, B = e.codigos_B, n = A.length, i;
    var t = function (k) { return e.t0_s + k * e.ts_s; };
    var bar = function (c) { return c * e.degrau_m * BAR; };

    var marcas = [];
    [s, p].forEach(function (r) {
      ["canal_A", "canal_B"].forEach(function (c) {
        if (r[c].detectado) { marcas.push(r[c].chegada, r[c].cruzamento); }
      });
    });
    var i0 = 0, i1 = n - 1;
    if (marcas.length) {
      i0 = Math.max(0, Math.min.apply(null, marcas) - 28);
      i1 = Math.min(n - 1, Math.max.apply(null, marcas) + 45);
    }
    var lo = Infinity, hi = -Infinity;
    for (i = i0; i <= i1; i++) {
      lo = Math.min(lo, bar(A[i]), bar(B[i])); hi = Math.max(hi, bar(A[i]), bar(B[i]));
    }
    var mg = (hi - lo) * 0.12 || 0.05; lo -= mg; hi += mg;
    var padL = 58, padR = 16, padT = 26, padB = 34, pw = w - padL - padR, ph = h - padT - padB;
    var X = function (k) { return padL + ((k - i0) / ((i1 - i0) || 1)) * pw; };
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
      var k = Math.round(i0 + (i1 - i0) * i / divisoes);
      g.fillStyle = "#5b655d"; g.textAlign = i === 0 ? "left" : (i === divisoes ? "right" : "center");
      g.fillText(fmt(t(k) * 1000, 1) + " ms", X(k), padT + ph + 9);
    }

    /* a serie em degraus: sao amostras inteiras, uma por periodo */
    function traco(S, cor) {
      g.strokeStyle = cor; g.lineWidth = 1.8; g.lineJoin = "miter"; g.beginPath();
      for (var k2 = i0; k2 <= i1; k2++) {
        var py = Y(bar(S[k2]));
        if (k2 === i0) { g.moveTo(X(k2), py); } else { g.lineTo(X(k2), py); }
        g.lineTo(X(Math.min(k2 + 1, i1)), py);
      }
      g.stroke();
    }
    traco(B, "#2fd6e8"); traco(A, "#b3f000");

    /* marca da placa: linha cheia; marca do software: triangulo branco no topo */
    [["canal_A", "#b3f000", "A"], ["canal_B", "#2fd6e8", "B"]].forEach(function (c, j) {
      if (p[c[0]].detectado) {
        var xa = X(p[c[0]].chegada);
        g.strokeStyle = c[1]; g.lineWidth = 1.6;
        g.beginPath(); g.moveTo(xa, padT); g.lineTo(xa, padT + ph); g.stroke();
        g.fillStyle = c[1]; g.textAlign = "left"; g.textBaseline = "top";
        g.fillText("t" + c[2], xa + 6, padT + 4 + j * 16);
      }
      if (s[c[0]].detectado) {
        var xs = X(s[c[0]].chegada);
        g.fillStyle = "#e9eee7"; g.beginPath();
        g.moveTo(xs - 6, padT - 12); g.lineTo(xs + 6, padT - 12); g.lineTo(xs, padT - 2); g.closePath(); g.fill();
      }
    });
    if (!marcas.length) {
      g.fillStyle = "#828d80"; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText("nenhuma chegada marcada, nem na placa nem no software", padL + pw / 2, padT + 14);
    }
  }

  /* ------------------------------------------------------------------ */
  /* lado a lado                                                          */
  /* ------------------------------------------------------------------ */

  function chegada(r, c, e) {
    if (!r[c].detectado) { return "sem chegada"; }
    return "amostra " + r[c].chegada + " · " + fmt((e.t0_s + r[c].chegada * e.ts_s) * 1000, 2) + " ms";
  }

  function dt(r, e) {
    if (r.delta_t_amostras === null || r.delta_t_amostras === undefined) { return "—"; }
    return fmt(r.delta_t_amostras, 0) + " amostras · " + fmt(r.delta_t_amostras * e.ts_s * 1000, 3) + " ms";
  }

  function posicao(r) {
    return r.posicao_m === null || r.posicao_m === undefined ? "—" : fmt(r.posicao_m, 2) + " m";
  }

  function mostrar() {
    var e = porId[atual], s = e.software, p = e.placa[origem], o = F.origens[origem];
    $("fpgaRotuloTexto").textContent = o.rotulo;
    $("fpgaEnsaio").textContent = e.id + " · " + (LINHAS[e.linha] || e.linha) +
      (e.tem_evento ? " · rompimento em " + fmt(e.posicao_real_m, 0) + " m" : "");
    $("fpgaHwTitulo").textContent = o.curto;

    var linhasCmp = [
      ["Resultado", CLASSES[s.classe] || s.classe, CLASSES[p.classe] || p.classe],
      ["Chegada no canal A", chegada(s, "canal_A", e), chegada(p, "canal_A", e)],
      ["Chegada no canal B", chegada(s, "canal_B", e), chegada(p, "canal_B", e)],
      ["Δt = tA − tB", dt(s, e), dt(p, e)],
      ["Posição estimada", posicao(s), posicao(p)]
    ];
    var corpo = $("fpgaCmp");
    corpo.querySelectorAll(".linha").forEach(function (x) { x.remove(); });
    linhasCmp.forEach(function (l) {
      el("div", { class: "rl linha", role: "rowheader", texto: l[0] }, corpo);
      el("div", { class: "linha", role: "cell", texto: l[1] }, corpo);
      var c = el("div", { class: "me linha", role: "cell" }, corpo);
      c.appendChild(document.createTextNode(l[2]));
      el("span", { class: l[1] === l[2] ? "eq" : "ne", texto: l[1] === l[2] ? "=" : "≠" }, c);
    });

    var frases = [];
    if (igual(e)) {
      frases.push(e.tem_evento || s.classe !== "sem_deteccao"
        ? "Mesma chegada nos dois canais, mesma diferença de tempo e mesma posição que o software."
        : "A placa e o software ficam em silêncio no mesmo ensaio: nenhum disparo sem evento.");
    } else {
      frases.push("Resultado diferente do software neste ensaio.");
    }
    ["canal_A", "canal_B"].forEach(function (c, j) {
      if (s[c].detectado && p[c].detectado && s[c].cruzamento !== p[c].cruzamento && s[c].chegada === p[c].chegada) {
        frases.push("No canal " + "AB"[j] + ", o limiar foi cruzado uma amostra " +
          (p[c].cruzamento > s[c].cruzamento ? "depois" : "antes") +
          " na placa, que trabalha com inteiros; o retrocesso chega à mesma amostra de chegada.");
      }
    });
    if (e.tem_evento && p.posicao_m !== null && p.posicao_m !== undefined) {
      frases.push("Posição real " + fmt(e.posicao_real_m, 2) + " m, erro de " +
        fmt(Math.abs(p.posicao_m - e.posicao_real_m), 2) + " m.");
    }
    $("fpgaVeredito").textContent = frases.join(" ");
    desenhar();
  }

  $("fpgaEntrada").textContent = F.entrada;
  montarOrigens();
  resumo();
  montarGrade();
  mostrar();
  var espera;
  window.addEventListener("resize", function () { clearTimeout(espera); espera = setTimeout(desenhar, 120); });
  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(desenhar); }
})();

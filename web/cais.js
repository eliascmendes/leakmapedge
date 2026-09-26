/* LEAKMAP Edge - tela da linha de produto do cais.
 *
 * Mostra, num esquematico da linha, o resultado do mesmo detector sobre a
 * simulacao TSNet da linha do cais (02_bancada/codigo/linha_cais.py e
 * manobras_cais.py): onde o evento aconteceu, onde o detector disse que
 * aconteceu, a classificacao e o nivel da escala de alerta, para cada tipo de
 * transmissor. Os dados vem de web/leakmap_dados_cais.js, gerado por
 * web/gerar_dados_cais.py a partir dos arquivos gravados. */
(function () {
  "use strict";
  var C = window.LEAKMAP_CAIS;
  var raiz = document.getElementById("cais");
  if (!C || !raiz) { return; }
  var P = C.premissas.posicoes_m;
  var NS = "http://www.w3.org/2000/svg";

  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, pai) {
    var svg = pai && (pai.namespaceURI === NS);
    var n = svg || tag === "svg" ? document.createElementNS(NS, tag) : document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "texto") { n.textContent = attrs[k]; } else { n.setAttribute(k, attrs[k]); }
    });
    if (pai) { pai.appendChild(n); }
    return n;
  }
  function fmt(v, casas) {
    var s = Math.abs(v).toFixed(casas).split(".");
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    return (v < 0 && Number(v.toFixed(casas)) !== 0 ? "−" : "") + s.join(",");
  }

  var NIVEIS = { registro: "Registro", suspeita: "Suspeita", provavel: "Provável", confirmado: "Confirmado" };
  var estado = { evento: C.eventos[2].id, tx: C.configuracoes[0].configuracao };

  function caso() { return C.casos[estado.evento + "/" + estado.tx]; }
  function evento() { return C.eventos.filter(function (e) { return e.id === estado.evento; })[0]; }

  function classificacao(r, ev) {
    if (r.classe === "localizado") { return "Vazamento localizado"; }
    if (r.classe === "manobra") { return "Manobra"; }
    if (r.classe === "fora_do_trecho") { return "Fora do trecho · lado " + r.lado; }
    if (r.classe === "detectado_sem_localizacao") { return "Posição retida"; }
    if (r.classe === "sem_deteccao") { return ev.tipo === "manobra" ? "Nenhuma onda vista" : "Não detectado"; }
    return "Falha";
  }

  function explicar(r, ev) {
    if (r.classe === "localizado") {
      return "Queda de pressão nos dois sensores, com diferença de tempo possível dentro do trecho: vazamento, " +
        "com a posição publicada junto com o alerta.";
    }
    if (r.classe === "manobra") {
      var pa = r.polaridade[0], pb = r.polaridade[1], onde;
      if (pa && pb && pa !== pb) { onde = "alta de um lado e queda do outro: uma válvula que fecha entre os sensores"; }
      else if (pa && pb) { onde = "alta de pressão nos dois sensores"; }
      else { onde = "alta de pressão no sensor " + (pa ? "A" : "B"); }
      return "A onda é de " + onde + ". Um rompimento sempre derruba a pressão: é manobra de operação, " +
        "não vazamento. Fica no histórico, nunca alarma.";
    }
    if (r.classe === "fora_do_trecho") {
      return "A onda chegou ao sensor " + r.lado + " com a diferença de tempo no limite físico: nasceu no sensor " +
        "ou fora do trecho, do lado dele. O LEAKMAP avisa e diz o lado, sem inventar uma posição que não mede.";
    }
    if (r.classe === "detectado_sem_localizacao") {
      var m = r.motivo || "", porque;
      if (/faixa fisica/.test(m)) {
        porque = "a diferença de tempo passou do limite físico do trecho, além do que o ruído de tempo explica. " +
          "Com transmissor lento, a saída em degraus embaralha os tempos";
      } else if (/nao declarou/.test(m)) {
        porque = "só um dos sensores viu a onda, e sem os dois não há diferença de tempo";
      } else if (/fundo de escala/.test(m)) {
        porque = "um transmissor saiu da faixa de medida";
      } else if (/abaixo do limiar/.test(m)) {
        porque = "a onda não se destacou do ruído com margem suficiente";
      } else {
        porque = m;
      }
      return "Evento detectado, posição retida: " + porque + ". O alerta sai como suspeita, sem apontar lugar.";
    }
    if (r.classe === "sem_deteccao" && ev.tipo === "manobra") {
      return "A frente da manobra é lenta e ficou abaixo do limiar nos dois sensores: nada a registrar.";
    }
    return r.motivo || "";
  }

  function desenhar() {
    var svg = $("caisSvg"), r = caso(), ev = evento();
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    var Wv = Math.max(300, Math.round(svg.getBoundingClientRect().width || 1000));
    var cp = Wv < 600, H = cp ? 190 : 200;
    svg.setAttribute("viewBox", "0 0 " + Wv + " " + H);
    var x0 = cp ? 16 : 40, x1 = Wv - (cp ? 16 : 40), y = 104;
    var ini = P.bomba, fim = P.navio + 40;
    var px = function (m) { return x0 + ((m - ini) / (fim - ini)) * (x1 - x0); };
    var MONO = "IBM Plex Mono, monospace", DISP = "Archivo, sans-serif";
    /* rotulo mantido dentro do desenho, pela largura estimada do texto */
    function txt(x, yy, cor, fam, tam, peso, conteudo, ancora) {
      var w = conteudo.length * Number(tam) * (fam === MONO ? 0.62 : 0.6), borda = 4;
      ancora = ancora || "middle";
      if (ancora === "middle") { x = Math.min(Math.max(x, borda + w / 2), Wv - borda - w / 2); }
      else if (ancora === "start") { x = Math.min(x, Wv - borda - w); }
      else { x = Math.max(x, borda + w); }
      return el("text", { x: x, y: yy, fill: cor, "font-family": fam, "font-size": tam, "font-weight": peso,
        "text-anchor": ancora, texto: conteudo }, svg);
    }
    /* trecho monitorado entre os sensores, e a linha inteira */
    el("rect", { x: px(P.sensor_A), y: y - 14, width: px(P.sensor_B_berco_108) - px(P.sensor_A), height: 28,
      fill: "#b3f000", "fill-opacity": ".05" }, svg);
    el("line", { x1: px(ini), y1: y, x2: px(P.navio), y2: y, stroke: "#5b655d", "stroke-width": 6,
      "stroke-linecap": "round" }, svg);
    /* ramal do berco 106 */
    el("line", { x1: px(P.berco_106), y1: y, x2: px(P.berco_106), y2: y - 40, stroke: "#5b655d",
      "stroke-width": 4 }, svg);
    txt(px(ini), y + 30, "#828d80", MONO, cp ? "11" : "12", "500", "bomba", "start");
    txt(px(P.berco_104), y + 30, "#828d80", MONO, cp ? "11" : "12", "500", "berço 104");
    /* na tela estreita, acima da faixa dos rotulos dos sensores */
    txt(px(P.berco_106), y - (cp ? 64 : 48), "#828d80", MONO, cp ? "11" : "12", "500", "berço 106");
    /* o navio fica 20 m depois do sensor B: o rotulo vai depois do fim da
     * linha, e some na tela estreita, onde nao cabe ao lado de "berco 108" */
    if (!cp) { txt(px(P.navio) + 6, y + 4, "#828d80", MONO, "12", "500", "navio", "start"); }
    [[P.sensor_A, "A"], [P.sensor_B_berco_108, "B"]].forEach(function (s) {
      var X = px(s[0]);
      el("line", { x1: X, y1: y - 12, x2: X, y2: y - 30, stroke: "#b3f000", "stroke-width": 2 }, svg);
      el("rect", { x: X - 11, y: y - 34, width: 22, height: 4, fill: "#b3f000" }, svg);
      txt(X, y - 42, "#b3f000", DISP, cp ? "12" : "14", "700", "SENSOR " + s[1]);
    });
    txt(px(P.sensor_B_berco_108), y + 30, "#828d80", MONO, cp ? "11" : "12", "500", "berço 108", "end");

    /* onde o evento aconteceu */
    var XR = px(ev.posicao_real_m);
    el("circle", { cx: XR, cy: y, r: 7, fill: ev.tipo === "manobra" ? "#2fd6e8" : "#f5a524",
      stroke: "#06080a", "stroke-width": 2 }, svg);
    txt(XR, y + 52, ev.tipo === "manobra" ? "#2fd6e8" : "#f5a524", MONO, "12", "600",
      (ev.tipo === "manobra" ? "manobra em " : "real ") + fmt(ev.posicao_real_m, 0) + " m");

    /* o que o detector disse */
    if (r.classe === "localizado") {
      var u = Math.max(r.incerteza_m || 0, 1.5), XE = px(r.posicao_estimada_m);
      el("rect", { x: px(r.posicao_estimada_m - u), y: y - 14, width: Math.max(px(r.posicao_estimada_m + u) -
        px(r.posicao_estimada_m - u), 2), height: 28, fill: "#b3f000", "fill-opacity": ".18" }, svg);
      el("circle", { cx: XE, cy: y, r: 13, fill: "none", stroke: "#b3f000", "stroke-width": 2.5 }, svg);
      txt(Math.min(Math.max(XE, x0 + 70), x1 - 70), y + 72, "#b3f000", MONO, "12", "600",
        "estimada " + fmt(r.posicao_estimada_m, 1) + " m");
    } else if (r.classe === "fora_do_trecho") {
      var XA = px(r.lado === "A" ? P.sensor_A : P.sensor_B_berco_108), d = r.lado === "A" ? -1 : 1;
      el("path", { d: "M" + XA + " " + (y - 20) + " l" + (d * 34) + " 0 m" + (-d * 8) + " -6 l" + (d * 8) +
        " 6 l" + (-d * 8) + " 6", stroke: "#f5a524", fill: "none", "stroke-width": 2.5 }, svg);
      txt(XA + d * 20, y + 72, "#f5a524", MONO, "12", "600", "origem fora do trecho, lado " + r.lado,
        d < 0 ? "start" : "end");
    } else if (r.classe === "manobra" && r.posicao_da_origem_m !== null && r.posicao_da_origem_m !== undefined) {
      var XO = px(r.posicao_da_origem_m);
      el("circle", { cx: XO, cy: y, r: 13, fill: "none", stroke: "#2fd6e8", "stroke-width": 2,
        "stroke-dasharray": "4 3" }, svg);
      txt(Math.min(Math.max(XO, x0 + 80), x1 - 80), y + 72, "#2fd6e8", MONO, "12", "600",
        "origem da onda " + fmt(r.posicao_da_origem_m, 1) + " m · sem alarme");
    }
  }

  function mostrar() {
    var r = caso(), ev = evento();
    Array.prototype.forEach.call(raiz.querySelectorAll("[data-evento]"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.evento === estado.evento));
    });
    Array.prototype.forEach.call(raiz.querySelectorAll("[data-tx]"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.tx === estado.tx));
    });
    desenhar();
    var alarme = r.nivel === "provavel" || r.nivel === "confirmado";
    $("caisNivel").textContent = r.nivel ? NIVEIS[r.nivel] : "Sem alerta";
    $("caisNivel").className = "val " + (alarme ? "alerta" : "ok");
    $("caisClasse").textContent = classificacao(r, ev);
    $("caisEst").innerHTML = r.posicao_estimada_m !== null && r.posicao_estimada_m !== undefined ?
      fmt(r.posicao_estimada_m, 1) + "<small>m</small>" : '<span class="vazio">—</span>';
    $("caisErro").innerHTML = r.erro_m !== null && r.erro_m !== undefined ?
      fmt(r.erro_m, 2) + "<small>m</small>" : '<span class="vazio">—</span>';
    $("caisMotivo").textContent = explicar(r, ev);
  }

  function montar() {
    $("caisLead").textContent = "Uma linha de produto de " + C.premissas.tubo.split(" ")[0] + " com " +
      C.premissas.produto + ", onda a " + fmt(C.premissas.velocidade_de_onda_m_s, 0) + " m/s, sensor A no início " +
      "do trecho e sensor B no berço 108, a " + fmt(P.sensor_B_berco_108 - P.sensor_A, 0) + " m um do outro, " +
      "simulada no TSNet. O mesmo detector do trecho de 200 m, com seis tipos de transmissor. Comprimentos, " +
      "espessura e vazão são premissas até chegar o dado da instalação real; o desenho é esquemático.";
    var grupos = { grande: $("caisGrande"), pequeno: $("caisPequeno"), manobra: $("caisManobras") };
    C.eventos.forEach(function (ev) {
      var alvo = ev.tipo === "manobra" ? grupos.manobra : grupos[ev.tamanho];
      var rotulo = ev.tipo === "manobra" ? ev.nome : fmt(ev.posicao_real_m, 0) + " m" +
        (ev.dentro_do_trecho ? "" : " · fora");
      var b = el("button", { type: "button", "data-evento": ev.id, texto: rotulo }, alvo);
      b.addEventListener("click", function () { estado.evento = ev.id; mostrar(); });
    });
    C.configuracoes.forEach(function (c) {
      var b = el("button", { type: "button", "data-tx": c.configuracao }, $("caisTx"));
      el("span", { class: "n", texto: c.nome }, b);
      el("span", { class: "s", texto: c.sub }, b);
      b.addEventListener("click", function () { estado.tx = c.configuracao; mostrar(); });
    });
    var t = $("caisResumo");
    C.resumo.forEach(function (l) {
      el("div", { class: "rl", role: "rowheader", texto: l.nome }, t);
      el("div", { role: "cell", texto: l.localizados + " de " + l.vazamentos }, t);
      el("div", { role: "cell", texto: fmt(l.erro_mediano_m[0], 2) + " · " + fmt(l.erro_mediano_m[1], 2) + " m" }, t);
      el("div", { role: "cell", texto: fmt(l.erro_maximo_m, 1) + " m" }, t);
      el("div", { role: "cell", texto: l.falsos_alarmes + " de " + l.ensaios_sem_evento }, t);
    });
    var f = $("caisFontes");
    f.appendChild(document.createTextNode("Fontes: "));
    C.fontes.forEach(function (arq, k) {
      if (k) { f.appendChild(document.createTextNode(", ")); }
      el("a", { class: "src num", "data-src": arq, href: "#", texto: arq }, f);
    });
    f.appendChild(document.createTextNode(". Simulação: 02_bancada/codigo/linha_cais.py e manobras_cais.py."));
    var espera;
    window.addEventListener("resize", function () { clearTimeout(espera); espera = setTimeout(desenhar, 120); });
    mostrar();
  }

  montar();
})();

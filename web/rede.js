/* LEAKMAP Edge - tela da rede do cais com manifold e tres ramais.
 *
 * Mostra, num esquematico da rede, o resultado da localizacao em rede
 * (04_detector/rede.py) sobre a simulacao TSNet de 02_bancada/codigo/rede_cais.py:
 * onde o vazamento estava, em que trecho e ponto o detector disse que estava
 * e o nivel da escala de alerta, para cada tipo de transmissor. Os dados vem
 * de web/leakmap_dados_rede.js, gerado por web/gerar_dados_rede.py. */
(function () {
  "use strict";
  var R = window.LEAKMAP_REDE;
  var raiz = document.getElementById("rede");
  if (!R || !raiz) { return; }
  var T = R.topologia;
  var NS = "http://www.w3.org/2000/svg";
  var RAMAIS = ["ramal_104", "ramal_106", "ramal_108"];
  var NOMES = { tronco: "tronco", ramal_104: "ramal do 104", ramal_106: "ramal do 106", ramal_108: "ramal do 108" };
  var NIVEIS = { registro: "Registro", suspeita: "Suspeita", provavel: "Provável", confirmado: "Confirmado" };
  var BOMBA = -300, NAVIO = 20;
  var estado = { evento: R.eventos[3].id, tx: R.configuracoes[0].configuracao };

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
  function caso() { return R.casos[estado.evento + "/" + estado.tx]; }
  function evento() { return R.eventos.filter(function (e) { return e.id === estado.evento; })[0]; }
  function comp(trecho) { return T.trechos[trecho].comprimento_monitorado_m; }

  function explicar(r, ev) {
    var n = r.sensores.length;
    if (r.classe === "localizado") {
      return "Queda de pressão em " + n + " sensores. Das chegadas, o LEAKMAP procura em cada trecho o ponto " +
        "cujos tempos pela tubulação até os sensores batem com os medidos, e aponta o " + NOMES[r.trecho] +
        ": vazamento, com a posição publicada junto com o alerta.";
    }
    if (r.classe === "fora_do_trecho") {
      return "As chegadas batem com um ponto em cima do sensor " + r.lado + ": a onda nasceu nele ou antes dele, " +
        "fora da rede monitorada. O LEAKMAP avisa e diz o lado, sem inventar uma posição que não mede.";
    }
    if (r.classe === "detectado_sem_localizacao") {
      return "Evento detectado, posição retida: " + (/ambigua/.test(r.motivo || "") ?
        "dois trechos explicam as chegadas igualmente bem" : "as chegadas não batem com nenhum ponto da rede " +
        "dentro da incerteza das marcas; com transmissor lento, a saída em degraus embaralha os tempos") +
        ". O alerta sai como suspeita, sem apontar lugar.";
    }
    return r.motivo || "";
  }

  function desenhar() {
    var svg = $("redeSvg"), r = caso(), ev = evento();
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    var Wv = Math.max(300, Math.round(svg.getBoundingClientRect().width || 1000));
    var cp = Wv < 600, H = cp ? 250 : 260;
    svg.setAttribute("viewBox", "0 0 " + Wv + " " + H);
    var x0 = cp ? 16 : 40, x1 = Wv - (cp ? 54 : 140), ym = 124, abre = cp ? 78 : 84;
    var maior = Math.max.apply(null, RAMAIS.map(function (k) { return comp(k) + NAVIO; }));
    var escala = (x1 - x0) / (comp("tronco") - BOMBA + maior);
    var xm = x0 + (comp("tronco") - BOMBA) * escala;
    var desvio = { ramal_104: -abre, ramal_106: 0, ramal_108: abre };
    var MONO = "IBM Plex Mono, monospace", DISP = "Archivo, sans-serif";
    /* ponto (trecho, s) no desenho; os ramais saem do manifold em leque */
    function xy(trecho, s) {
      if (trecho === "tronco") { return [x0 + (s - BOMBA) * escala, ym]; }
      /* sobe ou desce em diagonal ate `dobra` e segue na horizontal ate o navio */
      var dobra = cp ? 18 : 30, andado = s * escala;
      if (andado <= dobra) { return [xm + andado, ym + (andado / dobra) * desvio[trecho]]; }
      return [xm + andado, ym + desvio[trecho]];
    }
    function txt(x, yy, cor, fam, tam, peso, conteudo, ancora) {
      var w = conteudo.length * Number(tam) * (fam === MONO ? 0.62 : 0.6), borda = 4;
      ancora = ancora || "middle";
      if (ancora === "middle") { x = Math.min(Math.max(x, borda + w / 2), Wv - borda - w / 2); }
      else if (ancora === "start") { x = Math.min(x, Wv - borda - w); }
      else { x = Math.max(x, borda + w); }
      return el("text", { x: x, y: yy, fill: cor, "font-family": fam, "font-size": tam, "font-weight": peso,
        "text-anchor": ancora, texto: conteudo }, svg);
    }
    function linha(trecho, de, ate, attrs) {
      var pts = [];
      for (var s = de; s <= ate + 0.01; s += Math.max((ate - de) / 40, 1)) { pts.push(xy(trecho, s).join(",")); }
      pts.push(xy(trecho, ate).join(","));
      var a = { points: pts.join(" "), fill: "none" };
      Object.keys(attrs).forEach(function (k) { a[k] = attrs[k]; });
      return el("polyline", a, svg);
    }
    /* rede monitorada (entre os sensores) em destaque, e a rede inteira */
    linha("tronco", BOMBA, comp("tronco"), { stroke: "#5b655d", "stroke-width": 6, "stroke-linecap": "round" });
    RAMAIS.forEach(function (k) {
      linha(k, 0, comp(k) + NAVIO, { stroke: "#5b655d", "stroke-width": 6, "stroke-linecap": "round",
        "stroke-linejoin": "round" });
    });
    linha("tronco", 0, comp("tronco"), { stroke: "#b3f000", "stroke-opacity": ".16", "stroke-width": 22 });
    RAMAIS.forEach(function (k) {
      linha(k, 0, comp(k), { stroke: "#b3f000", "stroke-opacity": ".16", "stroke-width": 22 });
    });
    var M = xy("tronco", comp("tronco"));
    el("circle", { cx: M[0], cy: M[1], r: 6, fill: "#06080a", stroke: "#828d80", "stroke-width": 2 }, svg);
    txt(M[0] - 8, ym + 30, "#828d80", MONO, cp ? "11" : "12", "500", "manifold", "end");
    txt(x0, ym + 30, "#828d80", MONO, cp ? "11" : "12", "500", "bomba", "start");
    /* sensores: A no tronco e um na ponta de cada ramal, junto ao berco */
    Object.keys(T.sensores).forEach(function (nome) {
      var s = T.sensores[nome], p = xy(s.trecho, s.s_m);
      el("line", { x1: p[0], y1: p[1] - 10, x2: p[0], y2: p[1] - 24, stroke: "#b3f000", "stroke-width": 2 }, svg);
      el("rect", { x: p[0] - 9, y: p[1] - 28, width: 18, height: 4, fill: "#b3f000" }, svg);
      if (nome === "A") { txt(p[0], p[1] - 36, "#b3f000", DISP, cp ? "12" : "14", "700", "SENSOR A"); }
      else { txt(xy(s.trecho, s.s_m + NAVIO)[0] + 8, p[1] + 4, "#b3f000", DISP, cp ? "11" : "13", "700",
        cp ? nome : nome + " · berço " + nome.slice(1), "start"); }
    });

    /* onde o vazamento estava */
    var PR = xy(ev.trecho, ev.s_m);
    el("circle", { cx: PR[0], cy: PR[1], r: 7, fill: "#f5a524", stroke: "#06080a", "stroke-width": 2 }, svg);
    /* nos ramais de cima e de baixo o rotulo vai acima do ponto; embaixo fica a linha da estimativa */
    var embaixo = ev.trecho === "tronco" || ev.trecho === "ramal_106" ? ym + 52 : PR[1] - 16;
    txt(PR[0], embaixo, "#f5a524", MONO, "12", "600", "real " + fmt(ev.s_m, 0) + " m");

    /* o que o detector disse */
    if (r.classe === "localizado") {
      var PE = xy(r.trecho, r.s_m);
      el("circle", { cx: PE[0], cy: PE[1], r: 13, fill: "none", stroke: "#b3f000", "stroke-width": 2.5 }, svg);
      txt(Math.min(Math.max(PE[0], x0 + 70), Wv - 90), H - 14, "#b3f000", MONO, "12", "600",
        "estimada: " + NOMES[r.trecho] + ", " + fmt(r.s_m, 1) + " m");
    } else if (r.classe === "fora_do_trecho") {
      var sA = T.sensores[r.lado], XA = xy(sA.trecho, sA.s_m);
      el("path", { d: "M" + XA[0] + " " + (XA[1] - 20) + " l-34 0 m8 -6 l-8 6 l8 6", stroke: "#f5a524",
        fill: "none", "stroke-width": 2.5 }, svg);
      txt(XA[0] - 20, H - 14, "#f5a524", MONO, "12", "600", "origem fora da rede, lado " + r.lado, "start");
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
    $("redeNivel").textContent = r.nivel ? NIVEIS[r.nivel] : "Sem alerta";
    $("redeNivel").className = "val " + (alarme ? "alerta" : "ok");
    $("redeClasse").textContent = r.classe === "localizado" ? "Vazamento · " + NOMES[r.trecho] :
      r.classe === "fora_do_trecho" ? "Fora da rede · lado " + r.lado :
      r.classe === "detectado_sem_localizacao" ? "Posição retida" : "Não detectado";
    $("redeEst").innerHTML = r.s_m !== null && r.s_m !== undefined && r.classe === "localizado" ?
      fmt(r.s_m, 1) + "<small>m</small>" : '<span class="vazio">—</span>';
    $("redeErro").innerHTML = r.erro_m !== null && r.erro_m !== undefined ?
      fmt(r.erro_m, 2) + "<small>m</small>" : '<span class="vazio">—</span>';
    $("redeMotivo").textContent = explicar(r, ev);
  }

  function montar() {
    $("redeLead").textContent = "A linha que sai da tancagem chega a um manifold e se divide em três ramais, um " +
      "por berço. Quatro sensores: um no início do tronco e um na ponta de cada ramal. Com mais de dois sensores, " +
      "a posição sai do ponto da rede cujos tempos de chegada pela tubulação batem com os medidos, e o LEAKMAP diz " +
      "também em que ramal está o vazamento. Simulado no TSNet, " + R.premissas.tubo.split(" ")[0] + " com " +
      R.premissas.produto + "; comprimentos são premissas e o desenho é esquemático.";
    var grupos = { grande: $("redeGrande"), pequeno: $("redePequeno") };
    R.eventos.forEach(function (ev) {
      var rot = ev.dentro ? (ev.trecho === "tronco" ? "tronco" : ev.trecho.replace("ramal_", "")) + " · " +
        fmt(ev.s_m, 0) + " m" : "antes de A";
      var b = el("button", { type: "button", "data-evento": ev.id, texto: rot }, grupos[ev.tamanho]);
      b.addEventListener("click", function () { estado.evento = ev.id; mostrar(); });
    });
    R.configuracoes.forEach(function (c) {
      var b = el("button", { type: "button", "data-tx": c.configuracao }, $("redeTx"));
      el("span", { class: "n", texto: c.nome }, b);
      el("span", { class: "s", texto: c.sub }, b);
      b.addEventListener("click", function () { estado.tx = c.configuracao; mostrar(); });
    });
    var t = $("redeResumo");
    R.resumo.forEach(function (l) {
      el("div", { class: "rl", role: "rowheader", texto: l.nome }, t);
      el("div", { role: "cell", texto: l.localizados + " de " + l.vazamentos + " · " + l.trecho_certo + " no trecho certo" }, t);
      el("div", { role: "cell", texto: l.erro_mediano_m.length ? l.erro_mediano_m.map(function (v) {
        return fmt(v, 2); }).join(" · ") + " m" : "—" }, t);
      el("div", { role: "cell", texto: l.erro_maximo_m !== null ?
        fmt(l.erro_maximo_m, l.erro_maximo_m < 10 ? 2 : 1) + " m" : "—" }, t);
      el("div", { role: "cell", texto: l.falsos_alarmes + " de " + l.ensaios_sem_evento }, t);
    });
    var f = $("redeFontes");
    f.appendChild(document.createTextNode("Fontes: "));
    R.fontes.forEach(function (arq, k) {
      if (k) { f.appendChild(document.createTextNode(", ")); }
      el("a", { class: "src num", "data-src": arq, href: "#", texto: arq }, f);
    });
    f.appendChild(document.createTextNode(". Simulação: 02_bancada/codigo/rede_cais.py. Localização: 04_detector/rede.py."));
    var espera;
    window.addEventListener("resize", function () { clearTimeout(espera); espera = setTimeout(desenhar, 120); });
    mostrar();
  }

  montar();
})();

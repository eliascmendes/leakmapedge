/*
 * Teste da tela do cenario B (B-12): rotulo de origem e numeros da tela.
 *
 * Exige que:
 *   - o rotulo "Processado na FPGA" so apareca para resultado com origem fpga;
 *   - toda origem da tela tenha rotulo e diga reproducao de sinais digitais;
 *   - os numeros de cada ensaio na tela sejam os dos arquivos gravados em
 *     04_detector/resultados e 06_fpga/resultados, sem nada calculado a mais;
 *   - o resumo (chegadas e posicoes iguais ao software) feche com os ensaios.
 *
 * Roda com: node --test web/testes/teste_paridade.js web/testes/teste_modo_fpga.js
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const RAIZ = path.join(__dirname, "..", "..");
const ler = (...p) => JSON.parse(fs.readFileSync(path.join(RAIZ, ...p), "utf8"));

const contexto = {};
vm.runInNewContext(fs.readFileSync(path.join(RAIZ, "web", "leakmap_dados_fpga.js"), "utf8") +
  "\nthis.LEAKMAP_FPGA = LEAKMAP_FPGA;", contexto);
const F = contexto.LEAKMAP_FPGA;
const SUFIXO = { fpga: "fpga", simulacao: "simulacao" };

test("rotulo de FPGA so para resultado com origem fpga", () => {
  assert.ok(F.ordem_das_origens.length > 0);
  for (const k of F.ordem_das_origens) {
    const o = F.origens[k];
    assert.match(o.rotulo, /reprodução de sinais digitais/);
    if (k === "fpga") {
      assert.strictEqual(o.rotulo, "Processado na FPGA · reprodução de sinais digitais");
    } else {
      assert.doesNotMatch(o.rotulo, /Processado na FPGA/);
    }
    const registros = ler("06_fpga", "resultados", `leakmap_cenario_b_resultado_${SUFIXO[k]}_v1.json`);
    const origens = new Set(registros.resultados.map((r) => r.origem));
    assert.deepStrictEqual([...origens], [k === "fpga" ? "fpga" : "simulacao_do_verilog"]);
  }
  assert.strictEqual(F.cenario, "reprodução de sinais digitais em FPGA física");
});

test("numeros de cada ensaio iguais aos arquivos gravados", () => {
  const software = new Map(ler("04_detector", "resultados", "leakmap_resultado_matriz_v1.json")
    .resultados.map((r) => [r.id, r]));
  for (const k of F.ordem_das_origens) {
    const placa = new Map(ler("06_fpga", "resultados", `leakmap_cenario_b_resultado_${SUFIXO[k]}_v1.json`)
      .resultados.map((r) => [r.id, r]));
    for (const e of F.ensaios) {
      for (const [tela, arquivo] of [[e.software, software.get(e.id)], [e.placa[k], placa.get(e.id)]]) {
        assert.strictEqual(tela.classe, arquivo.classe, e.id);
        assert.strictEqual(tela.posicao_m ?? null, arquivo.posicao_estimada_m ?? null, e.id);
        assert.strictEqual(tela.delta_t_amostras ?? null, arquivo.delta_t_amostras ?? null, e.id);
        for (const c of ["canal_A", "canal_B"]) {
          const d = arquivo[c] || {};
          assert.strictEqual(tela[c].detectado, Boolean(d.detectado), e.id + " " + c);
          assert.strictEqual(tela[c].chegada, d.detectado ? d.indice_de_chegada : null, e.id + " " + c);
        }
      }
    }
  }
});

test("resumo da tela fecha com os ensaios", () => {
  for (const k of F.ordem_das_origens) {
    let canais = 0, posicoes = 0;
    for (const e of F.ensaios) {
      const s = e.software, p = e.placa[k];
      for (const c of ["canal_A", "canal_B"]) {
        if (s[c].detectado === p[c].detectado && s[c].chegada === p[c].chegada) { canais++; }
      }
      const mesma = (s.posicao_m == null && p.posicao_m == null) ||
        (s.posicao_m != null && p.posicao_m != null && Math.abs(s.posicao_m - p.posicao_m) < 1e-9);
      if (mesma && s.classe === p.classe) { posicoes++; }
    }
    assert.strictEqual(F.origens[k].chegadas_iguais_ao_software, canais);
    assert.strictEqual(F.origens[k].posicoes_iguais_ao_software, posicoes);
    assert.strictEqual(F.origens[k].canais, 2 * F.ensaios.length);
  }
});

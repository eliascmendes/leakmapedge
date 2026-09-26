/*
 * Teste de paridade: a adaptacao em JavaScript contra o gabarito do Python.
 *
 * O gabarito e gerado por web/gerar_gabarito.py rodando o Python de
 * 04_detector. Este teste exige que web/leakmap_detector.js reproduza:
 *
 *   - indices, classes, motivos e booleanos: exatamente iguais;
 *   - numeros em ponto flutuante: diferenca relativa de no maximo 1e-9.
 *
 * Roda com: node --test web/testes/teste_paridade.js web/testes/teste_modo_fpga.js
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const RAIZ = path.join(__dirname, "..", "..");
const LEAKMAP = require(path.join(RAIZ, "web", "leakmap_detector.js"));

const ler = (...p) => JSON.parse(fs.readFileSync(path.join(RAIZ, ...p), "utf8"));
const gabarito = ler("web", "gabarito", "leakmap_gabarito_js_v1.json");
const pacote = ler("03_ensaios", "pacotes", "leakmap_pacote_matriz_v1.json");
const amostras = ler("03_ensaios", "amostras", "leakmap_amostras_v1.json");

const TOLERANCIA = 1e-9;
const CHAVES_INTEIRAS = /^(indice|n_|amostras_retrocedidas|delta_t_amostras|bits|ordem|semente|fator_de_decimacao|n_pontos)/;

let maiorDiferenca = 0;

/* NaN do JavaScript corresponde a null no gabarito (JSON nao tem NaN) */
function normalizar(v) {
  return (typeof v === "number" && !Number.isFinite(v)) ? null : v;
}

function comparar(obtido, esperado, caminho, ignorar) {
  obtido = normalizar(obtido);
  if (esperado === null || typeof esperado !== "object") {
    if (typeof esperado === "number" && typeof obtido === "number") {
      const chave = caminho.split(".").pop();
      if (CHAVES_INTEIRAS.test(chave)) {
        assert.strictEqual(obtido, esperado, caminho);
        return;
      }
      const escala = Math.max(1, Math.abs(esperado));
      const dif = Math.abs(obtido - esperado) / escala;
      if (dif > maiorDiferenca) { maiorDiferenca = dif; }
      assert.ok(dif <= TOLERANCIA,
        `${caminho}: JavaScript ${obtido} contra Python ${esperado} (dif. relativa ${dif})`);
      return;
    }
    assert.strictEqual(obtido, esperado, caminho);
    return;
  }
  if (Array.isArray(esperado)) {
    assert.ok(Array.isArray(obtido), `${caminho}: esperado vetor`);
    assert.strictEqual(obtido.length, esperado.length, `${caminho}: tamanho`);
    for (let i = 0; i < esperado.length; i++) { comparar(obtido[i], esperado[i], `${caminho}[${i}]`, ignorar); }
    return;
  }
  assert.ok(obtido && typeof obtido === "object", `${caminho}: esperado objeto`);
  const chavesE = Object.keys(esperado).filter((k) => !(ignorar || []).includes(k)).sort();
  const chavesO = Object.keys(obtido).filter((k) => !(ignorar || []).includes(k)).sort();
  assert.deepStrictEqual(chavesO, chavesE, `${caminho}: chaves`);
  for (const k of chavesE) { comparar(obtido[k], esperado[k], `${caminho}.${k}`, ignorar); }
}

const porId = Object.fromEntries(amostras.ensaios.map((e) => [e.id, e]));
const tsSolucionador = gabarito.base_de_tempo_s;

test("configuracoes de sensor, velocidades e calibracao iguais as do Python", () => {
  const cfg = gabarito.configuracoes;
  comparar(LEAKMAP.modeloSensor.configNeutra(), cfg.neutra, "config_neutra");
  for (const [semente, esperado] of Object.entries(cfg.matriz_por_semente)) {
    comparar(LEAKMAP.matriz.configuracoesDeSensor(Number(semente)), esperado,
      `configuracoes_de_sensor(${semente})`);
  }
  comparar(LEAKMAP.matriz.velocidades(cfg.velocidades.casada.c_m_s), cfg.velocidades, "velocidades");
  comparar(LEAKMAP.detector.calibracaoPadrao(), cfg.calibracao_padrao, "calibracao_padrao");
  const esc = cfg.escolha_de_frequencia;
  comparar(LEAKMAP.amostragem.escolherFrequencia(esc.velocidade_de_onda_usada_m_s, tsSolucionador),
    esc, "escolha_de_frequencia", ["conta"]);
});

test("A-09 modelo de sensor: um efeito por vez e configuracoes completas", () => {
  for (const caso of gabarito.modelo_sensor) {
    const origem = porId[caso.ensaio];
    const r = LEAKMAP.modeloSensor.aplicar(origem.canal_A_carga_m, origem.canal_B_carga_m,
      tsSolucionador, caso.config, LEAKMAP.modeloSensor.fonteGravada(caso.sorteios));
    comparar(r.a, caso.saida_A, `${caso.nome}.saida_A`);
    comparar(r.b, caso.saida_B, `${caso.nome}.saida_B`);
    comparar(r.registro, caso.registro, `${caso.nome}.registro`);
    comparar(LEAKMAP.modeloSensor.resolucaoDeclaradaM(caso.config), caso.resolucao_declarada_m,
      `${caso.nome}.resolucao_declarada_m`);
  }
});

test("cadeia completa A-09, A-10 e A-11 a A-14 nos cinco eventos", () => {
  const escolha = LEAKMAP.amostragem.escolherFrequencia(
    gabarito.configuracoes.escolha_de_frequencia.velocidade_de_onda_usada_m_s, tsSolucionador);
  for (const grupo of gabarito.cadeia) {
    const origem = porId[grupo.ensaio_de_origem];
    const nome = `${grupo.ensaio_de_origem}/${grupo.nivel}`;
    const r = LEAKMAP.modeloSensor.aplicar(origem.canal_A_carga_m, origem.canal_B_carga_m,
      tsSolucionador, grupo.config, LEAKMAP.modeloSensor.fonteGravada(grupo.sorteios));
    for (const v of grupo.por_velocidade) {
      const ensaio = LEAKMAP.amostragem.montarEnsaio(`${nome}/${v.velocidade}`, origem.tempo_s,
        r.a, r.b, v.parametros_do_detector, {}, escolha);
      comparar(ensaio.canal_A_carga_m, grupo.decimado_A, `${nome}.decimado_A`);
      comparar(ensaio.canal_B_carga_m, grupo.decimado_B, `${nome}.decimado_B`);
      const registro = LEAKMAP.detector.processarEnsaio(ensaio, grupo.escala);
      comparar(registro, v.registro, `${nome}/${v.velocidade}.registro`);
    }
  }
});

test("A-11 a A-15 sobre os 45 ensaios do pacote da matriz", () => {
  const escala = pacote.escala || {};
  const cal = LEAKMAP.detector.calibracaoPadrao();
  assert.strictEqual(gabarito.detector.length, pacote.ensaios.length);
  pacote.ensaios.forEach((ensaio, k) => {
    const esperado = gabarito.detector[k];
    assert.strictEqual(ensaio.id, esperado.id);
    comparar(LEAKMAP.detector.processarEnsaio(ensaio, escala, cal), esperado.registro,
      `${ensaio.id}.registro`);
    if (!esperado.intermediarios) { return; }
    const t = ensaio.tempo_s, diffs = [];
    for (let i = 1; i < t.length; i++) { diffs.push(t[i] - t[i - 1]); }
    diffs.sort((a, b) => a - b);
    const m = diffs.length >> 1;
    const ts = diffs.length % 2 ? diffs[m] : (diffs[m - 1] + diffs[m]) / 2;
    for (const canal of ["canal_A", "canal_B"]) {
      const r = LEAKMAP.detector.detectarCanal(ensaio[`${canal}_carga_m`], ts, cal,
        escala.resolucao_declarada_m);
      const inter = esperado.intermediarios[canal];
      comparar(r.y, inter.passa_altas, `${ensaio.id}.${canal}.passa_altas`);
      comparar(r.razao, inter.razao, `${ensaio.id}.${canal}.razao`);
      comparar(r.eLonga, inter.energia_longa, `${ensaio.id}.${canal}.energia_longa`);
    }
  });
});

test("classificacao por polaridade e origem igual a do Python", () => {
  assert.ok(gabarito.classificacao && gabarito.classificacao.length >= 9);
  for (const caso of gabarito.classificacao) {
    const r = LEAKMAP.detector.processarEnsaio(caso.ensaio, caso.escala, undefined, caso.classificar);
    comparar(r, caso.registro, `classificacao.${caso.nome}`);
  }
});

test("gerador do navegador: mesma estatistica do ruido gaussiano", () => {
  const z = LEAKMAP.modeloSensor.fonteAleatoria(42).normais("ruido_A", 200000);
  const media = z.reduce((s, v) => s + v, 0) / z.length;
  const desvio = Math.sqrt(z.reduce((s, v) => s + (v - media) ** 2, 0) / z.length);
  assert.ok(Math.abs(media) < 0.01, `media ${media}`);
  assert.ok(Math.abs(desvio - 1) < 0.01, `desvio ${desvio}`);
  const outro = LEAKMAP.modeloSensor.fonteAleatoria(42).normais("ruido_B", 1000);
  assert.notDeepStrictEqual(outro, z.slice(0, 1000), "canais precisam ser independentes");
});

test.after(() => {
  console.log(`maior diferenca relativa observada entre JavaScript e Python: ${maiorDiferenca.toExponential(2)}`);
});

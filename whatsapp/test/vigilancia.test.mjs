import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";

import { vigilarLlamada } from "../vigilancia.mjs";

const llamadaFalsa = () => {
  const l = new EventEmitter();
  l.colgada = false;
  l.end = () => {
    if (l.colgada) return;
    l.colgada = true;
    l.emit("ended", "hangup");
  };
  return l;
};
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

test("cuelga si nadie contesta", async () => {
  const l = llamadaFalsa();
  vigilarLlamada(l, { sinRespuestaMs: 40, cadaMs: 10 });
  await esperar(90);
  assert.ok(l.colgada);
});

test("cuelga si deja de llegar audio después de contestar", async () => {
  const l = llamadaFalsa();
  vigilarLlamada(l, { sinRespuestaMs: 1000, sinAudioMs: 50, cadaMs: 10 });
  l.emit("connected");
  for (let i = 0; i < 5; i += 1) {
    l.emit("audio", new Float32Array(320));
    await esperar(20);
  }
  assert.equal(l.colgada, false);
  await esperar(100);
  assert.ok(l.colgada);
});

test("deja de vigilar cuando la llamada termina", async () => {
  const l = llamadaFalsa();
  const detener = vigilarLlamada(l, { sinRespuestaMs: 30, cadaMs: 10 });
  l.emit("ended", "remote_end");
  let colgo = false;
  l.end = () => { colgo = true; };
  await esperar(80);
  assert.equal(colgo, false);
  detener();
});

import { esFinDeLlamada } from "../vigilancia.mjs";

const nodo = (tag, id) => ({ tag: "call", attrs: {}, content: [{ tag, attrs: { "call-id": id } }] });

test("reconoce cuando la otra persona cuelga o rechaza", () => {
  assert.equal(esFinDeLlamada(nodo("terminate", "ABC"), "abc"), "colgó");
  assert.equal(esFinDeLlamada(nodo("reject", "ABC"), "ABC"), "rechazó");
});

test("ignora otros avisos u otras llamadas", () => {
  assert.equal(esFinDeLlamada(nodo("accept", "ABC"), "ABC"), null);
  assert.equal(esFinDeLlamada(nodo("terminate", "OTRA"), "ABC"), null);
  assert.equal(esFinDeLlamada({ tag: "call" }, "ABC"), null);
});

import { debeReintentar } from "../vigilancia.mjs";

test("reintenta solo si falló el audio al contestar", () => {
  const base = { contestoEn: 1000, terminoEn: 7000, bloquesPersona: 0, reintentos: 0 };
  assert.equal(debeReintentar(base), true);
  assert.equal(debeReintentar({ ...base, reintentos: 1 }), false); // una sola vez
  assert.equal(debeReintentar({ ...base, contestoEn: 0 }), false); // no contestó
  assert.equal(debeReintentar({ ...base, bloquesPersona: 219 }), false); // sí hubo audio
  assert.equal(debeReintentar({ ...base, terminoEn: 60_000 }), false); // llamada normal
});

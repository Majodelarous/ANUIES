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

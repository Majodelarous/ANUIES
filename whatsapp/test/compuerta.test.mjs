import assert from "node:assert/strict";
import { test } from "node:test";

import { Compuerta, esperaReinicio } from "../compuerta.mjs";

test("las peticiones esperan hasta que el puente esté listo", async () => {
  const c = new Compuerta();
  let paso = false;
  const espera = c.esperar(1000).then(() => { paso = true; });
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(paso, false);
  c.abrir();
  await espera;
  assert.equal(paso, true);
});

test("con la compuerta abierta pasan de inmediato", async () => {
  const c = new Compuerta();
  c.abrir();
  await c.esperar(10);
  c.cerrar();
  assert.equal(c.abierta, false);
});

test("si el puente no llega a tiempo, la petición falla", async () => {
  await assert.rejects(new Compuerta().esperar(20), /a tiempo/);
});

test("la espera entre caídas crece y tiene tope", () => {
  assert.equal(esperaReinicio(1), 1000);
  assert.equal(esperaReinicio(3), 4000);
  assert.equal(esperaReinicio(20), 60000);
});

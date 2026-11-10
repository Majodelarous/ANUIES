import assert from "node:assert/strict";
import { test } from "node:test";

// Se importa el archivo parchado directamente para probar la fuente "push".
import { AudioFeeder } from "../node_modules/baileys-caller/dist/audio-feeder.mjs";
import { floatAPcm16, normalizarNumero, numeroDeJid, pcm16AFloat } from "../audio.mjs";

test("PCM de 16 bits ida y vuelta conserva la señal", () => {
  const original = new Float32Array([0, 0.5, -0.5, 0.999, -1]);
  const vuelta = pcm16AFloat(floatAPcm16(original));
  original.forEach((v, i) => assert.ok(Math.abs(v - vuelta[i]) < 1e-3));
});

test("satura valores fuera de rango", () => {
  const pcm = floatAPcm16(new Float32Array([2, -2]));
  assert.equal(pcm.readInt16LE(0), 32767);
  assert.equal(pcm.readInt16LE(2), -32768);
});

test("normaliza y valida números", () => {
  assert.equal(normalizarNumero("+52 222 123 4567"), "522221234567");
  assert.equal(normalizarNumero("222 123 4567"), "522221234567");
  assert.throws(() => normalizarNumero("12345"));
  assert.equal(numeroDeJid("5212221234567:3@s.whatsapp.net"), "5212221234567");
});

test("la fuente push entrega bloques en orden y silencio cuando falta audio", async () => {
  const bloques = [];
  const feeder = new AudioFeeder(16000, 1, 320, (b) => bloques.push(b), "push");
  feeder.start();
  feeder.push(new Float32Array(480).fill(0.25)); // 1.5 bloques
  feeder.push(new Float32Array(160).fill(0.25)); // completa el segundo
  await new Promise((r) => setTimeout(r, 120));
  feeder.stop();
  assert.ok(bloques.length >= 3);
  assert.equal(bloques[0].length, 320);
  assert.equal(bloques[0][0], 0.25);
  assert.equal(bloques[1][319], 0.25);
  assert.equal(bloques[2][0], 0); // ya no hay audio: silencio
});

test("clear descarta el audio pendiente", async () => {
  const bloques = [];
  const feeder = new AudioFeeder(16000, 1, 320, (b) => bloques.push(b), "push");
  feeder.start();
  feeder.push(new Float32Array(320 * 50).fill(0.5));
  await new Promise((r) => setTimeout(r, 30));
  feeder.clear();
  const antes = bloques.length;
  await new Promise((r) => setTimeout(r, 60));
  feeder.stop();
  assert.ok(antes < 50);
  assert.ok(bloques.slice(antes).every((b) => b[0] === 0));
});

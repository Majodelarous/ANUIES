import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { cargarEnv, clasificarMensaje, notaAWav, wavDesdePcm } from "../mensajes.mjs";

const GRUPO = "123@g.us";
const msg = (contenido, extra = {}) => ({
  key: { remoteJid: GRUPO, fromMe: false, ...extra },
  pushName: "Majo",
  contenido,
});

test("toda nota de voz del grupo es para la persona", () => {
  const info = clasificarMensaje(msg({ audioMessage: { seconds: 7 } }), GRUPO);
  assert.deepEqual(info, { tipo: "voz", de: "Majo", segundos: 7 });
  const largo = clasificarMensaje({ ...msg({ audioMessage: {} }), pushName: "Fortino Romero" }, GRUPO);
  assert.equal(largo.de, "Fortino");
});

test("texto con el prefijo cuenta, aunque lleve acento o mayúsculas", () => {
  assert.equal(clasificarMensaje(msg({ conversation: "Abue, el sábado voy" }), GRUPO).texto, "Abue, el sábado voy");
  assert.equal(clasificarMensaje(msg({ extendedTextMessage: { text: "ABUE: la quiero" } }), GRUPO).tipo, "texto");
});

test("la plática normal del grupo no se le pasa", () => {
  assert.equal(clasificarMensaje(msg({ conversation: "¿Quién lleva el pastel?" }), GRUPO), null);
  assert.equal(clasificarMensaje(msg({ conversation: "abuelita linda" }), GRUPO), null);
});

test("ignora mensajes propios, de otros chats o sin grupo", () => {
  assert.equal(clasificarMensaje(msg({ audioMessage: {} }, { fromMe: true }), GRUPO), null);
  assert.equal(clasificarMensaje(msg({ audioMessage: {} }, { remoteJid: "52@s.whatsapp.net" }), GRUPO), null);
  assert.equal(clasificarMensaje(msg({ audioMessage: {} }), null), null);
});

test("el WAV lleva tamaños correctos", () => {
  const wav = wavDesdePcm(Buffer.alloc(3200), 16000);
  assert.equal(wav.length, 44 + 3200);
  assert.equal(wav.toString("ascii", 0, 4), "RIFF");
  assert.equal(wav.readUInt32LE(40), 3200);
  assert.equal(wav.readUInt32LE(24), 16000);
});

test("convierte una nota ogg/opus a WAV de 16 kHz", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nota-"));
  const ogg = join(dir, "nota.ogg");
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
    "sine=frequency=440:duration=1", "-c:a", "libopus", "-ar", "48000", ogg]);
  const { readFileSync } = await import("node:fs");
  const wav = await notaAWav(readFileSync(ogg));
  const muestras = wav.readUInt32LE(40) / 2;
  assert.ok(Math.abs(muestras - 16000) < 800, `muestras: ${muestras}`);
});

test("lee el .env sin pisar lo que ya existe", () => {
  const dir = mkdtempSync(join(tmpdir(), "env-"));
  const ruta = join(dir, ".env");
  process.env.PRUEBA_YA = "original";
  writeFileSync(ruta, 'PRUEBA_YA=otro\nPRUEBA_NUEVA="Familia Test"\n# comentario\n');
  cargarEnv(ruta);
  assert.equal(process.env.PRUEBA_YA, "original");
  assert.equal(process.env.PRUEBA_NUEVA, "Familia Test");
});

import { wavAOggOpus } from "../mensajes.mjs";

test("convierte un WAV a nota de voz ogg/opus", async () => {
  const pcm = Buffer.alloc(16000 * 2); // 1 s de silencio
  const ogg = await wavAOggOpus(wavDesdePcm(pcm, 16000));
  assert.equal(ogg.toString("ascii", 0, 4), "OggS");
});

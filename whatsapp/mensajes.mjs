/**
 * Utilidades puras para los mensajes de la familia: configuración, clasificación y audio.
 */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

/** Lee un archivo .env sencillo (CLAVE=valor) sin pisar variables que ya existan. */
export const cargarEnv = (ruta) => {
  if (!existsSync(ruta)) return {};
  const leidas = {};
  for (const linea of readFileSync(ruta, "utf8").split(/\r?\n/)) {
    const m = linea.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!m) continue;
    const valor = m[2].replace(/^(['"])(.*)\1$/, "$2");
    leidas[m[1]] = valor;
    if (process.env[m[1]] === undefined) process.env[m[1]] = valor;
  }
  return leidas;
};

const sinAcentos = (texto) => texto.normalize("NFD").replace(/[̀-ͯ]/g, "");

/**
 * Decide si un mensaje de WhatsApp es para la persona mayor.
 *
 * Solo cuenta lo que llega al grupo de la familia y no lo mandó la asistente:
 * - toda nota de voz;
 * - texto que empieza con el prefijo (por omisión "abue"), por ejemplo "Abue, el sábado voy".
 *
 * `contenido` es el mensaje ya normalizado (sin envolturas de mensajes temporales).
 */
export const clasificarMensaje = ({ key, pushName, contenido }, grupoJid, prefijo = "abue") => {
  if (!key || key.fromMe || !grupoJid || key.remoteJid !== grupoJid || !contenido) return null;
  // Solo el primer nombre: "Ana López" queda "Ana"
  const de = (pushName || "Alguien de la familia").trim().split(/\s+/)[0].slice(0, 60);
  if (contenido.audioMessage) {
    return { tipo: "voz", de, segundos: Number(contenido.audioMessage.seconds || 0) };
  }
  const texto = (contenido.conversation || contenido.extendedTextMessage?.text || "").trim();
  if (!texto) return null;
  const inicio = new RegExp(`^${sinAcentos(prefijo)}\\b[\\s,:.!-]*`, "i");
  if (!inicio.test(sinAcentos(texto))) return null;
  return { tipo: "texto", de, texto: texto.slice(0, 1000) };
};

/** Últimos 10 dígitos de un JID o número: ignora el 52/521 de México y el sufijo del servidor. */
export const ultimos10 = (jid) => String(jid ?? "").split("@")[0].split(":")[0].replace(/\D/g, "").slice(-10);

/**
 * ¿Es una imagen que mandó la persona mayor? Para buscarle imágenes parecidas (tipo Google Lens).
 *
 * WhatsApp puede identificar al remitente por número o por LID (un id anónimo), así que se
 * revisan todos los campos donde puede venir su número.
 * Devuelve "privado" (se la mandó a la asistente), "grupo" (la compartió en el grupo) o null.
 */
export const imagenDeLaPersona = ({ key, contenido }, numeroPersona, grupoJid = null) => {
  const persona = ultimos10(numeroPersona);
  if (!key || key.fromMe || !persona || persona.length < 10 || !contenido?.imageMessage) return null;
  const enGrupo = String(key.remoteJid || "").endsWith("@g.us");
  const candidatos = enGrupo
    ? [key.participant, key.participantAlt, key.participantPn]
    : [key.remoteJid, key.remoteJidAlt, key.senderPn];
  if (!candidatos.some((jid) => jid && ultimos10(jid) === persona)) return null;
  if (enGrupo) return key.remoteJid === grupoJid ? "grupo" : null;
  return "privado";
};

/** Arma un WAV (PCM 16 bits, mono) con los tamaños correctos. */
export const wavDesdePcm = (pcm, frecuencia = 16000) => {
  const cabecera = Buffer.alloc(44);
  cabecera.write("RIFF", 0);
  cabecera.writeUInt32LE(36 + pcm.length, 4);
  cabecera.write("WAVE", 8);
  cabecera.write("fmt ", 12);
  cabecera.writeUInt32LE(16, 16);
  cabecera.writeUInt16LE(1, 20); // PCM
  cabecera.writeUInt16LE(1, 22); // mono
  cabecera.writeUInt32LE(frecuencia, 24);
  cabecera.writeUInt32LE(frecuencia * 2, 28);
  cabecera.writeUInt16LE(2, 32);
  cabecera.writeUInt16LE(16, 34);
  cabecera.write("data", 36);
  cabecera.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([cabecera, pcm]);
};

/** Convierte una nota de voz (ogg/opus u otro formato) a WAV de 16 kHz mono con ffmpeg. */
export const notaAWav = (audio, frecuencia = 16000) =>
  new Promise((resolve, reject) => {
    const ffmpeg = spawn("ffmpeg", [
      "-hide_banner", "-loglevel", "error",
      "-i", "pipe:0",
      "-ac", "1", "-ar", String(frecuencia), "-f", "s16le", "pipe:1",
    ]);
    const partes = [];
    let error = "";
    ffmpeg.stdout.on("data", (d) => partes.push(d));
    ffmpeg.stderr.on("data", (d) => { error += d; });
    ffmpeg.on("error", reject);
    ffmpeg.on("close", (codigo) => {
      if (codigo !== 0) return reject(new Error(`ffmpeg falló: ${error.trim() || codigo}`));
      resolve(wavDesdePcm(Buffer.concat(partes), frecuencia));
    });
    ffmpeg.stdin.on("error", () => {});
    ffmpeg.stdin.end(audio);
  });

/** Convierte un WAV a nota de voz de WhatsApp (ogg/opus mono). */
export const wavAOggOpus = (wav) =>
  new Promise((resolve, reject) => {
    const ffmpeg = spawn("ffmpeg", [
      "-hide_banner", "-loglevel", "error",
      "-i", "pipe:0",
      "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
    ]);
    const partes = [];
    let error = "";
    ffmpeg.stdout.on("data", (d) => partes.push(d));
    ffmpeg.stderr.on("data", (d) => { error += d; });
    ffmpeg.on("error", reject);
    ffmpeg.on("close", (codigo) => {
      if (codigo !== 0) return reject(new Error(`ffmpeg falló: ${error.trim() || codigo}`));
      resolve(Buffer.concat(partes));
    });
    ffmpeg.stdin.on("error", () => {});
    ffmpeg.stdin.end(wav);
  });

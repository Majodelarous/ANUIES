/**
 * Puente entre WhatsApp y el agente de Compañía por voz.
 *
 * Mantiene la sesión de WhatsApp de la asistente (vinculada como dispositivo con un QR) y,
 * cuando se le pide, hace una llamada de voz y conecta su audio con el bot por websocket.
 *
 *   npm start                     # la primera vez muestra un QR: WhatsApp > Dispositivos vinculados
 *   POST http://127.0.0.1:7864/llamar  {"numero": "522221234567"}
 *
 * Variables: WA_AUTH_DIR (./auth), PUENTE_PUERTO (7864), BOT_WS_URL (ws://127.0.0.1:7863/wa),
 * DURACION_MAX_MIN (15).
 */
import { createServer } from "node:http";
import { VoipClient } from "baileys-caller";
import WebSocket from "ws";

import { floatAPcm16, normalizarNumero, numeroDeJid, pcm16AFloat } from "./audio.mjs";

const AUTH_DIR = process.env.WA_AUTH_DIR || "./auth";
const PUERTO = Number(process.env.PUENTE_PUERTO || 7864);
const BOT_WS_URL = process.env.BOT_WS_URL || "ws://127.0.0.1:7863/wa";
const DURACION_MAX_MS = Number(process.env.DURACION_MAX_MIN || 15) * 60_000;

const cliente = new VoipClient({ authDir: AUTH_DIR });
let ocupado = false;

const log = (...args) => console.log(new Date().toISOString().slice(11, 19), ...args);

/** Busca el número tal como lo registra WhatsApp (en México puede ser 52 o 521). */
const resolverNumero = async (digitos) => {
  try {
    const [resultado] = (await cliente.socket?.onWhatsApp(digitos)) ?? [];
    if (resultado?.exists === false) throw new Error(`El número ${digitos} no tiene WhatsApp`);
    return resultado?.jid ? numeroDeJid(resultado.jid) : digitos;
  } catch (error) {
    if (String(error.message).includes("no tiene WhatsApp")) throw error;
    log("No se pudo verificar el número; se intenta tal cual:", error.message);
    return digitos;
  }
};

/** Conecta una llamada contestada con el bot. */
const conectarConBot = (llamada) => {
  const ws = new WebSocket(BOT_WS_URL);
  let abierto = false;

  ws.on("open", () => {
    abierto = true;
    log("Bot conectado");
  });
  ws.on("message", (datos, esBinario) => {
    if (!esBinario) {
      if (datos.toString() === "clear") llamada.clearAudio();
      return;
    }
    llamada.pushAudio(pcm16AFloat(Buffer.from(datos)));
  });
  ws.on("close", () => {
    log("El bot cerró la conexión; se cuelga");
    llamada.end();
  });
  ws.on("error", (error) => {
    log("Error con el bot:", error.message, "¿Está corriendo uv run compania-whatsapp?");
    llamada.end();
  });

  llamada.on("audio", (muestras) => {
    if (abierto && ws.readyState === WebSocket.OPEN) ws.send(floatAPcm16(muestras));
  });
  llamada.on("ended", () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
  });
};

const llamar = async (digitos) => {
  const numero = await resolverNumero(digitos);
  log(`Llamando a ${numero}...`);
  const llamada = await cliente.call(numero, { audioSource: "push", durationMs: DURACION_MAX_MS });
  ocupado = true;
  llamada.on("ringing", () => log("Sonando"));
  llamada.on("connected", () => {
    log("Contestó");
    conectarConBot(llamada);
  });
  llamada.on("error", (error) => log("Error en la llamada:", error.message));
  llamada.on("ended", (motivo) => {
    ocupado = false;
    log("Llamada terminada:", motivo);
  });
  return llamada.callId;
};

const responder = (res, codigo, cuerpo) => {
  res.writeHead(codigo, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(cuerpo));
};

const leerJson = (req) =>
  new Promise((resolve, reject) => {
    let texto = "";
    req.on("data", (parte) => {
      texto += parte;
      if (texto.length > 4096) reject(new Error("Petición demasiado grande"));
    });
    req.on("end", () => {
      try {
        resolve(texto ? JSON.parse(texto) : {});
      } catch {
        reject(new Error("JSON inválido"));
      }
    });
  });

const servidor = createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/estado") {
    return responder(res, 200, { conectado: Boolean(cliente.socket), en_llamada: ocupado });
  }
  if (req.method !== "POST" || req.url !== "/llamar") {
    return responder(res, 404, { error: "Ruta no encontrada" });
  }
  try {
    const { numero } = await leerJson(req);
    const digitos = normalizarNumero(numero);
    if (ocupado) return responder(res, 409, { error: "Ya hay una llamada en curso" });
    const callId = await llamar(digitos);
    return responder(res, 200, { mensaje: `Llamando por WhatsApp a ${digitos}...`, llamada: callId });
  } catch (error) {
    ocupado = false;
    log("No se pudo llamar:", error.message);
    return responder(res, 400, { error: error.message });
  }
});

log("Conectando con WhatsApp (si aparece un QR, escanéalo desde el celular de la asistente)...");
await cliente.connect();
servidor.listen(PUERTO, "127.0.0.1", () => {
  log(`Listo. Puente en http://127.0.0.1:${PUERTO}  (bot: ${BOT_WS_URL})`);
});

const cerrar = () => {
  log("Cerrando sesión del puente");
  servidor.close();
  cliente.disconnect();
  process.exit(0);
};
process.on("SIGINT", cerrar);
process.on("SIGTERM", cerrar);

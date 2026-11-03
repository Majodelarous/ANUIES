/**
 * Puente entre WhatsApp y el agente de Compañía por voz.
 *
 * Mantiene la sesión de WhatsApp de la asistente (vinculada como dispositivo con un QR) y,
 * cuando se le pide, hace una llamada de voz y conecta su audio con el bot por websocket.
 *
 *   npm start                     # la primera vez muestra un QR: WhatsApp > Dispositivos vinculados
 *   POST http://127.0.0.1:7864/llamar  {"numero": "522221234567"}
 *   POST http://127.0.0.1:7864/enviar  {"texto": "..."}   # al grupo de la familia
 *   POST http://127.0.0.1:7864/colgar                      # cuelga y libera el puente
 *
 * También escucha el grupo de la familia (WHATSAPP_GRUPO): las notas de voz y los textos que
 * empiezan con "abue" se guardan en el bot para la próxima llamada.
 *
 * Lee ../agente/.env. Variables: WHATSAPP_GRUPO, WHATSAPP_PREFIJO (abue), WA_AUTH_DIR (./auth),
 * WHATSAPP_PUENTE_PUERTO (7864), WHATSAPP_BOT_PUERTO (7863), DURACION_MAX_MIN (15).
 */
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { downloadMediaMessage, normalizeMessageContent } from "@whiskeysockets/baileys";
import { VoipClient } from "baileys-caller";
import WebSocket from "ws";

import { floatAPcm16, normalizarNumero, numeroDeJid, pcm16AFloat } from "./audio.mjs";
import { cargarEnv, clasificarMensaje, notaAWav } from "./mensajes.mjs";
import { vigilarLlamada } from "./vigilancia.mjs";

cargarEnv(join(dirname(fileURLToPath(import.meta.url)), "..", "agente", ".env"));

const AUTH_DIR = process.env.WA_AUTH_DIR || "./auth";
const PUERTO = Number(process.env.WHATSAPP_PUENTE_PUERTO || process.env.PUENTE_PUERTO || 7864);
const BOT_PUERTO = Number(process.env.WHATSAPP_BOT_PUERTO || 7863);
const BOT_WS_URL = process.env.BOT_WS_URL || `ws://127.0.0.1:${BOT_PUERTO}/wa`;
const BOT_HTTP_URL = `http://127.0.0.1:${BOT_PUERTO}`;
const DURACION_MAX_MS = Number(process.env.DURACION_MAX_MIN || 15) * 60_000;
const GRUPO = (process.env.WHATSAPP_GRUPO || "").trim();
const PREFIJO = process.env.WHATSAPP_PREFIJO || "abue";
const SIN_AUDIO_MS = Number(process.env.WHATSAPP_SIN_AUDIO_S || 20) * 1000;

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
  vigilarLlamada(llamada, { sinAudioMs: SIN_AUDIO_MS, log });
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

// --- Grupo de la familia ---------------------------------------------------

let grupoJid = null;

const buscarGrupo = async () => {
  if (!GRUPO) return null;
  const grupos = await cliente.socket.groupFetchAllParticipating();
  const encontrado = Object.values(grupos).find(
    (g) => (g.subject || "").trim().toLowerCase() === GRUPO.toLowerCase(),
  );
  grupoJid = encontrado?.id ?? null;
  if (grupoJid) log(`Grupo de la familia: "${encontrado.subject}"`);
  else log(`No encontré el grupo "${GRUPO}". Revisa que el número de la asistente esté en el grupo.`);
  return grupoJid;
};

const enviarAlGrupo = async (texto) => {
  const jid = grupoJid ?? (await buscarGrupo());
  if (!jid) throw new Error(`No hay grupo "${GRUPO || "(WHATSAPP_GRUPO vacío)"}"`);
  await cliente.socket.sendMessage(jid, { text: texto });
  log("Mensaje enviado al grupo");
};

/** Guarda en el bot un mensaje para la persona y confirma en el grupo. */
const guardarParaLaPersona = async (msg, info) => {
  const cuerpo = { de: info.de, texto: info.texto ?? "" };
  if (info.tipo === "voz") {
    const audio = await downloadMediaMessage(msg, "buffer", {}, {
      reuploadRequest: cliente.socket.updateMediaMessage,
    });
    cuerpo.audio_wav_b64 = (await notaAWav(audio)).toString("base64");
  }
  const respuesta = await fetch(`${BOT_HTTP_URL}/mensajes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) throw new Error(datos.detail || `el bot respondió ${respuesta.status}`);
  log(`Guardado ${info.tipo === "voz" ? "nota de voz" : "mensaje"} de ${info.de}`);
  await cliente.socket.sendMessage(
    msg.key.remoteJid,
    { text: `Listo, ${info.de}. Se lo paso a ${datos.trato} en la próxima llamada.` },
    { quoted: msg },
  );
};

const escucharGrupo = () => {
  cliente.socket.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify" || !grupoJid) return;
    for (const msg of messages) {
      const info = clasificarMensaje(
        { key: msg.key, pushName: msg.pushName, contenido: normalizeMessageContent(msg.message) },
        grupoJid,
        PREFIJO,
      );
      if (!info) continue;
      guardarParaLaPersona(msg, info).catch((error) => {
        log("No se pudo guardar el mensaje:", error.message, "¿Está corriendo uv run compania-whatsapp?");
      });
    }
  });
};

// --- API local --------------------------------------------------------------

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
    return responder(res, 200, { conectado: Boolean(cliente.socket), en_llamada: ocupado, grupo: Boolean(grupoJid) });
  }
  if (req.method === "POST" && req.url === "/colgar") {
    const llamada = cliente.activeCall;
    if (llamada) llamada.end();
    ocupado = false;
    log(llamada ? "Llamada colgada a mano" : "No había llamada; se libera el puente");
    return responder(res, 200, { mensaje: llamada ? "Llamada colgada" : "No había llamada en curso" });
  }
  if (req.method === "POST" && req.url === "/enviar") {
    try {
      const { texto } = await leerJson(req);
      if (!texto || typeof texto !== "string") return responder(res, 400, { error: "Falta el texto" });
      await enviarAlGrupo(texto.slice(0, 4000));
      return responder(res, 200, { enviado: true });
    } catch (error) {
      log("No se pudo enviar al grupo:", error.message);
      return responder(res, 502, { error: error.message });
    }
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
if (GRUPO) {
  await buscarGrupo().catch((error) => log("No se pudo leer los grupos:", error.message));
  escucharGrupo();
} else {
  log("WHATSAPP_GRUPO vacío: no se escuchan ni se envían mensajes de la familia");
}
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

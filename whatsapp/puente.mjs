/**
 * Puente entre WhatsApp y el agente de Compañía por voz.
 *
 * Mantiene la sesión de WhatsApp de la asistente (vinculada como dispositivo con un QR) y,
 * cuando se le pide, hace una llamada de voz y conecta su audio con el bot por websocket.
 *
 *   npm start                     # arranca el supervisor, que levanta este puente (ver supervisor.mjs)
 *   npm run puente                # solo el puente, sin supervisor (para pruebas)
 *
 * Bajo el supervisor, el puente atiende una llamada y al terminar se cierra; el supervisor lo
 * vuelve a levantar limpio para la siguiente.
 *
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
import { debeReintentar, esFinDeLlamada, vigilarLlamada } from "./vigilancia.mjs";

cargarEnv(join(dirname(fileURLToPath(import.meta.url)), "..", "agente", ".env"));

const AUTH_DIR = process.env.WA_AUTH_DIR || "./auth";
const BAJO_SUPERVISOR = process.env.BAJO_SUPERVISOR === "1" && typeof process.send === "function";
const PUERTO = BAJO_SUPERVISOR
  ? Number(process.env.WHATSAPP_PUENTE_INTERNO || 7865)
  : Number(process.env.WHATSAPP_PUENTE_PUERTO || process.env.PUENTE_PUERTO || 7864);
const BOT_PUERTO = Number(process.env.WHATSAPP_BOT_PUERTO || 7863);
const BOT_WS_URL = process.env.BOT_WS_URL || `ws://127.0.0.1:${BOT_PUERTO}/wa`;
const BOT_HTTP_URL = `http://127.0.0.1:${BOT_PUERTO}`;
const DURACION_MAX_MS = Number(process.env.DURACION_MAX_MIN || 15) * 60_000;
const GRUPO = (process.env.WHATSAPP_GRUPO || "").trim();
const PREFIJO = process.env.WHATSAPP_PREFIJO || "abue";
const SIN_AUDIO_MS = Number(process.env.WHATSAPP_SIN_AUDIO_S || 30) * 1000;
const SIN_RESPUESTA_MS = Number(process.env.WHATSAPP_SIN_RESPUESTA_S || 90) * 1000;

const cliente = new VoipClient({ authDir: AUTH_DIR });
// La llamada en curso la lleva la librería (cliente.activeCall). "marcando" cubre los segundos
// en que se prepara la llamada, y la pausa deja que lleguen los últimos eventos de la anterior.
const PAUSA_ENTRE_LLAMADAS_MS = 4_000;
let marcando = false;
let finUltimaLlamada = 0;
const ocupado = () => marcando || Boolean(cliente.activeCall);

const DIAGNOSTICO = (process.env.WHATSAPP_DIAGNOSTICO ?? "1") !== "0";

// libsignal imprime cada sesión que abre o cierra, con llaves de cifrado incluidas: se omite.
const RUIDO = /^(Closing session|Opening session|Closing open session|Removing old closed session|Session already|Migrating session|Blocking on the main thread)/;
for (const metodo of ["log", "info", "warn"]) {
  const original = console[metodo].bind(console);
  console[metodo] = (...args) => {
    if (typeof args[0] === "string" && RUIDO.test(args[0])) return;
    original(...args);
  };
}

const hora = () => new Date().toLocaleTimeString("es-MX", { hour12: false });
const log = (...args) => console.log(hora(), ...args);
const resumir = (texto, max = 240) => {
  const t = typeof texto === "string" ? texto : JSON.stringify(texto);
  return t.length > max ? `${t.slice(0, max)}…` : t;
};

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
const conectarConBot = (llamada, motivo) => {
  const ws = new WebSocket(`${BOT_WS_URL}?motivo=${encodeURIComponent(motivo)}`);
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

  // Contadores de audio para diagnóstico: bloques de la persona y de la asistente cada 5 s
  const cuenta = { persona: 0, asistente: 0 };
  ws.on("message", (_datos, esBinario) => {
    if (esBinario) cuenta.asistente += 1;
  });
  const medidor = DIAGNOSTICO
    ? setInterval(() => {
        log(`Audio 5 s: persona ${cuenta.persona} bloques, asistente ${cuenta.asistente} bloques`);
        cuenta.persona = 0;
        cuenta.asistente = 0;
      }, 5_000)
    : null;

  llamada.on("audio", (muestras) => {
    cuenta.persona += 1;
    if (abierto && ws.readyState === WebSocket.OPEN) ws.send(floatAPcm16(muestras));
  });
  llamada.on("ended", () => {
    if (medidor) clearInterval(medidor);
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
  });
};

const avisarSupervisor = (mensaje) => {
  if (BAJO_SUPERVISOR) process.send(mensaje);
};

const llamar = async (digitos, reintentos = 0, motivo = "manual") => {
  marcando = true;
  let llamada;
  try {
    const espera = finUltimaLlamada + PAUSA_ENTRE_LLAMADAS_MS - Date.now();
    if (espera > 0) {
      log(`Esperando ${Math.ceil(espera / 1000)} s a que cierre la llamada anterior`);
      await new Promise((r) => setTimeout(r, espera));
    }
    const numero = await resolverNumero(digitos);
    log(`Llamando a ${numero}...`);
    llamada = await cliente.call(numero, { audioSource: "push", durationMs: DURACION_MAX_MS });
    avisarSupervisor({ tipo: "llamada", callId: llamada.callId, numero: digitos, motivo });
  } finally {
    marcando = false;
  }
  // Para decidir si se reintenta: cuándo contestó y cuánto audio de la persona llegó
  const seguimiento = { contestoEn: 0, bloquesPersona: 0 };
  llamada.on("connected", () => { seguimiento.contestoEn = Date.now(); });
  // Solo cuenta el audio después de contestar: mientras suena también llega audio (el tono)
  llamada.on("audio", () => {
    if (seguimiento.contestoEn) seguimiento.bloquesPersona += 1;
  });

  // waitForEnd se resuelve aunque la llamada haya terminado antes de llegar aquí
  llamada.waitForEnd().then((motivo) => {
    finUltimaLlamada = Date.now();
    log("Llamada terminada:", motivo);
    const reintentar = debeReintentar({ ...seguimiento, terminoEn: finUltimaLlamada, reintentos });
    if (reintentar) log("El audio no se conectó al contestar; se vuelve a marcar una vez");

    if (BAJO_SUPERVISOR) {
      // Proceso nuevo para la siguiente llamada (y para el reintento, si toca)
      process.send({
        tipo: "fin",
        contesto: Boolean(seguimiento.contestoEn),
        reintentar: reintentar ? { numero: digitos, motivo } : null,
      });
      setTimeout(() => {
        servidor.close();
        cliente.disconnect();
        process.exit(0);
      }, 1_500);
    } else if (reintentar) {
      llamar(digitos, reintentos + 1, motivo).catch((error) => log("No se pudo reintentar:", error.message));
    }
  });
  if (DIAGNOSTICO) {
    // Se omiten los eventos que se repiten varias veces por segundo (niveles de audio, relays)
    const RUIDOSOS = new Set(["tipo 100", "tipo 156"]);
    llamada.on("evento", (nombre, datos) => {
      if (!RUIDOSOS.has(nombre)) log("Evento del motor:", nombre, resumir(datos, 160));
    });
  }
  vigilarLlamada(llamada, { sinAudioMs: SIN_AUDIO_MS, sinRespuestaMs: SIN_RESPUESTA_MS, log });
  llamada.on("estado", (estado) => log("Estado de la llamada:", estado));
  llamada.on("ringing", () => log("Sonando"));
  llamada.on("connected", () => {
    log("Contestó");
    avisarSupervisor({ tipo: "contesto" });
    conectarConBot(llamada, motivo);
  });
  llamada.on("error", (error) => log("Error en la llamada:", error.message));
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
    {
      text: info.tipo === "voz"
        ? `Gracias, ${info.de.split(" ")[0]}. En la próxima llamada le pongo su audio a ${datos.trato}.`
        : `Gracias, ${info.de.split(" ")[0]}. Se lo digo a ${datos.trato} en la próxima llamada.`,
    },
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
    return responder(res, 200, { conectado: Boolean(cliente.socket), en_llamada: ocupado(), grupo: Boolean(grupoJid) });
  }
  if (req.method === "POST" && req.url === "/colgar") {
    const llamada = cliente.activeCall;
    if (llamada) llamada.end();
    marcando = false;
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
    const { numero, motivo = "manual" } = await leerJson(req);
    if (!/^(manual|programada|recordatorio:\d+)$/.test(motivo)) {
      return responder(res, 400, { error: "Motivo inválido" });
    }
    const digitos = normalizarNumero(numero);
    if (ocupado()) {
      return responder(res, 409, {
        error: "Ya hay una llamada en curso. Si ya colgaste, usa: uv run compania-llamar-wa --colgar",
      });
    }
    const callId = await llamar(digitos, 0, motivo);
    return responder(res, 200, { mensaje: `Llamando por WhatsApp a ${digitos}...`, llamada: callId });
  } catch (error) {
    log("No se pudo llamar:", error.message);
    return responder(res, 400, { error: error.message });
  }
});

log("Conectando con WhatsApp (si aparece un QR, escanéalo desde el celular de la asistente)...");
await cliente.connect();

// Aviso directo de WhatsApp cuando la otra persona cuelga o rechaza. No depende de los
// estados del motor de llamadas, que no siempre reporta el fin.
cliente.socket.ws.on("CB:call", (nodo) => {
  const llamada = cliente.activeCall;
  if (DIAGNOSTICO) {
    const hijo = Array.isArray(nodo?.content) ? nodo.content[0] : null;
    if (hijo?.tag !== "relaylatency") log("Aviso de WhatsApp:", hijo?.tag ?? "?", hijo?.attrs?.["call-id"] ?? "", llamada ? `(activa ${llamada.callId})` : "(sin llamada)");
  }
  const fin = llamada && esFinDeLlamada(nodo, llamada.callId);
  if (fin) {
    log(`La otra persona ${fin} la llamada`);
    llamada.end();
  }
});
if (GRUPO) {
  await buscarGrupo().catch((error) => log("No se pudo leer los grupos:", error.message));
  escucharGrupo();
} else {
  log("WHATSAPP_GRUPO vacío: no se escuchan ni se envían mensajes de la familia");
}
servidor.listen(PUERTO, "127.0.0.1", () => {
  log(`Listo. Puente en http://127.0.0.1:${PUERTO}  (bot: ${BOT_WS_URL})`);
  if (BAJO_SUPERVISOR) process.send({ tipo: "listo" });
});

const cerrar = () => {
  log("Cerrando sesión del puente");
  servidor.close();
  cliente.disconnect();
  process.exit(0);
};
process.on("SIGINT", cerrar);
process.on("SIGTERM", cerrar);

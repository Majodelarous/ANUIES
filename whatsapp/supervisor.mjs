/**
 * Supervisor del puente de WhatsApp.
 *
 * Cada llamada corre en un proceso de puente nuevo: al terminar una llamada el puente se cierra
 * y aquí se vuelve a levantar limpio. La librería de llamadas guarda estado interno (motor,
 * conexiones de audio) que hace fallar la siguiente llamada si se reutiliza el proceso.
 *
 * El supervisor atiende siempre el puerto público (7864) y reenvía al puente. Si el puente se
 * está reiniciando, la petición espera a que esté listo (por ejemplo, el resumen que el bot
 * manda al grupo justo al colgar).
 *
 *   npm start
 */
import { fork } from "node:child_process";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Compuerta, esperaReinicio } from "./compuerta.mjs";
import { cargarEnv } from "./mensajes.mjs";

const AQUI = dirname(fileURLToPath(import.meta.url));
cargarEnv(join(AQUI, "..", "agente", ".env"));

const PUERTO = Number(process.env.WHATSAPP_PUENTE_PUERTO || 7864);
const PUERTO_INTERNO = Number(process.env.WHATSAPP_PUENTE_INTERNO || 7865);
const ESPERA_MAX_MS = 90_000;

const hora = () => new Date().toLocaleTimeString("es-MX", { hour12: false });
const log = (...args) => console.log(hora(), "[supervisor]", ...args);

const compuerta = new Compuerta();
let puente = null;
let cerrando = false;
let caidasSeguidas = 0;
let reintentoPendiente = null;
// Resultado de la última llamada, para el programador (sobrevive a los reinicios del puente)
let ultima = null;

const levantar = () => {
  const inicio = Date.now();
  compuerta.cerrar();
  puente = fork(join(AQUI, "puente.mjs"), [], {
    env: { ...process.env, WHATSAPP_PUENTE_INTERNO: String(PUERTO_INTERNO), BAJO_SUPERVISOR: "1" },
  });

  puente.on("message", (m) => {
    if (m?.tipo === "listo") {
      caidasSeguidas = 0;
      compuerta.abrir();
      if (reintentoPendiente) {
        const pendiente = reintentoPendiente;
        reintentoPendiente = null;
        log("Volviendo a marcar con un puente nuevo");
        reenviar("POST", "/llamar", JSON.stringify(pendiente)).catch((e) => log("Reintento fallido:", e.message));
      }
    } else if (m?.tipo === "llamada") {
      ultima = { callId: m.callId, numero: m.numero, motivo: m.motivo, inicio: Date.now(), contesto: false, terminada: false };
    } else if (m?.tipo === "contesto") {
      if (ultima) ultima.contesto = true;
    } else if (m?.tipo === "fin") {
      if (ultima) {
        ultima.terminada = !m.reintentar; // si se reintenta, la llamada sigue "en curso"
        ultima.contesto = ultima.contesto || Boolean(m.contesto);
      }
      // El puente terminó su llamada y se va a cerrar: lo que llegue espera al siguiente
      compuerta.cerrar();
      if (m.reintentar) reintentoPendiente = m.reintentar;
    }
  });

  puente.on("exit", (codigo) => {
    compuerta.cerrar();
    puente = null;
    if (cerrando) return;
    if (codigo !== 0 && Date.now() - inicio < 30_000) caidasSeguidas += 1;
    const espera = codigo === 0 ? 500 : esperaReinicio(caidasSeguidas);
    log(codigo === 0 ? "Puente cerrado tras la llamada; se reinicia" : `El puente se cayó (código ${codigo}); se reinicia en ${espera / 1000} s`);
    setTimeout(levantar, espera);
  });
};

const reenviar = async (metodo, ruta, cuerpo) => {
  await compuerta.esperar(ESPERA_MAX_MS);
  const respuesta = await fetch(`http://127.0.0.1:${PUERTO_INTERNO}${ruta}`, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: metodo === "GET" ? undefined : cuerpo || "{}",
  });
  return { codigo: respuesta.status, texto: await respuesta.text() };
};

const leer = (req) =>
  new Promise((resolve, reject) => {
    let texto = "";
    req.on("data", (p) => {
      texto += p;
      if (texto.length > 6 * 1024 * 1024) reject(new Error("Petición demasiado grande"));
    });
    req.on("end", () => resolve(texto));
  });

const servidor = createServer(async (req, res) => {
  const responder = (codigo, texto) => {
    res.writeHead(codigo, { "Content-Type": "application/json; charset=utf-8" });
    res.end(texto);
  };
  if (req.method === "GET" && req.url === "/ultima-llamada") {
    return responder(200, JSON.stringify(ultima ?? {}));
  }
  if (req.method === "GET" && req.url === "/estado" && !compuerta.abierta) {
    return responder(200, JSON.stringify({ conectado: false, reiniciando: true }));
  }
  try {
    const cuerpo = await leer(req);
    if (!compuerta.abierta) log(`${req.url}: esperando a que el puente esté listo...`);
    const { codigo, texto } = await reenviar(req.method, req.url, cuerpo);
    responder(codigo, texto);
  } catch (error) {
    responder(503, JSON.stringify({ error: error.message }));
  }
});

servidor.listen(PUERTO, "127.0.0.1", () => log(`Atendiendo en http://127.0.0.1:${PUERTO}`));
levantar();

const salir = () => {
  cerrando = true;
  log("Cerrando");
  servidor.close();
  if (puente) puente.kill("SIGTERM");
  setTimeout(() => process.exit(0), 1500);
};
process.on("SIGINT", salir);
process.on("SIGTERM", salir);

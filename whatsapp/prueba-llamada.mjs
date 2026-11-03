/**
 * Prueba aislada: llama con un tono, sin el bot y sin el parche de audio en vivo.
 * Sirve para saber si los cortes vienen de la red o de nuestra integración.
 *
 *   (detén antes el puente: la sesión de WhatsApp no puede usarse dos veces)
 *   npm run prueba -- 522221234567
 */
import { VoipClient } from "baileys-caller";

const numero = (process.argv[2] || process.env.WHATSAPP_PERSONA || "").replace(/\D/g, "");
if (!numero) {
  console.error("Uso: npm run prueba -- 522221234567");
  process.exit(1);
}
const hora = () => new Date().toLocaleTimeString("es-MX", { hour12: false });
const log = (...a) => console.log(hora(), ...a);
for (const m of ["log", "info", "warn"]) {
  const o = console[m].bind(console);
  console[m] = (...a) => (typeof a[0] === "string" && /^(Closing|Opening|Removing|Session|Migrating|Blocking)/.test(a[0]) ? undefined : o(...a));
}

const cliente = new VoipClient({ authDir: process.env.WA_AUTH_DIR || "./auth" });
await cliente.connect();
const [res] = (await cliente.socket.onWhatsApp(numero)) ?? [];
const destino = res?.jid ? res.jid.split("@")[0] : numero;
log(`Llamando a ${destino} con un tono de 60 s...`);

const llamada = await cliente.call(destino, {
  audioSource: "lavfi:sine=frequency=440:duration=60",
  durationMs: 75_000,
});
let bloques = 0;
llamada.on("ringing", () => log("Sonando"));
llamada.on("connected", () => log("Contestó"));
llamada.on("audio", () => { bloques += 1; });
llamada.on("evento", (n, d) => { if (!["tipo 100", "tipo 156"].includes(n)) log("Evento:", n, String(d).slice(0, 120)); });
const medidor = setInterval(() => { log(`Audio 5 s: ${bloques} bloques de tu teléfono`); bloques = 0; }, 5000);
log("Llamada terminada:", await llamada.waitForEnd());
clearInterval(medidor);
cliente.disconnect();
process.exit(0);

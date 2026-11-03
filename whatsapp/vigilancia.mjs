/**
 * Vigila una llamada y la cuelga si quedó colgada del otro lado sin que WhatsApp avisara.
 *
 * - Si nadie contesta en `sinRespuestaMs`, cuelga.
 * - Ya contestada, el motor de WhatsApp entrega audio de la otra persona de forma continua
 *   (aunque sea silencio). Si deja de llegar audio por `sinAudioMs`, se asume que colgaron.
 */
export const vigilarLlamada = (
  llamada,
  { sinRespuestaMs = 60_000, sinAudioMs = 20_000, cadaMs = 1_000, log = () => {} } = {},
) => {
  const inicio = Date.now();
  let contestada = false;
  let ultimoAudio = Date.now();

  llamada.on("connected", () => {
    contestada = true;
    ultimoAudio = Date.now();
  });
  llamada.on("audio", () => {
    ultimoAudio = Date.now();
  });

  const revisar = setInterval(() => {
    const ahora = Date.now();
    if (!contestada && ahora - inicio > sinRespuestaMs) {
      log("Nadie contestó; se cuelga");
      llamada.end();
    } else if (contestada && ahora - ultimoAudio > sinAudioMs) {
      log(`Sin audio de la otra persona por ${Math.round(sinAudioMs / 1000)} s; se cuelga`);
      llamada.end();
    }
  }, cadaMs);

  const detener = () => clearInterval(revisar);
  llamada.once("ended", detener);
  return detener;
};

/**
 * ¿Este aviso de WhatsApp dice que la otra persona colgó o rechazó la llamada `callId`?
 * WhatsApp manda un nodo <call> con un hijo <terminate> o <reject> que trae el call-id.
 */
export const esFinDeLlamada = (nodo, callId) => {
  const hijo = Array.isArray(nodo?.content) ? nodo.content[0] : null;
  if (!hijo || !["terminate", "reject"].includes(hijo.tag)) return null;
  const id = String(hijo.attrs?.["call-id"] ?? hijo.attrs?.call_id ?? "");
  if (callId && id && id.toUpperCase() !== String(callId).toUpperCase()) return null;
  return hijo.tag === "reject" ? "rechazó" : "colgó";
};

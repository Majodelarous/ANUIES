# Tareas

## Iteración 1: agente de voz con herramientas

- [x] T01 Estructura del repo, constitución, especificación, plan y lenguaje ubicuo
- [x] T02 Dominio: modelos, bienestar (GDS-15 y soledad), juegos de memoria, política de alertas (HU-03, HU-04, HU-06)
- [x] T03 Repositorio SQLite con pruebas
- [x] T04 Instrucciones del sistema construidas con perfil, recuerdos, recordatorios, mensajes y preguntas del día (HU-01, HU-02, HU-05)
- [x] T05 Herramientas del agente con pruebas (HU-02 a HU-06)
- [x] T06 Bot de voz con Gemini Live o Nova Sonic, canales WebRTC y Twilio, registro de llamadas (HU-01)
- [x] T07 Prueba real en navegador con Nova Sonic (voz lupe); Gemini Live verificado con llave gratuita
- [ ] T08 Comparar Gemini Live y Nova Sonic con la misma conversación (naturalidad, comprensión, latencia)
- [ ] T09 Llamada telefónica real con Twilio (bloqueada: la cuenta de prueba no permite `<Stream>`)
- [x] T09b Llamada por app: Asterisk + Linphone (funciona con la app abierta; iOS no suena en segundo plano sin notificaciones push)
- [x] T09c Llamada por WhatsApp con puente baileys-caller: suena con el celular bloqueado y la asistente conversa (probado el 2026-11-02)

## Iteración 2: familia y voz familiar

- [x] T10 Panel familiar web: llamadas, señal de bienestar, recordatorios, recuerdos compartidos, alertas (HU-07)
- [x] T11 Alta de recordatorios y mensajes desde el panel (HU-05)
- [ ] T12 Mensaje con audio de voz familiar consentida y reproducción dentro de la llamada (HU-05.3)
- [ ] T13 Ajuste de ritmo, silencios y vocabulario con pruebas con la persona real

## Revisión pendiente

- [x] Se revisó la rama `mejoras-prioritarias` (T18 versión 1, T21, T22, T23) en llamadas reales el 2026-11-03 y se unió a `main`. Se corrigió "recuérdame en 5 minutos" (se guardaba en hora UTC). La versión estable anterior queda en la etiqueta `v0.1-estable`.
- [x] Se revisó la rama `ideas` (T19, T17, T16 y T16b) en llamadas reales el 2026-11-04 y se unió a `main`.
- [ ] Investigar llamadas que se cuelgan solas a los 5 segundos de contestar (evento 44 sin audio de la persona): ¿red o motor de voz?

## Iteración 3: notificaciones y despliegue

- [x] T14 Grupo de WhatsApp de la familia: resumen al terminar cada llamada, alertas de atención y crisis al momento, notas de voz y textos ("Abue, ...") que se entregan en la llamada, respuesta de la persona al grupo (probado el 2026-11-02: notas de voz, respuestas y resumen llegan al grupo)
- [x] T17 Respuesta de la persona como nota de voz con su propia voz (grabar lo que dicta en la llamada y mandarlo al grupo como audio, en lugar de texto) (pendiente) (probado en llamada real el 2026-11-04)
- [~] T18 Puente con la familia (versión 1 probada en llamada real el 2026-11-03; falta versión 2): tras platicar de alguien (por ejemplo, su hija Elena), la asistente ofrece comunicarle con esa persona. Versión 1: avisa al grupo que la abue quiere platicar y le pide a esa persona que le marque. Versión 2: revisa la disponibilidad (agenda) y conecta la llamada. En la siguiente llamada pregunta cómo le fue. Responde al hallazgo de que la asistente debe ser puente y no sustituto (pendiente)
- [x] T19 La familia programa llamadas desde el grupo: "Abue, salgo a las 5, a esa hora te marco" queda como pendiente; Rous se lo dice a la persona y a esa hora le recuerda a quien prometió llamar, o le propone conectarlos (se relaciona con T18) (pendiente) (probado en llamada real el 2026-11-04)
- [ ] T20 Canal sin internet: llamada al teléfono fijo o celular básico por la red telefónica (proveedor de voz con número local) y número local al que la persona puede marcar; ya existe el código con Twilio, falta cuenta de pago (pendiente)
- [x] T21 Llamadas programadas a la hora que pone la familia en el panel, con un reintento y aviso al grupo si no contesta (probado en llamada real el 2026-11-03)
- [x] T22 Recordatorios a su hora con una llamada corta (probado en llamada real el 2026-11-03)
- [x] T23 Consentimiento de palabra en la primera llamada; sin permiso no se guardan recuerdos ni respuestas de bienestar (probado en llamada real el 2026-11-03)
- [x] T16 Imágenes de buenos días: Rous ofrece mandar al grupo una imagen de saludo original de parte de la persona (probado en llamada real el 2026-11-04)
- [x] T16b (probado en llamada real el 2026-11-04; falta decidir con Majo si se queda) Imágenes parecidas tipo Google Lens: si la abue le manda una imagen a Rous por WhatsApp, Rous entiende qué muestra (Gemini), aprende el tema que le gusta y le regresa a su chat 3 imágenes parecidas buscadas en internet (ddgs con Bing) para que ella las reenvíe. En la llamada, buscar_imagenes_para_compartir hace lo mismo con el tema que diga o con sus favoritos; si no hay internet, manda la imagen dibujada de T16
- [ ] T15 Despliegue en la nube con infraestructura como código

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

## Iteración 3: notificaciones y despliegue

- [ ] T14 Grupo de WhatsApp de la familia: resumen al terminar cada llamada, alertas de atención y crisis al momento, notas de voz y textos ("Abue, ...") que se entregan en la llamada, respuesta de la persona al grupo (código listo; falta probar)
- [ ] T16 Imágenes de buenos días: ayudar a la persona a conseguir y mandar sus imágenes al grupo (pendiente)
- [ ] T15 Despliegue en la nube con infraestructura como código

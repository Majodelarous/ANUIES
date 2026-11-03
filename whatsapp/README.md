# Puente de WhatsApp

La asistente llama por WhatsApp a la persona. Es una llamada normal de WhatsApp, así que suena aunque el celular esté bloqueado.

```
compania-llamar-wa  ──HTTP──>  puente (Node, este folder)  ──ws, PCM 16 kHz──>  bot (uv run compania-whatsapp)
                                   │
                                   └── sesión de WhatsApp de la asistente (dispositivo vinculado)
```

Usa [baileys-caller](https://github.com/SheIITear/baileys-caller) (MIT), fijado a un commit, con un parche en `patches/` que:

- agrega la fuente de audio `push` para mandar la voz del bot en vivo (la librería original solo reproduce archivos);
- agrega `clearAudio()` para cortar la voz cuando la persona interrumpe;
- libera la llamada al terminar, para poder hacer otra sin reconectar;
- expone el socket de Baileys, para enviar mensajes con la misma sesión más adelante.

## Aviso

Es un cliente no oficial de WhatsApp. WhatsApp puede restringir o bloquear el número que lo usa. Usa un número secundario para la asistente, nunca el personal ni el de la persona. Para un producto, la ruta es la API oficial de WhatsApp Business Calling.

La carpeta `auth/` guarda las llaves de la sesión: quien la tenga puede actuar como ese dispositivo. No se sube al repositorio.

## Requisitos

- Node.js 20 o superior
- El celular con WhatsApp del número de la asistente, para escanear el QR una vez

## Uso

```bash
cd whatsapp
npm install                       # aplica el parche automáticamente

# Terminal 1: bot
cd ../agente && uv run compania-whatsapp

# Terminal 2: puente (la primera vez muestra un QR)
cd whatsapp && npm start
# En el celular de la asistente: WhatsApp > Dispositivos vinculados > Vincular un dispositivo

# Terminal 3: que la asistente llame
cd agente && uv run compania-llamar-wa 522221234567
```

El número va con código de país y solo dígitos. El puente verifica con WhatsApp el formato correcto (en México puede ser 52 o 521).

El celular de la asistente no necesita estar prendido todo el tiempo, pero WhatsApp cierra los dispositivos vinculados si el celular principal pasa mucho tiempo sin conectarse.

## Grupo de la familia

Con `WHATSAPP_GRUPO` en `agente/.env` (nombre exacto del grupo, y el número de la asistente dentro del grupo):

- Al terminar cada llamada, la asistente manda al grupo un resumen: duración, recuerdos que la persona quiso compartir, juegos, mensajes recibidos, recordatorios y alertas. Las respuestas de bienestar no se comparten.
- Las alertas de atención y crisis llegan al momento, durante la llamada.
- Toda nota de voz que alguien mande al grupo se guarda para la próxima llamada. En la llamada, la asistente pregunta si quiere escucharla y reproduce la voz real; mientras suena, el micrófono de la persona se silencia para que no se corte.
- Los textos que empiezan con "abue" (`WHATSAPP_PREFIJO`) también se guardan, por ejemplo "Abue, el sábado voy". La plática normal del grupo no se le pasa.
- Si la persona quiere responder, la asistente confirma el texto y lo manda al grupo.

El puente lee `../agente/.env`, así que la configuración está en un solo lugar. Si creas el grupo con el puente encendido, reinícialo para que lo encuentre.

## Variables

| Variable | Omisión | Uso |
|---|---|---|
| `WA_AUTH_DIR` | `./auth` | Sesión de WhatsApp |
| `WHATSAPP_GRUPO` | vacío | Nombre del grupo de la familia |
| `WHATSAPP_PREFIJO` | `abue` | Textos del grupo que se pasan a la persona |
| `WHATSAPP_PUENTE_PUERTO` | `7864` | API local del puente |
| `WHATSAPP_BOT_PUERTO` | `7863` | Bot (websocket `/wa` y `POST /mensajes`) |
| `DURACION_MAX_MIN` | `15` | Cuelga solo después de N minutos |

## Pruebas

```bash
npm test
```

## Si deja de funcionar

La librería usa el motor de llamadas de WhatsApp Web. Si WhatsApp lo actualiza, puede fallar; baileys-caller trae `npm run fetch-wasm` para descargar la versión nueva. Si falla la conexión con Baileys 7.0.0-rc14, prueba con la versión que usa la librería (`7.0.0-rc11`), sabiendo que esa tiene un aviso de seguridad (GHSA-qvv5-jq5g-4cgg).

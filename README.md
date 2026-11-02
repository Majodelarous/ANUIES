# Compañía por voz

Agente conversacional de voz para personas adultas mayores. Llama a la persona a su teléfono de siempre (o se usa desde el navegador), platica con ella, la ayuda a recordar su historia de vida, propone juegos de memoria, entrega recordatorios y mensajes de su familia, y genera una señal semanal de bienestar para la familia.

No diagnostica ni sustituye atención profesional.

## Cómo funciona

```
Teléfono (Twilio) o navegador (WebRTC)
        |
   Agente de voz (Pipecat)
        |-- Modelo de voz a voz: Gemini Live o Amazon Nova Sonic
        |-- Herramientas: recuerdos, juegos, bienestar, recordatorios,
        |                 mensajes de la familia, alertas
        |
   SQLite (datos locales del prototipo)
```

## Estructura

```
docs/                 constitución, especificación, plan, tareas y lenguaje del dominio
agente/
  src/compania/
    dominio/          reglas del negocio sin dependencias externas
    infraestructura/  persistencia (SQLite)
    agente/           instrucciones, herramientas y bot de voz
  tests/              pruebas del dominio y de las herramientas
```

## Requisitos

- Python 3.12 o superior y [uv](https://docs.astral.sh/uv/)
- Una llave de Gemini API (Google AI Studio) o credenciales de AWS con acceso a Nova Sonic
- Opcional: cuenta de Twilio para llamadas telefónicas

## Uso rápido

```bash
cd agente
cp .env.example .env        # completar llaves
uv sync
uv run pytest               # pruebas
uv run compania-semilla --nombre "Carmen" --trato "doña Carmen"
uv run compania-bot         # abre http://localhost:7860/client en el navegador
uv run compania-panel       # panel familiar en http://localhost:7861
```

Para que la asistente llame por teléfono (Twilio):

```bash
ngrok http 7860                                     # en otra terminal; copiar el dominio
uv run compania-bot -t twilio -x <dominio-ngrok>
uv run compania-llamar --a +52XXXXXXXXXX --host <dominio-ngrok>
```

Con cuenta de prueba de Twilio solo se puede llamar a números verificados en la consola, y la llamada inicia con un aviso de cuenta de prueba.

Para llamar por app sin operador telefónico (Asterisk + Linphone), ver `telefonia/README.md`.

## Principios

Ver `docs/constitucion.md`. En resumen: la asistente siempre dice que es una asistente, no diagnostica, promueve el contacto con personas, pide consentimiento por escrito para datos de salud y nunca usa voces de personas fallecidas.

## Licencia

Por definir.

# Operación: instalar, configurar y pasar a datos reales

Esta guía usa `make` (Linux o macOS con Python y Node). En Windows, o para no instalar nada, usar Docker: [DOCKER.md](DOCKER.md).

Guía para dejar a Rous funcionando con una persona real: instalación, entornos separados de prueba y producción, número de WhatsApp de la asistente, perfil de la persona, motor de IA y mantenimiento. Todos los comandos se corren desde la raíz del repositorio. `make` sin nada muestra la lista completa.

## 1. Requisitos

| Programa | Para qué |
|---|---|
| Python 3.12 o 3.13 y [uv](https://docs.astral.sh/uv/) | Bot de voz, programador y panel |
| Node.js 20 o superior | Puente de WhatsApp |
| ffmpeg | Notas de voz (convertir audio) |
| make | Los comandos de esta guía |

Python 3.15 todavía no sirve: una dependencia (onnxruntime) no tiene versión para él.

Además:

- Un celular con un número exclusivo para la asistente, con WhatsApp instalado. No uses un número personal: el puente es un cliente no oficial y WhatsApp puede restringir ese número.
- Una llave del motor de IA que se vaya a usar (ver sección 6).

## 2. Instalar

```bash
git clone <repositorio> compania-voz
cd compania-voz
make instalar      # uv sync y npm install (aplica el parche del puente)
make test          # debe pasar todo
```

## 3. Entornos: prueba y prod

Cada entorno tiene su propia configuración y sus propios datos, para que lo que se probó no se mezcle con la persona real:

| Entorno | Configuración | Base de datos | Notas de voz | Sesión de WhatsApp |
|---|---|---|---|---|
| prueba | `agente/.env.prueba` | `agente/compania.db` | `agente/audios/` | `whatsapp/auth/` |
| prod | `agente/.env.prod` | `agente/datos/prod/compania.db` | `agente/datos/prod/audios/` | `whatsapp/auth-prod/` |

`agente/.env` es un enlace al entorno activo; el bot y el puente siempre leen ese. Nada de esto se sube a git.

```bash
make entorno                      # qué entorno está activo y qué le falta
make nuevo-entorno ENTORNO=prod   # crea prod con las mismas llaves de IA y lo demás en blanco
make usar ENTORNO=prod            # cambia al entorno prod
make usar ENTORNO=prueba          # regresa a prueba
```

La primera vez que se usa `make usar`, el `agente/.env` que ya existía se convierte en el entorno `prueba`; no se pierde nada. Para cambiar de entorno los servicios deben estar apagados (Ctrl+C en `make dev`).

Solo puede correr un entorno a la vez: comparten los puertos.

## 4. Poner en marcha con una persona real (orden recomendado)

Haz los pasos en este orden. Al terminar cada uno, `make entorno` muestra qué falta.

### Paso 1. Crear y activar el entorno

```bash
make nuevo-entorno ENTORNO=prod
make usar ENTORNO=prod
```

### Paso 2. Motor de IA y llaves

Las llaves se escriben directo en el archivo, para que no queden en el historial de la terminal:

```bash
nano agente/.env.prod     # o el editor que prefieras: GOOGLE_API_KEY, OPENAI_API_KEY o AWS_*
make motor MOTOR=gemini   # gemini, openai o nova
```

### Paso 3. Número de la asistente

```bash
make poner CLAVE=WHATSAPP_ASISTENTE VALOR=522221234567
make vincular CONFIRMAR=si
```

`make vincular` levanta solo el puente y muestra un QR. En el celular de la asistente: WhatsApp, Dispositivos vinculados, Vincular un dispositivo, y escanea el QR. Cuando la terminal diga "Listo", detén con Ctrl+C.

Pon en ese WhatsApp el nombre y la foto con los que la familia reconocerá a la asistente (por ejemplo, "Rous").

### Paso 4. Grupo de la familia

1. Desde el celular de la asistente, crea un grupo con los familiares que recibirán resúmenes y alertas. La persona mayor no necesita estar en el grupo.
2. Registra el nombre exacto del grupo:

```bash
make poner CLAVE=WHATSAPP_GRUPO VALOR="Familia López"
```

Los textos del grupo que empiezan con "abue" se le pasan a la persona. Para usar otra palabra: `make poner CLAVE=WHATSAPP_PREFIJO VALOR=mamá`.

### Paso 5. Perfil de la persona

```bash
make persona NOMBRE="Amada López" TRATO="abuelita" TELEFONO=522221234567
make poner CLAVE=WHATSAPP_PERSONA VALOR=522221234567
make personas
```

- `TRATO` es cómo le gusta que le digan; Rous lo usa en cada llamada y en los resúmenes.
- `CONTACTO="Elena 5522..."` guarda un contacto de emergencia (opcional).
- Agrega `CONSENTIMIENTO=si` solo si la persona ya firmó el consentimiento por escrito. Si no, Rous le explica y le pide permiso de palabra en la primera llamada, y sin permiso no guarda recuerdos ni respuestas de bienestar.
- El número va con código de país y solo dígitos. En México puede funcionar con 52 o 521; el puente lo verifica con WhatsApp.

### Paso 6. Horarios y recordatorios

```bash
make panel        # abre http://127.0.0.1:7861
```

En el panel: horario de llamada diaria, recordatorios y mensajes. Detén el panel con Ctrl+C.

### Paso 7. Primera llamada

```bash
make entorno      # revisar que no falte nada
make dev          # levanta los cuatro servicios y guarda el log en logs/
make llamar       # en otra terminal: Rous llama a WHATSAPP_PERSONA
```

## 5. Cambiar números

| Qué cambia | Comandos |
|---|---|
| Número de la asistente (otro chip) | `make poner CLAVE=WHATSAPP_ASISTENTE VALOR=52...` y `make vincular CONFIRMAR=si`. En el celular anterior, quita el dispositivo vinculado. |
| Número de la persona | `make personas` para ver su id, `make telefono ID=1 NUMERO=52...` y `make poner CLAVE=WHATSAPP_PERSONA VALOR=52...` |
| Grupo de la familia | `make poner CLAVE=WHATSAPP_GRUPO VALOR="Nombre exacto"` (el número de la asistente debe estar en el grupo) |
| Nombre de la asistente | `make poner CLAVE=NOMBRE_ASISTENTE VALOR=Rous` |

Después de cualquier cambio, reinicia `make dev`.

## 6. Cambiar el motor de IA

```bash
make motor MOTOR=gemini    # Gemini Live (Google AI Studio)
make motor MOTOR=openai    # OpenAI Realtime (ChatGPT)
make motor MOTOR=nova      # Amazon Nova Sonic (AWS Bedrock)
```

El comando avisa si falta la llave del motor elegido. Reinicia `make dev` para que tome el cambio.

| Motor | Llave | Voz (variable y valores) | Modelo |
|---|---|---|---|
| gemini | `GOOGLE_API_KEY` | `GOOGLE_VOICE_ID`, por omisión Aoede | `GOOGLE_MODEL`; vacío usa el de Pipecat |
| openai | `OPENAI_API_KEY` | `OPENAI_VOICE`: marin, cedar, alloy, ash, ballad, coral, echo, sage, shimmer, verse | `OPENAI_MODEL`, por omisión gpt-realtime-2.1 |
| nova | `AWS_PROFILE` o `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` | `NOVA_VOICE_ID`: lupe o carlos | Nova Sonic en `AWS_REGION` (us-east-1) |

Ejemplo para cambiar la voz: `make poner CLAVE=OPENAI_VOICE VALOR=coral`.

La búsqueda de imágenes parecidas usa `GOOGLE_API_KEY` sin importar el motor de voz. Sin esa llave, Rous manda la imagen dibujada.

## 7. Respaldos y limpieza

```bash
make respaldo               # copia base, notas de voz y sesión de WhatsApp a respaldos/
make limpiar CONFIRMAR=si   # vacía base y notas de voz del entorno activo
```

`make limpiar` no borra: mueve los datos a `respaldos/<entorno>-<fecha>/`. La sesión de WhatsApp se queda. Después, registra de nuevo a la persona (paso 5). Para recuperar un respaldo, detén los servicios y copia los archivos de vuelta a las rutas que muestra `make entorno`.

Respalda antes de cualquier cambio grande y guarda `respaldos/` fuera de la computadora: ahí están los recuerdos de la persona y las llaves de la sesión de WhatsApp.

## 8. Uso diario

```bash
make dev            # todo en una terminal; Ctrl+C detiene todo
make log            # desde otra terminal, sigue el log en vivo
make logs           # logs guardados, por sesión
make colgar         # si el puente dice "Ya hay una llamada en curso"
```

Cada servicio se puede levantar solo: `make bot`, `make puente`, `make programador`, `make panel`.

## 9. Problemas comunes

| Qué pasa | Qué hacer |
|---|---|
| La llamada se cuelga sola a los 5 segundos de contestar | El puente vuelve a marcar una vez por su cuenta. Falla conocida en investigación: guarda el log de `logs/` de esa sesión. |
| "Ya hay una llamada en curso" | `make colgar` |
| No aparece el grupo | Revisa el nombre exacto con `make entorno`, que la asistente esté en el grupo y reinicia `make dev`. |
| Pide QR otra vez | WhatsApp cerró el dispositivo vinculado (pasa si el celular de la asistente pasa mucho tiempo sin conexión). `make vincular CONFIRMAR=si`. |
| `make usar` dice que detengas los servicios | Ctrl+C en `make dev` y vuelve a intentar. |
| La IA tarda o se corta | Puede ser la red o el plan gratuito del motor. Prueba otro motor con `make motor`. |

## 10. Límites actuales

- Una persona por entorno. La base admite varias (`PERSONA_ID`), pero el puente atiende un solo número de persona y un solo grupo. Para otra persona mayor, crea otro entorno.
- Un entorno corriendo a la vez.
- WhatsApp por un cliente no oficial: para un servicio con muchas familias, la ruta es la API oficial de WhatsApp Business Calling.

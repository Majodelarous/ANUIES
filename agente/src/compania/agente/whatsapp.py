"""Llamadas por WhatsApp: el puente de Node (carpeta ``whatsapp/``) conecta cada llamada con el bot.

Uso::

    uv run compania-whatsapp            # servidor para el puente en ws://127.0.0.1:7863/wa
    cd ../whatsapp && npm start         # puente: sesión de WhatsApp de la asistente
    uv run compania-llamar-wa 522221234567

Protocolo del websocket ``/wa``: mensajes binarios con PCM de 16 bits, 16 kHz, mono, en ambos
sentidos. El bot manda el texto ``clear`` cuando la persona interrumpe, para descartar el audio
que el puente aún no reproduce.

``POST /mensajes`` recibe del puente los mensajes que la familia manda por WhatsApp (texto o
nota de voz ya convertida a WAV) y los guarda para la próxima llamada.

``POST /imagenes/parecidas`` recibe una imagen que mandó la persona, aprende qué le gusta y
devuelve imágenes parecidas para que el puente se las mande a su chat.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import urllib.error
import urllib.request
import wave
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from loguru import logger
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer
from pydantic import BaseModel, Field

from compania.infraestructura.puente_whatsapp import host_del_puente

FRECUENCIA = 16000
NUMERO = re.compile(r"^\d{10,15}$")
LIMPIAR = "clear"
MAX_AUDIO_BYTES = 8 * 1024 * 1024  # unos 4 minutos a 16 kHz


class MensajeEntrante(BaseModel):
    de: str = Field(min_length=1, max_length=60)
    texto: str = Field(default="", max_length=1000)
    audio_wav_b64: str | None = None


class ImagenEntrante(BaseModel):
    imagen_b64: str
    mime: str = Field(default="image/jpeg", max_length=40)
    buscar: bool = True


class SerializadorPCM(FrameSerializer):
    """PCM crudo de 16 bits y 16 kHz entre el puente de WhatsApp y Pipecat."""

    def __init__(self, frecuencia: int = FRECUENCIA):
        super().__init__()
        self._frecuencia = frecuencia
        self._remuestreo = create_stream_resampler()

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, InterruptionFrame):
            return LIMPIAR
        if isinstance(frame, AudioRawFrame) and not isinstance(frame, InputAudioRawFrame):
            audio = frame.audio
            if frame.sample_rate != self._frecuencia:
                audio = await self._remuestreo.resample(audio, frame.sample_rate, self._frecuencia)
            return audio or None
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, str) or not data:
            return None
        return InputAudioRawFrame(audio=bytes(data), num_channels=1, sample_rate=self._frecuencia)


def crear_app(repo=None, carpeta_audios: str | Path | None = None, imagenes=None) -> FastAPI:
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

    from compania.agente.bot import run_bot
    from compania.agente.herramientas import cargar_audio
    from compania.agente.imagenes_parecidas import ImagenesParecidas
    from compania.dominio.compromisos import extraer_compromiso
    from compania.dominio.modelos import Compromiso, MensajeFamiliar, Seguimiento
    from compania.infraestructura.repositorio import Repositorio

    app = FastAPI(title="Compañía por voz: WhatsApp")
    repositorio = repo or Repositorio(os.getenv("RUTA_DB", "compania.db"))
    audios = Path(carpeta_audios or os.getenv("CARPETA_AUDIOS", "audios"))
    lente = imagenes or ImagenesParecidas(repositorio)

    def persona_actual():
        persona_id = os.getenv("PERSONA_ID")
        persona = (
            repositorio.obtener_persona(int(persona_id)) if persona_id else repositorio.persona_activa()
        )
        if persona is None or persona.id is None:
            raise HTTPException(404, "No hay persona registrada")
        return persona

    @app.post("/imagenes/parecidas")
    async def imagenes_parecidas(entrada: ImagenEntrante) -> dict:
        from compania.dominio.saludos import texto_para_la_persona

        persona = persona_actual()
        try:
            imagen = base64.b64decode(entrada.imagen_b64, validate=True)
        except binascii.Error:
            raise HTTPException(422, "Imagen inválida") from None
        if len(imagen) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "La imagen es demasiado grande")
        if not entrada.buscar:
            descripcion = await lente.aprender(persona.id, imagen, entrada.mime)
            return {"tema": descripcion.tema if descripcion else None, "imagenes_b64": []}
        resultado = await lente.parecidas(persona.id, imagen, entrada.mime)
        tema = resultado.descripcion.tema if resultado.descripcion else None
        logger.info(f"Imágenes parecidas para {persona.trato}: {len(resultado.imagenes)} ({tema})")
        texto = (
            texto_para_la_persona(persona.trato, datetime.now(), parecidas=True)
            if resultado.imagenes
            else "Ahorita no encontré imágenes parecidas. Al rato lo vuelvo a intentar."
        )
        return {
            "tema": tema,
            "texto": texto,
            "imagenes_b64": [base64.b64encode(i).decode() for i in resultado.imagenes],
        }

    @app.post("/mensajes")
    def nuevo_mensaje(mensaje: MensajeEntrante) -> dict:
        persona = persona_actual()
        if not mensaje.texto.strip() and not mensaje.audio_wav_b64:
            raise HTTPException(422, "El mensaje está vacío")

        ruta = None
        if mensaje.audio_wav_b64:
            try:
                datos = base64.b64decode(mensaje.audio_wav_b64, validate=True)
            except binascii.Error:
                raise HTTPException(422, "Audio inválido") from None
            if len(datos) > MAX_AUDIO_BYTES:
                raise HTTPException(413, "La nota de voz es demasiado larga")
            audios.mkdir(parents=True, exist_ok=True)
            ruta = audios / f"mensaje-{datetime.now():%Y%m%d-%H%M%S-%f}.wav"
            ruta.write_bytes(datos)
            try:
                cargar_audio(ruta)
            except (ValueError, wave.Error, EOFError):
                ruta.unlink(missing_ok=True)
                raise HTTPException(422, "El audio debe ser WAV mono de 16 bits") from None

        guardado = repositorio.guardar_mensaje(
            MensajeFamiliar(
                persona.id, mensaje.de.strip(), mensaje.texto.strip(), str(ruta) if ruta else None
            )
        )
        logger.info(
            f"Mensaje {guardado.id} de {guardado.de} para {persona.trato} ({'voz' if ruta else 'texto'})"
        )
        respuesta = {"id": guardado.id, "trato": persona.trato}
        # "Abue, salgo a las 5 y te marco": recordarle al familiar a esa hora y preguntar después
        compromiso = extraer_compromiso(mensaje.texto, datetime.now()) if mensaje.texto else None
        if compromiso:
            fecha, hora = compromiso
            de = mensaje.de.strip()
            repositorio.guardar_compromiso(Compromiso(persona.id, de, fecha, hora, mensaje.texto.strip()))
            repositorio.guardar_seguimiento(Seguimiento(persona.id, de, f"quedó de marcarle a las {hora}"))
            respuesta["compromiso"] = {"fecha": fecha, "hora": hora}
        return respuesta

    @app.websocket("/wa")
    async def llamada(websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("El puente de WhatsApp conectó una llamada")
        transporte = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                serializer=SerializadorPCM(),
            ),
        )
        try:
            motivo = websocket.query_params.get("motivo", "")[:60]
            await run_bot(transporte, canal="whatsapp", frecuencia_audio=FRECUENCIA, motivo=motivo)
        except Exception:
            logger.exception("La llamada terminó con error")

    return app


def main() -> None:
    import uvicorn

    from compania.agente.bot import verificar_motor

    load_dotenv(override=True)
    verificar_motor()
    # En Docker se escucha en 0.0.0.0 (WHATSAPP_BOT_ESCUCHA) para que el puente llegue desde su contenedor
    host = os.getenv("WHATSAPP_BOT_ESCUCHA") or "127.0.0.1"
    uvicorn.run(crear_app(), host=host, port=int(os.getenv("WHATSAPP_BOT_PUERTO", "7863")))


def solicitud_llamada(numero: str, puerto: int = 7864, host: str | None = None) -> urllib.request.Request:
    """Petición al puente para que la asistente llame por WhatsApp a ``numero``."""
    digitos = re.sub(r"\D", "", numero)
    if not NUMERO.match(digitos):
        raise ValueError("Usa el número con código de país, por ejemplo 522221234567")
    datos = json.dumps({"numero": digitos}).encode()
    return urllib.request.Request(
        f"http://{host or host_del_puente()}:{puerto}/llamar",
        data=datos,
        method="POST",
        headers={"Content-Type": "application/json"},
    )


def _pedir_al_puente(solicitud: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as error:
        detalle = json.loads(error.read() or b"{}")
        raise SystemExit(f"El puente rechazó la petición: {detalle.get('error', error.code)}") from None
    except urllib.error.URLError:
        raise SystemExit(
            "No responde el puente de WhatsApp. Inícialo con: cd whatsapp && npm start"
        ) from None


def llamar() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="La asistente llama por WhatsApp")
    parser.add_argument(
        "numero",
        nargs="?",
        default=os.getenv("WHATSAPP_PERSONA"),
        help="Número con código de país (o WHATSAPP_PERSONA en .env)",
    )
    parser.add_argument("--colgar", action="store_true", help="Cuelga la llamada en curso y libera el puente")
    args = parser.parse_args()
    puerto = int(os.getenv("WHATSAPP_PUENTE_PUERTO", "7864"))

    if args.colgar:
        solicitud = urllib.request.Request(
            f"http://{host_del_puente()}:{puerto}/colgar", data=b"{}", method="POST"
        )
        print(_pedir_al_puente(solicitud).get("mensaje", "Listo"))
        return
    if not args.numero:
        parser.error("Falta el número: pásalo como argumento o define WHATSAPP_PERSONA en .env")
    print(_pedir_al_puente(solicitud_llamada(args.numero, puerto)).get("mensaje", "Llamando..."))


if __name__ == "__main__":
    main()

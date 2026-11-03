"""Llamadas por WhatsApp: el puente de Node (carpeta ``whatsapp/``) conecta cada llamada con el bot.

Uso::

    uv run compania-whatsapp            # servidor para el puente en ws://127.0.0.1:7863/wa
    cd ../whatsapp && npm start         # puente: sesión de WhatsApp de la asistente
    uv run compania-llamar-wa 522221234567

Protocolo del websocket ``/wa``: mensajes binarios con PCM de 16 bits, 16 kHz, mono, en ambos
sentidos. El bot manda el texto ``clear`` cuando la persona interrumpe, para descartar el audio
que el puente aún no reproduce.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from loguru import logger
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

FRECUENCIA = 16000
NUMERO = re.compile(r"^\d{10,15}$")
LIMPIAR = "clear"


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


def crear_app() -> FastAPI:
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

    from compania.agente.bot import run_bot

    app = FastAPI(title="Compañía por voz: WhatsApp")

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
            await run_bot(transporte, canal="whatsapp", frecuencia_audio=FRECUENCIA)
        except Exception:
            logger.exception("La llamada terminó con error")

    return app


def main() -> None:
    import uvicorn

    load_dotenv(override=True)
    uvicorn.run(crear_app(), host="127.0.0.1", port=int(os.getenv("WHATSAPP_BOT_PUERTO", "7863")))


def solicitud_llamada(numero: str, puerto: int = 7864) -> urllib.request.Request:
    """Petición al puente para que la asistente llame por WhatsApp a ``numero``."""
    digitos = re.sub(r"\D", "", numero)
    if not NUMERO.match(digitos):
        raise ValueError("Usa el número con código de país, por ejemplo 522221234567")
    datos = json.dumps({"numero": digitos}).encode()
    return urllib.request.Request(
        f"http://127.0.0.1:{puerto}/llamar",
        data=datos,
        method="POST",
        headers={"Content-Type": "application/json"},
    )


def llamar() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="La asistente llama por WhatsApp")
    parser.add_argument(
        "numero",
        nargs="?",
        default=os.getenv("WHATSAPP_PERSONA"),
        help="Número con código de país (o WHATSAPP_PERSONA en .env)",
    )
    args = parser.parse_args()
    if not args.numero:
        parser.error("Falta el número: pásalo como argumento o define WHATSAPP_PERSONA en .env")
    solicitud = solicitud_llamada(args.numero, int(os.getenv("WHATSAPP_PUENTE_PUERTO", "7864")))
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            print(json.load(respuesta).get("mensaje", "Llamando..."))
    except urllib.error.HTTPError as error:
        detalle = json.loads(error.read() or b"{}")
        raise SystemExit(f"El puente rechazó la llamada: {detalle.get('error', error.code)}") from None
    except urllib.error.URLError:
        raise SystemExit(
            "No responde el puente de WhatsApp. Inícialo con: cd whatsapp && npm start"
        ) from None


if __name__ == "__main__":
    main()

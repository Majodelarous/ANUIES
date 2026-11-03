"""Grabadora de la voz de la persona dentro de la llamada (nota de voz para su familia).

``Grabadora`` es un procesador de Pipecat que va justo después de la entrada de audio: deja
pasar todo y, cuando se le pide, guarda el audio de la persona hasta que se queda callada.

``DetectorDeFin`` decide cuándo terminó de hablar con la energía del audio (sin modelos):
- termina tras ``silencio_fin_s`` de silencio después de haber hablado;
- se rinde si en ``sin_voz_s`` no habló nada;
- corta en ``max_s`` como máximo.
"""

from __future__ import annotations

import array
import asyncio
import io
import math
import os
import wave
from dataclasses import dataclass, field

from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


def energia(pcm: bytes) -> float:
    """Raíz cuadrática media de PCM de 16 bits."""
    muestras = array.array("h", pcm[: len(pcm) // 2 * 2])
    if not muestras:
        return 0.0
    return math.sqrt(sum(m * m for m in muestras) / len(muestras))


@dataclass
class DetectorDeFin:
    umbral: float = 500.0
    silencio_fin_s: float = 1.6
    sin_voz_s: float = 6.0
    max_s: float = 25.0
    transcurrido: float = 0.0
    hablo: bool = False
    silencio: float = 0.0
    partes: list[bytes] = field(default_factory=list)

    def agregar(self, pcm: bytes, segundos: float) -> bool:
        """Agrega un bloque de audio. Devuelve True cuando la grabación terminó."""
        self.partes.append(pcm)
        self.transcurrido += segundos
        if energia(pcm) >= self.umbral:
            self.hablo = True
            self.silencio = 0.0
        else:
            self.silencio += segundos
        if self.transcurrido >= self.max_s:
            return True
        if self.hablo:
            return self.silencio >= self.silencio_fin_s
        return self.transcurrido >= self.sin_voz_s

    def audio(self) -> bytes | None:
        """El audio grabado sin el silencio final, o None si no habló."""
        if not self.hablo:
            return None
        datos = b"".join(self.partes)
        if self.partes and self.silencio > 0:
            # Quitar el silencio final, dejando medio segundo para que no suene cortado
            por_segundo = len(datos) / self.transcurrido if self.transcurrido else 0
            sobra = max(0.0, self.silencio - 0.5)
            corte = int(por_segundo * sobra) // 2 * 2
            if 0 < corte < len(datos):
                datos = datos[:-corte]
        return datos


def a_wav(pcm: bytes, frecuencia: int) -> bytes:
    salida = io.BytesIO()
    with wave.open(salida, "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(pcm)
    return salida.getvalue()


def tono(frecuencia_audio: int, segundos: float = 0.35, hz: float = 880.0) -> bytes:
    """Tonito suave para indicar que empieza la grabación."""
    n = int(frecuencia_audio * segundos)
    muestras = array.array(
        "h",
        (
            int(6000 * math.sin(2 * math.pi * hz * i / frecuencia_audio) * min(1.0, i / 400, (n - i) / 400))
            for i in range(n)
        ),
    )
    return muestras.tobytes()


class Grabadora(FrameProcessor):
    """Deja pasar el audio y, mientras graba, guarda el de la persona."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._detector: DetectorDeFin | None = None
        self._listo: asyncio.Future | None = None
        self.frecuencia = 16000

    async def grabar(self) -> tuple[bytes, int] | None:
        """Graba hasta que la persona termina. Devuelve (wav, frecuencia) o None si no habló."""
        self._detector = DetectorDeFin(umbral=float(os.getenv("GRABADORA_UMBRAL", "500")))
        self._listo = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(self._listo, timeout=self._detector.max_s + 5)
        except TimeoutError:
            pass
        detector, self._detector = self._detector, None
        pcm = detector.audio() if detector else None
        return (a_wav(pcm, self.frecuencia), self.frecuencia) if pcm else None

    def observar(self, frame: Frame) -> None:
        """Si está grabando, guarda el audio de la persona."""
        if self._detector is None or not isinstance(frame, InputAudioRawFrame) or frame.num_channels != 1:
            return
        self.frecuencia = frame.sample_rate
        segundos = len(frame.audio) / 2 / frame.sample_rate
        if self._detector.agregar(frame.audio, segundos) and self._listo and not self._listo.done():
            self._listo.set_result(True)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        self.observar(frame)
        await self.push_frame(frame, direction)

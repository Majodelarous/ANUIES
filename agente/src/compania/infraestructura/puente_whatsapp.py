"""Envío de mensajes al grupo de WhatsApp de la familia a través del puente de Node."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from loguru import logger


def host_del_puente() -> str:
    """Dónde está el puente de WhatsApp: 127.0.0.1 en local, el nombre del servicio en Docker."""
    return os.getenv("WHATSAPP_PUENTE_HOST") or "127.0.0.1"


class AvisoFamilia(Protocol):
    """Canal para avisar a la familia. La llamada nunca falla si el aviso falla."""

    async def enviar(self, texto: str) -> bool: ...

    async def enviar_audio(self, wav: bytes, texto: str = "") -> bool: ...

    async def enviar_imagen(self, imagen: bytes, texto: str = "", para: str = "") -> bool:
        """Al grupo, o al chat de ``para`` (número con código de país) si se indica."""
        ...


class SinAviso:
    """No envía nada (cuando no hay grupo configurado)."""

    async def enviar(self, texto: str) -> bool:
        logger.info(f"Aviso a la familia (sin grupo configurado): {texto}")
        return False

    async def enviar_audio(self, wav: bytes, texto: str = "") -> bool:
        logger.info(f"Nota de voz para la familia (sin grupo configurado): {len(wav)} bytes")
        return False

    async def enviar_imagen(self, imagen: bytes, texto: str = "", para: str = "") -> bool:
        logger.info(f"Imagen para {para or 'la familia'} (sin grupo configurado): {len(imagen)} bytes")
        return False


class PuenteWhatsApp:
    """Pide al puente que mande un texto al grupo configurado en ``WHATSAPP_GRUPO``."""

    def __init__(self, puerto: int = 7864, timeout: float = 30, host: str | None = None):
        self.base = f"http://{host or host_del_puente()}:{puerto}"
        self.timeout = timeout

    def _post(self, ruta: str, cuerpo: dict) -> bool:
        datos = json.dumps(cuerpo).encode()
        solicitud = urllib.request.Request(
            self.base + ruta, data=datos, method="POST", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(solicitud, timeout=self.timeout) as respuesta:
            return respuesta.status == 200

    async def _enviar(self, ruta: str, cuerpo: dict) -> bool:
        try:
            return await asyncio.to_thread(self._post, ruta, cuerpo)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning(f"No se pudo avisar al grupo de la familia: {error}")
            return False

    async def enviar(self, texto: str) -> bool:
        return await self._enviar("/enviar", {"texto": texto})

    async def enviar_audio(self, wav: bytes, texto: str = "") -> bool:
        return await self._enviar(
            "/enviar-audio", {"audio_wav_b64": base64.b64encode(wav).decode(), "texto": texto}
        )

    async def enviar_imagen(self, imagen: bytes, texto: str = "", para: str = "") -> bool:
        cuerpo = {"imagen_b64": base64.b64encode(imagen).decode(), "texto": texto}
        if para:
            cuerpo["para"] = para
        return await self._enviar("/enviar-imagen", cuerpo)


def aviso_desde_entorno() -> AvisoFamilia:
    if not os.getenv("WHATSAPP_GRUPO"):
        return SinAviso()
    return PuenteWhatsApp(int(os.getenv("WHATSAPP_PUENTE_PUERTO", "7864")))


class PuenteLlamadas:
    """Pide llamadas al puente de WhatsApp y consulta cómo terminó la última."""

    def __init__(self, puerto: int = 7864, timeout: float = 120, host: str | None = None):
        self.base = f"http://{host or host_del_puente()}:{puerto}"
        self.timeout = timeout

    def _pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> tuple[int, dict]:
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        solicitud = urllib.request.Request(
            self.base + ruta, data=datos, method=metodo, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(solicitud, timeout=self.timeout) as respuesta:
                return respuesta.status, json.loads(respuesta.read() or b"{}")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return 0, {"error": f"El puente no responde: {error}"}

    async def llamar(self, numero: str, motivo: str) -> tuple[int, dict]:
        return await asyncio.to_thread(self._pedir, "POST", "/llamar", {"numero": numero, "motivo": motivo})

    async def ultima_llamada(self) -> dict:
        _, datos = await asyncio.to_thread(self._pedir, "GET", "/ultima-llamada")
        return datos

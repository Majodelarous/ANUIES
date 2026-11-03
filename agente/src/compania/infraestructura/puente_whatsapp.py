"""Envío de mensajes al grupo de WhatsApp de la familia a través del puente de Node."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from loguru import logger


class AvisoFamilia(Protocol):
    """Canal para avisar a la familia. La llamada nunca falla si el aviso falla."""

    async def enviar(self, texto: str) -> bool: ...


class SinAviso:
    """No envía nada (cuando no hay grupo configurado)."""

    async def enviar(self, texto: str) -> bool:
        logger.info(f"Aviso a la familia (sin grupo configurado): {texto}")
        return False


class PuenteWhatsApp:
    """Pide al puente que mande un texto al grupo configurado en ``WHATSAPP_GRUPO``."""

    def __init__(self, puerto: int = 7864, timeout: float = 15):
        self.url = f"http://127.0.0.1:{puerto}/enviar"
        self.timeout = timeout

    def _post(self, texto: str) -> bool:
        datos = json.dumps({"texto": texto}).encode()
        solicitud = urllib.request.Request(
            self.url, data=datos, method="POST", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(solicitud, timeout=self.timeout) as respuesta:
            return respuesta.status == 200

    async def enviar(self, texto: str) -> bool:
        try:
            return await asyncio.to_thread(self._post, texto)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning(f"No se pudo avisar al grupo de la familia: {error}")
            return False


def aviso_desde_entorno() -> AvisoFamilia:
    if not os.getenv("WHATSAPP_GRUPO"):
        return SinAviso()
    return PuenteWhatsApp(int(os.getenv("WHATSAPP_PUENTE_PUERTO", "7864")))

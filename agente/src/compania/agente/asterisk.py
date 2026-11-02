"""Llamadas por app: Asterisk (Docker) conecta cada llamada de Linphone con el bot por websocket.

Uso::

    uv run compania-asterisk            # servidor para Asterisk en ws://127.0.0.1:7862/ws
    uv run compania-llamar-app abue     # la asistente llama a la cuenta SIP "abue"

Ver ``telefonia/README.md`` para levantar Asterisk y configurar Linphone.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from loguru import logger

CONTENEDOR = "compania-asterisk"
CUENTA = re.compile(r"^[a-z0-9_-]{1,32}$")
# Debe coincidir con c(slin16) en telefonia/asterisk/extensions.conf
FRECUENCIA = 16000


def crear_app() -> FastAPI:
    from pipecat_asterisk import AsteriskWebsocketTransport

    from compania.agente.bot import run_bot

    app = FastAPI(title="Compañía por voz: Asterisk")

    @app.websocket("/ws")
    async def llamada(websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("Asterisk conectó una llamada")
        try:
            await run_bot(
                AsteriskWebsocketTransport(websocket=websocket), canal="app", frecuencia_audio=FRECUENCIA
            )
        except Exception:
            logger.exception("La llamada terminó con error")

    return app


def main() -> None:
    import uvicorn

    load_dotenv(override=True)
    uvicorn.run(crear_app(), host="127.0.0.1", port=int(os.getenv("ASTERISK_BOT_PUERTO", "7862")))


def comando_originar(cuenta: str, contenedor: str = CONTENEDOR) -> list[str]:
    """Comando de Asterisk para que la asistente llame a una cuenta SIP."""
    if not CUENTA.match(cuenta):
        raise ValueError("La cuenta solo puede tener minúsculas, números, guion y guion bajo")
    return [
        "docker",
        "exec",
        contenedor,
        "asterisk",
        "-rx",
        f"channel originate PJSIP/{cuenta} extension compania@salida",
    ]


def llamar() -> None:
    parser = argparse.ArgumentParser(description="La asistente llama a una cuenta de Linphone")
    parser.add_argument("cuenta", nargs="?", default="abue", help="Cuenta SIP, por ejemplo abue")
    args = parser.parse_args()
    if shutil.which("docker") is None:
        raise SystemExit("No se encontró docker en esta máquina")
    resultado = subprocess.run(comando_originar(args.cuenta), capture_output=True, text=True, check=False)
    salida = (resultado.stdout + resultado.stderr).strip()
    if resultado.returncode != 0:
        raise SystemExit(f"Asterisk no pudo iniciar la llamada: {salida or 'sin detalle'}")
    print(salida or f"Llamando a {args.cuenta}...")


if __name__ == "__main__":
    main()

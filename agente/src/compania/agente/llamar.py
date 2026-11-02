"""Inicia una llamada saliente: la asistente llama al teléfono de la persona.

Requiere el bot corriendo con Twilio y un dominio público (por ejemplo, ngrok)::

    ngrok http 7860
    uv run compania-bot -t twilio -x <dominio-ngrok>
    uv run compania-llamar --a +52XXXXXXXXXX --host <dominio-ngrok>
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import quoteattr

from dotenv import load_dotenv

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"


def twiml_stream(host: str) -> str:
    """TwiML que conecta la llamada con el websocket del bot."""
    host = host.removeprefix("https://").removeprefix("wss://").strip("/")
    url = quoteattr(f"wss://{host}/ws")
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url={url}/></Connect></Response>'
    )


def solicitud_llamada(sid: str, token: str, origen: str, destino: str, host: str) -> urllib.request.Request:
    for numero in (origen, destino):
        if not E164.match(numero):
            raise ValueError(
                f"Número inválido {numero!r}: usa formato internacional, por ejemplo +5222XXXXXXXX"
            )
    datos = urllib.parse.urlencode({"To": destino, "From": origen, "Twiml": twiml_stream(host)}).encode()
    credencial = base64.b64encode(f"{sid}:{token}".encode()).decode()
    return urllib.request.Request(
        API.format(sid=sid), data=datos, method="POST", headers={"Authorization": f"Basic {credencial}"}
    )


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="La asistente llama a la persona por teléfono")
    parser.add_argument("--a", dest="destino", required=True, help="Número de la persona, formato +52...")
    parser.add_argument(
        "--host", required=True, help="Dominio público del bot, por ejemplo abc.ngrok-free.app"
    )
    parser.add_argument(
        "--desde", default=os.getenv("TWILIO_NUMERO"), help="Número de Twilio (o TWILIO_NUMERO)"
    )
    args = parser.parse_args()
    if not args.desde:
        parser.error("Falta el número de Twilio: usa --desde o define TWILIO_NUMERO en .env")

    solicitud = solicitud_llamada(
        os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"], args.desde, args.destino, args.host
    )
    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            llamada = json.load(respuesta)
        print(f"Llamada creada: {llamada['sid']} (estado: {llamada['status']})")
    except urllib.error.HTTPError as error:
        detalle = json.loads(error.read() or b"{}")
        raise SystemExit(
            f"Twilio rechazó la llamada ({error.code}): {detalle.get('message', 'sin detalle')}"
        ) from None


if __name__ == "__main__":
    main()

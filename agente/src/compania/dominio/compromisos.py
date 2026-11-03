"""Promesas de llamada que la familia deja en el grupo: "Abue, salgo a las 5 y te marco".

Se reconoce una hora y un verbo de llamar. La hora sin "de la mañana" o "de la tarde" se
interpreta como la más probable: de 1 a 7 es por la tarde, y una hora que ya pasó hoy por la
mañana también se pasa a la tarde. Si la hora resultante ya pasó, el compromiso es para mañana.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

LLAMAR = re.compile(r"\b(te\s+)?(marco|marcare|llamo|llamare|hablo|hablare|marcamos|llamamos|videollamada)\b")
HORA_CON_MINUTOS = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm|a\.?\s?m\.?|p\.?\s?m\.?)?")
A_LAS = re.compile(
    r"\ba\s+la(?:s)?\s+(\d{1,2})(?:\s+y\s+(media|cuarto))?"
    r"(?:\s+(de\s+la\s+manana|de\s+la\s+tarde|de\s+la\s+noche|am|pm))?"
)


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")


def _a_24(hora: int, marca: str | None, minutos: int, ahora: datetime) -> int | None:
    if not 0 <= hora <= 23:
        return None
    marca = (marca or "").replace(".", "").replace(" ", "")
    if marca in ("pm", "delatarde", "delanoche") and hora < 12:
        return hora + 12
    if marca in ("am", "delamanana"):
        return 0 if hora == 12 else hora
    if hora >= 12:
        return hora
    if 1 <= hora <= 7:
        return hora + 12
    # De 8 a 11 sin marca: si esa hora de la mañana ya pasó, es por la tarde o noche
    if ahora.replace(hour=hora, minute=minutos) <= ahora:
        return hora + 12
    return hora


def extraer_compromiso(texto: str, ahora: datetime) -> tuple[str, str] | None:
    """Devuelve (fecha, hora) si el texto promete una llamada a una hora; si no, None."""
    t = _normalizar(texto)
    if not LLAMAR.search(t):
        return None

    m = HORA_CON_MINUTOS.search(t)
    if m:
        hora, minutos, marca = int(m.group(1)), int(m.group(2)), m.group(3)
    else:
        m = A_LAS.search(t)
        if not m:
            return None
        hora = int(m.group(1))
        minutos = {"media": 30, "cuarto": 15}.get(m.group(2) or "", 0)
        marca = m.group(3)
    if minutos > 59:
        return None

    hora24 = _a_24(hora, marca, minutos, ahora)
    if hora24 is None:
        return None
    momento = ahora.replace(hour=hora24, minute=minutos, second=0, microsecond=0)
    if momento <= ahora:
        momento += timedelta(days=1)
    return momento.strftime("%Y-%m-%d"), momento.strftime("%H:%M")

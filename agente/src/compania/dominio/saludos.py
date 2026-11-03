"""Imágenes de saludo que la persona comparte con su familia ("buenos días, feliz martes").

La asistente aprende qué le gusta (rosas, la Virgen, café, gatitos...) a partir de las imágenes
que la persona manda o reenvía, y arma búsquedas con esos temas y el día de la semana.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
TEMA_POR_OMISION = "flores"


def saludo_de_la_hora(ahora: datetime) -> str:
    if ahora.hour < 12:
        return "buenos días"
    if ahora.hour < 19:
        return "buenas tardes"
    return "buenas noches"


def consulta_del_dia(temas: Sequence[str], ahora: datetime, indice: int = 0) -> str:
    """Búsqueda para imágenes de saludo del día con uno de sus temas favoritos."""
    tema = temas[indice % len(temas)] if temas else TEMA_POR_OMISION
    dia = DIAS[ahora.weekday()]
    # Corta, como la escribe la gente: las frases largas traen fotos de stock sin saludo
    return f"{saludo_de_la_hora(ahora)} feliz {dia} {tema} frases"


def texto_para_la_persona(trato: str, ahora: datetime, parecidas: bool = False) -> str:
    """Mensaje que acompaña las imágenes en el chat de la persona."""
    hola = saludo_de_la_hora(ahora).capitalize()
    que = "unas imágenes parecidas a la que me mandó" if parecidas else "estas imágenes"
    return (
        f"{hola}, {trato}. Le encontré {que} para que se las mande a su familia. "
        "Si alguna le gusta, déjela presionada y toque Reenviar."
    )

"""Juegos de memoria por voz."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum


class TipoJuego(StrEnum):
    REFRAN = "refran"
    ADIVINANZA = "adivinanza"
    LISTA_PALABRAS = "lista_palabras"


@dataclass(frozen=True, slots=True)
class Juego:
    id: str
    tipo: TipoJuego
    instruccion: str
    contenido: str
    respuesta: str
    pista: str


JUEGOS: tuple[Juego, ...] = (
    Juego(
        "ref01",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "Al que madruga...",
        "Dios lo ayuda",
        "Habla de levantarse temprano",
    ),
    Juego(
        "ref02",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "Camarón que se duerme...",
        "se lo lleva la corriente",
        "Pasa en el río",
    ),
    Juego(
        "ref03",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "Más vale pájaro en mano...",
        "que ciento volando",
        "Son muchos pájaros",
    ),
    Juego(
        "ref04",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "No por mucho madrugar...",
        "amanece más temprano",
        "Habla del sol",
    ),
    Juego(
        "ref05",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "A falta de pan...",
        "tortillas",
        "Algo que se come diario",
    ),
    Juego(
        "ref06",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "Dime con quién andas...",
        "y te diré quién eres",
        "Habla de las amistades",
    ),
    Juego(
        "ref07",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "Agua que no has de beber...",
        "déjala correr",
        "El agua sigue su camino",
    ),
    Juego(
        "ref08",
        TipoJuego.REFRAN,
        "Complete el refrán",
        "El que es perico...",
        "dondequiera es verde",
        "Habla de un color",
    ),
    Juego(
        "adi01",
        TipoJuego.ADIVINANZA,
        "Adivine qué es",
        "Blanca por dentro, verde por fuera; si quiere que se lo diga, espera.",
        "la pera",
        "Es una fruta",
    ),
    Juego(
        "adi02",
        TipoJuego.ADIVINANZA,
        "Adivine qué es",
        "Oro parece, plata no es; el que no lo adivine, bien tonto es.",
        "el plátano",
        "Es una fruta amarilla",
    ),
    Juego(
        "adi03",
        TipoJuego.ADIVINANZA,
        "Adivine qué es",
        "Tiene dientes y no come, tiene barbas y no es hombre.",
        "el ajo",
        "Se usa en la cocina",
    ),
    Juego(
        "lis01",
        TipoJuego.LISTA_PALABRAS,
        "Escuche y repita estas palabras al final de la plática",
        "mesa, naranja, perro",
        "mesa, naranja, perro",
        "Un mueble, una fruta y un animal",
    ),
    Juego(
        "lis02",
        TipoJuego.LISTA_PALABRAS,
        "Escuche y repita estas palabras al final de la plática",
        "río, guitarra, sombrero, pan",
        "río, guitarra, sombrero, pan",
        "Agua, música, ropa y comida",
    ),
)

JUEGOS_POR_ID: dict[str, Juego] = {j.id: j for j in JUEGOS}


def obtener_juego(tipo: TipoJuego | str | None, excluir: Collection[str] = ()) -> Juego | None:
    """Devuelve el primer juego del tipo pedido que no esté en ``excluir``."""
    tipo = TipoJuego(tipo) if tipo else None
    for juego in JUEGOS:
        if juego.id in excluir:
            continue
        if tipo is None or juego.tipo == tipo:
            return juego
    return None

"""Preguntas de bienestar y cálculo de la señal de bienestar.

Las preguntas se inspiran en la Escala de Depresión Geriátrica de 15 ítems (GDS-15,
Yesavage) y en la escala breve de soledad de tres ítems (Hughes et al., 2004).
La señal es una tendencia para la familia y no un diagnóstico: aplicar las
preguntas dentro de una conversación no es el formato validado de las escalas.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from compania.dominio.modelos import RespuestaBienestar, Semaforo

DIAS_VENTANA = 14
MINIMO_RESPUESTAS = 5
UMBRAL_AMARILLO = 0.34
UMBRAL_ROJO = 0.60


@dataclass(frozen=True, slots=True)
class Pregunta:
    id: str
    texto: str
    respuesta_que_suma: str
    escala: str


# GDS-15: suma un punto la respuesta indicada. Los ítems 1, 5, 7, 11 y 13 suman con "no".
PREGUNTAS_GDS15: tuple[Pregunta, ...] = (
    Pregunta("gds01", "¿Está satisfecho o satisfecha con su vida?", "no", "gds15"),
    Pregunta("gds02", "¿Ha dejado muchas de sus actividades y cosas que le interesaban?", "si", "gds15"),
    Pregunta("gds03", "¿Siente que su vida está vacía?", "si", "gds15"),
    Pregunta("gds04", "¿Se aburre seguido?", "si", "gds15"),
    Pregunta("gds05", "¿Está de buen ánimo la mayor parte del tiempo?", "no", "gds15"),
    Pregunta("gds06", "¿Tiene miedo de que algo malo le vaya a pasar?", "si", "gds15"),
    Pregunta("gds07", "¿Se siente feliz la mayor parte del tiempo?", "no", "gds15"),
    Pregunta("gds08", "¿Se siente seguido desamparado o desamparada?", "si", "gds15"),
    Pregunta("gds09", "¿Prefiere quedarse en casa en lugar de salir a hacer cosas nuevas?", "si", "gds15"),
    Pregunta("gds10", "¿Siente que tiene más problemas de memoria que la mayoría?", "si", "gds15"),
    Pregunta("gds11", "¿Piensa que es maravilloso estar vivo o viva?", "no", "gds15"),
    Pregunta("gds12", "¿Se siente inútil tal como está ahora?", "si", "gds15"),
    Pregunta("gds13", "¿Se siente con mucha energía?", "no", "gds15"),
    Pregunta("gds14", "¿Siente que su situación no tiene esperanza?", "si", "gds15"),
    Pregunta("gds15", "¿Cree que la mayoría de la gente está mejor que usted?", "si", "gds15"),
)

# Escala breve de soledad: se registra "si" cuando la persona lo siente seguido.
PREGUNTAS_SOLEDAD: tuple[Pregunta, ...] = (
    Pregunta("sol01", "¿Seguido siente que le falta compañía?", "si", "soledad3"),
    Pregunta("sol02", "¿Seguido se siente excluido o excluida?", "si", "soledad3"),
    Pregunta("sol03", "¿Seguido se siente aislado o aislada de los demás?", "si", "soledad3"),
)

PREGUNTAS: dict[str, Pregunta] = {p.id: p for p in PREGUNTAS_GDS15 + PREGUNTAS_SOLEDAD}

RESPUESTAS_VALIDAS = {"si", "no"}


def normalizar_respuesta(respuesta: str) -> str:
    """Convierte variantes habladas a "si" o "no"."""
    valor = respuesta.strip().lower().replace("í", "i")
    if valor in {"si", "sí", "claro", "a veces si", "seguido"}:
        return "si"
    if valor in {"no", "casi no", "nunca"}:
        return "no"
    raise ValueError(f"Respuesta no reconocida: {respuesta!r}")


def puntua(pregunta_id: str, respuesta: str) -> int:
    """Devuelve 1 si la respuesta suma en la escala, 0 si no."""
    pregunta = PREGUNTAS[pregunta_id]
    return int(normalizar_respuesta(respuesta) == pregunta.respuesta_que_suma)


@dataclass(frozen=True, slots=True)
class SenalBienestar:
    semaforo: Semaforo
    respondidas: int
    puntos: int
    proporcion: float
    hubo_crisis: bool
    nota: str = "Tendencia calculada con preguntas inspiradas en escalas validadas. No es un diagnóstico."


def _ultimas_por_pregunta(
    respuestas: Iterable[RespuestaBienestar], desde: datetime
) -> dict[str, RespuestaBienestar]:
    ultimas: dict[str, RespuestaBienestar] = {}
    for r in sorted(respuestas, key=lambda x: x.creado):
        if r.creado >= desde and r.pregunta_id in PREGUNTAS:
            ultimas[r.pregunta_id] = r
    return ultimas


def calcular_senal(
    respuestas: Iterable[RespuestaBienestar],
    *,
    ahora: datetime | None = None,
    hubo_crisis: bool = False,
) -> SenalBienestar:
    """Calcula la señal con la respuesta más reciente de cada pregunta en la ventana."""
    ahora = ahora or datetime.now()
    ultimas = _ultimas_por_pregunta(respuestas, ahora - timedelta(days=DIAS_VENTANA))
    respondidas = len(ultimas)
    puntos = sum(puntua(r.pregunta_id, r.respuesta) for r in ultimas.values())
    proporcion = puntos / respondidas if respondidas else 0.0

    if hubo_crisis:
        semaforo = Semaforo.ROJO
    elif respondidas < MINIMO_RESPUESTAS:
        semaforo = Semaforo.INSUFICIENTE
    elif proporcion >= UMBRAL_ROJO:
        semaforo = Semaforo.ROJO
    elif proporcion >= UMBRAL_AMARILLO:
        semaforo = Semaforo.AMARILLO
    else:
        semaforo = Semaforo.VERDE

    return SenalBienestar(semaforo, respondidas, puntos, round(proporcion, 2), hubo_crisis)


def elegir_preguntas_del_dia(
    respuestas: Sequence[RespuestaBienestar],
    *,
    cantidad: int = 2,
    ahora: datetime | None = None,
) -> list[Pregunta]:
    """Elige preguntas sin respuesta reciente, en orden, para no repetir."""
    ahora = ahora or datetime.now()
    recientes = _ultimas_por_pregunta(respuestas, ahora - timedelta(days=DIAS_VENTANA))
    pendientes = [p for p in PREGUNTAS.values() if p.id not in recientes]
    if len(pendientes) < cantidad:
        mas_antiguas = sorted(recientes.values(), key=lambda r: r.creado)
        pendientes += [PREGUNTAS[r.pregunta_id] for r in mas_antiguas]
    return pendientes[:cantidad]

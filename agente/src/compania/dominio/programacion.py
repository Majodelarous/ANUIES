"""Qué llamadas toca lanzar: llamadas diarias y recordatorios a su hora.

Reglas:
- Una llamada programada se lanza a su hora, con una ventana de tolerancia por si el
  programador estuvo detenido unos minutos.
- Un recordatorio se lanza como llamada corta a su hora, salvo que haya una llamada diaria
  en los 30 minutos siguientes: en esa llamada la asistente ya lo menciona. Una llamada diaria
  anterior no lo cubre (pudo crearse en esa misma llamada, por ejemplo "en 5 minutos").
- Un recordatorio de una sola vez siempre tiene su propia llamada y luego se desactiva.
- Cada tarea se lanza una sola vez al día (su clave incluye la fecha).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from compania.dominio.modelos import Horario, Recordatorio

VENTANA = timedelta(minutes=10)
CERCANIA = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class Tarea:
    clave: str
    tipo: str  # "llamada" o "recordatorio"
    persona_id: int
    hora: str
    recordatorio_id: int | None = None
    texto: str = ""

    @property
    def motivo(self) -> str:
        return f"recordatorio:{self.recordatorio_id}" if self.tipo == "recordatorio" else "programada"


def a_fecha(hora: str, dia: datetime) -> datetime:
    h, m = (int(x) for x in hora.split(":"))
    return dia.replace(hour=h, minute=m, second=0, microsecond=0)


def tareas_pendientes(
    ahora: datetime,
    horarios: Iterable[Horario],
    recordatorios: Iterable[Recordatorio],
    ejecutadas: Collection[str],
) -> list[Tarea]:
    """Tareas cuya hora ya llegó (dentro de la ventana) y que no se han lanzado hoy."""
    dia = ahora.strftime("%Y-%m-%d")
    horarios = [h for h in horarios if h.activo]
    horas_llamada = [a_fecha(h.hora, ahora) for h in horarios]
    tareas: list[Tarea] = []

    for h in horarios:
        momento = a_fecha(h.hora, ahora)
        clave = f"{dia} {h.hora} llamada {h.persona_id}"
        if momento <= ahora < momento + VENTANA and clave not in ejecutadas:
            tareas.append(Tarea(clave, "llamada", h.persona_id, h.hora))

    for r in recordatorios:
        if not r.activo or r.id is None:
            continue
        momento = a_fecha(r.hora, ahora)
        if not r.una_vez and any(timedelta(0) <= llamada - momento <= CERCANIA for llamada in horas_llamada):
            continue  # la llamada diaria que viene ya lo incluye
        clave = f"{dia} {r.hora} recordatorio {r.id}"
        if momento <= ahora < momento + VENTANA and clave not in ejecutadas:
            tareas.append(Tarea(clave, "recordatorio", r.persona_id, r.hora, r.id, r.texto))

    return sorted(tareas, key=lambda t: t.hora)

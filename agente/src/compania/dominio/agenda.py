"""Agenda de la llamada: lo que la asistente debe entregar y todavía no entrega.

El modelo de voz puede olvidar un pendiente, por ejemplo si la persona le interrumpe al
inicio. La agenda lleva la cuenta en el código y decide cuándo recordárselo, sin depender
de la memoria del modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compania.dominio.modelos import MensajeFamiliar

PRIMER_RECORDATORIO = 2  # turnos de la asistente antes del primer recordatorio
CADA = 3  # turnos entre recordatorios


@dataclass
class Agenda:
    mensajes: dict[int, MensajeFamiliar] = field(default_factory=dict)
    entregados: set[int] = field(default_factory=set)
    turnos: int = 0
    ultimo_recordatorio: int | None = None

    @classmethod
    def desde(cls, mensajes: list[MensajeFamiliar]) -> Agenda:
        return cls({m.id: m for m in mensajes if m.id is not None})

    def entregar(self, mensaje_id: int) -> None:
        if mensaje_id in self.mensajes:
            self.entregados.add(mensaje_id)

    def pendientes(self) -> list[MensajeFamiliar]:
        return [m for i, m in self.mensajes.items() if i not in self.entregados]

    def descripcion(self) -> str:
        """Pendientes en una frase, para el modelo."""
        partes = [
            f"id {m.id}, {'nota de voz' if m.audio else 'mensaje'} de {m.de}" for m in self.pendientes()
        ]
        return "; ".join(partes) if partes else "ninguno"

    def turno_terminado(self) -> str | None:
        """Cuenta un turno de la asistente y devuelve una nota si toca recordar los pendientes."""
        self.turnos += 1
        if not self.pendientes() or self.turnos < PRIMER_RECORDATORIO:
            return None
        if self.ultimo_recordatorio is not None and self.turnos - self.ultimo_recordatorio < CADA:
            return None
        self.ultimo_recordatorio = self.turnos
        return (
            "[Nota interna, no la leas en voz alta] Siguen pendientes: "
            f"{self.descripcion()}. En la próxima pausa natural, ofrécelos. "
            "Si es nota de voz, pregunta si quiere escucharla."
        )

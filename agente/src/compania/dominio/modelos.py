"""Entidades del dominio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class NivelAlerta(StrEnum):
    INFORMATIVA = "informativa"
    ATENCION = "atencion"
    CRISIS = "crisis"


class Semaforo(StrEnum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"
    INSUFICIENTE = "insuficiente"


@dataclass(slots=True)
class Persona:
    nombre: str
    trato: str
    contacto_emergencia: str | None = None
    id: int | None = None
    # Número de WhatsApp o teléfono, con código de país
    telefono: str | None = None
    # Cuándo aceptó que la asistente recuerde lo que cuenta y comparta un resumen con su familia
    consentimiento: datetime | None = None


@dataclass(slots=True)
class Recuerdo:
    persona_id: int
    tema: str
    contenido: str
    compartir_con_familia: bool = False
    creado: datetime = field(default_factory=datetime.now)
    id: int | None = None


@dataclass(slots=True)
class RespuestaBienestar:
    persona_id: int
    pregunta_id: str
    respuesta: str
    creado: datetime = field(default_factory=datetime.now)
    id: int | None = None


@dataclass(slots=True)
class Recordatorio:
    persona_id: int
    texto: str
    hora: str
    creado_por: str = "persona"
    activo: bool = True
    id: int | None = None


@dataclass(slots=True)
class MensajeFamiliar:
    persona_id: int
    de: str
    texto: str
    audio: str | None = None
    entregado: bool = False
    creado: datetime = field(default_factory=datetime.now)
    id: int | None = None


@dataclass(slots=True)
class Alerta:
    persona_id: int
    nivel: NivelAlerta
    motivo: str
    creado: datetime = field(default_factory=datetime.now)
    id: int | None = None


@dataclass(slots=True)
class Llamada:
    persona_id: int
    canal: str
    inicio: datetime = field(default_factory=datetime.now)
    fin: datetime | None = None
    id: int | None = None


@dataclass(slots=True)
class Seguimiento:
    """Algo que quedó pendiente de preguntar en otra llamada (por ejemplo, si ya habló con su hija)."""

    persona_id: int
    para: str
    motivo: str
    creado: datetime = field(default_factory=datetime.now)
    cerrado: datetime | None = None
    resultado: str | None = None
    id: int | None = None


@dataclass(slots=True)
class Horario:
    """Hora del día a la que la asistente llama a la persona."""

    persona_id: int
    hora: str
    activo: bool = True
    id: int | None = None

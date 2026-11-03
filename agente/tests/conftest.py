from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from compania.dominio.modelos import Persona
from compania.infraestructura.repositorio import Repositorio


@pytest.fixture
def repo(tmp_path):
    repositorio = Repositorio(tmp_path / "prueba.db")
    yield repositorio
    repositorio.cerrar()


@pytest.fixture
def persona(repo) -> Persona:
    return repo.guardar_persona(
        Persona("Carmen", "doña Carmen", "555 000 0000", consentimiento=datetime.now())
    )


class LLMFalso:
    """Guarda los frames que una herramienta empuja hacia la salida."""

    def __init__(self) -> None:
        self.frames: list = []

    async def push_frame(self, frame, *args, **kwargs) -> None:
        self.frames.append(frame)


class AvisoFalso:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.enviados: list[str] = []
        self.audios: list[tuple[bytes, str]] = []
        self.imagenes: list[tuple[bytes, str]] = []

    async def enviar(self, texto: str) -> bool:
        self.enviados.append(texto)
        return self.ok

    async def enviar_audio(self, wav: bytes, texto: str = "") -> bool:
        self.audios.append((wav, texto))
        return self.ok

    async def enviar_imagen(self, imagen: bytes, texto: str = "") -> bool:
        self.imagenes.append((imagen, texto))
        return self.ok


@dataclass
class ParametrosFalsos:
    """Imita lo que las herramientas usan de FunctionCallParams."""

    arguments: dict
    resultado: Any = field(default=None)
    llm: Any = field(default_factory=LLMFalso)

    async def result_callback(self, result: Any, **kwargs: Any) -> None:
        self.resultado = result

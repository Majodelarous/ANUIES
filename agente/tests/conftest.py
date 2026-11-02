from dataclasses import dataclass, field
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
    return repo.guardar_persona(Persona("Carmen", "doña Carmen", "555 000 0000"))


@dataclass
class ParametrosFalsos:
    """Imita lo que las herramientas usan de FunctionCallParams."""

    arguments: dict
    resultado: Any = field(default=None)

    async def result_callback(self, result: Any, **kwargs: Any) -> None:
        self.resultado = result

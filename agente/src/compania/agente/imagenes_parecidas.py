"""Busca imágenes de saludo para que la persona las reenvíe a su familia (tipo Google Lens).

- Si la persona le manda una imagen a la asistente, se entiende qué muestra, se guarda el tema
  como algo que le gusta y se buscan imágenes parecidas en internet.
- En la llamada, la asistente puede buscarle imágenes de un tema o de sus temas favoritos.

Las imágenes llegan al chat de la persona; ella elige cuál reenviar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from compania.dominio.saludos import consulta_del_dia
from compania.infraestructura.lente import (
    Buscador,
    BuscadorDDGS,
    Descripcion,
    Descriptor,
    DescriptorGemini,
)
from compania.infraestructura.repositorio import Repositorio

CUANTAS = 3


@dataclass
class Resultado:
    imagenes: list[bytes] = field(default_factory=list)
    descripcion: Descripcion | None = None


class ImagenesParecidas:
    def __init__(
        self,
        repo: Repositorio,
        descriptor: Descriptor | None = None,
        buscador: Buscador | None = None,
    ) -> None:
        self.repo = repo
        self.descriptor = descriptor or DescriptorGemini()
        self.buscador = buscador or BuscadorDDGS()

    async def aprender(self, persona_id: int, imagen: bytes, mime: str) -> Descripcion | None:
        """Entiende la imagen y guarda su tema como algo que le gusta a la persona."""
        descripcion = await self.descriptor.describir(imagen, mime)
        if descripcion:
            self.repo.sumar_preferencia_imagen(persona_id, descripcion.tema)
        return descripcion

    async def parecidas(self, persona_id: int, imagen: bytes, mime: str) -> Resultado:
        descripcion = await self.aprender(persona_id, imagen, mime)
        if descripcion is None:
            return Resultado()
        return Resultado(await self.buscador.buscar(descripcion.consulta, CUANTAS), descripcion)

    async def del_dia(self, persona_id: int, ahora: datetime, tema: str = "") -> Resultado:
        """Imágenes de saludo con el tema pedido o con lo que más le gusta."""
        temas = [tema.strip().lower()] if tema.strip() else self.repo.temas_favoritos(persona_id)
        return Resultado(await self.buscador.buscar(consulta_del_dia(temas, ahora), CUANTAS))

"""Lente de imágenes: entiende una imagen y busca otras parecidas en internet.

- ``DescriptorGemini`` describe la imagen con Gemini (tema y una búsqueda para encontrar
  imágenes parecidas). Usa ``GOOGLE_API_KEY``; el modelo se cambia con ``LENTE_MODELO``.
- ``BuscadorDDGS`` busca imágenes con ddgs (código abierto, sin llave) usando Bing, y las
  descarga. El backend de DuckDuckGo de ddgs falla ("malformed headers"), por eso va fijo.
- ``preparar_imagen`` valida lo descargado y lo deja en JPEG de tamaño razonable.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from loguru import logger
from PIL import Image, UnidentifiedImageError

LADO_MAXIMO = 1280
LADO_MINIMO = 300
AGENTE = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

INSTRUCCION = (
    "Es una imagen que una persona mayor mexicana compartió o le gustó, probablemente un saludo "
    "para WhatsApp (buenos días, bendiciones, feliz día). Responde solo con JSON: "
    '{"tema": "2 a 4 palabras con lo principal, por ejemplo rosas rojas, Virgen de Guadalupe, '
    'taza de café, gatitos", "consulta": "búsqueda corta en español de 4 a 7 palabras para '
    'encontrar imágenes de saludo parecidas, como buenos días rosas rojas frases", '
    '"descripcion": "una frase corta de lo que muestra"}'
)


@dataclass(frozen=True, slots=True)
class Descripcion:
    tema: str
    consulta: str
    descripcion: str = ""


class Descriptor(Protocol):
    async def describir(self, imagen: bytes, mime: str) -> Descripcion | None: ...


class Buscador(Protocol):
    async def buscar(self, consulta: str, cuantas: int = 3) -> list[bytes]: ...


def preparar_imagen(datos: bytes) -> bytes | None:
    """JPEG listo para WhatsApp, o None si no es imagen o es muy chica."""
    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    if min(imagen.size) < LADO_MINIMO:
        return None
    imagen = imagen.convert("RGB")
    imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=88)
    return salida.getvalue()


def _leer_json(texto: str) -> dict:
    texto = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(texto)


# Si un modelo está saturado (503) se prueba el siguiente
MODELOS_DE_RESPALDO = ("gemini-flash-latest", "gemini-flash-lite-latest")


class DescriptorGemini:
    def __init__(self, api_key: str | None = None, modelo: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        elegido = modelo or os.getenv("LENTE_MODELO")
        self.modelos = tuple(dict.fromkeys(([elegido] if elegido else []) + list(MODELOS_DE_RESPALDO)))

    def _describir(self, imagen: bytes, mime: str, modelo: str) -> Descripcion | None:
        from google import genai
        from google.genai import types

        cliente = genai.Client(api_key=self.api_key)
        respuesta = cliente.models.generate_content(
            model=modelo,
            contents=[types.Part.from_bytes(data=imagen, mime_type=mime), INSTRUCCION],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        datos = _leer_json(respuesta.text or "{}")
        tema = str(datos.get("tema") or "").strip().lower()
        consulta = str(datos.get("consulta") or "").strip()
        if not tema or not consulta:
            return None
        return Descripcion(tema[:60], consulta[:150], str(datos.get("descripcion") or "")[:200])

    async def describir(self, imagen: bytes, mime: str) -> Descripcion | None:
        if not self.api_key:
            logger.warning("Lente: falta GOOGLE_API_KEY para entender la imagen")
            return None
        for modelo in self.modelos:
            try:
                return await asyncio.to_thread(self._describir, imagen, mime, modelo)
            except Exception as error:  # la llamada a la API puede fallar de muchas formas
                logger.warning(f"Lente: {modelo} no pudo describir la imagen: {str(error)[:160]}")
        return None


class BuscadorDDGS:
    def __init__(self, region: str = "mx-es", intentos: int = 15, backend: str | None = None):
        self.region = region
        self.backend = backend or os.getenv("LENTE_BUSCADOR") or "bing"
        self.intentos = intentos

    @staticmethod
    def _descargar(url: str) -> bytes | None:
        solicitud = urllib.request.Request(url, headers={"User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(solicitud, timeout=8) as respuesta:
                return respuesta.read(6 * 1024 * 1024)
        except Exception:  # sitios caídos, bloqueos, tiempos de espera
            return None

    def _buscar(self, consulta: str, cuantas: int) -> list[bytes]:
        from ddgs import DDGS

        resultados = DDGS(timeout=10).images(
            consulta,
            region=self.region,
            safesearch="on",
            max_results=self.intentos,
            backend=self.backend,
        )
        imagenes: list[bytes] = []
        vistas: set[int] = set()
        for r in resultados:
            datos = self._descargar(str(r.get("image") or ""))
            lista = preparar_imagen(datos) if datos else None
            if lista is None or len(lista) in vistas:
                continue
            vistas.add(len(lista))
            imagenes.append(lista)
            if len(imagenes) >= cuantas:
                break
        return imagenes

    async def buscar(self, consulta: str, cuantas: int = 3) -> list[bytes]:
        try:
            return await asyncio.to_thread(self._buscar, consulta, cuantas)
        except Exception as error:
            logger.warning(f"Lente: falló la búsqueda de imágenes '{consulta}': {error}")
            return []

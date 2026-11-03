"""Imágenes de buenos días que la persona manda a su familia.

Se dibujan aquí mismo (originales, sin personajes ni imágenes de internet): degradado cálido,
sol, flores sencillas y el saludo del día con la frase y la firma de la persona.
"""

from __future__ import annotations

import io
import math
import random
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LADO = 1080
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# Colores (arriba, abajo, flores) por día de la semana
PALETAS = [
    ((255, 214, 165), (255, 159, 128), (214, 69, 80)),
    ((255, 236, 179), (255, 183, 77), (230, 81, 0)),
    ((200, 230, 201), (129, 199, 132), (233, 30, 99)),
    ((187, 222, 251), (144, 202, 249), (255, 152, 0)),
    ((248, 187, 208), (240, 98, 146), (255, 235, 59)),
    ((255, 224, 178), (255, 171, 145), (156, 39, 176)),
    ((225, 190, 231), (186, 104, 200), (255, 213, 79)),
]
FUENTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSerif-Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
]


def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for ruta in FUENTES:
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default(size=tamano)


def saludo(ahora: datetime) -> tuple[str, str]:
    """(saludo según la hora, frase del día)."""
    if ahora.hour < 12:
        hola = "¡Buenos días!"
    elif ahora.hour < 19:
        hola = "¡Buenas tardes!"
    else:
        hola = "¡Buenas noches!"
    dia = DIAS[ahora.weekday()]
    frase = "Feliz inicio de semana" if ahora.weekday() == 0 else f"Feliz {dia}"
    return hola, frase


def _envolver(texto: str, fuente, ancho: int, dibujo: ImageDraw.ImageDraw) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if dibujo.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _texto_centrado(dibujo, y, texto, fuente, color, sombra=(0, 0, 0, 70)) -> int:
    ancho = dibujo.textlength(texto, font=fuente)
    x = (LADO - ancho) / 2
    dibujo.text((x + 3, y + 3), texto, font=fuente, fill=sombra)
    dibujo.text((x, y), texto, font=fuente, fill=color)
    alto = fuente.getbbox(texto)[3] if hasattr(fuente, "getbbox") else 40
    return y + alto


def _flor(dibujo, cx, cy, r, color):
    for i in range(5):
        a = 2 * math.pi * i / 5
        px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
        dibujo.ellipse((px - r * 0.8, py - r * 0.8, px + r * 0.8, py + r * 0.8), fill=color)
    dibujo.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55), fill=(239, 108, 0))


def dibujar(mensaje: str, firma: str, ahora: datetime | None = None) -> bytes:
    """Devuelve la imagen en JPEG."""
    ahora = ahora or datetime.now()
    arriba, abajo, flores = PALETAS[ahora.weekday()]
    azar = random.Random(ahora.strftime("%Y%m%d"))

    fondo = Image.new("RGB", (LADO, LADO))
    pixeles = fondo.load()
    for y in range(LADO):
        t = y / (LADO - 1)
        color = tuple(int(arriba[i] + (abajo[i] - arriba[i]) * t) for i in range(3))
        for x in range(LADO):
            pixeles[x, y] = color

    capa = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    # Sol con rayos
    sx, sy = 860, 200
    for i in range(16):
        a = 2 * math.pi * i / 16
        d.line(
            (sx + math.cos(a) * 110, sy + math.sin(a) * 110, sx + math.cos(a) * 160, sy + math.sin(a) * 160),
            fill=(255, 241, 118, 220),
            width=10,
        )
    d.ellipse((sx - 90, sy - 90, sx + 90, sy + 90), fill=(255, 235, 59, 255))
    # Puntos de luz
    for _ in range(40):
        x, y, r = azar.randint(0, LADO), azar.randint(0, LADO // 2), azar.randint(3, 9)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 90))
    # Flores abajo
    for i in range(9):
        cx = 60 + i * 120 + azar.randint(-20, 20)
        cy = LADO - 70 - azar.randint(0, 60)
        d.line((cx, cy, cx + azar.randint(-15, 15), LADO), fill=(76, 140, 74, 255), width=8)
        _flor(d, cx, cy, azar.randint(28, 42), flores + (255,))
    capa = capa.filter(ImageFilter.SMOOTH)
    fondo = Image.alpha_composite(fondo.convert("RGBA"), capa)

    # Recuadro para el texto
    tarjeta = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    ImageDraw.Draw(tarjeta).rounded_rectangle((90, 330, LADO - 90, 830), radius=48, fill=(255, 255, 255, 120))
    fondo = Image.alpha_composite(fondo, tarjeta)

    d = ImageDraw.Draw(fondo)
    hola, frase = saludo(ahora)
    oscuro = (93, 46, 30, 255)
    y = _texto_centrado(d, 370, hola, _fuente(96), oscuro) + 30
    y = _texto_centrado(d, y, frase, _fuente(64), oscuro) + 40
    fuente_mensaje = _fuente(46)
    for linea in _envolver(mensaje.strip(), fuente_mensaje, LADO - 260, d)[:3]:
        y = _texto_centrado(d, y, linea, fuente_mensaje, (60, 30, 20, 255), sombra=(0, 0, 0, 0)) + 14
    if firma.strip():
        _texto_centrado(
            d, max(y + 20, 740), f"Con cariño, {firma.strip()}", _fuente(42), oscuro, sombra=(0, 0, 0, 0)
        )

    salida = io.BytesIO()
    fondo.convert("RGB").save(salida, "JPEG", quality=90)
    return salida.getvalue()

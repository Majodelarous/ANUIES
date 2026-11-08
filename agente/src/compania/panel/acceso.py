"""Inicio de sesión del panel con una contraseña compartida.

- ``PANEL_CLAVE_HASH`` en el .env: hash PBKDF2 de la contraseña (``uv run compania-panel-clave``).
- ``PANEL_PUBLICO=1``: el panel está en internet (detrás de Caddy). Sin hash, no abre.
- Sin hash y sin ``PANEL_PUBLICO``: el panel queda abierto, como antes, para usarlo en la propia computadora.

La sesión es una cookie firmada con una llave derivada del hash: al cambiar la contraseña se
cierran todas las sesiones. Tras varios intentos fallidos desde una IP, se bloquea un rato.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

COOKIE = "rous_sesion"
DURACION_S = 7 * 24 * 3600
ITERACIONES = 600_000
VENTANA_S = 15 * 60
MAX_POR_IP = 5
MAX_TOTAL = 40
LIBRES = {"/entrar"}


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _desde_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def hash_de_clave(clave: str, sal: bytes | None = None, iteraciones: int = ITERACIONES) -> str:
    """Formato ``pbkdf2_sha256:iteraciones:sal:hash`` (sin "$", que Docker Compose interpretaría)."""
    sal = sal or secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, iteraciones)
    return f"pbkdf2_sha256:{iteraciones}:{_b64(sal)}:{_b64(derivada)}"


def clave_correcta(clave: str, guardado: str) -> bool:
    try:
        algoritmo, iteraciones, sal, esperado = guardado.split(":")
        if algoritmo != "pbkdf2_sha256":
            return False
        derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), _desde_b64(sal), int(iteraciones))
    except ValueError:
        return False
    return hmac.compare_digest(_b64(derivada), esperado)


class Acceso:
    def __init__(self, clave_hash: str | None, publico: bool, reloj=time.time):
        self.clave_hash = (clave_hash or "").strip()
        self.publico = publico
        self.reloj = reloj
        self.llave = hashlib.sha256(b"rous-sesion:" + self.clave_hash.encode()).digest()
        self.fallos: dict[str, deque[float]] = defaultdict(deque)
        self.fallos_totales: deque[float] = deque()

    @property
    def activo(self) -> bool:
        return bool(self.clave_hash)

    @property
    def sin_configurar(self) -> bool:
        """En internet sin contraseña: no se abre nada."""
        return self.publico and not self.activo

    def firmar(self, vence: int) -> str:
        firma = hmac.new(self.llave, str(vence).encode(), hashlib.sha256).hexdigest()
        return f"{vence}.{firma}"

    def sesion_valida(self, valor: str | None) -> bool:
        if not valor or "." not in valor:
            return False
        vence, _ = valor.split(".", 1)
        if not vence.isdigit() or int(vence) < self.reloj():
            return False
        return hmac.compare_digest(self.firmar(int(vence)), valor)

    def _limpiar(self, cola: deque[float]) -> None:
        limite = self.reloj() - VENTANA_S
        while cola and cola[0] < limite:
            cola.popleft()

    def bloqueado(self, ip: str) -> bool:
        self._limpiar(self.fallos[ip])
        self._limpiar(self.fallos_totales)
        return len(self.fallos[ip]) >= MAX_POR_IP or len(self.fallos_totales) >= MAX_TOTAL

    def registrar_fallo(self, ip: str) -> None:
        ahora = self.reloj()
        self.fallos[ip].append(ahora)
        self.fallos_totales.append(ahora)


def ip_de(request: Request, publico: bool) -> str:
    # Detrás de Caddy, la IP real llega en X-Forwarded-For (Caddy pone la del cliente al final)
    if publico and (reenviada := request.headers.get("x-forwarded-for")):
        return reenviada.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def destino_seguro(siguiente: str) -> str:
    return siguiente if siguiente.startswith("/") and not siguiente.startswith("//") else "/control"


def pagina_entrar(css: str, error: str = "", siguiente: str = "/control") -> str:
    aviso = f'<p class="aviso-entrar" role="alert">{escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="es-MX"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Entrar al panel</title><style>{css}</style></head>
<body><main class="entrar"><div class="contenido">
<p class="marca">Compañía por voz</p>
<h1>Entrar al panel</h1>
{aviso}
<form method="post" action="/entrar">
<input type="hidden" name="siguiente" value="{escape(destino_seguro(siguiente))}">
<label>Contraseña<input name="clave" type="password" required autocomplete="current-password" autofocus></label>
<button type="submit">Entrar</button></form>
</div></main></body></html>"""


def proteger(app: FastAPI, css: str, acceso: Acceso | None = None) -> Acceso:
    acceso = acceso or Acceso(os.getenv("PANEL_CLAVE_HASH"), os.getenv("PANEL_PUBLICO") == "1")

    @app.middleware("http")
    async def exigir_sesion(request: Request, call_next):
        if acceso.sin_configurar:
            return HTMLResponse(
                "<h1>Panel cerrado</h1><p>Falta PANEL_CLAVE_HASH en el .env. "
                "Genera una con: uv run compania-panel-clave</p>",
                status_code=503,
            )
        if not acceso.activo or request.url.path in LIBRES:
            return await call_next(request)
        if acceso.sesion_valida(request.cookies.get(COOKIE)):
            return await call_next(request)
        if (
            request.method == "GET"
            and not request.url.path.startswith("/api")
            and not request.url.path.endswith((".svg", "/estado"))
        ):
            siguiente = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/entrar?siguiente={siguiente}", status_code=303)
        return JSONResponse({"error": "Inicia sesión de nuevo"}, status_code=401)

    @app.get("/entrar", response_class=HTMLResponse)
    def entrar_pagina(siguiente: str = "/control"):
        if not acceso.activo:
            return RedirectResponse("/control", status_code=303)
        return pagina_entrar(css, siguiente=siguiente)

    @app.post("/entrar")
    def entrar(request: Request, clave: str = Form(...), siguiente: str = Form("/control")):
        ip = ip_de(request, acceso.publico)
        if acceso.bloqueado(ip):
            return HTMLResponse(
                pagina_entrar(css, "Demasiados intentos. Espera 15 minutos.", siguiente), status_code=429
            )
        if not acceso.activo or not clave_correcta(clave, acceso.clave_hash):
            acceso.registrar_fallo(ip)
            return HTMLResponse(pagina_entrar(css, "Contraseña incorrecta.", siguiente), status_code=401)
        respuesta = RedirectResponse(destino_seguro(siguiente), status_code=303)
        vence = int(acceso.reloj()) + DURACION_S
        respuesta.set_cookie(
            COOKIE,
            acceso.firmar(vence),
            max_age=DURACION_S,
            httponly=True,
            samesite="lax",
            secure=acceso.publico,
            path="/",
        )
        return respuesta

    @app.post("/salir")
    def salir():
        respuesta = RedirectResponse("/entrar", status_code=303)
        respuesta.delete_cookie(COOKIE, path="/")
        return respuesta

    return acceso


def generar_clave() -> None:
    """Pide la contraseña dos veces e imprime la línea para el .env."""
    clave = getpass.getpass("Contraseña nueva para el panel (mínimo 12 caracteres): ")
    if len(clave) < 12:
        raise SystemExit("Muy corta: usa al menos 12 caracteres (una frase sirve).")
    if getpass.getpass("Repítela: ") != clave:
        raise SystemExit("No coinciden.")
    print("\nAgrega esta línea a agente/.env (reemplaza la anterior si había):\n")
    print(f"PANEL_CLAVE_HASH={hash_de_clave(clave)}")

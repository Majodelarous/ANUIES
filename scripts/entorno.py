"""Entornos de configuración y datos: prueba, prod u otros.

Cada entorno es un archivo ``agente/.env.<nombre>`` con sus propias llaves, números de WhatsApp,
base de datos, notas de voz y sesión de WhatsApp. ``agente/.env`` es un enlace al entorno activo:
el bot y el puente siempre leen ``agente/.env``.

Se usa desde el Makefile (``make entorno``, ``make usar ENTORNO=prod``...). Solo usa la
biblioteca estándar. Nunca imprime llaves.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AGENTE = RAIZ / "agente"
WHATSAPP = RAIZ / "whatsapp"
ACTIVO = AGENTE / ".env"
RESPALDOS = RAIZ / "respaldos"
MOTORES = {"gemini": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY", "nova": "AWS"}
# Lo que cambia de un entorno a otro al crearlo: datos separados y números por llenar
POR_ENTORNO = ("RUTA_DB", "CARPETA_AUDIOS", "WA_AUTH_DIR")
EN_BLANCO = ("WHATSAPP_ASISTENTE", "WHATSAPP_PERSONA", "WHATSAPP_GRUPO", "PERSONA_ID")
PUERTOS = {7863: "bot", 7864: "puente", 7861: "panel"}


def fallar(mensaje: str) -> None:
    print(f"Error: {mensaje}", file=sys.stderr)
    sys.exit(1)


def leer(ruta: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    for linea in ruta.read_text().splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip().strip("'\"")
    return valores


def poner_en(ruta: Path, clave: str, valor: str) -> None:
    """Cambia CLAVE=valor conservando comentarios y orden; si no existe, la agrega al final."""
    lineas = ruta.read_text().splitlines()
    for i, linea in enumerate(lineas):
        if linea.split("=", 1)[0].strip() == clave and not linea.lstrip().startswith("#"):
            lineas[i] = f"{clave}={valor}"
            break
    else:
        lineas.append(f"{clave}={valor}")
    ruta.write_text("\n".join(lineas) + "\n")


def nombre_activo() -> str | None:
    if ACTIVO.is_symlink():
        destino = ACTIVO.readlink().name
        return destino.removeprefix(".env.") if destino.startswith(".env.") else None
    return None


def archivo_activo() -> Path:
    if not ACTIVO.exists():
        fallar("no hay agente/.env. Crea un entorno con: make nuevo-entorno ENTORNO=prod")
    return ACTIVO.resolve()


def rutas_de_datos(valores: dict[str, str]) -> dict[str, Path]:
    db = AGENTE / (valores.get("RUTA_DB") or "compania.db")
    return {
        "base de datos": db,
        "notas de voz": AGENTE / (valores.get("CARPETA_AUDIOS") or "audios"),
        "sesión de WhatsApp": WHATSAPP / (valores.get("WA_AUTH_DIR") or "./auth"),
    }


def servicios_encendidos() -> list[str]:
    encendidos = []
    for puerto, nombre in PUERTOS.items():
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", puerto)) == 0:
                encendidos.append(nombre)
    return encendidos


def exigir_apagado() -> None:
    if encendidos := servicios_encendidos():
        fallar(f"detén primero los servicios ({', '.join(encendidos)}): Ctrl+C en make dev")


def mostrar(_: argparse.Namespace) -> None:
    valores = leer(archivo_activo())
    nombre = nombre_activo() or "(agente/.env es un archivo propio; usa make usar ENTORNO=... )"
    motor = (valores.get("MOTOR_VOZ") or "gemini").lower()
    llave = MOTORES.get(motor, "?")
    if llave == "AWS":
        tiene = bool(valores.get("AWS_PROFILE") or valores.get("AWS_ACCESS_KEY_ID"))
    else:
        tiene = bool(valores.get(llave))
    datos = rutas_de_datos(valores)
    print(f"Entorno activo:      {nombre}")
    print(f"Motor de voz:        {motor} ({'llave configurada' if tiene else 'FALTA LA LLAVE'})")
    print(f"Asistente:           {valores.get('NOMBRE_ASISTENTE') or 'Rous'}")
    print(f"WhatsApp asistente:  {valores.get('WHATSAPP_ASISTENTE') or '(vacío)'}")
    print(f"WhatsApp persona:    {valores.get('WHATSAPP_PERSONA') or '(vacío)'}")
    print(f"Grupo de la familia: {valores.get('WHATSAPP_GRUPO') or '(vacío)'}")
    print(f"PERSONA_ID:          {valores.get('PERSONA_ID') or '(la primera registrada)'}")
    for etiqueta, ruta in datos.items():
        estado = "existe" if ruta.exists() else "aún no existe"
        print(f"{etiqueta[0].upper() + etiqueta[1:] + ':':<21}{ruta.relative_to(RAIZ)} ({estado})")
    otros = sorted(p.name.removeprefix(".env.") for p in AGENTE.glob(".env.*") if p.name != ".env.example")
    print(f"Entornos disponibles: {', '.join(otros) or 'ninguno'}")


def crear(args: argparse.Namespace) -> None:
    nombre = args.entorno
    if not nombre.isidentifier():
        fallar("usa un nombre simple, por ejemplo prod o prueba")
    destino = AGENTE / f".env.{nombre}"
    if destino.exists():
        fallar(f"ya existe agente/.env.{nombre}; edítalo o usa make usar ENTORNO={nombre}")
    origen = ACTIVO if ACTIVO.exists() else AGENTE / ".env.example"
    shutil.copyfile(origen.resolve(), destino)
    destino.chmod(0o600)
    poner_en(destino, "RUTA_DB", f"datos/{nombre}/compania.db")
    poner_en(destino, "CARPETA_AUDIOS", f"datos/{nombre}/audios")
    poner_en(destino, "WA_AUTH_DIR", f"./auth-{nombre}")
    for clave in EN_BLANCO:
        poner_en(destino, clave, "")
    (AGENTE / "datos" / nombre).mkdir(parents=True, exist_ok=True)
    print(f"Creado agente/.env.{nombre} a partir de {origen.name} (con las mismas llaves de IA).")
    print("Datos separados: base, notas de voz y sesión de WhatsApp propias. Números y grupo en blanco.")
    print(f"Siguiente: make usar ENTORNO={nombre}")


def usar(args: argparse.Namespace) -> None:
    nombre = args.entorno
    destino = AGENTE / f".env.{nombre}"
    if not destino.exists():
        fallar(f"no existe agente/.env.{nombre}. Créalo con: make nuevo-entorno ENTORNO={nombre}")
    exigir_apagado()
    if ACTIVO.exists() and not ACTIVO.is_symlink():
        # Primera vez: el .env que ya existía es el entorno de prueba
        prueba = AGENTE / ".env.prueba"
        if prueba.exists():
            fallar("agente/.env es un archivo y ya existe .env.prueba; renombra uno de los dos a mano")
        ACTIVO.rename(prueba)
        print("Tu agente/.env de siempre ahora es el entorno 'prueba' (agente/.env.prueba).")
    if ACTIVO.is_symlink():
        ACTIVO.unlink()
    ACTIVO.symlink_to(destino.name)
    print(f"Entorno activo: {nombre}\n")
    mostrar(args)


def poner(args: argparse.Namespace) -> None:
    clave = args.clave.strip().upper()
    if not clave.replace("_", "").isalnum():
        fallar("la clave debe ser como MOTOR_VOZ o WHATSAPP_PERSONA")
    valor = args.valor.strip()
    if clave == "MOTOR_VOZ":
        valor = valor.lower()
        if valor not in MOTORES:
            fallar("MOTOR_VOZ debe ser gemini, nova u openai")
    if clave in ("WHATSAPP_PERSONA", "WHATSAPP_ASISTENTE"):
        valor = "".join(c for c in valor if c.isdigit())
        if valor and not 10 <= len(valor) <= 15:
            fallar("el número va con código de país, solo dígitos, por ejemplo 522221234567")
    ruta = archivo_activo()
    poner_en(ruta, clave, valor)
    secreta = any(p in clave for p in ("KEY", "TOKEN", "SECRET", "SID"))
    print(f"{clave}={'(guardada)' if secreta else valor} en agente/{ruta.name}")
    if clave == "MOTOR_VOZ":
        mostrar(args)


def respaldo(args: argparse.Namespace, mover: tuple[str, ...] = ()) -> Path:
    """Copia los datos del entorno activo a respaldos/; mueve (en vez de copiar) los indicados."""
    valores = leer(archivo_activo())
    carpeta = RESPALDOS / f"{nombre_activo() or 'sin-nombre'}-{datetime.now():%Y%m%d-%H%M%S}"
    carpeta.mkdir(parents=True)
    for etiqueta, ruta in rutas_de_datos(valores).items():
        piezas = [ruta] if etiqueta != "base de datos" else sorted(ruta.parent.glob(ruta.name + "*"))
        for pieza in piezas:
            if not pieza.exists():
                continue
            if etiqueta in mover:
                shutil.move(pieza, carpeta / pieza.name)
            elif pieza.is_dir():
                shutil.copytree(pieza, carpeta / pieza.name)
            else:
                shutil.copy2(pieza, carpeta / pieza.name)
    print(f"Respaldo en {carpeta.relative_to(RAIZ)}")
    return carpeta


def limpiar(args: argparse.Namespace) -> None:
    if not args.si:
        fallar("esto vacía la base y las notas de voz del entorno activo. Confirma con CONFIRMAR=si")
    exigir_apagado()
    respaldo(args, mover=("base de datos", "notas de voz"))
    print("Base y notas de voz vacías (se movieron al respaldo). La sesión de WhatsApp sigue igual.")
    print("Siguiente: make persona NOMBRE=... TRATO=... TELEFONO=...")


def desvincular(args: argparse.Namespace) -> None:
    if not args.si:
        fallar("esto quita la sesión de WhatsApp del entorno activo. Confirma con CONFIRMAR=si")
    exigir_apagado()
    respaldo(args, mover=("sesión de WhatsApp",))
    print("Sesión de WhatsApp quitada. Al levantar el puente aparecerá un QR nuevo.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("mostrar").set_defaults(fn=mostrar)
    for nombre, fn in (("crear", crear), ("usar", usar)):
        p = sub.add_parser(nombre)
        p.add_argument("entorno")
        p.set_defaults(fn=fn)
    p = sub.add_parser("poner")
    p.add_argument("clave")
    p.add_argument("valor", nargs="?", default="")
    p.set_defaults(fn=poner)
    sub.add_parser("respaldo").set_defaults(fn=respaldo)
    for nombre, fn in (("limpiar", limpiar), ("desvincular", desvincular)):
        p = sub.add_parser(nombre)
        p.add_argument("--si", action="store_true")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

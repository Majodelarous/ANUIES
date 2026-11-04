"""Consulta y ajusta las personas registradas en la base del entorno activo.

Uso::

    uv run compania-datos personas
    uv run compania-datos telefono 1 522221234567
"""

from __future__ import annotations

import argparse
import os
import re

from dotenv import load_dotenv

from compania.infraestructura.repositorio import Repositorio


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Personas registradas")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("personas", help="Lista las personas registradas")
    telefono = sub.add_parser("telefono", help="Cambia el WhatsApp de una persona")
    telefono.add_argument("persona_id", type=int)
    telefono.add_argument("numero")
    args = parser.parse_args()

    ruta = os.getenv("RUTA_DB", "compania.db")
    repo = Repositorio(ruta)
    if args.comando == "personas":
        personas = repo.personas()
        print(f"Base: {ruta}")
        if not personas:
            print("No hay personas. Registra una con: make persona NOMBRE=... TRATO=... TELEFONO=...")
        for p in personas:
            permiso = f"sí, desde {p.consentimiento:%Y-%m-%d}" if p.consentimiento else "aún no"
            print(
                f'  id {p.id}: {p.nombre} (le dice "{p.trato}"), WhatsApp {p.telefono or "-"}, permiso: {permiso}'
            )
        return

    numero = re.sub(r"\D", "", args.numero)
    if not re.fullmatch(r"\d{10,15}", numero):
        raise SystemExit("Usa el número con código de país, solo dígitos, por ejemplo 522221234567")
    if not repo.actualizar_telefono(args.persona_id, numero):
        raise SystemExit(f"No existe la persona con id {args.persona_id}")
    print(f"Persona {args.persona_id}: WhatsApp {numero}")


if __name__ == "__main__":
    main()

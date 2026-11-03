"""Registra una persona y, opcionalmente, datos de ejemplo para el demo."""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime

from dotenv import load_dotenv

from compania.dominio.modelos import MensajeFamiliar, Persona, Recordatorio
from compania.infraestructura.repositorio import Repositorio


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Registrar una persona en la base local")
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--trato", required=True, help='Cómo le gusta que le digan, p. ej. "doña Carmen"')
    parser.add_argument("--contacto", help="Teléfono o nombre del contacto de emergencia")
    parser.add_argument("--telefono", help="WhatsApp o teléfono con código de país, p. ej. 522221234567")
    parser.add_argument(
        "--consentimiento",
        action="store_true",
        help="La persona ya firmó el consentimiento por escrito; Rous no lo pedirá en la primera llamada",
    )
    parser.add_argument("--demo", action="store_true", help="Agregar un recordatorio y un mensaje de ejemplo")
    args = parser.parse_args()

    repo = Repositorio(os.getenv("RUTA_DB", "compania.db"))
    telefono = re.sub(r"\D", "", args.telefono) if args.telefono else None
    persona = repo.guardar_persona(
        Persona(
            args.nombre,
            args.trato,
            args.contacto,
            telefono=telefono,
            consentimiento=datetime.now() if args.consentimiento else None,
        )
    )
    assert persona.id is not None
    if args.demo:
        repo.guardar_recordatorio(
            Recordatorio(persona.id, "Tomar la pastilla de la presión", "14:00", "familia")
        )
        repo.guardar_mensaje(
            MensajeFamiliar(persona.id, "su nieta", "Te quiero mucho, el sábado voy a verte.")
        )
    print(f"Persona registrada con id {persona.id}. Usa PERSONA_ID={persona.id} si hay varias.")


if __name__ == "__main__":
    main()

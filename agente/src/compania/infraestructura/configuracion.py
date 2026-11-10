"""Configuración que se cambia en vivo desde el panel.

Cada valor sale de la tabla ``ajustes`` (lo que guardó el panel) y, si no hay, del .env.
Las llaves de los motores no van aquí: siguen en el .env.
"""

from __future__ import annotations

import os
import re

from compania.infraestructura.repositorio import Repositorio

# clave en la base: (variable del .env, valor por omisión, etiqueta para el panel)
AJUSTES = {
    "whatsapp_grupo": ("WHATSAPP_GRUPO", "", "Nombre del grupo de la familia"),
    "whatsapp_prefijo": ("WHATSAPP_PREFIJO", "abue", "Palabra con la que la familia le habla a la abuelita"),
    "nombre_asistente": ("NOMBRE_ASISTENTE", "Rous", "Nombre de la asistente"),
    "voz_gemini": ("GOOGLE_VOICE_ID", "Aoede", "Voz con Gemini"),
    "voz_openai": ("OPENAI_VOICE", "marin", "Voz con OpenAI"),
    "voz_nova": ("NOVA_VOICE_ID", "lupe", "Voz con Nova"),
}

# Voces que acepta cada motor (las de Nova son las de español). Una voz fuera de la lista haría
# fallar la llamada, por eso el panel solo deja elegir de aquí.
VOCES = {
    "voz_gemini": ("Aoede", "Kore", "Leda", "Zephyr", "Puck", "Charon", "Fenrir", "Orus"),
    "voz_openai": ("marin", "cedar", "coral", "shimmer", "sage", "ballad", "alloy", "ash", "echo", "verse"),
    "voz_nova": ("lupe", "carlos"),
}


def voz(repo: Repositorio | None, motor: str) -> str:
    return valor(repo, f"voz_{motor}")


def valor(repo: Repositorio | None, clave: str) -> str:
    variable, omision, _ = AJUSTES[clave]
    guardado = repo.ajuste(clave) if repo else None
    if guardado and guardado.strip():
        return guardado.strip()
    return (os.getenv(variable) or omision).strip()


def origen(repo: Repositorio, clave: str) -> str:
    """De dónde sale el valor: panel, .env o valor por omisión."""
    guardado = repo.ajuste(clave)
    if guardado and guardado.strip():
        return "panel"
    return ".env" if os.getenv(AJUSTES[clave][0]) else "omisión"


def nombre_asistente(repo: Repositorio | None = None) -> str:
    return valor(repo, "nombre_asistente") or "Rous"


def con_lada(texto: str | None) -> str:
    """Solo dígitos; un número de 10 dígitos es de México y se le agrega el 52."""
    digitos = re.sub(r"\D", "", texto or "")
    return f"52{digitos}" if len(digitos) == 10 else digitos


def numero_de_la_persona(repo: Repositorio | None = None) -> str:
    """WhatsApp de la persona activa; si no tiene, WHATSAPP_PERSONA del .env."""
    persona = repo.persona_activa() if repo else None
    return con_lada((persona.telefono if persona else None) or os.getenv("WHATSAPP_PERSONA"))


def para_el_puente(repo: Repositorio) -> dict:
    """Lo que el puente de WhatsApp lee al arrancar."""
    return {
        "grupo": valor(repo, "whatsapp_grupo"),
        "prefijo": valor(repo, "whatsapp_prefijo"),
        "persona": numero_de_la_persona(repo),
        "nombre": nombre_asistente(repo),
    }

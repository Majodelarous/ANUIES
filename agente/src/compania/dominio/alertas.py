"""Política de alertas."""

from __future__ import annotations

from compania.dominio.modelos import NivelAlerta

LINEA_DE_LA_VIDA = "800 911 2000"

MENSAJE_CRISIS = (
    "Lo que siente es importante y no está solo. "
    f"Puede llamar ahora a la Línea de la Vida, al {LINEA_DE_LA_VIDA}, a cualquier hora. "
    "También voy a avisarle a su familia para que se comunique con usted."
)


def instruccion_para_nivel(nivel: NivelAlerta) -> str:
    """Qué debe decir la asistente después de generar una alerta."""
    if nivel == NivelAlerta.CRISIS:
        return MENSAJE_CRISIS
    if nivel == NivelAlerta.ATENCION:
        return "Dígale a la persona que su familia se va a comunicar con ella pronto."
    return "Continúe la plática con normalidad."

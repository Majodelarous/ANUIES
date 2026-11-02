"""Herramientas que el modelo de voz puede llamar durante una llamada."""

from __future__ import annotations

import re
from typing import Any, Protocol

from loguru import logger
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema

from compania.dominio import bienestar
from compania.dominio.alertas import instruccion_para_nivel
from compania.dominio.juegos import JUEGOS_POR_ID, TipoJuego, obtener_juego
from compania.dominio.modelos import (
    Alerta,
    NivelAlerta,
    Recordatorio,
    Recuerdo,
    RespuestaBienestar,
)
from compania.infraestructura.repositorio import Repositorio

HORA = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


class ParametrosLlamada(Protocol):
    """Lo que las herramientas usan de ``FunctionCallParams`` de Pipecat."""

    arguments: Any

    async def result_callback(self, result: Any, **kwargs: Any) -> None: ...


class Sesion:
    """Estado de una llamada y manejadores de herramientas."""

    def __init__(self, repo: Repositorio, persona_id: int) -> None:
        self.repo = repo
        self.persona_id = persona_id
        self.juegos_usados: set[str] = set()

    async def guardar_recuerdo(self, params: ParametrosLlamada) -> None:
        args = params.arguments
        recuerdo = self.repo.guardar_recuerdo(
            Recuerdo(
                self.persona_id,
                tema=str(args["tema"]),
                contenido=str(args["contenido"]),
                compartir_con_familia=bool(args.get("compartir_con_familia", False)),
            )
        )
        await params.result_callback({"guardado": True, "id": recuerdo.id})

    async def buscar_recuerdos(self, params: ParametrosLlamada) -> None:
        tema = params.arguments.get("tema") or None
        recuerdos = self.repo.buscar_recuerdos(self.persona_id, tema, limite=5)
        await params.result_callback(
            {"recuerdos": [{"tema": r.tema, "contenido": r.contenido} for r in recuerdos]}
        )

    async def obtener_juego(self, params: ParametrosLlamada) -> None:
        tipo = params.arguments.get("tipo") or None
        try:
            juego = obtener_juego(tipo, self.juegos_usados)
        except ValueError:
            juego = obtener_juego(None, self.juegos_usados)
        if juego is None:
            await params.result_callback({"disponible": False})
            return
        self.juegos_usados.add(juego.id)
        await params.result_callback(
            {
                "disponible": True,
                "juego_id": juego.id,
                "tipo": juego.tipo.value,
                "instruccion": juego.instruccion,
                "contenido": juego.contenido,
                "respuesta": juego.respuesta,
                "pista": juego.pista,
            }
        )

    async def registrar_resultado_juego(self, params: ParametrosLlamada) -> None:
        juego_id = str(params.arguments["juego_id"])
        if juego_id not in JUEGOS_POR_ID:
            await params.result_callback({"error": "juego desconocido"})
            return
        self.repo.guardar_resultado_juego(self.persona_id, juego_id, bool(params.arguments["acerto"]))
        await params.result_callback({"registrado": True})

    async def registrar_respuesta_bienestar(self, params: ParametrosLlamada) -> None:
        pregunta_id = str(params.arguments["pregunta_id"])
        if pregunta_id not in bienestar.PREGUNTAS:
            await params.result_callback({"error": "pregunta desconocida"})
            return
        try:
            respuesta = bienestar.normalizar_respuesta(str(params.arguments["respuesta"]))
        except ValueError:
            await params.result_callback({"error": "responde con si o no"})
            return
        self.repo.guardar_respuesta(RespuestaBienestar(self.persona_id, pregunta_id, respuesta))
        await params.result_callback({"registrado": True})

    async def crear_recordatorio(self, params: ParametrosLlamada) -> None:
        hora = str(params.arguments["hora"]).strip()
        if not HORA.match(hora):
            await params.result_callback({"error": "la hora debe tener formato HH:MM de 24 horas"})
            return
        recordatorio = self.repo.guardar_recordatorio(
            Recordatorio(self.persona_id, str(params.arguments["texto"]), hora.zfill(5))
        )
        await params.result_callback({"creado": True, "id": recordatorio.id})

    async def marcar_mensaje_entregado(self, params: ParametrosLlamada) -> None:
        ok = self.repo.marcar_entregado(int(params.arguments["mensaje_id"]), self.persona_id)
        await params.result_callback({"marcado": ok})

    async def generar_alerta(self, params: ParametrosLlamada) -> None:
        nivel = NivelAlerta(str(params.arguments["nivel"]))
        alerta = self.repo.guardar_alerta(Alerta(self.persona_id, nivel, str(params.arguments["motivo"])))
        logger.warning(f"Alerta {nivel.value} para persona {self.persona_id}: {alerta.motivo}")
        await params.result_callback({"registrada": True, "que_decir": instruccion_para_nivel(nivel)})

    def esquemas(self) -> list[FunctionSchema]:
        """Esquemas con sus manejadores, listos para el servicio de voz."""
        return [
            FunctionSchema(
                name="guardar_recuerdo",
                description="Guarda algo significativo que la persona contó de su vida, con su permiso.",
                properties={
                    "tema": {
                        "type": "string",
                        "description": "Tema breve, por ejemplo 'infancia en Atlixco'",
                    },
                    "contenido": {"type": "string", "description": "Lo que contó, en una o dos frases"},
                    "compartir_con_familia": {
                        "type": "boolean",
                        "description": "True solo si la persona aceptó que su familia lo vea",
                    },
                },
                required=["tema", "contenido"],
                handler=self.guardar_recuerdo,
            ),
            FunctionSchema(
                name="buscar_recuerdos",
                description="Busca recuerdos que la persona ya contó, por tema o los más recientes.",
                properties={"tema": {"type": "string", "description": "Palabra clave opcional"}},
                required=[],
                handler=self.buscar_recuerdos,
            ),
            FunctionSchema(
                name="obtener_juego",
                description="Obtiene un juego de memoria por voz que no se haya usado en esta llamada.",
                properties={
                    "tipo": {
                        "type": "string",
                        "enum": [t.value for t in TipoJuego],
                        "description": "Tipo de juego; opcional",
                    }
                },
                required=[],
                handler=self.obtener_juego,
            ),
            FunctionSchema(
                name="registrar_resultado_juego",
                description="Registra si la persona acertó un juego de memoria.",
                properties={
                    "juego_id": {"type": "string"},
                    "acerto": {"type": "boolean"},
                },
                required=["juego_id", "acerto"],
                handler=self.registrar_resultado_juego,
            ),
            FunctionSchema(
                name="registrar_respuesta_bienestar",
                description="Registra la respuesta a una pregunta de bienestar de las indicadas para hoy.",
                properties={
                    "pregunta_id": {"type": "string", "description": "Id de la pregunta, por ejemplo gds05"},
                    "respuesta": {"type": "string", "enum": ["si", "no"]},
                },
                required=["pregunta_id", "respuesta"],
                handler=self.registrar_respuesta_bienestar,
            ),
            FunctionSchema(
                name="crear_recordatorio",
                description="Crea un recordatorio que la persona pidió.",
                properties={
                    "texto": {"type": "string", "description": "Qué recordar"},
                    "hora": {"type": "string", "description": "Hora en formato HH:MM de 24 horas"},
                },
                required=["texto", "hora"],
                handler=self.crear_recordatorio,
            ),
            FunctionSchema(
                name="marcar_mensaje_entregado",
                description="Marca como entregado un mensaje de la familia después de decirlo.",
                properties={"mensaje_id": {"type": "integer"}},
                required=["mensaje_id"],
                handler=self.marcar_mensaje_entregado,
            ),
            FunctionSchema(
                name="generar_alerta",
                description="Avisa a la familia. Usa 'crisis' si la persona expresa ideas de hacerse daño.",
                properties={
                    "nivel": {"type": "string", "enum": [n.value for n in NivelAlerta]},
                    "motivo": {"type": "string", "description": "Qué pasó, en una frase"},
                },
                required=["nivel", "motivo"],
                handler=self.generar_alerta,
            ),
        ]

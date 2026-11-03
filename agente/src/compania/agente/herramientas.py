"""Herramientas que el modelo de voz puede llamar durante una llamada."""

from __future__ import annotations

import asyncio
import re
import wave
from pathlib import Path
from typing import Any, Protocol

from loguru import logger
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import OutputAudioRawFrame

from compania.dominio import bienestar
from compania.dominio.alertas import LINEA_DE_LA_VIDA, instruccion_para_nivel
from compania.dominio.juegos import JUEGOS_POR_ID, TipoJuego, obtener_juego
from compania.dominio.modelos import (
    Alerta,
    NivelAlerta,
    Recordatorio,
    Recuerdo,
    RespuestaBienestar,
)
from compania.infraestructura.puente_whatsapp import AvisoFamilia, SinAviso
from compania.infraestructura.repositorio import Repositorio

HORA = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
BLOQUE_SEGUNDOS = 0.2
NOMBRE_NIVEL = {
    NivelAlerta.INFORMATIVA: "Aviso",
    NivelAlerta.ATENCION: "Poner atención",
    NivelAlerta.CRISIS: "URGENTE",
}


def cargar_audio(ruta: str | Path) -> tuple[bytes, int]:
    """Lee un WAV PCM de 16 bits y un canal. Devuelve los bytes y la frecuencia."""
    with wave.open(str(ruta), "rb") as archivo:
        if archivo.getnchannels() != 1 or archivo.getsampwidth() != 2:
            raise ValueError("El audio debe ser WAV mono de 16 bits")
        return archivo.readframes(archivo.getnframes()), archivo.getframerate()


class ParametrosLlamada(Protocol):
    """Lo que las herramientas usan de ``FunctionCallParams`` de Pipecat."""

    arguments: Any
    llm: Any

    async def result_callback(self, result: Any, **kwargs: Any) -> None: ...


class Sesion:
    """Estado de una llamada y manejadores de herramientas."""

    def __init__(
        self,
        repo: Repositorio,
        persona_id: int,
        *,
        aviso: AvisoFamilia | None = None,
        trato: str = "la persona",
    ) -> None:
        self.repo = repo
        self.persona_id = persona_id
        self.aviso = aviso or SinAviso()
        self.trato = trato
        self.juegos_usados: set[str] = set()
        # Lo que pasó en la llamada, para el resumen a la familia
        self.recuerdos_compartidos: list[str] = []
        self.aciertos = 0
        self.juegos_jugados = 0
        self.mensajes_entregados: list[str] = []
        self.recordatorios_creados: list[str] = []
        self.alertas: list[str] = []

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
        if recuerdo.compartir_con_familia:
            self.recuerdos_compartidos.append(f"{recuerdo.tema}: {recuerdo.contenido}")
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
        acerto = bool(params.arguments["acerto"])
        self.repo.guardar_resultado_juego(self.persona_id, juego_id, acerto)
        self.juegos_jugados += 1
        self.aciertos += int(acerto)
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
        self.recordatorios_creados.append(f"{recordatorio.hora} {recordatorio.texto}")
        await params.result_callback({"creado": True, "id": recordatorio.id})

    def _entregar(self, mensaje_id: int) -> bool:
        mensaje = self.repo.obtener_mensaje(mensaje_id, self.persona_id)
        ok = self.repo.marcar_entregado(mensaje_id, self.persona_id)
        if ok and mensaje:
            self.mensajes_entregados.append(mensaje.de)
        return ok

    async def marcar_mensaje_entregado(self, params: ParametrosLlamada) -> None:
        await params.result_callback({"marcado": self._entregar(int(params.arguments["mensaje_id"]))})

    async def reproducir_mensaje_voz(self, params: ParametrosLlamada) -> None:
        """Reproduce en la llamada la nota de voz real que mandó la familia.

        Mientras suena, el micrófono de la persona está silenciado (estrategia de Pipecat
        para llamadas a herramientas), así que un comentario no corta el audio.
        """
        mensaje_id = int(params.arguments["mensaje_id"])
        mensaje = self.repo.obtener_mensaje(mensaje_id, self.persona_id)
        if mensaje is None or not mensaje.audio:
            await params.result_callback({"error": "ese mensaje no tiene nota de voz"})
            return
        try:
            audio, frecuencia = cargar_audio(mensaje.audio)
        except (OSError, ValueError, wave.Error) as error:
            logger.error(f"No se pudo leer la nota de voz {mensaje.audio}: {error}")
            await params.result_callback({"error": "no se pudo reproducir; dile el mensaje con tus palabras"})
            return

        tamano = int(frecuencia * BLOQUE_SEGUNDOS) * 2
        for inicio in range(0, len(audio), tamano):
            await params.llm.push_frame(OutputAudioRawFrame(audio[inicio : inicio + tamano], frecuencia, 1))
        duracion = len(audio) / 2 / frecuencia
        logger.info(f"Reproduciendo nota de voz de {mensaje.de} ({duracion:.1f} s)")
        await asyncio.sleep(duracion + 0.5)
        self._entregar(mensaje_id)
        await params.result_callback(
            {
                "reproducido": True,
                "que_hacer": f"Pregúntale qué le pareció y si quiere mandarle una respuesta a {mensaje.de}.",
            }
        )

    async def enviar_mensaje_a_familia(self, params: ParametrosLlamada) -> None:
        texto = str(params.arguments["texto"]).strip()
        para = str(params.arguments.get("para") or "la familia").strip()
        enviado = await self.aviso.enviar(f"Mensaje de {self.trato} para {para}: {texto}")
        await params.result_callback(
            {"enviado": enviado}
            if enviado
            else {"enviado": False, "que_decir": "Dile que se lo pasarás después."}
        )

    async def generar_alerta(self, params: ParametrosLlamada) -> None:
        nivel = NivelAlerta(str(params.arguments["nivel"]))
        alerta = self.repo.guardar_alerta(Alerta(self.persona_id, nivel, str(params.arguments["motivo"])))
        logger.warning(f"Alerta {nivel.value} para persona {self.persona_id}: {alerta.motivo}")
        self.alertas.append(f"{NOMBRE_NIVEL[nivel]}: {alerta.motivo}")
        if nivel != NivelAlerta.INFORMATIVA:
            aviso = f"{NOMBRE_NIVEL[nivel]} sobre {self.trato}: {alerta.motivo}"
            if nivel == NivelAlerta.CRISIS:
                aviso += f". Llámenle ahora. Línea de la Vida: {LINEA_DE_LA_VIDA}, 24 horas."
            await self.aviso.enviar(aviso)
        await params.result_callback({"registrada": True, "que_decir": instruccion_para_nivel(nivel)})

    def resumen(self, minutos: int) -> str:
        """Texto breve para el grupo de la familia al terminar la llamada."""
        lineas = [f"Llamada con {self.trato}: {minutos} min."]
        if self.recuerdos_compartidos:
            lineas.append("Quiso compartirles: " + "; ".join(self.recuerdos_compartidos) + ".")
        if self.juegos_jugados:
            lineas.append(f"Juegos de memoria: {self.aciertos} de {self.juegos_jugados} acertados.")
        if self.mensajes_entregados:
            lineas.append(
                "Recibió los mensajes de: " + ", ".join(dict.fromkeys(self.mensajes_entregados)) + "."
            )
        if self.recordatorios_creados:
            lineas.append("Pidió recordatorios: " + "; ".join(self.recordatorios_creados) + ".")
        if self.alertas:
            lineas.append("Alertas: " + "; ".join(self.alertas) + ".")
        else:
            lineas.append("Sin alertas.")
        return "\n".join(lineas)

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
                name="reproducir_mensaje_voz",
                description=(
                    "Reproduce la nota de voz real que mandó la familia. Úsala solo después de que la "
                    "persona dijo que quiere escucharla. Ya la marca como entregada."
                ),
                properties={"mensaje_id": {"type": "integer"}},
                required=["mensaje_id"],
                handler=self.reproducir_mensaje_voz,
            ),
            FunctionSchema(
                name="enviar_mensaje_a_familia",
                description=(
                    "Manda al grupo de WhatsApp de la familia un mensaje que la persona dictó. "
                    "Confirma el texto con ella antes de enviarlo."
                ),
                properties={
                    "texto": {"type": "string", "description": "El mensaje con las palabras de la persona"},
                    "para": {"type": "string", "description": "A quién va dirigido, por ejemplo 'Majo'"},
                },
                required=["texto"],
                handler=self.enviar_mensaje_a_familia,
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

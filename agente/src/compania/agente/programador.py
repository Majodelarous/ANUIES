"""Programador: lanza las llamadas diarias y los recordatorios a su hora.

Uso::

    uv run compania-programador        # junto al bot (compania-whatsapp) y al puente (npm start)

Si nadie contesta, vuelve a marcar una vez a los 10 minutos. Si tampoco contestan, avisa al
grupo de la familia y deja una alerta informativa en el panel.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from dotenv import load_dotenv
from loguru import logger

from compania.dominio.modelos import Alerta, NivelAlerta, Persona
from compania.dominio.programacion import Tarea, tareas_pendientes
from compania.infraestructura.puente_whatsapp import AvisoFamilia, PuenteLlamadas, aviso_desde_entorno
from compania.infraestructura.repositorio import Repositorio

CADA_S = 20
REINTENTO_S = 10 * 60
OCUPADO_S = 2 * 60
SONDEO_S = 5
ESPERA_MAX_S = 6 * 60


class Llamadas(Protocol):
    async def llamar(self, numero: str, motivo: str) -> tuple[int, dict]: ...

    async def ultima_llamada(self) -> dict: ...


def numero_de(persona: Persona) -> str | None:
    numero = persona.telefono or os.getenv("WHATSAPP_PERSONA") or ""
    numero = re.sub(r"\D", "", numero)
    return numero or None


def texto_sin_respuesta(tarea: Tarea, trato: str, nombre: str) -> str:
    if tarea.tipo == "recordatorio":
        que = f"para recordarle: {tarea.texto.rstrip('.')}"
    else:
        que = "para platicar"
    return (
        f"Hola, familia, soy {nombre}. Hoy a las {tarea.hora} le marqué dos veces a {trato} {que}, "
        "y no contestó. ¿Alguien puede llamarle o pasar a verle?"
    )


class Programador:
    def __init__(
        self,
        repo: Repositorio,
        llamadas: Llamadas,
        aviso: AvisoFamilia,
        *,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
        reloj: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.repo = repo
        self.llamadas = llamadas
        self.aviso = aviso
        self.dormir = dormir
        self.reloj = reloj
        self.en_curso: set[asyncio.Task] = set()

    async def revisar(self) -> list[Tarea]:
        """Lanza las tareas que tocan ahora. Devuelve las que lanzó."""
        ahora = self.reloj()
        tareas = tareas_pendientes(
            ahora,
            self.repo.horarios(),
            self.repo.todos_los_recordatorios_activos(),
            self.repo.ejecutadas_desde(ahora.strftime("%Y-%m-%d")),
            self.repo.compromisos_por_avisar(),
        )
        for tarea in tareas:
            self.repo.marcar_ejecutada(tarea.clave)
            if tarea.tipo == "recordatorio" and tarea.recordatorio_id is not None:
                recordatorio = self.repo.obtener_recordatorio(tarea.recordatorio_id)
                if recordatorio and recordatorio.una_vez:
                    self.repo.desactivar_recordatorio(recordatorio.id)
            tarea_async = asyncio.create_task(self.atender(tarea))
            self.en_curso.add(tarea_async)
            tarea_async.add_done_callback(self.en_curso.discard)
        return tareas

    async def atender(self, tarea: Tarea) -> str:
        """Llama, espera el resultado y reintenta o avisa. Devuelve: contesto, sin_respuesta, omitida o error."""
        persona = self.repo.obtener_persona(tarea.persona_id)
        if tarea.tipo == "compromiso":
            return await self.recordar_compromiso(tarea, persona.trato if persona else "su familiar")
        numero = numero_de(persona) if persona else None
        if persona is None or numero is None:
            logger.warning(f"{tarea.clave}: la persona no tiene número; se omite")
            return "omitida"

        for intento in (1, 2):
            resultado = await self._llamar_y_esperar(numero, tarea)
            if resultado is None:
                # No se pudo ni marcar (puente apagado o error): no es culpa de la persona
                logger.error(f"{tarea.clave}: no se pudo lanzar la llamada; no se avisa a la familia")
                return "error"
            if resultado:
                logger.info(f"{tarea.clave}: contestó (intento {intento})")
                return "contesto"
            if intento == 1:
                logger.info(f"{tarea.clave}: no contestó; se vuelve a marcar en {REINTENTO_S // 60} min")
                await self.dormir(REINTENTO_S)

        nombre = os.getenv("NOMBRE_ASISTENTE") or "Rous"
        self.repo.guardar_alerta(
            Alerta(persona.id, NivelAlerta.INFORMATIVA, f"No contestó la llamada de las {tarea.hora}")
        )
        await self.aviso.enviar(texto_sin_respuesta(tarea, persona.trato, nombre))
        logger.warning(f"{tarea.clave}: no contestó en dos intentos; se avisó a la familia")
        return "sin_respuesta"

    async def recordar_compromiso(self, tarea: Tarea, trato: str) -> str:
        """A la hora prometida, le recuerda al familiar por el grupo que quedó de llamar."""
        if tarea.compromiso_id is not None:
            self.repo.marcar_compromiso_avisado(tarea.compromiso_id)
        enviado = await self.aviso.enviar(
            f"{tarea.texto}, son las {tarea.hora}: quedaste de marcarle a {trato}. Le va a dar mucho gusto escucharte."
        )
        return "avisado" if enviado else "error"

    async def _llamar_y_esperar(self, numero: str, tarea: Tarea) -> bool | None:
        """True si contestó, False si no contestó, None si no se pudo lanzar la llamada."""
        # Si el puente está ocupado (otra llamada), espera y reintenta unas veces
        for _ in range(3):
            lanzado = self.reloj().timestamp() * 1000
            codigo, datos = await self.llamadas.llamar(numero, tarea.motivo)
            if codigo == 200:
                break
            if codigo == 409:
                await self.dormir(OCUPADO_S)
                continue
            logger.error(f"{tarea.clave}: el puente rechazó la llamada: {datos}")
            return None
        else:
            return None

        esperado = 0
        while esperado < ESPERA_MAX_S:
            await self.dormir(SONDEO_S)
            esperado += SONDEO_S
            ultima = await self.llamadas.ultima_llamada()
            if ultima.get("inicio", 0) >= lanzado - 5_000 and ultima.get("terminada"):
                return bool(ultima.get("contesto"))
        return False


async def correr() -> None:
    load_dotenv(override=True)
    repo = Repositorio(os.getenv("RUTA_DB", "compania.db"))
    programador = Programador(
        repo, PuenteLlamadas(int(os.getenv("WHATSAPP_PUENTE_PUERTO", "7864"))), aviso_desde_entorno()
    )
    horarios = ", ".join(h.hora for h in repo.horarios()) or "ninguno"
    logger.info(f"Programador listo. Horarios de llamada: {horarios}. Revisa cada {CADA_S} s.")
    while True:
        try:
            for tarea in await programador.revisar():
                logger.info(f"Lanzando {tarea.tipo} de las {tarea.hora}")
        except Exception:
            logger.exception("Error al revisar las tareas")
        await asyncio.sleep(CADA_S)


def main() -> None:
    try:
        asyncio.run(correr())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

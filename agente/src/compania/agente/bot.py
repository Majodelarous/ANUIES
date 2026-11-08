"""Bot de voz con Pipecat.

Uso::

    uv run compania-bot                 # navegador: http://localhost:7860/client
    uv run compania-bot -t twilio -x <dominio-publico>
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesAppendFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.turns.user_mute import FunctionCallUserMuteStrategy
from pipecat.workers.runner import WorkerRunner

from compania.agente.grabadora import Grabadora
from compania.agente.herramientas import Sesion
from compania.agente.instrucciones import construir_instrucciones
from compania.dominio import bienestar
from compania.infraestructura.puente_whatsapp import aviso_desde_entorno
from compania.infraestructura.repositorio import Repositorio

load_dotenv(override=True)

LLAMADA_MINIMA_S = 20  # llamadas más cortas y sin actividad (se cayó al contestar) no se reportan
SALUDO = "Inicia la llamada saludando a la persona como indican tus instrucciones."


def credenciales_aws() -> dict[str, str | None]:
    """Credenciales de AWS desde variables de entorno o desde el perfil ``AWS_PROFILE``."""
    region = os.getenv("AWS_REGION") or "us-east-1"
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        return {
            "access_key_id": os.environ["AWS_ACCESS_KEY_ID"],
            "secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
            "session_token": os.getenv("AWS_SESSION_TOKEN") or None,
            "region": region,
        }

    import boto3

    perfil = os.getenv("AWS_PROFILE") or None
    sesion = boto3.Session(profile_name=perfil)
    actuales = sesion.get_credentials()
    if actuales is None:
        raise RuntimeError(f"No se encontraron credenciales de AWS para el perfil {perfil!r}")
    congeladas = actuales.get_frozen_credentials()
    return {
        "access_key_id": congeladas.access_key,
        "secret_access_key": congeladas.secret_key,
        "session_token": congeladas.token,
        "region": os.getenv("AWS_REGION") or sesion.region_name or region,
    }


MOTORES = ("gemini", "openai", "nova")


def motor_elegido(repo: Repositorio | None = None) -> str:
    """El motor elegido en el panel; si no hay elección, ``MOTOR_VOZ`` del .env."""
    elegido = repo.ajuste("motor_voz") if repo else None
    if elegido in MOTORES:
        return elegido
    return os.getenv("MOTOR_VOZ", "gemini").lower()


def falta_para_motor(motor: str) -> str | None:
    """Qué falta en el .env para usar ``motor``, o None si está listo."""
    if motor == "gemini":
        return None if os.getenv("GOOGLE_API_KEY") else "Falta GOOGLE_API_KEY en .env"
    if motor == "openai":
        return None if os.getenv("OPENAI_API_KEY") else "Falta OPENAI_API_KEY en .env"
    if motor == "nova":
        try:
            credenciales_aws()
        except Exception as error:  # noqa: BLE001
            return f"Faltan credenciales de AWS: {error}"
        return None
    return f"El motor {motor!r} no existe; usa gemini, openai o nova"


def crear_servicio_voz(instrucciones: str, herramientas: list, motor: str | None = None):
    """Crea el servicio de voz a voz: ``motor`` o, si falta, ``MOTOR_VOZ`` (gemini, openai o nova)."""
    motor = (motor or os.getenv("MOTOR_VOZ", "gemini")).lower()

    if motor == "openai":
        from pipecat.services.openai.realtime import events
        from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService

        ajustes_openai = OpenAIRealtimeLLMService.Settings(
            model=os.getenv("OPENAI_MODEL") or "gpt-realtime-2.1",
            system_instruction=instrucciones,
            session_properties=events.SessionProperties(
                audio=events.AudioConfiguration(
                    output=events.AudioOutput(voice=os.getenv("OPENAI_VOICE") or "marin")
                )
            ),
        )
        return OpenAIRealtimeLLMService(
            api_key=os.environ["OPENAI_API_KEY"], settings=ajustes_openai, tools=herramientas
        )

    if motor == "nova":
        from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService

        ajustes_nova = AWSNovaSonicLLMService.Settings(system_instruction=instrucciones)
        ajustes_nova.voice = os.getenv("NOVA_VOICE_ID") or "lupe"
        credenciales = credenciales_aws()
        return AWSNovaSonicLLMService(
            access_key_id=credenciales["access_key_id"],
            secret_access_key=credenciales["secret_access_key"],
            session_token=credenciales["session_token"],
            region=credenciales["region"],
            settings=ajustes_nova,
            tools=herramientas,
        )

    from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiVADParams

    ajustes = GeminiLiveLLMService.Settings(
        voice=os.getenv("GOOGLE_VOICE_ID", "Aoede"),
        language=os.getenv("IDIOMA", "es-US"),
        system_instruction=instrucciones,
        vad=GeminiVADParams(silence_duration_ms=int(os.getenv("SILENCIO_MS", "900"))),
    )
    if os.getenv("GOOGLE_MODEL"):
        ajustes.model = os.environ["GOOGLE_MODEL"]
    return GeminiLiveLLMService(api_key=os.environ["GOOGLE_API_KEY"], settings=ajustes, tools=herramientas)


def verificar_motor() -> str:
    """Revisa al arrancar que el motor de voz elegido esté instalado y configurado.

    Así el error aparece en la terminal del bot y no cuando la persona ya contestó.
    """
    motor = os.getenv("MOTOR_VOZ", "gemini").lower()
    try:
        if motor == "nova":
            from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService  # noqa: F401

            credenciales_aws()
        elif motor == "openai":
            from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService  # noqa: F401

            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("Falta OPENAI_API_KEY en .env")
        elif motor == "gemini":
            from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService  # noqa: F401

            if not os.getenv("GOOGLE_API_KEY"):
                raise RuntimeError("Falta GOOGLE_API_KEY en .env")
        else:
            raise RuntimeError(f"MOTOR_VOZ={motor!r} no existe; usa gemini, nova u openai")
    except ImportError as error:
        raise SystemExit(f"Falta instalar el motor {motor}: ejecuta uv sync ({error})") from None
    except Exception as error:
        raise SystemExit(f"El motor de voz {motor} no está listo: {error}") from None
    logger.info(f"Motor de voz: {motor}")
    return motor


def recordatorio_del_motivo(repo: Repositorio, motivo: str, persona_id: int) -> str:
    """Texto del recordatorio si la llamada es de tipo "recordatorio:<id>"; si no, cadena vacía."""
    if not motivo.startswith("recordatorio:"):
        return ""
    try:
        recordatorio = repo.obtener_recordatorio(int(motivo.split(":", 1)[1]))
    except ValueError:
        return ""
    return recordatorio.texto if recordatorio and recordatorio.persona_id == persona_id else ""


def _canal(runner_args: RunnerArguments) -> str:
    return "web" if isinstance(runner_args, SmallWebRTCRunnerArguments) else "telefono"


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments | None = None,
    *,
    canal: str | None = None,
    frecuencia_audio: int | None = None,
    motivo: str = "",
) -> None:
    """Corre una llamada.

    ``canal``: web, telefono, app o whatsapp; si falta se deduce de ``runner_args``.
    ``motivo``: vacío o "programada" para una llamada normal; "recordatorio:<id>" para una llamada
    corta que solo entrega ese recordatorio.
    """
    repo = Repositorio(os.getenv("RUTA_DB", "compania.db"))
    persona_id = os.getenv("PERSONA_ID")
    persona = repo.obtener_persona(int(persona_id)) if persona_id else repo.persona_activa()
    if persona is None or persona.id is None:
        raise RuntimeError("No hay persona registrada. Ejecuta: uv run compania-semilla --help")

    canal = canal or (_canal(runner_args) if runner_args else "telefono")
    llamada = repo.iniciar_llamada(persona.id, canal)
    respuestas = repo.respuestas(persona.id)
    recordatorio = recordatorio_del_motivo(repo, motivo, persona.id)
    instrucciones = construir_instrucciones(
        persona,
        primera_llamada=repo.es_primera_llamada(persona.id),
        recuerdos=repo.buscar_recuerdos(persona.id, limite=8),
        recordatorios=repo.recordatorios_activos(persona.id),
        mensajes=repo.mensajes_pendientes(persona.id),
        preguntas_bienestar=bienestar.elegir_preguntas_del_dia(respuestas),
        seguimientos=repo.seguimientos_abiertos(persona.id),
        recordatorio_de_la_llamada=recordatorio,
        ahora=datetime.now(),
    )
    grabadora = Grabadora()
    sesion = Sesion(
        repo,
        persona.id,
        aviso=aviso_desde_entorno(),
        trato=persona.trato,
        motivo=recordatorio,
        grabadora=grabadora,
    )
    motor = motor_elegido(repo)
    llm = crear_servicio_voz(instrucciones, sesion.esquemas(), motor)
    logger.info(f"Llamada {llamada.id} con {persona.trato} por {llamada.canal} (motor {motor})")

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # OpenAI detecta los turnos en su servidor; sumar la detección local los duplicaría
            vad_analyzer=None if motor == "openai" else SileroVADAnalyzer(),
            # Silencia el micrófono mientras corre una herramienta, por ejemplo una nota de voz
            user_mute_strategies=[FunctionCallUserMuteStrategy()],
        ),
    )
    # La grabadora va antes del agregador: así escucha a la persona aunque el modelo esté en silencio
    pipeline = Pipeline(
        [transport.input(), grabadora, user_aggregator, llm, transport.output(), assistant_aggregator]
    )
    frecuencias = (
        {"audio_in_sample_rate": frecuencia_audio, "audio_out_sample_rate": frecuencia_audio}
        if frecuencia_audio
        else {}
    )
    parametros = PipelineParams(enable_metrics=True, enable_usage_metrics=True, **frecuencias)
    worker = PipelineWorker(pipeline, params=parametros)
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint if runner_args else False)
    await runner.add_workers(worker)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        nota = sesion.agenda.turno_terminado()
        if nota:
            logger.info(f"Recordando pendientes: {sesion.agenda.descripcion()}")
            await worker.queue_frames(
                [LLMMessagesAppendFrame([{"role": "user", "content": nota}], run_llm=False)]
            )

    async def iniciar_conversacion() -> None:
        saludo = SALUDO
        if sesion.agenda.pendientes():
            saludo += f" Después del saludo ofrece los mensajes de la familia: {sesion.agenda.descripcion()}."
        context.add_message({"role": "developer", "content": saludo})
        await worker.queue_frames([LLMRunFrame()])

    if llamada.canal == "web":

        @worker.rtvi.event_handler("on_client_ready")
        async def on_client_ready(rtvi):
            await iniciar_conversacion()

    else:

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            await iniciar_conversacion()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Fin de la llamada {llamada.id}")
        repo.terminar_llamada(llamada.id)
        segundos = (datetime.now() - llamada.inicio).total_seconds()
        if segundos < LLAMADA_MINIMA_S and not sesion.hubo_actividad():
            logger.info(f"Llamada de {segundos:.0f} s sin actividad: no se manda resumen a la familia")
        else:
            await sesion.aviso.enviar(sesion.resumen(max(1, round(segundos / 60))))
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Punto de entrada que usa el runner de Pipecat."""
    transport_params = {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
        "twilio": lambda: FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


def main() -> None:
    """Arranca el servidor de desarrollo de Pipecat con este bot."""
    from pipecat.runner.run import main as pipecat_main

    sys.modules["__main__"].bot = bot  # el runner busca `bot` en __main__
    pipecat_main()


if __name__ == "__main__":
    main()

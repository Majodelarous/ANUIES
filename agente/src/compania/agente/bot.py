"""Bot de voz con Pipecat.

Uso::

    uv run compania-bot                 # navegador: http://localhost:7860/client
    uv run compania-bot -t twilio -x <dominio-publico>
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
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
from pipecat.workers.runner import WorkerRunner

from compania.agente.herramientas import Sesion
from compania.agente.instrucciones import construir_instrucciones
from compania.dominio import bienestar
from compania.infraestructura.repositorio import Repositorio

load_dotenv(override=True)

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


def crear_servicio_voz(instrucciones: str, herramientas: list):
    """Crea el servicio de voz a voz según ``MOTOR_VOZ`` (gemini o nova)."""
    motor = os.getenv("MOTOR_VOZ", "gemini").lower()

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
        elif motor == "gemini":
            from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService  # noqa: F401

            if not os.getenv("GOOGLE_API_KEY"):
                raise RuntimeError("Falta GOOGLE_API_KEY en .env")
        else:
            raise RuntimeError(f"MOTOR_VOZ={motor!r} no existe; usa gemini o nova")
    except ImportError as error:
        raise SystemExit(f"Falta instalar el motor {motor}: ejecuta uv sync ({error})") from None
    except Exception as error:
        raise SystemExit(f"El motor de voz {motor} no está listo: {error}") from None
    logger.info(f"Motor de voz: {motor}")
    return motor


def _canal(runner_args: RunnerArguments) -> str:
    return "web" if isinstance(runner_args, SmallWebRTCRunnerArguments) else "telefono"


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments | None = None,
    *,
    canal: str | None = None,
    frecuencia_audio: int | None = None,
) -> None:
    """Corre una llamada. ``canal``: web, telefono o app; si falta se deduce de ``runner_args``."""
    repo = Repositorio(os.getenv("RUTA_DB", "compania.db"))
    persona_id = os.getenv("PERSONA_ID")
    persona = repo.obtener_persona(int(persona_id)) if persona_id else repo.primera_persona()
    if persona is None or persona.id is None:
        raise RuntimeError("No hay persona registrada. Ejecuta: uv run compania-semilla --help")

    canal = canal or (_canal(runner_args) if runner_args else "telefono")
    llamada = repo.iniciar_llamada(persona.id, canal)
    respuestas = repo.respuestas(persona.id)
    instrucciones = construir_instrucciones(
        persona,
        primera_llamada=repo.es_primera_llamada(persona.id),
        recuerdos=repo.buscar_recuerdos(persona.id, limite=8),
        recordatorios=repo.recordatorios_activos(persona.id),
        mensajes=repo.mensajes_pendientes(persona.id),
        preguntas_bienestar=bienestar.elegir_preguntas_del_dia(respuestas),
    )
    sesion = Sesion(repo, persona.id)
    llm = crear_servicio_voz(instrucciones, sesion.esquemas())
    logger.info(f"Llamada {llamada.id} con {persona.trato} por {llamada.canal}")

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    pipeline = Pipeline([transport.input(), user_aggregator, llm, transport.output(), assistant_aggregator])
    frecuencias = (
        {"audio_in_sample_rate": frecuencia_audio, "audio_out_sample_rate": frecuencia_audio}
        if frecuencia_audio
        else {}
    )
    parametros = PipelineParams(enable_metrics=True, enable_usage_metrics=True, **frecuencias)
    worker = PipelineWorker(pipeline, params=parametros)
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint if runner_args else False)
    await runner.add_workers(worker)

    async def iniciar_conversacion() -> None:
        context.add_message({"role": "developer", "content": SALUDO})
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

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


def crear_servicio_voz(instrucciones: str, herramientas: list):
    """Crea el servicio de voz a voz según ``MOTOR_VOZ`` (gemini o nova)."""
    motor = os.getenv("MOTOR_VOZ", "gemini").lower()

    if motor == "nova":
        from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService

        ajustes_nova = AWSNovaSonicLLMService.Settings(system_instruction=instrucciones)
        if os.getenv("NOVA_VOICE_ID"):
            ajustes_nova.voice = os.environ["NOVA_VOICE_ID"]
        return AWSNovaSonicLLMService(
            access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            session_token=os.getenv("AWS_SESSION_TOKEN") or None,
            region=os.getenv("AWS_REGION", "us-east-1"),
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


def _canal(runner_args: RunnerArguments) -> str:
    return "web" if isinstance(runner_args, SmallWebRTCRunnerArguments) else "telefono"


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    repo = Repositorio(os.getenv("RUTA_DB", "compania.db"))
    persona_id = os.getenv("PERSONA_ID")
    persona = repo.obtener_persona(int(persona_id)) if persona_id else repo.primera_persona()
    if persona is None or persona.id is None:
        raise RuntimeError("No hay persona registrada. Ejecuta: uv run compania-semilla --help")

    llamada = repo.iniciar_llamada(persona.id, _canal(runner_args))
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
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True))
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
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

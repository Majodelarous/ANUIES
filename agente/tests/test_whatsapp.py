import json

import pytest
from pipecat.frames.frames import InputAudioRawFrame, InterruptionFrame, OutputAudioRawFrame

from compania.agente.whatsapp import LIMPIAR, SerializadorPCM, solicitud_llamada


async def test_audio_del_puente_entra_como_pcm_16k():
    frame = await SerializadorPCM().deserialize(b"\x01\x00" * 320)
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.sample_rate == 16000 and frame.num_channels == 1
    assert len(frame.audio) == 640


async def test_texto_del_puente_se_ignora():
    assert await SerializadorPCM().deserialize('{"evento": "x"}') is None


async def test_voz_de_la_asistente_sale_como_bytes():
    audio = b"\x00\x10" * 320
    salida = await SerializadorPCM().serialize(OutputAudioRawFrame(audio, 16000, 1))
    assert salida == audio


async def test_voz_a_otra_frecuencia_se_remuestrea():
    salida = await SerializadorPCM().serialize(OutputAudioRawFrame(b"\x00\x10" * 2400, 24000, 1))
    assert isinstance(salida, bytes)


async def test_interrupcion_pide_limpiar_el_audio():
    assert await SerializadorPCM().serialize(InterruptionFrame()) == LIMPIAR


def test_solicitud_al_puente():
    req = solicitud_llamada("+52 222 123 4567")
    assert req.full_url == "http://127.0.0.1:7864/llamar"
    assert json.loads(req.data) == {"numero": "522221234567"}


def test_rechaza_numero_corto():
    with pytest.raises(ValueError):
        solicitud_llamada("12345")


def test_motor_inexistente_falla_al_arrancar(monkeypatch):
    from compania.agente.bot import verificar_motor

    monkeypatch.setenv("MOTOR_VOZ", "otro")
    with pytest.raises(SystemExit):
        verificar_motor()


def test_gemini_sin_llave_falla_al_arrancar(monkeypatch):
    from compania.agente.bot import verificar_motor

    monkeypatch.setenv("MOTOR_VOZ", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="GOOGLE_API_KEY"):
        verificar_motor()


def test_nova_instalado(monkeypatch):
    import compania.agente.bot as bot

    monkeypatch.setenv("MOTOR_VOZ", "nova")
    monkeypatch.setattr(bot, "credenciales_aws", lambda: {})
    assert bot.verificar_motor() == "nova"

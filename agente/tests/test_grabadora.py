import array
import asyncio
import math

from pipecat.frames.frames import InputAudioRawFrame

from compania.agente.grabadora import DetectorDeFin, Grabadora, energia, tono

F = 16000
BLOQUE = 0.02  # 20 ms


def voz(segundos=BLOQUE):
    n = int(F * segundos)
    return array.array("h", (int(3000 * math.sin(2 * math.pi * 220 * i / F)) for i in range(n))).tobytes()


def silencio(segundos=BLOQUE):
    return b"\x00\x00" * int(F * segundos)


def alimentar(detector, bloques):
    for b in bloques:
        if detector.agregar(b, len(b) / 2 / F):
            return True
    return False


def test_energia():
    assert energia(silencio()) == 0
    assert energia(voz()) > 1000


def test_termina_tras_silencio_despues_de_hablar():
    d = DetectorDeFin()
    assert not alimentar(d, [silencio()] * 50)  # 1 s mientras llega el tonito (se ignora)
    assert not alimentar(d, [voz()] * 50)  # 1 s hablando
    assert alimentar(d, [silencio()] * 100)  # 2 s de silencio: termina
    audio = d.audio()
    assert audio is not None
    # Se quita el silencio final salvo medio segundo
    assert abs(len(audio) / 2 / F - 1.5) < 0.15


def test_el_eco_del_tonito_no_queda_en_la_nota():
    d = DetectorDeFin()
    # Medio segundo de silencio y el eco del tonito, como llega en la llamada; luego la voz
    alimentar(d, [silencio()] * 25 + [voz()] * 25)
    assert not d.hablo and d.partes == []
    assert not alimentar(d, [voz()] * 50)
    alimentar(d, [silencio()] * 100)
    assert abs(len(d.audio()) / 2 / F - 1.5) < 0.15  # solo la voz y medio segundo final


def test_el_eco_solo_no_cuenta_como_que_hablo():
    d = DetectorDeFin(sin_voz_s=3.0)
    assert alimentar(d, [voz()] * 50 + [silencio()] * 150)
    assert d.audio() is None


def test_si_no_habla_se_rinde_sin_audio():
    d = DetectorDeFin(sin_voz_s=1.0)
    assert alimentar(d, [silencio()] * 60)
    assert d.audio() is None


def test_corta_en_el_maximo():
    d = DetectorDeFin(max_s=1.0)
    assert alimentar(d, [voz()] * 60)


def test_tono_dura_lo_pedido():
    assert len(tono(F, 0.35)) == int(F * 0.35) * 2


async def test_grabadora_graba_hasta_que_se_calla():
    g = Grabadora()

    async def hablar():
        await asyncio.sleep(0.01)
        for b in [silencio()] * 50 + [voz()] * 25 + [silencio()] * 100:
            g.observar(InputAudioRawFrame(b, F, 1))

    tarea = asyncio.create_task(hablar())
    resultado = await g.grabar()
    await tarea
    assert resultado is not None
    wav, frecuencia = resultado
    assert frecuencia == F and wav[:4] == b"RIFF"


def test_sin_grabar_no_guarda_nada():
    g = Grabadora()
    g.observar(InputAudioRawFrame(voz(), F, 1))  # no truena ni guarda
    assert g._detector is None


async def test_espera_a_que_termine_de_sonar_el_audio_en_cola():
    import asyncio

    from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame
    from pipecat.processors.frame_processor import FrameDirection

    g = Grabadora()
    antes = g.paradas

    async def la_salida_termina_despues():
        await asyncio.sleep(0.1)
        await g.process_frame(BotStartedSpeakingFrame(), FrameDirection.UPSTREAM)
        await asyncio.sleep(0.2)
        await g.process_frame(BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM)

    tarea = asyncio.create_task(la_salida_termina_despues())
    espera = await g.esperar_fin_de_audio(antes, max_s=2)
    assert espera >= 0.3 and g.paradas == antes + 1
    await tarea
    assert await g.esperar_fin_de_audio(g.paradas, max_s=0.2) < 1


def test_quita_lo_que_tardo_en_empezar_a_hablar():
    d = DetectorDeFin()
    alimentar(d, [silencio()] * 50)  # 1 s del tonito (se ignora)
    alimentar(d, [silencio()] * 75)  # 1.5 s pensando antes de hablar
    alimentar(d, [voz()] * 50)  # 1 s hablando
    assert alimentar(d, [silencio()] * 100)
    # 0.3 s antes de la voz + 1 s de voz + 0.5 s al final
    assert abs(len(d.audio()) / 2 / F - 1.8) < 0.15

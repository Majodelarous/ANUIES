import base64
import io
import wave

import pytest
from conftest import AvisoFalso, ParametrosFalsos
from fastapi.testclient import TestClient

from compania.agente import herramientas
from compania.agente.herramientas import Sesion
from compania.agente.instrucciones import construir_instrucciones
from compania.dominio.alertas import LINEA_DE_LA_VIDA
from compania.dominio.modelos import MensajeFamiliar


def wav(segundos: float = 0.5, frecuencia: int = 16000) -> bytes:
    salida = io.BytesIO()
    with wave.open(salida, "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(b"\x10\x00" * int(segundos * frecuencia))
    return salida.getvalue()


@pytest.fixture
def sin_espera(monkeypatch):
    async def nada(_):
        return None

    monkeypatch.setattr(herramientas.asyncio, "sleep", nada)


async def test_reproduce_la_nota_de_voz_y_la_entrega(repo, persona, tmp_path, sin_espera):
    ruta = tmp_path / "nota.wav"
    ruta.write_bytes(wav(0.5))
    mensaje = repo.guardar_mensaje(MensajeFamiliar(persona.id, "Majo", "", str(ruta)))
    sesion = Sesion(repo, persona.id)

    p = ParametrosFalsos({"mensaje_id": mensaje.id})
    await sesion.reproducir_mensaje_voz(p)

    assert p.resultado["reproducido"]
    audio = b"".join(f.audio for f in p.llm.frames)
    assert len(audio) == 16000  # 0.5 s a 16 kHz, 2 bytes por muestra
    assert all(f.sample_rate == 16000 for f in p.llm.frames)
    assert repo.mensajes_pendientes(persona.id) == []
    assert sesion.mensajes_entregados == ["Majo"]


async def test_mensaje_sin_audio_no_se_reproduce(repo, persona):
    mensaje = repo.guardar_mensaje(MensajeFamiliar(persona.id, "Majo", "Hola abue"))
    p = ParametrosFalsos({"mensaje_id": mensaje.id})
    await Sesion(repo, persona.id).reproducir_mensaje_voz(p)
    assert "error" in p.resultado
    assert p.llm.frames == []


async def test_audio_danado_pide_decirlo_con_palabras(repo, persona, tmp_path):
    ruta = tmp_path / "mala.wav"
    ruta.write_bytes(b"no es audio")
    mensaje = repo.guardar_mensaje(MensajeFamiliar(persona.id, "Majo", "", str(ruta)))
    p = ParametrosFalsos({"mensaje_id": mensaje.id})
    await Sesion(repo, persona.id).reproducir_mensaje_voz(p)
    assert "palabras" in p.resultado["error"]


async def test_respuesta_de_la_persona_va_al_grupo(repo, persona):
    aviso = AvisoFalso()
    p = ParametrosFalsos({"texto": "Gracias mija, aquí la espero", "para": "Majo"})
    await Sesion(repo, persona.id, aviso=aviso, trato="la abue").enviar_mensaje_a_familia(p)
    assert p.resultado == {"enviado": True}
    assert aviso.enviados == ["Mensaje de la abue para Majo: Gracias mija, aquí la espero"]


async def test_si_falla_el_envio_la_asistente_lo_dice(repo, persona):
    p = ParametrosFalsos({"texto": "Hola"})
    await Sesion(repo, persona.id, aviso=AvisoFalso(ok=False)).enviar_mensaje_a_familia(p)
    assert p.resultado["enviado"] is False


async def test_crisis_avisa_al_grupo_de_inmediato(repo, persona):
    aviso = AvisoFalso()
    p = ParametrosFalsos({"nivel": "crisis", "motivo": "Dijo que ya no quiere vivir"})
    await Sesion(repo, persona.id, aviso=aviso, trato="la abue").generar_alerta(p)
    assert len(aviso.enviados) == 1
    assert aviso.enviados[0].startswith("URGENTE sobre la abue")
    assert LINEA_DE_LA_VIDA in aviso.enviados[0]


async def test_alerta_informativa_no_se_envia(repo, persona):
    aviso = AvisoFalso()
    p = ParametrosFalsos({"nivel": "informativa", "motivo": "Comentó que llovió"})
    await Sesion(repo, persona.id, aviso=aviso).generar_alerta(p)
    assert aviso.enviados == []


async def test_resumen_de_la_llamada(repo, persona):
    sesion = Sesion(repo, persona.id, trato="la abue")
    await sesion.guardar_recuerdo(
        ParametrosFalsos({"tema": "boda", "contenido": "Se casó en 1968", "compartir_con_familia": True})
    )
    await sesion.guardar_recuerdo(ParametrosFalsos({"tema": "privado", "contenido": "No compartir"}))
    juego = ParametrosFalsos({"tipo": "refran"})
    await sesion.obtener_juego(juego)
    await sesion.registrar_resultado_juego(
        ParametrosFalsos({"juego_id": juego.resultado["juego_id"], "acerto": True})
    )

    texto = sesion.resumen(7)
    assert texto.startswith("Llamada con la abue: 7 min.")
    assert "boda: Se casó en 1968" in texto
    assert "No compartir" not in texto
    assert "1 de 1" in texto
    assert "Sin alertas." in texto


def test_instrucciones_ofrecen_la_nota_de_voz(persona):
    mensajes = [
        MensajeFamiliar(persona.id, "Majo", "", "audios/x.wav", id=3),
        MensajeFamiliar(persona.id, "Luis", "Te quiero", id=4),
    ]
    texto = construir_instrucciones(persona, primera_llamada=False, mensajes=mensajes)
    assert "- id 3, de Majo: nota de voz" in texto
    assert '- id 4, de Luis: "Te quiero"' in texto
    assert "reproducir_mensaje_voz" in texto


@pytest.fixture
def cliente(repo, persona, tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_ID", raising=False)
    from compania.agente.whatsapp import crear_app

    return TestClient(crear_app(repo, tmp_path / "audios"))


def test_puente_guarda_nota_de_voz(cliente, repo, persona):
    r = cliente.post("/mensajes", json={"de": "Majo", "audio_wav_b64": base64.b64encode(wav(1.0)).decode()})
    assert r.status_code == 200
    assert r.json()["trato"] == "doña Carmen"
    [mensaje] = repo.mensajes_pendientes(persona.id)
    assert mensaje.de == "Majo" and mensaje.audio.endswith(".wav")


def test_puente_guarda_texto(cliente, repo, persona):
    assert cliente.post("/mensajes", json={"de": "Luis", "texto": "Voy el domingo"}).status_code == 200
    assert repo.mensajes_pendientes(persona.id)[0].texto == "Voy el domingo"


def test_puente_rechaza_audio_que_no_es_wav(cliente, repo, persona, tmp_path):
    r = cliente.post("/mensajes", json={"de": "Majo", "audio_wav_b64": base64.b64encode(b"hola").decode()})
    assert r.status_code == 422
    assert repo.mensajes_pendientes(persona.id) == []
    assert list((tmp_path / "audios").glob("*.wav")) == []


def test_puente_rechaza_mensaje_vacio(cliente):
    assert cliente.post("/mensajes", json={"de": "Majo"}).status_code == 422


async def test_sin_grupo_no_se_envia_nada(monkeypatch):
    from compania.infraestructura.puente_whatsapp import SinAviso, aviso_desde_entorno

    monkeypatch.delenv("WHATSAPP_GRUPO", raising=False)
    aviso = aviso_desde_entorno()
    assert isinstance(aviso, SinAviso)
    assert await aviso.enviar("hola") is False


async def test_puente_apagado_no_rompe_la_llamada():
    from compania.infraestructura.puente_whatsapp import PuenteWhatsApp

    assert await PuenteWhatsApp(puerto=9, timeout=1).enviar("hola") is False

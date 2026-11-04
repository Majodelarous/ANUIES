from conftest import ParametrosFalsos

from compania.agente.herramientas import Sesion
from compania.dominio.alertas import LINEA_DE_LA_VIDA
from compania.dominio.modelos import MensajeFamiliar


def test_esquemas_tienen_manejador_y_nombres_unicos(repo, persona):
    esquemas = Sesion(repo, persona.id).esquemas()
    nombres = [e.name for e in esquemas]
    assert len(nombres) == len(set(nombres)) == 14
    assert all(e.handler is not None for e in esquemas)


async def test_guardar_y_buscar_recuerdo(repo, persona):
    sesion = Sesion(repo, persona.id)
    p = ParametrosFalsos({"tema": "cocina", "contenido": "El mole de su mamá"})
    await sesion.guardar_recuerdo(p)
    assert p.resultado["guardado"]

    b = ParametrosFalsos({"tema": "mole"})
    await sesion.buscar_recuerdos(b)
    assert b.resultado["recuerdos"][0]["tema"] == "cocina"


async def test_juego_no_se_repite_en_la_llamada(repo, persona):
    sesion = Sesion(repo, persona.id)
    a, b = ParametrosFalsos({"tipo": "refran"}), ParametrosFalsos({"tipo": "refran"})
    await sesion.obtener_juego(a)
    await sesion.obtener_juego(b)
    assert a.resultado["juego_id"] != b.resultado["juego_id"]

    r = ParametrosFalsos({"juego_id": a.resultado["juego_id"], "acerto": True})
    await sesion.registrar_resultado_juego(r)
    assert r.resultado == {"registrado": True}


async def test_tipo_de_juego_invalido_usa_cualquiera(repo, persona):
    p = ParametrosFalsos({"tipo": "domino"})
    await Sesion(repo, persona.id).obtener_juego(p)
    assert p.resultado["disponible"]


async def test_respuesta_bienestar(repo, persona):
    sesion = Sesion(repo, persona.id)
    ok = ParametrosFalsos({"pregunta_id": "gds05", "respuesta": "sí"})
    await sesion.registrar_respuesta_bienestar(ok)
    assert ok.resultado == {"registrado": True}
    assert repo.respuestas(persona.id)[0].respuesta == "si"

    mala = ParametrosFalsos({"pregunta_id": "xyz", "respuesta": "si"})
    await sesion.registrar_respuesta_bienestar(mala)
    assert "error" in mala.resultado


async def test_recordatorio_valida_hora(repo, persona):
    sesion = Sesion(repo, persona.id)
    mala = ParametrosFalsos({"texto": "pastilla", "hora": "2 de la tarde"})
    await sesion.crear_recordatorio(mala)
    assert "error" in mala.resultado

    buena = ParametrosFalsos({"texto": "pastilla", "hora": "8:30"})
    await sesion.crear_recordatorio(buena)
    assert repo.recordatorios_activos(persona.id)[0].hora == "08:30"


async def test_marcar_mensaje(repo, persona):
    mensaje = repo.guardar_mensaje(MensajeFamiliar(persona.id, "su nieta", "Te quiero"))
    p = ParametrosFalsos({"mensaje_id": mensaje.id})
    await Sesion(repo, persona.id).marcar_mensaje_entregado(p)
    assert p.resultado == {"marcado": True}


async def test_alerta_de_crisis_indica_linea_de_la_vida(repo, persona):
    p = ParametrosFalsos({"nivel": "crisis", "motivo": "Expresó que no quiere seguir"})
    await Sesion(repo, persona.id).generar_alerta(p)
    assert LINEA_DE_LA_VIDA in p.resultado["que_decir"]
    assert len(repo.alertas(persona.id)) == 1


async def test_recordatorio_en_minutos_lo_calcula_el_programa(repo, persona):
    from datetime import datetime

    sesion = Sesion(repo, persona.id, reloj=lambda: datetime(2026, 11, 3, 19, 31))
    p = ParametrosFalsos({"texto": "apagar la luz", "en_minutos": 5})
    await sesion.crear_recordatorio(p)
    assert p.resultado["hora"] == "19:36" and p.resultado["repetir"] == "solo una vez"
    [r] = repo.recordatorios_activos(persona.id)
    assert r.hora == "19:36" and r.una_vez

    noche = Sesion(repo, persona.id, reloj=lambda: datetime(2026, 11, 3, 23, 58))
    q = ParametrosFalsos({"texto": "dormir", "en_minutos": "10"})
    await noche.crear_recordatorio(q)
    assert q.resultado["hora"] == "00:08"

    mala = ParametrosFalsos({"texto": "x", "en_minutos": 0})
    await sesion.crear_recordatorio(mala)
    assert "error" in mala.resultado


async def test_recordatorio_a_una_hora_se_repite_salvo_solo_hoy(repo, persona):
    sesion = Sesion(repo, persona.id)
    diario = ParametrosFalsos({"texto": "pastilla", "hora": "14:00"})
    await sesion.crear_recordatorio(diario)
    assert diario.resultado["repetir"] == "todos los días"
    hoy = ParametrosFalsos({"texto": "llamar al doctor", "hora": "16:00", "solo_hoy": True})
    await sesion.crear_recordatorio(hoy)
    assert hoy.resultado["repetir"] == "solo una vez"

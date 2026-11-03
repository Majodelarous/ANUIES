from conftest import ParametrosFalsos

from compania.agente.herramientas import Sesion
from compania.dominio.agenda import Agenda
from compania.dominio.modelos import MensajeFamiliar


def mensajes():
    return [
        MensajeFamiliar(1, "Majo", "", "audios/a.wav", id=10),
        MensajeFamiliar(1, "Luis", "Voy el domingo", id=11),
    ]


def test_recuerda_pendientes_despues_de_unos_turnos():
    agenda = Agenda.desde(mensajes())
    assert agenda.turno_terminado() is None  # turno 1: aún no
    nota = agenda.turno_terminado()  # turno 2
    assert nota and "nota de voz de Majo" in nota and "mensaje de Luis" in nota
    assert agenda.turno_terminado() is None  # no insiste cada turno
    assert agenda.turno_terminado() is None
    assert agenda.turno_terminado()  # turno 5: vuelve a recordar


def test_no_recuerda_lo_ya_entregado():
    agenda = Agenda.desde(mensajes())
    agenda.entregar(10)
    agenda.turno_terminado()
    nota = agenda.turno_terminado()
    assert "Majo" not in nota and "Luis" in nota
    agenda.entregar(11)
    assert [agenda.turno_terminado() for _ in range(6)] == [None] * 6


def test_sin_mensajes_no_hay_notas():
    agenda = Agenda.desde([])
    assert agenda.descripcion() == "ninguno"
    assert all(agenda.turno_terminado() is None for _ in range(5))


async def test_consultar_pendientes_y_entregar(repo, persona):
    mensaje = repo.guardar_mensaje(MensajeFamiliar(persona.id, "Luis", "Hola"))
    sesion = Sesion(repo, persona.id)

    p = ParametrosFalsos({})
    await sesion.consultar_pendientes(p)
    assert p.resultado["pendientes"][0]["de"] == "Luis"

    await sesion.marcar_mensaje_entregado(ParametrosFalsos({"mensaje_id": mensaje.id}))
    q = ParametrosFalsos({})
    await sesion.consultar_pendientes(q)
    assert q.resultado["pendientes"] == []


def test_resumen_avisa_lo_que_quedo_pendiente(repo, persona):
    repo.guardar_mensaje(MensajeFamiliar(persona.id, "Majo", "", "audios/a.wav"))
    texto = Sesion(repo, persona.id, trato="la abue").resumen(3)
    assert "Quedó pendiente para la próxima llamada: nota de voz de Majo." in texto


async def test_actividad_de_la_llamada(repo, persona):
    sesion = Sesion(repo, persona.id)
    assert not sesion.hubo_actividad()
    await sesion.crear_recordatorio(ParametrosFalsos({"texto": "Regar", "hora": "18:00"}))
    assert sesion.hubo_actividad()

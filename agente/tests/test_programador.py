import asyncio
from datetime import datetime

import pytest
from conftest import AvisoFalso

from compania.agente.programador import Programador, texto_sin_respuesta
from compania.dominio.modelos import Horario, Persona, Recordatorio
from compania.dominio.programacion import Tarea


class PuenteFalso:
    """Simula el puente: cada llamada contesta o no según la lista ``respuestas``."""

    def __init__(self, respuestas, codigos=None):
        self.respuestas = list(respuestas)
        self.codigos = list(codigos or [])
        self.pedidas: list[tuple[str, str]] = []
        self._ultima: dict = {}

    async def llamar(self, numero, motivo):
        codigo = self.codigos.pop(0) if self.codigos else 200
        if codigo != 200:
            return codigo, {"error": "x"}
        self.pedidas.append((numero, motivo))
        contesto = self.respuestas.pop(0)
        self._ultima = {"inicio": 9e15, "terminada": True, "contesto": contesto}
        return 200, {"llamada": "X"}

    async def ultima_llamada(self):
        return self._ultima


async def sin_espera(_):
    return None


@pytest.fixture
def abue(repo):
    return repo.guardar_persona(
        Persona("Amada", "abuelita", telefono="522221234567", consentimiento=datetime.now())
    )


def programador(repo, puente, aviso, ahora=datetime(2026, 11, 5, 17, 30)):
    return Programador(repo, puente, aviso, dormir=sin_espera, reloj=lambda: ahora)


TAREA = Tarea("2026-11-05 17:30 llamada 1", "llamada", 1, "17:30")


async def test_si_contesta_no_avisa(repo, abue):
    puente, aviso = PuenteFalso([True]), AvisoFalso()
    assert await programador(repo, puente, aviso).atender(TAREA) == "contesto"
    assert puente.pedidas == [("522221234567", "programada")]
    assert aviso.enviados == []


async def test_reintenta_una_vez_y_si_contesta_no_avisa(repo, abue):
    puente, aviso = PuenteFalso([False, True]), AvisoFalso()
    assert await programador(repo, puente, aviso).atender(TAREA) == "contesto"
    assert len(puente.pedidas) == 2
    assert aviso.enviados == []


async def test_si_no_contesta_dos_veces_avisa_y_deja_alerta(repo, abue):
    puente, aviso = PuenteFalso([False, False]), AvisoFalso()
    assert await programador(repo, puente, aviso).atender(TAREA) == "sin_respuesta"
    assert aviso.enviados == [
        "Hola, familia, soy Rous. Hoy a las 17:30 le marqué dos veces a abuelita para platicar, "
        "y no contestó. ¿Alguien puede llamarle o pasar a verle?"
    ]
    [alerta] = repo.alertas(abue.id)
    assert alerta.motivo == "No contestó la llamada de las 17:30"


async def test_si_el_puente_no_responde_no_culpa_a_la_persona(repo, abue):
    puente, aviso = PuenteFalso([], codigos=[0]), AvisoFalso()
    assert await programador(repo, puente, aviso).atender(TAREA) == "error"
    assert aviso.enviados == []
    assert repo.alertas(abue.id) == []


async def test_si_el_puente_esta_ocupado_espera_y_vuelve_a_intentar(repo, abue):
    puente, aviso = PuenteFalso([True], codigos=[409]), AvisoFalso()
    assert await programador(repo, puente, aviso).atender(TAREA) == "contesto"


async def test_sin_numero_se_omite(repo, monkeypatch):
    monkeypatch.delenv("WHATSAPP_PERSONA", raising=False)
    persona = repo.guardar_persona(Persona("Sin", "número"))
    tarea = Tarea("c", "llamada", persona.id, "17:30")
    assert await programador(repo, PuenteFalso([]), AvisoFalso()).atender(tarea) == "omitida"


async def test_revisar_lanza_solo_lo_que_toca_y_una_vez(repo, abue):
    repo.guardar_horario(Horario(abue.id, "17:30"))
    repo.guardar_recordatorio(Recordatorio(abue.id, "Regar las plantas", "09:00"))
    puente = PuenteFalso([True, True])
    prog = programador(repo, puente, AvisoFalso())

    [tarea] = await prog.revisar()
    assert tarea.tipo == "llamada"
    await asyncio.gather(*prog.en_curso)
    assert await prog.revisar() == []  # ya se lanzó hoy
    assert puente.pedidas == [("522221234567", "programada")]


async def test_recordatorio_lanza_llamada_corta(repo, abue):
    r = repo.guardar_recordatorio(Recordatorio(abue.id, "Tomar la pastilla", "14:00"))
    puente = PuenteFalso([True])
    prog = programador(repo, puente, AvisoFalso(), ahora=datetime(2026, 11, 5, 14, 2))
    await prog.revisar()
    await asyncio.gather(*prog.en_curso)
    assert puente.pedidas == [("522221234567", f"recordatorio:{r.id}")]


def test_aviso_de_recordatorio_sin_respuesta():
    tarea = Tarea("c", "recordatorio", 1, "14:00", 3, "Tomar la pastilla.")
    assert texto_sin_respuesta(tarea, "abuelita", "Rous") == (
        "Hola, familia, soy Rous. Hoy a las 14:00 le marqué dos veces a abuelita para recordarle: "
        "Tomar la pastilla, y no contestó. ¿Alguien puede llamarle o pasar a verle?"
    )

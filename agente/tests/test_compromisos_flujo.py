from datetime import datetime

from conftest import AvisoFalso
from fastapi.testclient import TestClient

from compania.agente.instrucciones import construir_instrucciones
from compania.agente.programador import Programador
from compania.dominio.modelos import Compromiso, Persona, Seguimiento
from compania.dominio.programacion import tareas_pendientes


def test_mensaje_con_promesa_crea_compromiso_y_seguimiento(repo, persona, tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_ID", raising=False)
    from compania.agente.whatsapp import crear_app

    cliente = TestClient(crear_app(repo, tmp_path))
    r = cliente.post("/mensajes", json={"de": "Fortino", "texto": "Abue, salgo a las 11:59 pm y te marco"})
    assert r.json()["compromiso"]["hora"] == "23:59"
    [compromiso] = repo.compromisos_por_avisar()
    assert compromiso.de == "Fortino"
    [seguimiento] = repo.seguimientos_abiertos(persona.id)
    assert seguimiento.motivo == "quedó de marcarle a las 23:59"


def test_mensaje_sin_promesa_no_crea_compromiso(repo, persona, tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_ID", raising=False)
    from compania.agente.whatsapp import crear_app

    r = TestClient(crear_app(repo, tmp_path)).post(
        "/mensajes", json={"de": "Majo", "texto": "Abue, te quiero"}
    )
    assert "compromiso" not in r.json()
    assert repo.compromisos_por_avisar() == []


def test_a_la_hora_le_recuerda_al_familiar(repo, persona):
    c = repo.guardar_compromiso(
        Compromiso(persona.id, "Fortino", "2026-11-05", "17:00", "Abue, a las 5 te marco")
    )
    ahora = datetime(2026, 11, 5, 17, 1)
    [tarea] = tareas_pendientes(ahora, [], [], set(), repo.compromisos_por_avisar())
    assert tarea.tipo == "compromiso" and tarea.compromiso_id == c.id

    aviso = AvisoFalso()

    async def nada(_):
        return None

    prog = Programador(repo, None, aviso, dormir=nada, reloj=lambda: ahora)
    import asyncio

    assert asyncio.run(prog.atender(tarea)) == "avisado"
    assert aviso.enviados == [
        "Fortino, son las 17:00: quedaste de marcarle a doña Carmen. Le va a dar mucho gusto escucharte."
    ]
    assert repo.compromisos_por_avisar() == []


def test_compromiso_de_otro_dia_no_se_lanza(repo, persona):
    repo.guardar_compromiso(Compromiso(persona.id, "Fortino", "2026-11-06", "17:00", "x"))
    assert tareas_pendientes(datetime(2026, 11, 5, 17, 1), [], [], set(), repo.compromisos_por_avisar()) == []


def test_rous_pregunta_si_le_marco():
    persona = Persona("Carmen", "doña Carmen", id=1, consentimiento=datetime.now())
    texto = construir_instrucciones(
        persona,
        primera_llamada=False,
        seguimientos=[Seguimiento(1, "Fortino", "quedó de marcarle a las 17:00", id=2)],
    )
    assert (
        "- id 2: Fortino quedó de marcarle a las 17:00; si ya pasó esa hora, pregúntale si le marcó" in texto
    )

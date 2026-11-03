from fastapi.testclient import TestClient

from compania.dominio.modelos import Alerta, NivelAlerta, Recuerdo
from compania.panel.app import crear_app


def test_panel_muestra_datos_y_respeta_privacidad(repo, persona):
    repo.guardar_recuerdo(Recuerdo(persona.id, "cocina", "El mole de su mamá", True))
    repo.guardar_recuerdo(Recuerdo(persona.id, "privado", "Algo que no quiso compartir", False))
    repo.iniciar_llamada(persona.id, "web")
    cliente = TestClient(crear_app(repo))
    html = cliente.get("/").text
    assert "doña Carmen" in html
    assert "El mole de su mamá" in html
    assert "Algo que no quiso compartir" not in html
    assert "Aún sin datos" in html
    assert "800 911 2000" in html


def test_crisis_pone_rojo(repo, persona):
    repo.guardar_alerta(Alerta(persona.id, NivelAlerta.CRISIS, "Expresó que no quiere seguir"))
    datos = TestClient(crear_app(repo)).get("/api/resumen").json()
    assert datos["senal"]["semaforo"] == "rojo"


def test_alta_de_recordatorio_y_mensaje(repo, persona):
    cliente = TestClient(crear_app(repo))
    r = cliente.post(
        "/recordatorios",
        data={"persona_id": persona.id, "texto": "Pastilla", "hora": "14:00"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    cliente.post("/mensajes", data={"persona_id": persona.id, "de": "su nieta", "texto": "<b>Hola</b>"})
    assert repo.recordatorios_activos(persona.id)[0].hora == "14:00"
    html = cliente.get("/").text
    assert "&lt;b&gt;Hola&lt;/b&gt;" in html


def test_hora_invalida(repo, persona):
    r = TestClient(crear_app(repo)).post(
        "/recordatorios", data={"persona_id": persona.id, "texto": "x", "hora": "2pm"}
    )
    assert r.status_code == 422


def test_horario_de_llamada_desde_el_panel(repo, persona):
    from fastapi.testclient import TestClient

    from compania.panel.app import crear_app

    cliente = TestClient(crear_app(repo))
    r = cliente.post("/horarios", data={"persona_id": persona.id, "hora": "17:30"}, follow_redirects=False)
    assert r.status_code == 303
    [horario] = repo.horarios(persona.id)
    html = cliente.get("/").text
    assert "17:30" in html and "Quitar" in html
    cliente.post(f"/horarios/{horario.id}/quitar", data={"persona_id": persona.id})
    assert repo.horarios(persona.id) == []
    assert "Sin horario" in cliente.get("/").text

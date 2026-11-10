from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from compania.agente.bot import motor_elegido
from compania.dominio.modelos import Persona
from compania.panel.app import crear_app


class PuenteFalso:
    def __init__(self, conectado=True, qr=None):
        self.conectado = conectado
        self.codigo_qr = qr
        self.llamadas: list[str] = []
        self.grupo: list[str] = []
        self.colgadas = 0
        self.desvinculadas = 0
        self.reinicios = 0

    def estado(self):
        return {"conectado": self.conectado, "en_llamada": False, "grupo": True}

    def qr(self):
        return self.codigo_qr

    def llamar(self, numero):
        self.llamadas.append(numero)
        return 200, {"mensaje": f"Llamando por WhatsApp a {numero}..."}

    def colgar(self):
        self.colgadas += 1
        return 200, {"mensaje": "Llamada colgada"}

    def desvincular(self):
        self.desvinculadas += 1
        return 200, {"mensaje": "Sesión cerrada."}

    def reiniciar(self):
        self.reinicios += 1
        return 200, {"mensaje": "Listo"}

    def enviar_al_grupo(self, texto):
        self.grupo.append(texto)
        return 200, {"enviado": True}


@pytest.fixture
def puente():
    return PuenteFalso()


@pytest.fixture
def cliente(repo, puente):
    return TestClient(crear_app(repo, puente))


def test_pagina_de_control_y_guia(cliente, persona):
    html = cliente.get("/control").text
    assert "Llamar ahora a doña Carmen" in html
    assert "Motor de voz" in html and "Vincular otro celular" in html
    guia = cliente.get("/guia").text
    assert "Antes de grabar" in guia and "Guion sugerido" in guia


def test_llamar_a_la_persona_activa_y_a_otro_numero(cliente, repo, puente, persona):
    repo.actualizar_telefono(persona.id, "525550001111")
    r = cliente.post("/control/llamar", data={}, follow_redirects=False)
    assert r.status_code == 303 and "tipo=ok" in r.headers["location"]
    cliente.post("/control/llamar", data={"numero": "+52 222 000 1234"})
    assert puente.llamadas == ["525550001111", "522220001234"]


def test_llamar_sin_numero_avisa(cliente, puente, persona, monkeypatch):
    monkeypatch.delenv("WHATSAPP_PERSONA", raising=False)
    r = cliente.post("/control/llamar", data={}, follow_redirects=False)
    assert "tipo=error" in r.headers["location"]
    assert puente.llamadas == []


def test_colgar_grupo_y_desvincular(cliente, puente, persona):
    cliente.post("/control/colgar")
    cliente.post("/control/grupo", data={"texto": "Hola familia"})
    sin_confirmar = cliente.post("/control/desvincular", data={}, follow_redirects=False)
    assert "tipo=error" in sin_confirmar.headers["location"]
    cliente.post("/control/desvincular", data={"confirmo": "si"})
    assert (puente.colgadas, puente.grupo, puente.desvinculadas) == (1, ["Hola familia"], 1)


def test_alta_y_cambio_de_perfil_activo(cliente, repo, persona):
    cliente.post(
        "/control/personas",
        data={
            "nombre": "Amada López",
            "trato": "abuelita Amada",
            "telefono": "52 222 555 0000",
            "activar": "si",
        },
    )
    activa = repo.persona_activa()
    assert activa.trato == "abuelita Amada" and activa.telefono == "522225550000"
    assert activa.consentimiento is None
    cliente.post("/control/personas/activa", data={"persona_id": persona.id})
    assert repo.persona_activa().id == persona.id
    cliente.post(f"/control/personas/{activa.id}", data={"consentimiento": "si"})
    assert repo.obtener_persona(activa.id).consentimiento is not None


def test_telefono_invalido(cliente, repo, persona):
    r = cliente.post(f"/control/personas/{persona.id}", data={"telefono": "123"}, follow_redirects=False)
    assert "tipo=error" in r.headers["location"]


def test_motor_se_guarda_si_tiene_llave(cliente, repo, monkeypatch):
    monkeypatch.setenv("MOTOR_VOZ", "gemini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-prueba")
    cliente.post("/control/motor", data={"motor": "openai"})
    assert motor_elegido(repo) == "openai"
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    r = cliente.post("/control/motor", data={"motor": "gemini"}, follow_redirects=False)
    assert "tipo=error" in r.headers["location"]
    assert motor_elegido(repo) == "openai"


def test_sin_eleccion_usa_el_env(repo, monkeypatch):
    monkeypatch.setenv("MOTOR_VOZ", "nova")
    assert motor_elegido(repo) == "nova"


def test_recordatorio_en_minutos_es_de_una_vez(cliente, repo, persona):
    cliente.post("/control/recordatorio", data={"texto": "Tomar agua", "minutos": "3"})
    recordatorio = repo.recordatorios_activos(persona.id)[0]
    assert recordatorio.una_vez and recordatorio.texto == "Tomar agua"
    esperado = datetime.now().replace(second=0, microsecond=0)
    h, m = map(int, recordatorio.hora.split(":"))
    minutos = (h * 60 + m - (esperado.hour * 60 + esperado.minute)) % 1440
    assert minutos in (3, 4)
    cliente.post(f"/control/recordatorios/{recordatorio.id}/quitar")
    assert repo.recordatorios_activos(persona.id) == []


def test_estado_y_qr(repo, persona):
    puente = PuenteFalso(conectado=False, qr="2@prueba,codigo,qr")
    cliente = TestClient(crear_app(repo, puente))
    estado = cliente.get("/control/estado").json()
    assert estado["whatsapp"] == "qr" and estado["hay_qr"]
    svg = cliente.get("/control/qr.svg")
    assert svg.status_code == 200 and svg.text.lstrip().startswith("<svg")
    puente.codigo_qr = None
    assert cliente.get("/control/qr.svg").status_code == 404


def test_rechaza_post_de_otro_sitio(cliente, puente, persona):
    r = cliente.post(
        "/control/llamar", data={"numero": "522220001234"}, headers={"origin": "https://otro.example"}
    )
    assert r.status_code == 403
    assert puente.llamadas == []


def test_sin_persona_lleva_al_registro(repo, puente):
    r = TestClient(crear_app(repo, puente)).get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/control")


def test_persona_activa_en_la_llamada(repo, persona):
    otra = repo.guardar_persona(Persona("Amada", "abuelita Amada"))
    assert repo.persona_activa().id == persona.id
    repo.guardar_ajuste("persona_activa", str(otra.id))
    assert repo.persona_activa().id == otra.id
    repo.guardar_ajuste("persona_activa", "999")
    assert repo.persona_activa().id == persona.id


def test_configuracion_viva_y_reinicio_del_puente(cliente, repo, puente, persona, monkeypatch):
    from compania.infraestructura import configuracion

    monkeypatch.setenv("WHATSAPP_GRUPO", "Familia del env")
    monkeypatch.delenv("NOMBRE_ASISTENTE", raising=False)
    assert configuracion.valor(repo, "whatsapp_grupo") == "Familia del env"
    assert configuracion.origen(repo, "whatsapp_grupo") == ".env"
    cliente.post(
        "/control/configuracion",
        data={"whatsapp_grupo": "Familia López", "whatsapp_prefijo": "", "nombre_asistente": "Rosita"},
    )
    assert configuracion.valor(repo, "whatsapp_grupo") == "Familia López"
    assert configuracion.origen(repo, "whatsapp_grupo") == "panel"
    assert configuracion.valor(repo, "whatsapp_prefijo") == "abue"  # vacío: se usa el .env o el de siempre
    assert configuracion.nombre_asistente(repo) == "Rosita"
    assert puente.reinicios == 1
    html = cliente.get("/control").text
    assert 'value="Familia López"' in html and "(de panel)" in html


def test_cambiar_perfil_o_numero_reinicia_el_puente(cliente, repo, puente, persona):
    cliente.post(f"/control/personas/{persona.id}", data={"telefono": "525550002222"})
    assert puente.reinicios == 1
    cliente.post(f"/control/personas/{persona.id}", data={"consentimiento": "no"})
    assert puente.reinicios == 1


def test_el_bot_le_da_la_configuracion_al_puente(repo, persona, monkeypatch):
    from compania.agente.whatsapp import crear_app as crear_bot

    monkeypatch.delenv("WHATSAPP_GRUPO", raising=False)
    repo.actualizar_telefono(persona.id, "525550003333")
    repo.guardar_ajuste("whatsapp_grupo", "Familia López")
    datos = TestClient(crear_bot(repo)).get("/config").json()
    assert datos == {"grupo": "Familia López", "prefijo": "abue", "persona": "525550003333", "nombre": "Rous"}


def test_aviso_usa_el_grupo_del_panel(repo, monkeypatch):
    from compania.infraestructura.puente_whatsapp import PuenteWhatsApp, SinAviso, aviso_desde_entorno

    monkeypatch.delenv("WHATSAPP_GRUPO", raising=False)
    assert isinstance(aviso_desde_entorno(repo), SinAviso)
    repo.guardar_ajuste("whatsapp_grupo", "Familia López")
    assert isinstance(aviso_desde_entorno(repo), PuenteWhatsApp)


def test_voces_por_motor(cliente, repo, monkeypatch):
    from compania.infraestructura import configuracion

    monkeypatch.delenv("OPENAI_VOICE", raising=False)
    assert configuracion.voz(repo, "openai") == "marin"
    cliente.post("/control/voces", data={"voz_openai": "cedar", "voz_gemini": "", "voz_nova": ""})
    assert configuracion.voz(repo, "openai") == "cedar"
    r = cliente.post("/control/voces", data={"voz_openai": "inventada"}, follow_redirects=False)
    assert "tipo=error" in r.headers["location"]
    assert configuracion.voz(repo, "openai") == "cedar"
    assert '<option value="cedar" selected>cedar</option>' in cliente.get("/control").text

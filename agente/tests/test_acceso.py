import pytest
from fastapi.testclient import TestClient

from compania.panel import acceso
from compania.panel.app import crear_app


class PuenteQuieto:
    def estado(self):
        return {"conectado": True, "en_llamada": False, "grupo": True}

    def qr(self):
        return None


CLAVE = "una frase larga de prueba"
HASH = acceso.hash_de_clave(CLAVE, iteraciones=1000)


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setenv("PANEL_CLAVE_HASH", HASH)
    monkeypatch.setenv("PANEL_PUBLICO", "1")


def test_hash_sin_signo_de_pesos_y_verificable():
    assert "$" not in HASH
    assert acceso.clave_correcta(CLAVE, HASH)
    assert not acceso.clave_correcta("otra", HASH)
    assert not acceso.clave_correcta(CLAVE, "basura")


def test_sin_sesion_redirige_y_con_sesion_entra(repo, persona, con_clave):
    cliente = TestClient(crear_app(repo, PuenteQuieto()), base_url="https://rous.foor.dev")
    r = cliente.get("/control", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/entrar")
    assert cliente.get("/control/estado").status_code == 401
    assert cliente.post("/control/colgar").status_code == 401
    r = cliente.post("/entrar", data={"clave": CLAVE, "siguiente": "/guia"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/guia"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "Guion sugerido" in cliente.get("/guia").text
    cliente.post("/salir")
    assert cliente.get("/control", follow_redirects=False).status_code == 303


def test_bloqueo_tras_intentos_fallidos(repo, persona, con_clave):
    cliente = TestClient(crear_app(repo, PuenteQuieto()))
    for _ in range(acceso.MAX_POR_IP):
        assert cliente.post("/entrar", data={"clave": "mala"}).status_code == 401
    assert cliente.post("/entrar", data={"clave": CLAVE}).status_code == 429


def test_no_redirige_a_otro_sitio(repo, persona, con_clave):
    cliente = TestClient(crear_app(repo, PuenteQuieto()))
    r = cliente.post("/entrar", data={"clave": CLAVE, "siguiente": "//malo.example"}, follow_redirects=False)
    assert r.headers["location"] == "/control"


def test_publico_sin_clave_no_abre(repo, persona, monkeypatch):
    monkeypatch.delenv("PANEL_CLAVE_HASH", raising=False)
    monkeypatch.setenv("PANEL_PUBLICO", "1")
    r = TestClient(crear_app(repo, PuenteQuieto())).get("/control")
    assert r.status_code == 503


def test_sesion_vencida_o_alterada(monkeypatch):
    reloj = [1000.0]
    a = acceso.Acceso(HASH, True, reloj=lambda: reloj[0])
    valor = a.firmar(2000)
    assert a.sesion_valida(valor)
    assert not a.sesion_valida(valor[:-1] + ("0" if valor[-1] != "0" else "1"))
    reloj[0] = 2001
    assert not a.sesion_valida(valor)
    otra = acceso.Acceso(acceso.hash_de_clave("otra clave larga", iteraciones=1000), True)
    reloj[0] = 1000
    assert not otra.sesion_valida(valor)

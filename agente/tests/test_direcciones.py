"""En Docker cada servicio vive en su contenedor: las direcciones salen del entorno."""

from compania.agente.whatsapp import solicitud_llamada
from compania.infraestructura.puente_whatsapp import PuenteLlamadas, PuenteWhatsApp


def test_en_local_todo_va_a_127(monkeypatch):
    monkeypatch.delenv("WHATSAPP_PUENTE_HOST", raising=False)
    assert PuenteWhatsApp(7864).base == "http://127.0.0.1:7864"
    assert PuenteLlamadas(7864).base == "http://127.0.0.1:7864"
    assert solicitud_llamada("522221234567").full_url == "http://127.0.0.1:7864/llamar"


def test_en_docker_se_usa_el_nombre_del_servicio(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PUENTE_HOST", "puente")
    assert PuenteWhatsApp(7864).base == "http://puente:7864"
    assert PuenteLlamadas(7864).base == "http://puente:7864"
    assert solicitud_llamada("522221234567").full_url == "http://puente:7864/llamar"
    assert PuenteWhatsApp(7864, host="otro").base == "http://otro:7864"

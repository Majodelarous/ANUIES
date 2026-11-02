import base64
import urllib.parse

import pytest

from compania.agente.llamar import solicitud_llamada, url_webhook


def test_url_apunta_al_webhook_del_bot():
    assert url_webhook("https://abc.ngrok-free.app/") == "https://abc.ngrok-free.app/"
    assert url_webhook("abc.up.railway.app") == "https://abc.up.railway.app/"


def test_solicitud_lleva_numeros_y_credenciales():
    req = solicitud_llamada("AC123", "tok", "+15550001111", "+522221234567", "abc.ngrok-free.app")
    datos = urllib.parse.parse_qs(req.data.decode())
    assert datos["To"] == ["+522221234567"]
    assert datos["From"] == ["+15550001111"]
    assert datos["Url"] == ["https://abc.ngrok-free.app/"]
    assert req.full_url.endswith("/Accounts/AC123/Calls.json")
    assert req.get_header("Authorization") == "Basic " + base64.b64encode(b"AC123:tok").decode()


def test_rechaza_numero_sin_formato_internacional():
    with pytest.raises(ValueError):
        solicitud_llamada("AC123", "tok", "+15550001111", "2221234567", "abc.ngrok-free.app")

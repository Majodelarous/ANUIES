import base64
import io
from datetime import datetime

import pytest
from conftest import AvisoFalso, ParametrosFalsos
from fastapi.testclient import TestClient
from PIL import Image

from compania.agente.herramientas import Sesion
from compania.agente.imagenes import dibujar, saludo
from compania.agente.imagenes_parecidas import ImagenesParecidas
from compania.dominio.saludos import consulta_del_dia, texto_para_la_persona
from compania.infraestructura.lente import Descripcion, _leer_json, preparar_imagen

MARTES = datetime(2026, 11, 3, 8, 30)


def _jpeg(lado: int = 600) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (lado, lado), "pink").save(salida, "PNG")
    return salida.getvalue()


class DescriptorFalso:
    def __init__(self, descripcion: Descripcion | None):
        self.descripcion = descripcion
        self.vistas: list[str] = []

    async def describir(self, imagen: bytes, mime: str) -> Descripcion | None:
        self.vistas.append(mime)
        return self.descripcion


class BuscadorFalso:
    def __init__(self, cuantas: int = 3):
        self.cuantas = cuantas
        self.consultas: list[str] = []

    async def buscar(self, consulta: str, cuantas: int = 3) -> list[bytes]:
        self.consultas.append(consulta)
        return [_jpeg() for _ in range(min(cuantas, self.cuantas))]


ROSAS = Descripcion("rosas rojas", "imágenes de buenos días con rosas rojas", "rosas y una taza")


def test_saludo_segun_dia_y_hora():
    assert saludo(datetime(2026, 11, 9, 8, 0)) == ("¡Buenos días!", "Feliz inicio de semana")
    assert saludo(datetime(2026, 11, 6, 16, 0)) == ("¡Buenas tardes!", "Feliz viernes")
    assert saludo(datetime(2026, 11, 8, 21, 0)) == ("¡Buenas noches!", "Feliz domingo")


def test_dibuja_una_imagen_cuadrada():
    imagen = Image.open(io.BytesIO(dibujar("Los quiero mucho", "la abue", datetime(2026, 11, 6, 9, 0))))
    assert imagen.format == "JPEG" and imagen.size == (1080, 1080)


def test_consulta_con_sus_temas_y_el_dia():
    assert consulta_del_dia(["rosas"], MARTES) == "buenos días feliz martes rosas frases"
    assert "flores" in consulta_del_dia([], datetime(2026, 11, 3, 20, 0))
    assert "buenas noches" in consulta_del_dia([], datetime(2026, 11, 3, 20, 0))


def test_texto_explica_como_reenviar():
    texto = texto_para_la_persona("abuelita", MARTES, parecidas=True)
    assert texto.startswith("Buenos días, abuelita.") and "Reenviar" in texto and "parecidas" in texto


def test_prepara_imagenes_validas_y_descarta_chicas():
    lista = preparar_imagen(_jpeg(2000))
    assert lista[:2] == b"\xff\xd8"
    assert max(Image.open(io.BytesIO(lista)).size) == 1280
    assert preparar_imagen(_jpeg(100)) is None
    assert preparar_imagen(b"<html>no es imagen</html>") is None


def test_lee_json_aunque_venga_en_bloque_de_codigo():
    assert _leer_json('```json\n{"tema": "café"}\n```') == {"tema": "café"}


async def test_aprende_lo_que_le_gusta_y_busca_parecidas(repo, persona):
    buscador = BuscadorFalso()
    lente = ImagenesParecidas(repo, DescriptorFalso(ROSAS), buscador)
    resultado = await lente.parecidas(persona.id, _jpeg(), "image/jpeg")
    assert len(resultado.imagenes) == 3
    assert buscador.consultas == ["imágenes de buenos días con rosas rojas"]
    assert repo.temas_favoritos(persona.id) == ["rosas rojas"]

    await lente.aprender(persona.id, _jpeg(), "image/jpeg")
    await ImagenesParecidas(repo, DescriptorFalso(Descripcion("café", "café")), buscador).aprender(
        persona.id, _jpeg(), "image/png"
    )
    assert repo.temas_favoritos(persona.id) == ["rosas rojas", "café"]

    await lente.del_dia(persona.id, MARTES)
    assert buscador.consultas[-1] == "buenos días feliz martes rosas rojas frases"


async def test_si_no_entiende_la_imagen_no_busca(repo, persona):
    buscador = BuscadorFalso()
    resultado = await ImagenesParecidas(repo, DescriptorFalso(None), buscador).parecidas(
        persona.id, _jpeg(), "image/jpeg"
    )
    assert resultado.imagenes == [] and buscador.consultas == []


async def test_en_la_llamada_le_manda_imagenes_a_su_whatsapp(repo, persona, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PERSONA", "525550001111")
    aviso = AvisoFalso()
    lente = ImagenesParecidas(repo, DescriptorFalso(None), BuscadorFalso())
    sesion = Sesion(repo, persona.id, aviso=aviso, trato="abuelita", imagenes=lente)
    p = ParametrosFalsos({"tema": "La Virgen"})
    await sesion.buscar_imagenes_para_compartir(p)
    assert p.resultado["enviado"] is True and p.resultado["cuantas"] == 3
    assert "la virgen" in lente.buscador.consultas[0]
    # Sin teléfono registrado se usa WHATSAPP_PERSONA: le llegan a ella, no al grupo
    assert aviso.destinos == ["525550001111"] * 3
    assert "Reenviar" in aviso.imagenes[0][1] and aviso.imagenes[1][1] == ""
    assert "imágenes de saludo a su WhatsApp" in sesion.resumen(2)

    otra = ParametrosFalsos({})
    await sesion.buscar_imagenes_para_compartir(otra)
    assert otra.resultado["enviado"] is False and len(aviso.imagenes) == 3


async def test_sin_resultados_manda_una_imagen_dibujada(repo, persona):
    aviso = AvisoFalso()
    lente = ImagenesParecidas(repo, DescriptorFalso(None), BuscadorFalso(cuantas=0))
    sesion = Sesion(repo, persona.id, aviso=aviso, trato="abuelita", imagenes=lente)
    p = ParametrosFalsos({})
    await sesion.buscar_imagenes_para_compartir(p)
    assert p.resultado["cuantas"] == 1 and aviso.imagenes[0][0][:2] == b"\xff\xd8"


@pytest.fixture
def cliente(repo, persona, tmp_path):
    from compania.agente.whatsapp import crear_app

    lente = ImagenesParecidas(repo, DescriptorFalso(ROSAS), BuscadorFalso(cuantas=2))
    return TestClient(crear_app(repo, tmp_path / "audios", imagenes=lente))


def test_endpoint_devuelve_imagenes_parecidas(cliente, repo, persona):
    imagen = base64.b64encode(_jpeg()).decode()
    respuesta = cliente.post("/imagenes/parecidas", json={"imagen_b64": imagen, "mime": "image/png"})
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["tema"] == "rosas rojas" and len(datos["imagenes_b64"]) == 2
    assert "Reenviar" in datos["texto"]

    solo = cliente.post("/imagenes/parecidas", json={"imagen_b64": imagen, "buscar": False}).json()
    assert solo["imagenes_b64"] == []
    assert repo.temas_favoritos(persona.id) == ["rosas rojas"]

    assert cliente.post("/imagenes/parecidas", json={"imagen_b64": "no-es-base64!"}).status_code == 422

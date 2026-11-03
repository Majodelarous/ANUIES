import io
from datetime import datetime

from conftest import AvisoFalso, ParametrosFalsos
from PIL import Image

from compania.agente.herramientas import Sesion
from compania.agente.imagenes import dibujar, saludo


def test_saludo_segun_dia_y_hora():
    assert saludo(datetime(2026, 11, 9, 8, 0)) == ("¡Buenos días!", "Feliz inicio de semana")
    assert saludo(datetime(2026, 11, 6, 16, 0)) == ("¡Buenas tardes!", "Feliz viernes")
    assert saludo(datetime(2026, 11, 8, 21, 0)) == ("¡Buenas noches!", "Feliz domingo")


def test_dibuja_una_imagen_cuadrada():
    imagen = Image.open(io.BytesIO(dibujar("Los quiero mucho", "la abue", datetime(2026, 11, 6, 9, 0))))
    assert imagen.format == "JPEG" and imagen.size == (1080, 1080)


async def test_manda_la_imagen_una_vez(repo, persona):
    aviso = AvisoFalso()
    sesion = Sesion(repo, persona.id, aviso=aviso, trato="abuelita")
    p = ParametrosFalsos({"mensaje": "Que Dios los bendiga", "firma": "su abuelita Amada"})
    await sesion.mandar_imagen_buenos_dias(p)
    assert p.resultado == {"enviado": True}
    [(imagen, texto)] = aviso.imagenes
    assert imagen[:2] == b"\xff\xd8" and texto == "De parte de su abuelita Amada, con cariño."
    assert "Les mandó una imagen de saludo." in sesion.resumen(2)

    otra = ParametrosFalsos({"mensaje": "Otra"})
    await sesion.mandar_imagen_buenos_dias(otra)
    assert otra.resultado["enviado"] is False
    assert len(aviso.imagenes) == 1

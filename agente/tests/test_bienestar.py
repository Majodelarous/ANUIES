from datetime import datetime, timedelta

import pytest

from compania.dominio import bienestar
from compania.dominio.modelos import RespuestaBienestar, Semaforo

AHORA = datetime(2026, 11, 2, 12, 0)


def r(pregunta_id: str, respuesta: str, dias_atras: int = 0) -> RespuestaBienestar:
    return RespuestaBienestar(1, pregunta_id, respuesta, AHORA - timedelta(days=dias_atras))


def test_gds15_tiene_15_preguntas_y_5_invertidas():
    assert len(bienestar.PREGUNTAS_GDS15) == 15
    invertidas = {p.id for p in bienestar.PREGUNTAS_GDS15 if p.respuesta_que_suma == "no"}
    assert invertidas == {"gds01", "gds05", "gds07", "gds11", "gds13"}


@pytest.mark.parametrize(
    ("pregunta", "respuesta", "puntos"),
    [("gds01", "no", 1), ("gds01", "sí", 0), ("gds03", "Si", 1), ("gds03", "no", 0)],
)
def test_puntua(pregunta, respuesta, puntos):
    assert bienestar.puntua(pregunta, respuesta) == puntos


def test_respuesta_no_reconocida():
    with pytest.raises(ValueError):
        bienestar.normalizar_respuesta("quién sabe")


def test_insuficiente_con_pocas_respuestas():
    senal = bienestar.calcular_senal([r("gds03", "si"), r("gds04", "si")], ahora=AHORA)
    assert senal.semaforo == Semaforo.INSUFICIENTE
    assert senal.respondidas == 2


def test_verde_amarillo_rojo():
    base = [r("gds01", "si"), r("gds02", "no"), r("gds03", "no"), r("gds04", "no"), r("gds05", "si")]
    assert bienestar.calcular_senal(base, ahora=AHORA).semaforo == Semaforo.VERDE

    amarillo = base[:3] + [r("gds04", "si"), r("gds05", "no")]
    assert bienestar.calcular_senal(amarillo, ahora=AHORA).semaforo == Semaforo.AMARILLO

    rojo = [r("gds01", "no"), r("gds02", "si"), r("gds03", "si"), r("gds04", "si"), r("gds05", "si")]
    assert bienestar.calcular_senal(rojo, ahora=AHORA).semaforo == Semaforo.ROJO


def test_crisis_pone_rojo():
    senal = bienestar.calcular_senal([], ahora=AHORA, hubo_crisis=True)
    assert senal.semaforo == Semaforo.ROJO
    assert "No es un diagnóstico" in senal.nota


def test_usa_la_respuesta_mas_reciente_y_respeta_ventana():
    respuestas = [
        r("gds03", "si", dias_atras=3),
        r("gds03", "no", dias_atras=1),
        r("gds04", "si", dias_atras=30),
    ]
    senal = bienestar.calcular_senal(respuestas, ahora=AHORA)
    assert senal.respondidas == 1
    assert senal.puntos == 0


def test_elegir_preguntas_evita_las_recientes():
    respuestas = [r("gds01", "si"), r("gds02", "no")]
    elegidas = bienestar.elegir_preguntas_del_dia(respuestas, cantidad=2, ahora=AHORA)
    assert [p.id for p in elegidas] == ["gds03", "gds04"]

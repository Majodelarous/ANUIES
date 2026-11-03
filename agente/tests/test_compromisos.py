from datetime import datetime

import pytest

from compania.dominio.compromisos import extraer_compromiso

MEDIODIA = datetime(2026, 11, 5, 12, 0)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Abue, salgo a las 5, a esa hora te marco", ("2026-11-05", "17:00")),
        ("Abue, a las 6 y media te llamo", ("2026-11-05", "18:30")),
        ("Abue, te marco a las 8 de la noche", ("2026-11-05", "20:00")),
        ("Abue, hoy te hablo a las 19:15", ("2026-11-05", "19:15")),
        ("Abue, te llamo a las 7:30 pm", ("2026-11-05", "19:30")),
        ("Abue, mañana te marco a las 10 de la mañana", ("2026-11-06", "10:00")),
        ("Abuelita, a la 1 te marco", ("2026-11-05", "13:00")),
    ],
)
def test_reconoce_la_hora(texto, esperado):
    assert extraer_compromiso(texto, MEDIODIA) == esperado


def test_hora_de_la_manana_que_ya_paso_se_entiende_por_la_noche():
    assert extraer_compromiso("Abue, a las 9 te llamo", MEDIODIA) == ("2026-11-05", "21:00")


def test_si_ya_paso_es_para_manana():
    tarde = datetime(2026, 11, 5, 22, 0)
    assert extraer_compromiso("Abue, a las 5 te marco", tarde) == ("2026-11-06", "17:00")


@pytest.mark.parametrize(
    "texto",
    [
        "Abue, salgo a las 5",  # no dice que va a llamar
        "Abue, te quiero mucho",
        "Abue, te marco al rato",  # no dice hora
        "Abue, te marco a las 99",
    ],
)
def test_no_es_compromiso(texto):
    assert extraer_compromiso(texto, MEDIODIA) is None

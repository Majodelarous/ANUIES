import pytest

from compania.agente.asterisk import comando_originar


def test_comando_originar():
    assert comando_originar("abue") == [
        "docker",
        "exec",
        "compania-asterisk",
        "asterisk",
        "-rx",
        "channel originate PJSIP/abue extension compania@salida",
    ]


@pytest.mark.parametrize("cuenta", ["Abue", "abue; rm -rf /", "", "a" * 40])
def test_rechaza_cuentas_invalidas(cuenta):
    with pytest.raises(ValueError):
        comando_originar(cuenta)

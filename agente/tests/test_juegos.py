from compania.dominio.juegos import JUEGOS, TipoJuego, obtener_juego


def test_hay_tres_tipos():
    assert {j.tipo for j in JUEGOS} == set(TipoJuego)


def test_ids_unicos():
    assert len({j.id for j in JUEGOS}) == len(JUEGOS)


def test_no_repite_juegos_usados():
    primero = obtener_juego(TipoJuego.REFRAN)
    segundo = obtener_juego(TipoJuego.REFRAN, excluir={primero.id})
    assert primero.id != segundo.id


def test_sin_tipo_devuelve_cualquiera_y_agota():
    usados = {j.id for j in JUEGOS}
    assert obtener_juego(None, usados) is None
    assert obtener_juego("adivinanza").tipo == TipoJuego.ADIVINANZA

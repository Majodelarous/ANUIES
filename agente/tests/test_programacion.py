from datetime import datetime

from compania.dominio.modelos import Horario, Recordatorio
from compania.dominio.programacion import tareas_pendientes

DIA = datetime(2026, 11, 5)


def a(h, m):
    return DIA.replace(hour=h, minute=m)


def test_llamada_diaria_a_su_hora_y_solo_una_vez():
    horarios = [Horario(1, "17:30", id=1)]
    assert tareas_pendientes(a(17, 29), horarios, [], set()) == []
    [tarea] = tareas_pendientes(a(17, 31), horarios, [], set())
    assert tarea.tipo == "llamada" and tarea.motivo == "programada"
    assert tareas_pendientes(a(17, 32), horarios, [], {tarea.clave}) == []


def test_fuera_de_la_ventana_ya_no_se_lanza():
    assert tareas_pendientes(a(17, 45), [Horario(1, "17:30", id=1)], [], set()) == []


def test_recordatorio_como_llamada_corta():
    [tarea] = tareas_pendientes(a(14, 0), [], [Recordatorio(1, "Tomar la pastilla", "14:00", id=9)], set())
    assert tarea.tipo == "recordatorio"
    assert tarea.motivo == "recordatorio:9"
    assert tarea.texto == "Tomar la pastilla"


def test_recordatorio_cerca_de_una_llamada_diaria_no_genera_otra_llamada():
    horarios = [Horario(1, "14:15", id=1)]
    recordatorios = [Recordatorio(1, "Tomar la pastilla", "14:00", id=9)]
    assert tareas_pendientes(a(14, 1), horarios, recordatorios, set()) == []


def test_horario_inactivo_no_cuenta():
    assert tareas_pendientes(a(17, 30), [Horario(1, "17:30", activo=False, id=1)], [], set()) == []


def test_la_clave_cambia_cada_dia():
    [hoy] = tareas_pendientes(a(9, 0), [Horario(1, "09:00", id=1)], [], set())
    [manana] = tareas_pendientes(a(9, 0).replace(day=6), [Horario(1, "09:00", id=1)], [], {hoy.clave})
    assert hoy.clave != manana.clave


def test_llamada_diaria_anterior_no_tapa_un_recordatorio_posterior():
    # En la llamada de las 19:05 pidió "recuérdame en 5 minutos": debe sonar a las 19:10
    horarios = [Horario(1, "19:05", id=1)]
    tareas = tareas_pendientes(a(19, 10), horarios, [Recordatorio(1, "Apagar la luz", "19:10", id=3)], set())
    assert [t.recordatorio_id for t in tareas if t.tipo == "recordatorio"] == [3]


def test_recordatorio_de_una_vez_siempre_tiene_su_llamada():
    horarios = [Horario(1, "14:10", id=1)]
    una_vez = Recordatorio(1, "Sacar la ropa", "14:00", id=4, una_vez=True)
    [tarea] = tareas_pendientes(a(14, 0), horarios, [una_vez], set())
    assert tarea.recordatorio_id == 4

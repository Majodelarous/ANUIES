from compania.dominio.modelos import Alerta, MensajeFamiliar, NivelAlerta, Recuerdo


def test_recuerdos_por_tema_y_recientes(repo, persona):
    repo.guardar_recuerdo(Recuerdo(persona.id, "infancia", "Creció en Atlixco"))
    repo.guardar_recuerdo(Recuerdo(persona.id, "cocina", "El mole de su mamá", True))
    assert [r.tema for r in repo.buscar_recuerdos(persona.id)] == ["cocina", "infancia"]
    encontrados = repo.buscar_recuerdos(persona.id, "Atlixco")
    assert len(encontrados) == 1 and not encontrados[0].compartir_con_familia


def test_mensajes_pendientes_y_entrega(repo, persona):
    mensaje = repo.guardar_mensaje(MensajeFamiliar(persona.id, "su nieta", "Te quiero"))
    assert len(repo.mensajes_pendientes(persona.id)) == 1
    assert repo.marcar_entregado(mensaje.id, persona.id)
    assert repo.mensajes_pendientes(persona.id) == []
    assert not repo.marcar_entregado(mensaje.id, persona.id + 1)


def test_llamadas(repo, persona):
    llamada = repo.iniciar_llamada(persona.id, "web")
    assert repo.es_primera_llamada(persona.id)
    repo.terminar_llamada(llamada.id)
    repo.iniciar_llamada(persona.id, "telefono")
    assert not repo.es_primera_llamada(persona.id)
    assert repo.llamadas(persona.id)[-1].fin is not None


def test_alertas(repo, persona):
    repo.guardar_alerta(Alerta(persona.id, NivelAlerta.CRISIS, "Dijo que ya no quiere vivir"))
    assert repo.alertas(persona.id)[0].nivel == NivelAlerta.CRISIS


def test_horarios_y_ejecuciones(repo, persona):
    from compania.dominio.modelos import Horario

    horario = repo.guardar_horario(Horario(persona.id, "17:30"))
    assert [h.hora for h in repo.horarios(persona.id)] == ["17:30"]
    assert repo.desactivar_horario(horario.id, persona.id)
    assert repo.horarios() == []

    repo.marcar_ejecutada("2026-11-05 17:30 llamada 1")
    repo.marcar_ejecutada("2026-11-05 17:30 llamada 1")  # no se duplica
    assert repo.ejecutadas_desde("2026-11-05") == {"2026-11-05 17:30 llamada 1"}
    assert repo.ejecutadas_desde("2026-11-06") == set()


def test_persona_con_telefono(repo):
    from compania.dominio.modelos import Persona

    persona = repo.guardar_persona(Persona("Amada", "abuelita", telefono="522221234567"))
    assert repo.obtener_persona(persona.id).telefono == "522221234567"
    assert [p.nombre for p in repo.personas()] == ["Amada"]


def test_actualizar_telefono(repo, persona):
    assert repo.actualizar_telefono(persona.id, "522221234567")
    assert repo.obtener_persona(persona.id).telefono == "522221234567"
    assert not repo.actualizar_telefono(999, "522221234567")

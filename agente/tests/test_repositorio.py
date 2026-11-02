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

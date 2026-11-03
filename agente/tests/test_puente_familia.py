from conftest import AvisoFalso, ParametrosFalsos

from compania.agente.bot import recordatorio_del_motivo
from compania.agente.herramientas import Sesion
from compania.dominio.modelos import Persona, Recordatorio


async def test_pedir_que_le_llamen_avisa_al_grupo_y_deja_seguimiento(repo, persona):
    aviso = AvisoFalso()
    sesion = Sesion(repo, persona.id, aviso=aviso, trato="abuelita")
    p = ParametrosFalsos({"para": "Elena", "motivo": "quiere contarle de la receta del mole"})
    await sesion.pedir_que_le_llamen(p)

    assert aviso.enviados == [
        "Hola, Elena. Abuelita tiene ganas de platicar contigo. Quiere contarle de la receta del mole. "
        "¿Le puedes marcar hoy cuando tengas un momento?"
    ]
    [seguimiento] = repo.seguimientos_abiertos(persona.id)
    assert seguimiento.para == "Elena"
    assert p.resultado["seguimiento_id"] == seguimiento.id
    assert "Tiene ganas de platicar con Elena; ya se lo avisé." in sesion.resumen(3)


async def test_en_la_siguiente_llamada_se_cierra_el_seguimiento(repo, persona):
    await Sesion(repo, persona.id, aviso=AvisoFalso()).pedir_que_le_llamen(
        ParametrosFalsos({"para": "Elena"})
    )
    [seguimiento] = repo.seguimientos_abiertos(persona.id)

    sesion = Sesion(repo, persona.id, trato="abuelita")
    p = ParametrosFalsos({"seguimiento_id": seguimiento.id, "resultado": "sí le marcó y platicaron una hora"})
    await sesion.cerrar_seguimiento(p)

    assert p.resultado == {"cerrado": True}
    assert repo.seguimientos_abiertos(persona.id) == []
    assert "Le pregunté cómo le fue con Elena: Sí le marcó y platicaron una hora." in sesion.resumen(5)


async def test_sin_permiso_no_guarda_recuerdos_ni_bienestar(repo):
    persona = repo.guardar_persona(Persona("Amada", "abuelita"))
    sesion = Sesion(repo, persona.id)

    r = ParametrosFalsos({"tema": "infancia", "contenido": "Creció en Atlixco"})
    await sesion.guardar_recuerdo(r)
    assert r.resultado["error"] == "sin permiso"
    assert repo.buscar_recuerdos(persona.id) == []

    b = ParametrosFalsos({"pregunta_id": "gds05", "respuesta": "si"})
    await sesion.registrar_respuesta_bienestar(b)
    assert b.resultado["error"] == "sin permiso"


async def test_con_permiso_ya_guarda(repo):
    persona = repo.guardar_persona(Persona("Amada", "abuelita"))
    sesion = Sesion(repo, persona.id)
    await sesion.registrar_consentimiento(ParametrosFalsos({"acepta": True}))
    assert repo.obtener_persona(persona.id).consentimiento is not None

    r = ParametrosFalsos({"tema": "infancia", "contenido": "Creció en Atlixco"})
    await sesion.guardar_recuerdo(r)
    assert r.resultado["guardado"]


def test_motivo_de_recordatorio(repo, persona):
    recordatorio = repo.guardar_recordatorio(Recordatorio(persona.id, "Tomar la pastilla", "14:00"))
    assert recordatorio_del_motivo(repo, f"recordatorio:{recordatorio.id}", persona.id) == "Tomar la pastilla"
    assert recordatorio_del_motivo(repo, "programada", persona.id) == ""
    assert recordatorio_del_motivo(repo, "recordatorio:x", persona.id) == ""
    assert recordatorio_del_motivo(repo, f"recordatorio:{recordatorio.id}", persona.id + 1) == ""


def test_resumen_de_llamada_de_recordatorio(repo, persona):
    texto = Sesion(repo, persona.id, trato="abuelita", motivo="Tomar la pastilla").resumen(1)
    assert texto.startswith(
        "Hola, familia, soy Rous. Le llamé a abuelita para recordarle: Tomar la pastilla."
    )

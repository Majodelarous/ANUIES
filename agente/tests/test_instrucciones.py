from compania.agente.instrucciones import construir_instrucciones
from compania.dominio.bienestar import PREGUNTAS
from compania.dominio.modelos import MensajeFamiliar, Persona, Recordatorio, Recuerdo


def test_instrucciones_incluyen_contexto_y_reglas():
    persona = Persona("Carmen", "doña Carmen", id=1)
    texto = construir_instrucciones(
        persona,
        primera_llamada=True,
        recuerdos=[Recuerdo(1, "cocina", "El mole de su mamá")],
        recordatorios=[Recordatorio(1, "Tomar la pastilla", "14:00")],
        mensajes=[MensajeFamiliar(1, "su nieta", "Te quiero", id=7)],
        preguntas_bienestar=[PREGUNTAS["gds05"]],
    )
    assert "doña Carmen" in texto
    assert "primera llamada" in texto
    assert "El mole de su mamá" in texto
    assert "id 7" in texto
    assert "14:00" in texto
    assert "gds05" in texto
    assert "800 911 2000" in texto
    assert "No diagnosticas" in texto


def test_sin_contexto_no_agrega_secciones_vacias():
    texto = construir_instrucciones(Persona("Carmen", "doña Carmen", id=1), primera_llamada=False)
    assert "Mensajes de la familia" not in texto
    assert "primera llamada" not in texto

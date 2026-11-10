from conftest import AvisoFalso, ParametrosFalsos

from compania.agente.herramientas import Sesion


class GrabadoraFalsa:
    frecuencia = 16000

    def __init__(self, resultado):
        self.resultado = resultado

    async def grabar(self):
        return self.resultado


async def test_graba_y_manda_la_nota_de_voz(repo, persona, monkeypatch):
    from compania.agente import herramientas

    async def nada(_):
        return None

    monkeypatch.setattr(herramientas.asyncio, "sleep", nada)
    aviso = AvisoFalso()
    sesion = Sesion(
        repo, persona.id, aviso=aviso, trato="abuelita", grabadora=GrabadoraFalsa((b"RIFFwav", 16000))
    )
    p = ParametrosFalsos({"para": "Majo"})
    await sesion.grabar_mensaje_de_voz(p)

    assert p.resultado == {"enviado": True}
    assert aviso.audios == [(b"RIFFwav", "Abuelita le manda esta nota de voz a Majo.")]
    assert len(p.llm.frames) == 1  # el tonito
    assert "Les mandó una nota de voz a Majo." in sesion.resumen(2)


async def test_si_no_habla_ofrece_intentar_de_nuevo(repo, persona, monkeypatch):
    from compania.agente import herramientas

    async def nada(_):
        return None

    monkeypatch.setattr(herramientas.asyncio, "sleep", nada)
    aviso = AvisoFalso()
    p = ParametrosFalsos({"para": "Majo"})
    await Sesion(repo, persona.id, aviso=aviso, grabadora=GrabadoraFalsa(None)).grabar_mensaje_de_voz(p)
    assert p.resultado["enviado"] is False
    assert "otra vez" in p.resultado["que_decir"]
    assert aviso.audios == []


async def test_sin_grabadora_pide_texto(repo, persona):
    p = ParametrosFalsos({"para": "Majo"})
    await Sesion(repo, persona.id).grabar_mensaje_de_voz(p)
    assert "enviar_mensaje_a_familia" in p.resultado["que_hacer"]


async def test_con_nova_espera_a_que_suene_el_tonito(repo, persona, monkeypatch):
    from compania.agente import herramientas

    async def nada(_):
        return None

    monkeypatch.setattr(herramientas.asyncio, "sleep", nada)
    esperas = []

    class GrabadoraQueEspera(GrabadoraFalsa):
        paradas = 3

        async def esperar_fin_de_audio(self, desde, max_s=12.0):
            esperas.append(desde)
            return 1.5

    sesion = Sesion(
        repo,
        persona.id,
        aviso=AvisoFalso(),
        grabadora=GrabadoraQueEspera((b"RIFFwav", 16000)),
        esperar_fin_del_audio=True,
    )
    await sesion.grabar_mensaje_de_voz(ParametrosFalsos({"para": "Majo"}))
    assert esperas == [3]
    # Con Gemini (por omisión) no se espera
    esperas.clear()
    await Sesion(
        repo, persona.id, aviso=AvisoFalso(), grabadora=GrabadoraQueEspera((b"RIFFwav", 16000))
    ).grabar_mensaje_de_voz(ParametrosFalsos({"para": "Majo"}))
    assert esperas == []

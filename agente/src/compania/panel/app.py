"""Panel familiar: señal de bienestar, llamadas, recordatorios, mensajes, recuerdos y alertas.

Uso::

    uv run compania-panel            # http://localhost:7861
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from compania.dominio import bienestar
from compania.dominio.modelos import Horario, MensajeFamiliar, NivelAlerta, Recordatorio, Semaforo
from compania.infraestructura.repositorio import Repositorio

CSS = (Path(__file__).parent / "estilos.css").read_text(encoding="utf-8")

TEXTO_SEMAFORO = {
    Semaforo.VERDE: ("Estable", "Las respuestas recientes no muestran señales de alerta."),
    Semaforo.AMARILLO: (
        "Poner atención",
        "Algunas respuestas sugieren desánimo. Buen momento para llamarle o visitarle.",
    ),
    Semaforo.ROJO: (
        "Acercarse pronto",
        "Varias respuestas o una alerta indican que necesita compañía y, quizá, apoyo profesional.",
    ),
    Semaforo.INSUFICIENTE: (
        "Aún sin datos",
        "Se necesitan al menos 5 respuestas en 14 días para mostrar una tendencia.",
    ),
}

NOMBRE_CANAL = {
    "telefono": "Teléfono",
    "app": "Llamada por app",
    "whatsapp": "WhatsApp",
    "web": "Navegador",
}

NOMBRE_NIVEL = {
    NivelAlerta.INFORMATIVA: "Informativa",
    NivelAlerta.ATENCION: "Atención",
    NivelAlerta.CRISIS: "Crisis",
}


def _fecha_corta(valor: datetime) -> str:
    meses = "ene feb mar abr may jun jul ago sep oct nov dic".split()
    return f"{valor.day} {meses[valor.month - 1]}, {valor:%H:%M}"


def _duracion(inicio: datetime, fin: datetime | None) -> str:
    if fin is None:
        return "En curso o sin cerrar"
    minutos = max(1, round((fin - inicio).total_seconds() / 60))
    return f"{minutos} min"


def _linea_de_llamadas(dias_con_llamada: set[date], hoy: date) -> str:
    """SVG: los últimos 14 días como puntos sobre una línea; relleno si hubo llamada."""
    ancho, alto, margen = 560, 48, 16
    paso = (ancho - 2 * margen) / 13
    partes = [
        f'<svg class="linea" viewBox="0 0 {ancho} {alto}" role="img" '
        'aria-label="Llamadas de los últimos 14 días">',
        f'<line x1="{margen}" y1="24" x2="{ancho - margen}" y2="24" />',
    ]
    for i in range(14):
        dia = hoy - timedelta(days=13 - i)
        x = margen + i * paso
        hubo = dia in dias_con_llamada
        clase = "punto lleno" if hubo else "punto"
        titulo = f"{dia:%d/%m}: {'con llamada' if hubo else 'sin llamada'}"
        partes.append(f'<circle class="{clase}" cx="{x:.1f}" cy="24" r="7"><title>{titulo}</title></circle>')
    partes.append("</svg>")
    inicio = hoy - timedelta(days=13)
    partes.append(f'<div class="ejes"><span>{inicio:%d/%m}</span><span>Hoy</span></div>')
    return '<div class="llamadas-14">' + "".join(partes) + "</div>"


def crear_app(repo: Repositorio | None = None) -> FastAPI:
    load_dotenv(override=True)
    repo = repo or Repositorio(os.getenv("RUTA_DB", "compania.db"))
    app = FastAPI(title="Panel familiar")

    def persona_o_404(persona_id: int | None):
        persona = repo.obtener_persona(persona_id) if persona_id else repo.primera_persona()
        if persona is None or persona.id is None:
            raise HTTPException(404, "No hay persona registrada. Ejecuta: uv run compania-semilla --help")
        return persona

    def resumen(persona_id: int | None) -> dict:
        persona = persona_o_404(persona_id)
        ahora = datetime.now()
        alertas = repo.alertas(persona.id, ahora - timedelta(days=30))
        crisis = any(
            a.nivel == NivelAlerta.CRISIS and a.creado >= ahora - timedelta(days=bienestar.DIAS_VENTANA)
            for a in alertas
        )
        senal = bienestar.calcular_senal(repo.respuestas(persona.id), ahora=ahora, hubo_crisis=crisis)
        return {
            "persona": persona,
            "senal": senal,
            "alertas": list(reversed(alertas)),
            "llamadas": repo.llamadas(persona.id, limite=30),
            "recordatorios": repo.recordatorios_activos(persona.id),
            "horarios": repo.horarios(persona.id),
            "mensajes": repo.mensajes_pendientes(persona.id),
            "recuerdos": [r for r in repo.buscar_recuerdos(persona.id, limite=50) if r.compartir_con_familia],
        }

    @app.get("/api/resumen")
    def api_resumen(persona_id: int | None = None) -> dict:
        datos = resumen(persona_id)
        s = datos["senal"]
        return {
            "persona": {"id": datos["persona"].id, "trato": datos["persona"].trato},
            "senal": {
                "semaforo": s.semaforo.value,
                "respondidas": s.respondidas,
                "proporcion": s.proporcion,
                "hubo_crisis": s.hubo_crisis,
                "nota": s.nota,
            },
            "llamadas": len(datos["llamadas"]),
            "alertas": [{"nivel": a.nivel.value, "motivo": a.motivo} for a in datos["alertas"]],
            "mensajes_pendientes": len(datos["mensajes"]),
            "recordatorios": [{"hora": r.hora, "texto": r.texto} for r in datos["recordatorios"]],
            "recuerdos_compartidos": [{"tema": r.tema, "contenido": r.contenido} for r in datos["recuerdos"]],
        }

    @app.get("/", response_class=HTMLResponse)
    def inicio(persona_id: int | None = None) -> str:
        return pagina(resumen(persona_id))

    @app.post("/recordatorios")
    def nuevo_recordatorio(persona_id: int = Form(...), texto: str = Form(...), hora: str = Form(...)):
        persona_o_404(persona_id)
        if len(hora) != 5 or hora[2] != ":":
            raise HTTPException(422, "La hora debe tener formato HH:MM")
        repo.guardar_recordatorio(Recordatorio(persona_id, texto.strip(), hora, "familia"))
        return RedirectResponse(f"/?persona_id={persona_id}#cuidado", status_code=303)

    @app.post("/horarios")
    def nuevo_horario(persona_id: int = Form(...), hora: str = Form(...)):
        persona_o_404(persona_id)
        if len(hora) != 5 or hora[2] != ":":
            raise HTTPException(422, "La hora debe tener formato HH:MM")
        repo.guardar_horario(Horario(persona_id, hora))
        return RedirectResponse(f"/?persona_id={persona_id}#llamadas", status_code=303)

    @app.post("/horarios/{horario_id}/quitar")
    def quitar_horario(horario_id: int, persona_id: int = Form(...)):
        persona_o_404(persona_id)
        repo.desactivar_horario(horario_id, persona_id)
        return RedirectResponse(f"/?persona_id={persona_id}#llamadas", status_code=303)

    @app.post("/mensajes")
    def nuevo_mensaje(persona_id: int = Form(...), de: str = Form(...), texto: str = Form(...)):
        persona_o_404(persona_id)
        repo.guardar_mensaje(MensajeFamiliar(persona_id, de.strip(), texto.strip()))
        return RedirectResponse(f"/?persona_id={persona_id}#cuidado", status_code=303)

    return app


def pagina(datos: dict) -> str:
    persona = datos["persona"]
    senal = datos["senal"]
    titulo, explicacion = TEXTO_SEMAFORO[senal.semaforo]
    hoy = date.today()
    dias = {ll.inicio.date() for ll in datos["llamadas"]}
    e = escape

    filas_llamadas = (
        "".join(
            f"<tr><td>{_fecha_corta(ll.inicio)}</td><td>{NOMBRE_CANAL.get(ll.canal, ll.canal)}</td>"
            f'<td class="num">{_duracion(ll.inicio, ll.fin)}</td></tr>'
            for ll in datos["llamadas"][:10]
        )
        or '<tr><td colspan="3" class="vacio">Todavía no hay llamadas.</td></tr>'
    )

    alertas = (
        "".join(
            f'<li class="alerta {a.nivel.value}"><strong>{NOMBRE_NIVEL[a.nivel]}</strong> '
            f"<span>{_fecha_corta(a.creado)}</span><p>{e(a.motivo)}</p></li>"
            for a in datos["alertas"][:5]
        )
        or '<li class="vacio">Sin alertas en los últimos 30 días.</li>'
    )

    recordatorios = (
        "".join(f'<li><span class="num">{e(r.hora)}</span> {e(r.texto)}</li>' for r in datos["recordatorios"])
        or '<li class="vacio">Sin recordatorios.</li>'
    )

    mensajes = "".join(
        f"<li><strong>{e(m.de)}:</strong> {e(m.texto) if m.texto else ''}"
        f"{' <span class="etiqueta">Nota de voz</span>' if m.audio else ''}</li>"
        for m in datos["mensajes"]
    ) or ('<li class="vacio">No hay mensajes por entregar.</li>')

    recuerdos = (
        "".join(f"<li><strong>{e(r.tema)}</strong><p>{e(r.contenido)}</p></li>" for r in datos["recuerdos"])
        or '<li class="vacio">Aún no hay recuerdos que haya querido compartir.</li>'
    )

    pid = persona.id
    horarios = (
        "".join(
            f'<li><span class="num">{e(h.hora)}</span> todos los días '
            f'<form class="en-linea" method="post" action="/horarios/{h.id}/quitar">'
            f'<input type="hidden" name="persona_id" value="{pid}">'
            f'<button type="submit" class="secundario">Quitar</button></form></li>'
            for h in datos["horarios"]
        )
        or '<li class="vacio">Sin horario: las llamadas se hacen a mano.</li>'
    )
    permiso = (
        f"Aceptó que Rous recuerde lo que cuenta y comparta un resumen desde el {_fecha_corta(persona.consentimiento)}."
        if persona.consentimiento
        else "Rous le pedirá permiso en la próxima llamada antes de guardar recuerdos."
    )
    return f"""<!doctype html>
<html lang="es-MX"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel familiar de {e(persona.trato)}</title>
<style>{CSS}</style></head>
<body>
<header class="barra"><div class="contenido"><span class="marca">Compañía por voz</span>
<span class="quien">{e(persona.trato)}</span></div></header>
<main>
<section class="portada"><div class="contenido">
<h1>¿Cómo ha estado {e(persona.trato)}?</h1>
<div class="senal {senal.semaforo.value}">
  <span class="figura" aria-hidden="true"></span>
  <div><p class="estado">{titulo}</p><p>{explicacion}</p>
  <p class="nota">{senal.respondidas} preguntas respondidas en 14 días. {e(senal.nota)}</p></div>
</div>
</div></section>

<section class="banda" id="llamadas"><div class="contenido">
<h2>Llamadas</h2>
<p class="nota">{e(permiso)}</p>
<h3>Horario de llamada</h3>
<ul class="lista">{horarios}</ul>
<form method="post" action="/horarios">
<input type="hidden" name="persona_id" value="{pid}">
<label>Que Rous le llame todos los días a las<input name="hora" type="time" required></label>
<button type="submit">Agregar horario</button></form>
{_linea_de_llamadas(dias, hoy)}
<table><thead><tr><th>Fecha</th><th>Canal</th><th class="num">Duración</th></tr></thead>
<tbody>{filas_llamadas}</tbody></table>
</div></section>

<section><div class="contenido">
<h2>Alertas</h2>
<ul class="lista">{alertas}</ul>
</div></section>

<section class="banda" id="cuidado"><div class="contenido rejilla">
<div><h2>Recordatorios</h2><ul class="lista">{recordatorios}</ul>
<form method="post" action="/recordatorios">
<input type="hidden" name="persona_id" value="{pid}">
<label>Qué recordar<input name="texto" required maxlength="140" placeholder="Tomar la pastilla"></label>
<label>Hora<input name="hora" type="time" required></label>
<button type="submit">Agregar recordatorio</button></form></div>
<div><h2>Mensajes para la próxima llamada</h2><ul class="lista">{mensajes}</ul>
<form method="post" action="/mensajes">
<input type="hidden" name="persona_id" value="{pid}">
<label>De parte de<input name="de" required maxlength="60" placeholder="su nieta"></label>
<label>Mensaje<textarea name="texto" required maxlength="280" rows="3"></textarea></label>
<button type="submit">Guardar mensaje</button></form></div>
</div></section>

<section><div class="contenido">
<h2>Recuerdos que quiso compartir</h2>
<ul class="lista">{recuerdos}</ul>
</div></section>
</main>
<footer><div class="contenido"><p>La señal de bienestar es una tendencia, no un diagnóstico.
Si hay riesgo, llame a la Línea de la Vida: 800 911 2000, las 24 horas.</p></div></footer>
</body></html>"""


def main() -> None:
    import uvicorn

    uvicorn.run(
        crear_app(), host=os.getenv("PANEL_HOST", "127.0.0.1"), port=int(os.getenv("PANEL_PUERTO", "7861"))
    )


if __name__ == "__main__":
    main()

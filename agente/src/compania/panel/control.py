"""Panel de control: todo lo que antes se hacía con comandos, con botones e instrucciones.

Rutas:
    GET  /control                 página de control
    GET  /control/estado          estado en vivo (JSON) para la página
    GET  /control/qr.svg          QR para vincular el celular de la asistente
    POST /control/llamar          Rous llama a la persona activa o a otro número
    POST /control/colgar          cuelga y libera el puente
    POST /control/motor           cambia el motor de voz (desde la siguiente llamada)
    POST /control/personas        registra una persona
    POST /control/personas/activa elige con qué perfil platica Rous
    POST /control/personas/{id}   cambia teléfono o consentimiento
    POST /control/recordatorio    recordatorio de una sola vez en N minutos
    POST /control/recordatorios/{id}/quitar
    POST /control/grupo           manda un texto al grupo de la familia
    POST /control/desvincular     cierra la sesión de WhatsApp para vincular otro celular
    GET  /guia                    guía para preparar y grabar la demo
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote

import segno
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from compania.agente.bot import MOTORES, falta_para_motor, motor_elegido
from compania.dominio.modelos import Persona, Recordatorio
from compania.infraestructura.puente_whatsapp import ControlPuente
from compania.infraestructura.repositorio import Repositorio

NOMBRE_MOTOR = {"gemini": "Gemini Live (Google)", "openai": "OpenAI Realtime", "nova": "Nova Sonic (AWS)"}
NUMERO = re.compile(r"^\d{10,15}$")


def solo_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def numero_de_la_persona(persona: Persona | None) -> str:
    return solo_digitos((persona.telefono if persona else None) or os.getenv("WHATSAPP_PERSONA") or "")


def volver(seccion: str, aviso: str, ok: bool = True) -> RedirectResponse:
    tipo = "ok" if ok else "error"
    return RedirectResponse(f"/control?aviso={quote(aviso)}&tipo={tipo}#{seccion}", status_code=303)


def mensaje_del_puente(codigo: int, datos: dict, exito: str) -> tuple[str, bool]:
    if codigo == 200:
        return datos.get("mensaje") or exito, True
    return datos.get("error") or f"El puente respondió {codigo}", False


def registrar(app: FastAPI, repo: Repositorio, puente: ControlPuente, pagina_base) -> None:
    """Agrega las rutas de control al panel. ``pagina_base(titulo, cuerpo, actual)`` arma la página."""

    def estado() -> dict:
        en_puente = puente.estado()
        qr = puente.qr() if not en_puente.get("conectado") else None
        persona = repo.persona_activa()
        if en_puente.get("apagado"):
            whatsapp = "apagado"
        elif en_puente.get("conectado"):
            whatsapp = "vinculado"
        elif qr:
            whatsapp = "qr"
        else:
            whatsapp = "reconectando"
        return {
            "whatsapp": whatsapp,
            "en_llamada": bool(en_puente.get("en_llamada")),
            "grupo": bool(en_puente.get("grupo")),
            "hay_qr": bool(qr),
            "motor": motor_elegido(repo),
            "persona": persona.trato if persona else None,
            "numero": numero_de_la_persona(persona) or None,
        }

    @app.get("/control/estado")
    def api_estado() -> dict:
        return estado()

    @app.get("/control/qr.svg")
    def qr_svg() -> Response:
        texto = puente.qr()
        if not texto:
            raise HTTPException(
                404, "No hay QR: el celular ya está vinculado o el puente se está reiniciando"
            )
        salida = io.BytesIO()
        segno.make(texto, error="l").save(
            salida, kind="svg", scale=6, border=3, dark="#1d2a2b", xmldecl=False
        )
        return Response(salida.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    @app.post("/control/llamar")
    def llamar(numero: str = Form("")):
        destino = solo_digitos(numero) or numero_de_la_persona(repo.persona_activa())
        if not NUMERO.match(destino):
            return volver(
                "llamar", "Falta el número: escríbelo con código de país, por ejemplo 522221234567.", False
            )
        texto, ok = mensaje_del_puente(*puente.llamar(destino), f"Llamando a {destino}...")
        return volver("llamar", texto, ok)

    @app.post("/control/colgar")
    def colgar():
        return volver("llamar", *mensaje_del_puente(*puente.colgar(), "Llamada colgada"))

    @app.post("/control/motor")
    def motor(motor: str = Form(...)):
        if motor not in MOTORES:
            return volver("motor", f"El motor {motor!r} no existe.", False)
        if falta := falta_para_motor(motor):
            return volver("motor", f"No se cambió: {falta}.", False)
        repo.guardar_ajuste("motor_voz", motor)
        return volver("motor", f"Listo: la siguiente llamada usa {NOMBRE_MOTOR[motor]}.")

    @app.post("/control/personas")
    def alta(
        nombre: str = Form(...),
        trato: str = Form(...),
        telefono: str = Form(""),
        contacto: str = Form(""),
        consentimiento: str = Form(""),
        activar: str = Form(""),
    ):
        numero = solo_digitos(telefono)
        if numero and not NUMERO.match(numero):
            return volver(
                "personas", "El teléfono debe llevar código de país, por ejemplo 522221234567.", False
            )
        persona = repo.guardar_persona(
            Persona(
                nombre.strip(),
                trato.strip(),
                contacto.strip() or None,
                telefono=numero or None,
                consentimiento=datetime.now() if consentimiento else None,
            )
        )
        if activar:
            repo.guardar_ajuste("persona_activa", str(persona.id))
        return volver(
            "personas",
            f"Se registró a {persona.trato}" + (" y quedó como perfil activo." if activar else "."),
        )

    @app.post("/control/personas/activa")
    def activa(persona_id: int = Form(...)):
        persona = repo.obtener_persona(persona_id)
        if persona is None:
            return volver("personas", "Ese perfil no existe.", False)
        repo.guardar_ajuste("persona_activa", str(persona_id))
        return volver(
            "personas", f"Listo: Rous platica con el perfil de {persona.trato} desde la siguiente llamada."
        )

    @app.post("/control/personas/{persona_id}")
    def editar(persona_id: int, telefono: str = Form(""), consentimiento: str = Form("")):
        persona = repo.obtener_persona(persona_id)
        if persona is None:
            return volver("personas", "Ese perfil no existe.", False)
        numero = solo_digitos(telefono)
        if numero and not NUMERO.match(numero):
            return volver(
                "personas", "El teléfono debe llevar código de país, por ejemplo 522221234567.", False
            )
        if numero:
            repo.actualizar_telefono(persona_id, numero)
        if consentimiento in ("si", "no"):
            repo.registrar_consentimiento(persona_id, consentimiento == "si")
        return volver("personas", f"Se guardaron los cambios de {persona.trato}.")

    @app.post("/control/recordatorio")
    def recordatorio(texto: str = Form(...), minutos: int = Form(...)):
        persona = repo.persona_activa()
        if persona is None or persona.id is None:
            return volver("recordatorios", "Primero registra a la persona.", False)
        if not 1 <= minutos <= 720:
            return volver("recordatorios", "Los minutos van de 1 a 720.", False)
        hora = (datetime.now() + timedelta(minutes=minutos)).strftime("%H:%M")
        repo.guardar_recordatorio(
            Recordatorio(persona.id, texto.strip()[:140], hora, "familia", una_vez=True)
        )
        return volver("recordatorios", f"Rous le llama a las {hora} para recordarle: {texto.strip()[:140]}.")

    @app.post("/control/recordatorios/{recordatorio_id}/quitar")
    def quitar_recordatorio(recordatorio_id: int):
        repo.desactivar_recordatorio(recordatorio_id)
        return volver("recordatorios", "Recordatorio quitado.")

    @app.post("/control/grupo")
    def grupo(texto: str = Form(...)):
        return volver(
            "grupo",
            *mensaje_del_puente(*puente.enviar_al_grupo(texto.strip()[:1000]), "Mensaje enviado al grupo."),
        )

    @app.post("/control/desvincular")
    def desvincular(confirmo: str = Form("")):
        if confirmo != "si":
            return volver(
                "whatsapp", "Marca la casilla para confirmar que quieres cerrar la sesión actual.", False
            )
        return volver("whatsapp", *mensaje_del_puente(*puente.desvincular(), "Sesión cerrada."))

    @app.get("/control", response_class=HTMLResponse)
    def pagina_control(aviso: str = "", tipo: str = "ok") -> str:
        return pagina_base("Control", cuerpo_control(repo, aviso, tipo), "control")

    @app.get("/guia", response_class=HTMLResponse)
    def pagina_guia() -> str:
        return pagina_base("Guía de la demo", GUIA, "guia")


def cuerpo_control(repo: Repositorio, aviso: str, tipo: str) -> str:
    e = escape
    activa = repo.persona_activa()
    personas = repo.personas()
    motor = motor_elegido(repo)
    numero = numero_de_la_persona(activa)

    aviso_html = (
        f'<div class="aviso {"error" if tipo == "error" else "ok"}" role="status">{e(aviso)}</div>'
        if aviso
        else ""
    )

    botones_motor = "".join(
        f'<form method="post" action="/control/motor" class="en-fila"><input type="hidden" name="motor" value="{m}">'
        f'<button type="submit" class="{"activo" if m == motor else "secundario"}"'
        f'{" disabled" if (falta := falta_para_motor(m)) else ""} aria-pressed="{str(m == motor).lower()}">'
        f"{e(NOMBRE_MOTOR[m])}</button>"
        f"{f'<span class=nota>{e(falta)}</span>' if falta else ''}</form>"
        for m in MOTORES
    )

    filas_personas = (
        "".join(
            f"""<tr{' class="elegida"' if activa and p.id == activa.id else ""}>
<td><strong>{e(p.trato)}</strong><br><span class="nota">{e(p.nombre)}</span></td>
<td class="num">{e(p.telefono or "sin número")}</td>
<td>{"Firmado" if p.consentimiento else "Lo pide Rous en la llamada"}</td>
<td>{
                "Perfil activo"
                if activa and p.id == activa.id
                else f'<form method="post" action="/control/personas/activa"><input type="hidden" name="persona_id" value="{p.id}"><button type="submit" class="secundario">Usar este perfil</button></form>'
            }</td>
</tr>"""
            for p in personas
        )
        or '<tr><td colspan="4" class="vacio">Todavía no hay personas. Registra la primera abajo.</td></tr>'
    )

    editar_activa = (
        f"""<form method="post" action="/control/personas/{activa.id}">
<h3>Cambiar datos de {e(activa.trato)}</h3>
<label>Teléfono de WhatsApp con código de país<input name="telefono" inputmode="numeric" placeholder="{e(activa.telefono or "522221234567")}"></label>
<label>Consentimiento por escrito
<select name="consentimiento"><option value="">Sin cambio</option><option value="si">Ya lo firmó</option><option value="no">Que Rous lo pida en la llamada</option></select></label>
<button type="submit">Guardar cambios</button></form>"""
        if activa
        else ""
    )

    recordatorios = (
        "".join(
            f'<li><span class="num">{e(r.hora)}</span> {e(r.texto)}'
            f"{' <span class=etiqueta>una vez</span>' if r.una_vez else ' <span class=etiqueta>diario</span>'}"
            f'<form class="en-linea" method="post" action="/control/recordatorios/{r.id}/quitar">'
            f'<button type="submit" class="secundario">Quitar</button></form></li>'
            for r in repo.recordatorios_activos(activa.id)
        )
        if activa and activa.id
        else ""
    ) or '<li class="vacio">Sin recordatorios.</li>'

    return f"""{aviso_html}
<section class="portada" id="estado"><div class="contenido">
<h1>Control de Rous</h1>
<p>Desde aquí se hace todo lo que antes era por comandos. Si es la primera vez, sigue la <a href="/guia">guía de la demo</a>.</p>
<dl class="estado-vivo" aria-live="polite">
<div><dt>WhatsApp de la asistente</dt><dd data-estado="whatsapp">Revisando...</dd></div>
<div><dt>Llamada</dt><dd data-estado="en_llamada">Revisando...</dd></div>
<div><dt>Grupo de la familia</dt><dd data-estado="grupo">Revisando...</dd></div>
<div><dt>Perfil activo</dt><dd>{e(activa.trato) if activa else "Sin persona registrada"}</dd></div>
<div><dt>Motor de voz</dt><dd>{e(NOMBRE_MOTOR.get(motor, motor))}</dd></div>
</dl>
<p class="nota">Se actualiza solo cada 3 segundos. Después de cada llamada el puente se reinicia unos segundos: es normal ver "Reconectando".</p>
</div></section>

<section class="banda" id="llamar"><div class="contenido rejilla">
<div><h2>Llamar</h2>
<p>Rous marca por WhatsApp desde el celular de la asistente. Suena aunque el celular esté bloqueado.</p>
<form method="post" action="/control/llamar">
<button type="submit" class="grande"{"" if numero else " disabled"}>Llamar ahora a {e(activa.trato) if activa else "la persona"}</button>
<span class="nota">{f"Al {e(numero)}." if numero else "Falta el número: agrégalo en Personas."}</span></form>
<form method="post" action="/control/colgar"><button type="submit" class="secundario">Colgar y liberar el puente</button>
<span class="nota">Úsalo si la llamada se quedó trabada o si sale "Ya hay una llamada en curso".</span></form></div>
<div><h3>Llamar a otro número</h3>
<form method="post" action="/control/llamar">
<label>Número de WhatsApp con código de país<input name="numero" inputmode="numeric" required placeholder="522221234567"></label>
<button type="submit">Llamar a este número</button>
<span class="nota">Rous platica con el perfil activo ({e(activa.trato) if activa else "ninguno"}). Para otra persona, cambia el perfil en Personas.</span></form></div>
</div></section>

<section id="recordatorios"><div class="contenido rejilla">
<div><h2>Recordatorio de prueba</h2>
<p>Rous llama a la hora para recordar una sola cosa y cuelga. Sirve para mostrar los recordatorios sin esperar.</p>
<form method="post" action="/control/recordatorio">
<label>Qué recordar<input name="texto" required maxlength="140" placeholder="Tomar agua"></label>
<label>En cuántos minutos<input name="minutos" type="number" min="1" max="720" value="3" required></label>
<button type="submit">Programar recordatorio</button></form>
<p class="nota">Los recordatorios diarios y el horario de llamada se ponen en la <a href="/#cuidado">página de la familia</a>.</p></div>
<div><h3>Recordatorios activos de {e(activa.trato) if activa else "la persona"}</h3><ul class="lista">{recordatorios}</ul></div>
</div></section>

<section class="banda" id="personas"><div class="contenido">
<h2>Personas</h2>
<p>Rous platica con el perfil activo: usa su nombre, sus recuerdos, recordatorios y mensajes.</p>
<table><thead><tr><th>Persona</th><th class="num">WhatsApp</th><th>Consentimiento</th><th></th></tr></thead>
<tbody>{filas_personas}</tbody></table>
<div class="rejilla separada">{editar_activa}
<form method="post" action="/control/personas">
<h3>Registrar a otra persona</h3>
<label>Nombre<input name="nombre" required maxlength="80" placeholder="Amada López"></label>
<label>Cómo le gusta que le digan<input name="trato" required maxlength="60" placeholder="abuelita Amada"></label>
<label>WhatsApp con código de país<input name="telefono" inputmode="numeric" placeholder="522221234567"></label>
<label>Contacto de emergencia<input name="contacto" maxlength="80" placeholder="Su hija Elena, 522221234567"></label>
<label class="casilla"><input type="checkbox" name="consentimiento" value="si"> Ya firmó el consentimiento por escrito</label>
<label class="casilla"><input type="checkbox" name="activar" value="si" checked> Usar este perfil desde ahora</label>
<button type="submit">Registrar persona</button></form></div>
</div></section>

<section id="motor"><div class="contenido">
<h2>Motor de voz</h2>
<p>El cambio aplica desde la siguiente llamada, sin reiniciar nada. Un motor sin su llave en el .env aparece desactivado.</p>
<div class="alterna">{botones_motor}</div>
</div></section>

<section class="banda" id="whatsapp"><div class="contenido rejilla">
<div><h2>WhatsApp de la asistente</h2>
<div data-qr hidden><p><strong>Escanea este QR</strong> desde el celular de la asistente: WhatsApp, Dispositivos vinculados, Vincular un dispositivo.</p>
<img alt="QR para vincular WhatsApp" width="320" height="320"></div>
<p data-vinculado hidden>El celular de la asistente está vinculado.</p>
<p data-sin-puente hidden>El puente está apagado o reiniciándose. Si no cambia en un minuto, revisa el registro del puente.</p></div>
<div><h3>Vincular otro celular</h3>
<p>Cierra la sesión actual y muestra un QR nuevo aquí. El celular anterior deja de ser la asistente.</p>
<form method="post" action="/control/desvincular">
<label class="casilla"><input type="checkbox" name="confirmo" value="si" required> Entiendo que se cierra la sesión actual</label>
<button type="submit" class="peligro">Cerrar sesión y mostrar QR nuevo</button></form></div>
</div></section>

<section id="grupo"><div class="contenido">
<h2>Grupo de la familia</h2>
<p>Rous manda aquí el resumen de cada llamada, las alertas y las notas de voz. Envía una prueba para confirmar que llega.</p>
<form method="post" action="/control/grupo">
<label>Mensaje<input name="texto" required maxlength="500" value="Prueba desde el panel de Rous"></label>
<button type="submit">Enviar al grupo</button></form>
</div></section>
{SCRIPT_ESTADO}"""


SCRIPT_ESTADO = """<script>
(() => {
  const texto = {
    whatsapp: { vinculado: "Vinculado", qr: "Esperando QR: escanéalo abajo", reconectando: "Reconectando...", apagado: "Puente apagado" },
  };
  const poner = (clave, valor) => {
    const nodo = document.querySelector(`[data-estado="${clave}"]`);
    if (nodo) { nodo.textContent = valor; nodo.dataset.valor = String(valor); }
  };
  const qr = document.querySelector("[data-qr]");
  const img = qr && qr.querySelector("img");
  const revisar = async () => {
    try {
      const r = await fetch("/control/estado", { cache: "no-store" });
      const s = await r.json();
      poner("whatsapp", texto.whatsapp[s.whatsapp] || s.whatsapp);
      poner("en_llamada", s.whatsapp === "vinculado" ? (s.en_llamada ? "En curso" : "Libre") : "Sin datos");
      poner("grupo", s.whatsapp === "vinculado" ? (s.grupo ? "Encontrado" : "No encontrado: revisa WHATSAPP_GRUPO") : "Sin datos");
      if (qr) {
        qr.hidden = !s.hay_qr;
        if (s.hay_qr) img.src = "/control/qr.svg?t=" + Date.now();
        document.querySelector("[data-vinculado]").hidden = s.whatsapp !== "vinculado";
        document.querySelector("[data-sin-puente]").hidden = !["apagado", "reconectando"].includes(s.whatsapp);
      }
    } catch {
      poner("whatsapp", "El panel no pudo consultar el estado");
    }
  };
  revisar();
  setInterval(revisar, 3000);
  // El aviso del último botón se queda 12 segundos al pie de la pantalla
  const aviso = document.querySelector(".aviso");
  if (aviso) setTimeout(() => aviso.remove(), 12000);
  if (location.search.includes("aviso=")) history.replaceState(null, "", location.pathname + location.hash);
})();
</script>"""


GUIA = """<section class="portada"><div class="contenido">
<h1>Guía de la demo</h1>
<p>Qué revisar antes de grabar y en qué orden mostrar cada función. Todo se hace desde el <a href="/control">control</a> y la <a href="/">página de la familia</a>.</p>
</div></section>

<section class="banda"><div class="contenido">
<h2>1. Antes de grabar</h2>
<ol class="pasos">
<li><strong>WhatsApp vinculado.</strong> En <a href="/control#estado">Control</a> debe decir "Vinculado". Si aparece un QR, escanéalo desde el celular de la asistente (WhatsApp, Dispositivos vinculados, Vincular un dispositivo).</li>
<li><strong>Un solo puente encendido.</strong> Si Rous corre aquí, apaga el de cualquier otra computadora. Con dos sesiones activas Rous puede contestar doble.</li>
<li><strong>Perfil correcto.</strong> En <a href="/control#personas">Personas</a>, el perfil activo es el de la abuelita, con su WhatsApp con código de país (52 y 10 dígitos). Si ya firmó el consentimiento, márcalo; si no, Rous se lo pide de palabra en la primera llamada.</li>
<li><strong>Motor de voz.</strong> En <a href="/control#motor">Motor de voz</a> elige el que mejor suene en sus pruebas. El cambio aplica en la siguiente llamada.</li>
<li><strong>Grupo de la familia.</strong> En <a href="/control#grupo">Grupo</a>, envía una prueba y confirma que llega. Ahí llegan los resúmenes y avisos.</li>
<li><strong>Celular de la abuelita.</strong> Con internet, volumen alto y WhatsApp abierto al menos una vez. No necesita estar desbloqueado.</li>
<li><strong>Llamada de ensayo.</strong> Haz una llamada corta con "Llamar ahora" y cuelga. Así confirmas audio, motor y número.</li>
</ol>
</div></section>

<section><div class="contenido">
<h2>2. Guion sugerido</h2>
<ol class="pasos">
<li><strong>La familia deja un mensaje.</strong> En la <a href="/#cuidado">página de la familia</a>, en "Mensajes para la próxima llamada", escribe uno de parte de la nieta. También funciona una nota de voz o un texto en el grupo que empiece con "Abue,".</li>
<li><strong>Rous llama.</strong> En Control, "Llamar ahora". Suena como llamada de WhatsApp aunque el celular esté bloqueado.</li>
<li><strong>La conversación.</strong> Rous saluda por su nombre, le da el mensaje de la familia y platica. Ideas para pedirle en la llamada:
<ul class="lista">
<li>"Cuéntame una adivinanza" o "juguemos algo": juego de memoria.</li>
<li>Platicar de su juventud o su familia: Rous guarda el recuerdo si ella dio permiso, y lo usa en la siguiente llamada.</li>
<li>"Recuérdame en 5 minutos tomar agua": Rous crea el recordatorio y llama a esa hora solo para eso.</li>
<li>"Quiero mandar buenos días con flores": Rous le manda a su WhatsApp imágenes de saludo para que ella las reenvíe.</li>
<li>"Dile a mi hija que la quiero": Rous confirma el texto y lo manda al grupo.</li>
<li>"Quiero mandarle una nota de voz a mi hija": Rous graba lo que dice y lo manda al grupo con su propia voz.</li>
<li>Hablar de alguien de la familia: Rous ofrece avisarle para que le marque.</li>
</ul></li>
<li><strong>Al colgar.</strong> Llega al grupo un resumen de la llamada.</li>
<li><strong>La familia programa una llamada.</strong> En el grupo: "Abue, salgo a las 5, a esa hora te marco". Rous se lo dice en la siguiente llamada y a esa hora le recuerda al familiar.</li>
<li><strong>Recordatorio rápido.</strong> En <a href="/control#recordatorios">Recordatorio de prueba</a>, pon 2 o 3 minutos. Rous llama, recuerda y cuelga.</li>
<li><strong>Si no contesta.</strong> Rous vuelve a marcar una vez y, si tampoco contesta, avisa al grupo. Funciona con las llamadas programadas y los recordatorios.</li>
<li><strong>Imágenes parecidas.</strong> La abuelita le manda una foto al chat de la asistente y Rous le regresa tres imágenes parecidas para reenviar. Solo funciona desde el número de WHATSAPP_PERSONA del .env.</li>
<li><strong>Página de la familia.</strong> Muestra la señal de bienestar, las llamadas de 14 días, recordatorios, alertas y los recuerdos que quiso compartir.</li>
</ol>
</div></section>

<section class="banda"><div class="contenido">
<h2>3. Si algo falla</h2>
<table class="simple"><thead><tr><th>Qué pasa</th><th>Qué hacer</th></tr></thead><tbody>
<tr><td>"Ya hay una llamada en curso"</td><td>Botón "Colgar y liberar el puente" y vuelve a llamar.</td></tr>
<tr><td>La llamada se cuelga a los pocos segundos</td><td>El puente vuelve a marcar una vez solo. Si no, colgar y llamar otra vez.</td></tr>
<tr><td>Dice "Reconectando" un rato</td><td>Es normal unos segundos después de cada llamada. Si pasa de un minuto, revisa el registro del puente.</td></tr>
<tr><td>Rous no dice el nombre correcto</td><td>Revisa el perfil activo en Personas.</td></tr>
<tr><td>No llega nada al grupo</td><td>En Control, el grupo debe decir "Encontrado". El nombre del grupo está en WHATSAPP_GRUPO del .env.</td></tr>
<tr><td>Un motor aparece desactivado</td><td>Falta su llave en el .env. Agrégala y reinicia los contenedores.</td></tr>
</tbody></table>
</div></section>

<section><div class="contenido">
<h2>4. Lo que sigue siendo por terminal</h2>
<p>Esto lo hace quien administra el servidor, no hace falta para la demo.</p>
<ul class="lista">
<li>Cambiar llaves o números del .env y reiniciar: <code>docker compose up -d</code>.</li>
<li>Actualizar a una versión nueva: <code>git pull</code> y <code>docker compose up -d --build</code>.</li>
<li>Respaldos de la base y de la sesión de WhatsApp: ver DOCKER.md.</li>
<li>Ver el registro de un servicio: <code>docker compose logs -f puente</code>.</li>
</ul>
</div></section>"""

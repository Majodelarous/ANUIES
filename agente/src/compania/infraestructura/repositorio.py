"""Repositorio SQLite del prototipo."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from compania.dominio.modelos import (
    Alerta,
    Compromiso,
    Horario,
    Llamada,
    MensajeFamiliar,
    NivelAlerta,
    Persona,
    Recordatorio,
    Recuerdo,
    RespuestaBienestar,
    Seguimiento,
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS personas (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    trato TEXT NOT NULL,
    contacto_emergencia TEXT
);
CREATE TABLE IF NOT EXISTS recuerdos (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    tema TEXT NOT NULL,
    contenido TEXT NOT NULL,
    compartir_con_familia INTEGER NOT NULL DEFAULT 0,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS respuestas_bienestar (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    pregunta_id TEXT NOT NULL,
    respuesta TEXT NOT NULL,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recordatorios (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    texto TEXT NOT NULL,
    hora TEXT NOT NULL,
    creado_por TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS mensajes_familia (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    de TEXT NOT NULL,
    texto TEXT NOT NULL,
    audio TEXT,
    entregado INTEGER NOT NULL DEFAULT 0,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    nivel TEXT NOT NULL,
    motivo TEXT NOT NULL,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llamadas (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    canal TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fin TEXT
);
CREATE TABLE IF NOT EXISTS seguimientos (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    para TEXT NOT NULL,
    motivo TEXT NOT NULL,
    creado TEXT NOT NULL,
    cerrado TEXT,
    resultado TEXT
);
CREATE TABLE IF NOT EXISTS horarios (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    hora TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS compromisos (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    de TEXT NOT NULL,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    texto TEXT NOT NULL,
    avisado INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS preferencias_imagen (
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    tema TEXT NOT NULL,
    veces INTEGER NOT NULL DEFAULT 1,
    actualizado TEXT NOT NULL,
    PRIMARY KEY (persona_id, tema)
);
CREATE TABLE IF NOT EXISTS ejecuciones (
    clave TEXT PRIMARY KEY,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resultados_juego (
    id INTEGER PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id),
    juego_id TEXT NOT NULL,
    acerto INTEGER NOT NULL,
    creado TEXT NOT NULL
);
"""


def _fecha(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


class Repositorio:
    """Acceso a datos con SQLite. Una instancia por proceso."""

    def __init__(self, ruta: str | Path = "compania.db") -> None:
        self._db = sqlite3.connect(str(ruta), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(ESQUEMA)
        self._migrar()
        self._db.commit()

    def _migrar(self) -> None:
        """Agrega columnas nuevas a bases creadas con versiones anteriores."""
        columnas = {f["name"] for f in self._db.execute("PRAGMA table_info(personas)")}
        if "telefono" not in columnas:
            self._db.execute("ALTER TABLE personas ADD COLUMN telefono TEXT")
        if "consentimiento" not in columnas:
            self._db.execute("ALTER TABLE personas ADD COLUMN consentimiento TEXT")
        columnas = {f["name"] for f in self._db.execute("PRAGMA table_info(recordatorios)")}
        if "una_vez" not in columnas:
            self._db.execute("ALTER TABLE recordatorios ADD COLUMN una_vez INTEGER NOT NULL DEFAULT 0")

    def cerrar(self) -> None:
        self._db.close()

    def _insertar(self, sql: str, valores: tuple) -> int:
        cur = self._db.execute(sql, valores)
        self._db.commit()
        return int(cur.lastrowid)

    # Personas

    def guardar_persona(self, persona: Persona) -> Persona:
        persona.id = self._insertar(
            "INSERT INTO personas (nombre, trato, contacto_emergencia, telefono, consentimiento)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                persona.nombre,
                persona.trato,
                persona.contacto_emergencia,
                persona.telefono,
                persona.consentimiento.isoformat() if persona.consentimiento else None,
            ),
        )
        return persona

    def obtener_persona(self, persona_id: int) -> Persona | None:
        fila = self._db.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
        if not fila:
            return None
        return Persona(
            fila["nombre"],
            fila["trato"],
            fila["contacto_emergencia"],
            fila["id"],
            fila["telefono"],
            _fecha(fila["consentimiento"]),
        )

    def personas(self) -> list[Persona]:
        filas = self._db.execute("SELECT id FROM personas ORDER BY id").fetchall()
        return [p for f in filas if (p := self.obtener_persona(f["id"])) is not None]

    def registrar_consentimiento(self, persona_id: int, acepta: bool) -> None:
        valor = datetime.now().isoformat() if acepta else None
        self._db.execute("UPDATE personas SET consentimiento = ? WHERE id = ?", (valor, persona_id))
        self._db.commit()

    def actualizar_telefono(self, persona_id: int, telefono: str) -> bool:
        cur = self._db.execute("UPDATE personas SET telefono = ? WHERE id = ?", (telefono, persona_id))
        self._db.commit()
        return cur.rowcount == 1

    def primera_persona(self) -> Persona | None:
        fila = self._db.execute("SELECT id FROM personas ORDER BY id LIMIT 1").fetchone()
        return self.obtener_persona(fila["id"]) if fila else None

    def persona_activa(self) -> Persona | None:
        """La persona elegida en el panel; si no hay elección, la primera registrada."""
        elegida = self.ajuste("persona_activa")
        if elegida and elegida.isdigit() and (persona := self.obtener_persona(int(elegida))):
            return persona
        return self.primera_persona()

    # Ajustes que cambia el panel y leen los demás servicios (comparten la base)

    def ajuste(self, clave: str) -> str | None:
        fila = self._db.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
        return fila["valor"] if fila else None

    def guardar_ajuste(self, clave: str, valor: str) -> None:
        self._db.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, valor),
        )
        self._db.commit()

    # Recuerdos

    def guardar_recuerdo(self, recuerdo: Recuerdo) -> Recuerdo:
        recuerdo.id = self._insertar(
            "INSERT INTO recuerdos (persona_id, tema, contenido, compartir_con_familia, creado)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                recuerdo.persona_id,
                recuerdo.tema,
                recuerdo.contenido,
                int(recuerdo.compartir_con_familia),
                recuerdo.creado.isoformat(),
            ),
        )
        return recuerdo

    def buscar_recuerdos(self, persona_id: int, tema: str | None = None, limite: int = 5) -> list[Recuerdo]:
        sql = "SELECT * FROM recuerdos WHERE persona_id = ?"
        valores: list = [persona_id]
        if tema:
            sql += " AND (tema LIKE ? OR contenido LIKE ?)"
            valores += [f"%{tema}%", f"%{tema}%"]
        sql += " ORDER BY creado DESC, id DESC LIMIT ?"
        valores.append(limite)
        return [
            Recuerdo(
                f["persona_id"],
                f["tema"],
                f["contenido"],
                bool(f["compartir_con_familia"]),
                datetime.fromisoformat(f["creado"]),
                f["id"],
            )
            for f in self._db.execute(sql, valores).fetchall()
        ]

    # Bienestar

    def guardar_respuesta(self, respuesta: RespuestaBienestar) -> RespuestaBienestar:
        respuesta.id = self._insertar(
            "INSERT INTO respuestas_bienestar (persona_id, pregunta_id, respuesta, creado)"
            " VALUES (?, ?, ?, ?)",
            (
                respuesta.persona_id,
                respuesta.pregunta_id,
                respuesta.respuesta,
                respuesta.creado.isoformat(),
            ),
        )
        return respuesta

    def respuestas(self, persona_id: int, desde: datetime | None = None) -> list[RespuestaBienestar]:
        desde = desde or datetime.now() - timedelta(days=30)
        filas = self._db.execute(
            "SELECT * FROM respuestas_bienestar WHERE persona_id = ? AND creado >= ? ORDER BY creado",
            (persona_id, desde.isoformat()),
        ).fetchall()
        return [
            RespuestaBienestar(
                f["persona_id"],
                f["pregunta_id"],
                f["respuesta"],
                datetime.fromisoformat(f["creado"]),
                f["id"],
            )
            for f in filas
        ]

    # Recordatorios

    def guardar_recordatorio(self, recordatorio: Recordatorio) -> Recordatorio:
        recordatorio.id = self._insertar(
            "INSERT INTO recordatorios (persona_id, texto, hora, creado_por, activo, una_vez)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                recordatorio.persona_id,
                recordatorio.texto,
                recordatorio.hora,
                recordatorio.creado_por,
                int(recordatorio.activo),
                int(recordatorio.una_vez),
            ),
        )
        return recordatorio

    def recordatorios_activos(self, persona_id: int) -> list[Recordatorio]:
        filas = self._db.execute(
            "SELECT * FROM recordatorios WHERE persona_id = ? AND activo = 1 ORDER BY hora",
            (persona_id,),
        ).fetchall()
        return [self._recordatorio(f) for f in filas]

    @staticmethod
    def _recordatorio(f) -> Recordatorio:
        return Recordatorio(
            f["persona_id"],
            f["texto"],
            f["hora"],
            f["creado_por"],
            bool(f["activo"]),
            f["id"],
            bool(f["una_vez"]),
        )

    def desactivar_recordatorio(self, recordatorio_id: int) -> None:
        self._db.execute("UPDATE recordatorios SET activo = 0 WHERE id = ?", (recordatorio_id,))
        self._db.commit()

    # Mensajes de la familia

    def guardar_mensaje(self, mensaje: MensajeFamiliar) -> MensajeFamiliar:
        mensaje.id = self._insertar(
            "INSERT INTO mensajes_familia (persona_id, de, texto, audio, entregado, creado)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                mensaje.persona_id,
                mensaje.de,
                mensaje.texto,
                mensaje.audio,
                int(mensaje.entregado),
                mensaje.creado.isoformat(),
            ),
        )
        return mensaje

    @staticmethod
    def _mensaje(f) -> MensajeFamiliar:
        return MensajeFamiliar(
            f["persona_id"],
            f["de"],
            f["texto"],
            f["audio"],
            bool(f["entregado"]),
            datetime.fromisoformat(f["creado"]),
            f["id"],
        )

    def mensajes_pendientes(self, persona_id: int) -> list[MensajeFamiliar]:
        filas = self._db.execute(
            "SELECT * FROM mensajes_familia WHERE persona_id = ? AND entregado = 0 ORDER BY creado",
            (persona_id,),
        ).fetchall()
        return [self._mensaje(f) for f in filas]

    def obtener_mensaje(self, mensaje_id: int, persona_id: int) -> MensajeFamiliar | None:
        fila = self._db.execute(
            "SELECT * FROM mensajes_familia WHERE id = ? AND persona_id = ?", (mensaje_id, persona_id)
        ).fetchone()
        return self._mensaje(fila) if fila else None

    def marcar_entregado(self, mensaje_id: int, persona_id: int) -> bool:
        cur = self._db.execute(
            "UPDATE mensajes_familia SET entregado = 1 WHERE id = ? AND persona_id = ?",
            (mensaje_id, persona_id),
        )
        self._db.commit()
        return cur.rowcount == 1

    # Alertas

    def guardar_alerta(self, alerta: Alerta) -> Alerta:
        alerta.id = self._insertar(
            "INSERT INTO alertas (persona_id, nivel, motivo, creado) VALUES (?, ?, ?, ?)",
            (alerta.persona_id, alerta.nivel.value, alerta.motivo, alerta.creado.isoformat()),
        )
        return alerta

    def alertas(self, persona_id: int, desde: datetime | None = None) -> list[Alerta]:
        desde = desde or datetime.now() - timedelta(days=30)
        filas = self._db.execute(
            "SELECT * FROM alertas WHERE persona_id = ? AND creado >= ? ORDER BY creado",
            (persona_id, desde.isoformat()),
        ).fetchall()
        return [
            Alerta(
                f["persona_id"],
                NivelAlerta(f["nivel"]),
                f["motivo"],
                datetime.fromisoformat(f["creado"]),
                f["id"],
            )
            for f in filas
        ]

    # Llamadas

    def iniciar_llamada(self, persona_id: int, canal: str) -> Llamada:
        llamada = Llamada(persona_id, canal)
        llamada.id = self._insertar(
            "INSERT INTO llamadas (persona_id, canal, inicio) VALUES (?, ?, ?)",
            (persona_id, canal, llamada.inicio.isoformat()),
        )
        return llamada

    def terminar_llamada(self, llamada_id: int) -> None:
        self._db.execute("UPDATE llamadas SET fin = ? WHERE id = ?", (datetime.now().isoformat(), llamada_id))
        self._db.commit()

    def llamadas(self, persona_id: int, limite: int = 20) -> list[Llamada]:
        filas = self._db.execute(
            "SELECT * FROM llamadas WHERE persona_id = ? ORDER BY inicio DESC LIMIT ?",
            (persona_id, limite),
        ).fetchall()
        return [
            Llamada(
                f["persona_id"], f["canal"], datetime.fromisoformat(f["inicio"]), _fecha(f["fin"]), f["id"]
            )
            for f in filas
        ]

    def es_primera_llamada(self, persona_id: int) -> bool:
        fila = self._db.execute(
            "SELECT COUNT(*) AS n FROM llamadas WHERE persona_id = ?", (persona_id,)
        ).fetchone()
        return fila["n"] <= 1

    # Juegos

    def guardar_resultado_juego(self, persona_id: int, juego_id: str, acerto: bool) -> None:
        self._insertar(
            "INSERT INTO resultados_juego (persona_id, juego_id, acerto, creado) VALUES (?, ?, ?, ?)",
            (persona_id, juego_id, int(acerto), datetime.now().isoformat()),
        )

    # Seguimientos (pendientes de preguntar en otra llamada)

    def guardar_seguimiento(self, seguimiento: Seguimiento) -> Seguimiento:
        seguimiento.id = self._insertar(
            "INSERT INTO seguimientos (persona_id, para, motivo, creado) VALUES (?, ?, ?, ?)",
            (seguimiento.persona_id, seguimiento.para, seguimiento.motivo, seguimiento.creado.isoformat()),
        )
        return seguimiento

    def seguimientos_abiertos(self, persona_id: int) -> list[Seguimiento]:
        filas = self._db.execute(
            "SELECT * FROM seguimientos WHERE persona_id = ? AND cerrado IS NULL ORDER BY creado",
            (persona_id,),
        ).fetchall()
        return [
            Seguimiento(
                f["persona_id"],
                f["para"],
                f["motivo"],
                datetime.fromisoformat(f["creado"]),
                None,
                None,
                f["id"],
            )
            for f in filas
        ]

    def cerrar_seguimiento(self, seguimiento_id: int, persona_id: int, resultado: str) -> bool:
        cur = self._db.execute(
            "UPDATE seguimientos SET cerrado = ?, resultado = ? WHERE id = ? AND persona_id = ? AND cerrado IS NULL",
            (datetime.now().isoformat(), resultado, seguimiento_id, persona_id),
        )
        self._db.commit()
        return cur.rowcount == 1

    # Horarios de llamada

    def guardar_horario(self, horario: Horario) -> Horario:
        horario.id = self._insertar(
            "INSERT INTO horarios (persona_id, hora, activo) VALUES (?, ?, ?)",
            (horario.persona_id, horario.hora, int(horario.activo)),
        )
        return horario

    def horarios(self, persona_id: int | None = None) -> list[Horario]:
        sql = "SELECT * FROM horarios WHERE activo = 1"
        valores: tuple = ()
        if persona_id is not None:
            sql += " AND persona_id = ?"
            valores = (persona_id,)
        filas = self._db.execute(sql + " ORDER BY hora", valores).fetchall()
        return [Horario(f["persona_id"], f["hora"], bool(f["activo"]), f["id"]) for f in filas]

    def desactivar_horario(self, horario_id: int, persona_id: int) -> bool:
        cur = self._db.execute(
            "UPDATE horarios SET activo = 0 WHERE id = ? AND persona_id = ?", (horario_id, persona_id)
        )
        self._db.commit()
        return cur.rowcount == 1

    def todos_los_recordatorios_activos(self) -> list[Recordatorio]:
        filas = self._db.execute("SELECT persona_id FROM recordatorios WHERE activo = 1 GROUP BY persona_id")
        return [r for f in filas.fetchall() for r in self.recordatorios_activos(f["persona_id"])]

    def obtener_recordatorio(self, recordatorio_id: int) -> Recordatorio | None:
        f = self._db.execute("SELECT * FROM recordatorios WHERE id = ?", (recordatorio_id,)).fetchone()
        if not f:
            return None
        return self._recordatorio(f)

    # Ejecuciones del programador (para no lanzar dos veces la misma tarea)

    def marcar_ejecutada(self, clave: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO ejecuciones (clave, creado) VALUES (?, ?)",
            (clave, datetime.now().isoformat()),
        )
        self._db.commit()

    def ejecutadas_desde(self, dia: str) -> set[str]:
        filas = self._db.execute("SELECT clave FROM ejecuciones WHERE clave >= ?", (dia,)).fetchall()
        return {f["clave"] for f in filas}

    # Compromisos de la familia ("a las 5 te marco")

    def guardar_compromiso(self, compromiso: Compromiso) -> Compromiso:
        compromiso.id = self._insertar(
            "INSERT INTO compromisos (persona_id, de, fecha, hora, texto, avisado) VALUES (?, ?, ?, ?, ?, ?)",
            (
                compromiso.persona_id,
                compromiso.de,
                compromiso.fecha,
                compromiso.hora,
                compromiso.texto,
                int(compromiso.avisado),
            ),
        )
        return compromiso

    def compromisos_por_avisar(self) -> list[Compromiso]:
        filas = self._db.execute(
            "SELECT * FROM compromisos WHERE avisado = 0 ORDER BY fecha, hora"
        ).fetchall()
        return [
            Compromiso(
                f["persona_id"], f["de"], f["fecha"], f["hora"], f["texto"], bool(f["avisado"]), f["id"]
            )
            for f in filas
        ]

    def marcar_compromiso_avisado(self, compromiso_id: int) -> None:
        self._db.execute("UPDATE compromisos SET avisado = 1 WHERE id = ?", (compromiso_id,))
        self._db.commit()

    def obtener_compromiso(self, compromiso_id: int) -> Compromiso | None:
        f = self._db.execute("SELECT * FROM compromisos WHERE id = ?", (compromiso_id,)).fetchone()
        if not f:
            return None
        return Compromiso(
            f["persona_id"], f["de"], f["fecha"], f["hora"], f["texto"], bool(f["avisado"]), f["id"]
        )

    # Temas de imágenes que le gustan a la persona

    def sumar_preferencia_imagen(self, persona_id: int, tema: str) -> None:
        tema = tema.strip().lower()
        if not tema:
            return
        self._db.execute(
            "INSERT INTO preferencias_imagen (persona_id, tema, veces, actualizado) VALUES (?, ?, 1, ?)"
            " ON CONFLICT(persona_id, tema) DO UPDATE SET veces = veces + 1, actualizado = excluded.actualizado",
            (persona_id, tema, datetime.now().isoformat()),
        )
        self._db.commit()

    def temas_favoritos(self, persona_id: int, limite: int = 5) -> list[str]:
        filas = self._db.execute(
            "SELECT tema FROM preferencias_imagen WHERE persona_id = ? ORDER BY veces DESC, actualizado DESC LIMIT ?",
            (persona_id, limite),
        ).fetchall()
        return [f["tema"] for f in filas]

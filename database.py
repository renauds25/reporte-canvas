from __future__ import annotations

import csv
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "reporte_canvas.db"

MAESTROS_USUARIOS_PATH = DATA_DIR / "usuarios.csv"
MAESTROS_CAPACITACIONES_PATH = DATA_DIR / "capacitaciones.csv"
MAESTROS_PENDIENTES_MEET_PATH = DATA_DIR / "maestros" / "pendientes_revision_meet.csv"
MAESTROS_DESCARTADOS_MEET_PATH = DATA_DIR / "maestros" / "descartados_menos_30_min_meet.csv"
MAESTROS_HORARIOS_PATH = DATA_DIR / "maestros" / "horarios_cursos.csv"

ALUMNOS_DATA_DIR = DATA_DIR / "alumnos"
ALUMNOS_USUARIOS_PATH = ALUMNOS_DATA_DIR / "usuarios.csv"
ALUMNOS_CAPACITACIONES_PATH = ALUMNOS_DATA_DIR / "capacitaciones.csv"
ALUMNOS_PENDIENTES_PATH = ALUMNOS_DATA_DIR / "pendientes_revision.csv"
ALUMNOS_DESCARTADOS_PATH = ALUMNOS_DATA_DIR / "descartados_menos_30_min.csv"
ALUMNOS_MEET_DESCARGADOS_PATH = ALUMNOS_DATA_DIR / "meet_descargados.csv"

CURSOS_MAESTROS = [
    "CANVAS 1. INTRODUCCIÓN Y APUNTES.",
    "CANVAS 2. TAREAS Y SPEEDGRADER.",
    "CANVAS 3. GRUPOS (EQUIPOS).",
    "CANVAS 4. RÚBRICAS.",
    "CANVAS 5. FOROS DE DISCUSIÓN.",
    "CANVAS 6. EXÁMENES Y SPEEDGRADER.",
]
CURSO_ALUMNOS = "CURSO DE ALUMNOS"


def reparar_mojibake(valor: Any) -> str:
    texto = str(valor or "")
    if not any(marcador in texto for marcador in ("Ã", "Â", "â")):
        return texto

    for encoding in ("cp1252", "latin1"):
        try:
            reparado = texto.encode(encoding).decode("utf-8")
            if reparado and reparado != texto:
                return reparado
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    return texto


def limpiar(valor: Any) -> str:
    texto = reparar_mojibake(valor).strip()
    if texto.lower() in {"null", "none", "nan", "n/a", "na", "sin dato", "sin datos"}:
        return ""
    return texto


def normalizar(valor: Any) -> str:
    texto = limpiar(valor).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Mn")
    texto = re.sub(r"[^a-z0-9@]+", " ", texto)
    return " ".join(texto.split())


def normalizar_correo(valor: Any) -> str:
    return limpiar(valor).lower()


def normalizar_clave(valor: Any) -> str:
    texto = normalizar(valor)
    return texto.replace(" ", "_")


def obtener_valor(fila: dict[str, Any], *claves: str) -> str:
    normalizado = {normalizar_clave(clave): valor for clave, valor in fila.items()}
    for clave in claves:
        clave_norm = normalizar_clave(clave)
        if clave_norm in normalizado:
            return limpiar(normalizado[clave_norm])
    return ""


def leer_csv(ruta: Path) -> list[dict[str, str]]:
    if not ruta.exists() or ruta.stat().st_size == 0:
        return []

    codificaciones = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
    ultimo_error: Exception | None = None

    for codificacion in codificaciones:
        try:
            with ruta.open("r", encoding=codificacion, newline="") as archivo:
                lector = csv.DictReader(archivo)
                return [{str(k or ""): limpiar(v) for k, v in fila.items()} for fila in lector]
        except UnicodeDecodeError as exc:
            ultimo_error = exc
            continue

    if ultimo_error:
        raise ultimo_error

    return []


def fecha_iso(valor: Any) -> str:
    texto = limpiar(valor)
    if not texto:
        return ""

    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return texto


def fecha_hora_actual() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def persona_key(tipo: str, id_externo: Any = "", correo: Any = "", nombre: Any = "") -> str:
    tipo = limpiar(tipo).lower() or "desconocido"
    id_valor = limpiar(id_externo)
    correo_valor = normalizar_correo(correo)
    nombre_valor = normalizar(nombre)

    if id_valor:
        return f"{tipo}|id:{id_valor}"
    if correo_valor:
        return f"{tipo}|correo:{correo_valor}"
    if nombre_valor:
        return f"{tipo}|nombre:{nombre_valor}"
    return f"{tipo}|sin_identificador"


def curso_key(tipo: str, curso: Any) -> str:
    return f"{limpiar(tipo).lower()}|{normalizar(curso)}"


def capacitacion_key(tipo: str, id_externo: Any, correo: Any, nombre: Any, curso: Any, modalidad: Any) -> str:
    return "|".join([
        persona_key(tipo, id_externo, correo, nombre),
        normalizar(curso),
        normalizar(modalidad),
    ])


@contextmanager
def conectar_bd(ruta: Path = DATABASE_PATH):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def inicializar_bd(conexion: sqlite3.Connection) -> None:
    conexion.executescript(
        """
        CREATE TABLE IF NOT EXISTS personas (
            persona_key TEXT PRIMARY KEY,
            tipo TEXT NOT NULL,
            id_externo TEXT,
            nombre TEXT,
            correo TEXT,
            carrera TEXT,
            division TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_personas_tipo ON personas(tipo);
        CREATE INDEX IF NOT EXISTS idx_personas_correo ON personas(correo);
        CREATE INDEX IF NOT EXISTS idx_personas_id_externo ON personas(id_externo);

        CREATE TABLE IF NOT EXISTS cursos (
            curso_key TEXT PRIMARY KEY,
            tipo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            orden INTEGER,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cursos_tipo ON cursos(tipo);

        CREATE TABLE IF NOT EXISTS sesiones (
            sesion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            curso_key TEXT,
            curso TEXT,
            modalidad TEXT,
            fecha TEXT,
            hora_inicio TEXT,
            hora_fin TEXT,
            fuente TEXT,
            archivo_origen TEXT,
            asunto_gmail TEXT,
            mensaje_id TEXT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY(curso_key) REFERENCES cursos(curso_key)
        );

        CREATE INDEX IF NOT EXISTS idx_sesiones_tipo_fecha ON sesiones(tipo, fecha);
        CREATE INDEX IF NOT EXISTS idx_sesiones_curso ON sesiones(curso_key);

        CREATE TABLE IF NOT EXISTS capacitaciones (
            capacitacion_key TEXT PRIMARY KEY,
            tipo TEXT NOT NULL,
            persona_key TEXT,
            curso_key TEXT,
            sesion_id INTEGER,
            id_externo TEXT,
            nombre TEXT,
            correo TEXT,
            carrera TEXT,
            division TEXT,
            curso TEXT NOT NULL,
            modalidad TEXT NOT NULL,
            fecha_actualizacion TEXT,
            duracion_minutos REAL,
            fuente TEXT,
            archivo_origen TEXT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY(persona_key) REFERENCES personas(persona_key),
            FOREIGN KEY(curso_key) REFERENCES cursos(curso_key),
            FOREIGN KEY(sesion_id) REFERENCES sesiones(sesion_id)
        );

        CREATE INDEX IF NOT EXISTS idx_capacitaciones_tipo ON capacitaciones(tipo);
        CREATE INDEX IF NOT EXISTS idx_capacitaciones_persona ON capacitaciones(persona_key);
        CREATE INDEX IF NOT EXISTS idx_capacitaciones_curso ON capacitaciones(curso_key);

        CREATE TABLE IF NOT EXISTS pendientes_revision (
            pendiente_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            id_externo TEXT,
            nombre TEXT,
            correo TEXT,
            carrera TEXT,
            division TEXT,
            curso TEXT,
            modalidad TEXT,
            fecha_actualizacion TEXT,
            duracion TEXT,
            minutos_num REAL,
            motivo TEXT,
            archivo_origen TEXT,
            hora_unio TEXT,
            creado_en TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pendientes_tipo ON pendientes_revision(tipo);
        CREATE INDEX IF NOT EXISTS idx_pendientes_motivo ON pendientes_revision(motivo);

        CREATE TABLE IF NOT EXISTS descartados (
            descartado_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            id_externo TEXT,
            nombre TEXT,
            correo TEXT,
            carrera TEXT,
            division TEXT,
            curso TEXT,
            modalidad TEXT,
            fecha_actualizacion TEXT,
            duracion TEXT,
            minutos_num REAL,
            motivo TEXT,
            archivo_origen TEXT,
            hora_unio TEXT,
            creado_en TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_descartados_tipo ON descartados(tipo);
        CREATE INDEX IF NOT EXISTS idx_descartados_motivo ON descartados(motivo);

        CREATE TABLE IF NOT EXISTS ingestas (
            ingesta_key TEXT PRIMARY KEY,
            tipo TEXT,
            mensaje_id TEXT,
            recurso_id TEXT,
            archivo TEXT,
            origen TEXT,
            asunto TEXT,
            fecha_reunion TEXT,
            fecha_descarga TEXT,
            estado TEXT,
            detalle TEXT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ingestas_tipo_estado ON ingestas(tipo, estado);
        """
    )


def reiniciar_datos(conexion: sqlite3.Connection) -> None:
    conexion.executescript(
        """
        DELETE FROM descartados;
        DELETE FROM pendientes_revision;
        DELETE FROM capacitaciones;
        DELETE FROM sesiones;
        DELETE FROM cursos;
        DELETE FROM personas;
        DELETE FROM ingestas;
        DELETE FROM sqlite_sequence WHERE name IN ('sesiones', 'pendientes_revision', 'descartados');
        """
    )


def upsert_persona(
    conexion: sqlite3.Connection,
    *,
    tipo: str,
    id_externo: str = "",
    nombre: str = "",
    correo: str = "",
    carrera: str = "",
    division: str = "",
) -> str:
    tipo = limpiar(tipo).lower()
    id_externo = limpiar(id_externo)
    nombre = limpiar(nombre)
    correo = normalizar_correo(correo)
    carrera = limpiar(carrera) or "No disponible"
    division = limpiar(division) or "No disponible"
    key = persona_key(tipo, id_externo, correo, nombre)
    ahora = fecha_hora_actual()

    conexion.execute(
        """
        INSERT INTO personas (
            persona_key, tipo, id_externo, nombre, correo, carrera, division, creado_en, actualizado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(persona_key) DO UPDATE SET
            id_externo = COALESCE(NULLIF(excluded.id_externo, ''), personas.id_externo),
            nombre = COALESCE(NULLIF(excluded.nombre, ''), personas.nombre),
            correo = COALESCE(NULLIF(excluded.correo, ''), personas.correo),
            carrera = CASE
                WHEN excluded.carrera != '' AND excluded.carrera != 'No disponible' THEN excluded.carrera
                ELSE personas.carrera
            END,
            division = CASE
                WHEN excluded.division != '' AND excluded.division != 'No disponible' THEN excluded.division
                ELSE personas.division
            END,
            actualizado_en = excluded.actualizado_en
        """,
        (key, tipo, id_externo, nombre, correo, carrera, division, ahora, ahora),
    )

    return key


def upsert_curso(conexion: sqlite3.Connection, *, tipo: str, nombre: str, orden: int | None = None) -> str:
    tipo = limpiar(tipo).lower()
    nombre = limpiar(nombre)
    key = curso_key(tipo, nombre)
    ahora = fecha_hora_actual()

    if not nombre:
        return ""

    conexion.execute(
        """
        INSERT INTO cursos (curso_key, tipo, nombre, orden, creado_en, actualizado_en)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(curso_key) DO UPDATE SET
            nombre = excluded.nombre,
            orden = COALESCE(excluded.orden, cursos.orden),
            actualizado_en = excluded.actualizado_en
        """,
        (key, tipo, nombre, orden, ahora, ahora),
    )

    return key


def upsert_capacitacion(
    conexion: sqlite3.Connection,
    *,
    tipo: str,
    id_externo: str = "",
    nombre: str = "",
    correo: str = "",
    carrera: str = "",
    division: str = "",
    curso: str,
    modalidad: str,
    fecha_actualizacion: str = "",
    duracion_minutos: float | None = None,
    fuente: str = "csv",
    archivo_origen: str = "",
) -> str:
    tipo = limpiar(tipo).lower()
    persona = upsert_persona(
        conexion,
        tipo=tipo,
        id_externo=id_externo,
        nombre=nombre,
        correo=correo,
        carrera=carrera,
        division=division,
    )
    curso_id = upsert_curso(conexion, tipo=tipo, nombre=curso)
    key = capacitacion_key(tipo, id_externo, correo, nombre, curso, modalidad)
    ahora = fecha_hora_actual()

    conexion.execute(
        """
        INSERT INTO capacitaciones (
            capacitacion_key, tipo, persona_key, curso_key, id_externo, nombre, correo,
            carrera, division, curso, modalidad, fecha_actualizacion, duracion_minutos,
            fuente, archivo_origen, creado_en, actualizado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(capacitacion_key) DO UPDATE SET
            persona_key = excluded.persona_key,
            curso_key = excluded.curso_key,
            id_externo = COALESCE(NULLIF(excluded.id_externo, ''), capacitaciones.id_externo),
            nombre = COALESCE(NULLIF(excluded.nombre, ''), capacitaciones.nombre),
            correo = COALESCE(NULLIF(excluded.correo, ''), capacitaciones.correo),
            carrera = COALESCE(NULLIF(excluded.carrera, ''), capacitaciones.carrera),
            division = COALESCE(NULLIF(excluded.division, ''), capacitaciones.division),
            fecha_actualizacion = CASE
                WHEN excluded.fecha_actualizacion >= capacitaciones.fecha_actualizacion THEN excluded.fecha_actualizacion
                ELSE capacitaciones.fecha_actualizacion
            END,
            duracion_minutos = COALESCE(excluded.duracion_minutos, capacitaciones.duracion_minutos),
            fuente = excluded.fuente,
            archivo_origen = COALESCE(NULLIF(excluded.archivo_origen, ''), capacitaciones.archivo_origen),
            actualizado_en = excluded.actualizado_en
        """,
        (
            key,
            tipo,
            persona,
            curso_id,
            limpiar(id_externo),
            limpiar(nombre),
            normalizar_correo(correo),
            limpiar(carrera) or "No disponible",
            limpiar(division) or "No disponible",
            limpiar(curso),
            limpiar(modalidad),
            fecha_iso(fecha_actualizacion),
            duracion_minutos,
            limpiar(fuente),
            limpiar(archivo_origen),
            ahora,
            ahora,
        ),
    )

    return key


def insertar_auxiliar(
    conexion: sqlite3.Connection,
    tabla: str,
    *,
    tipo: str,
    fila: dict[str, Any],
) -> None:
    if tabla not in {"pendientes_revision", "descartados"}:
        raise ValueError("Tabla auxiliar inválida")

    conexion.execute(
        f"""
        INSERT INTO {tabla} (
            tipo, id_externo, nombre, correo, carrera, division, curso, modalidad,
            fecha_actualizacion, duracion, minutos_num, motivo, archivo_origen, hora_unio, creado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            limpiar(tipo).lower(),
            obtener_valor(fila, "id", "id_externo"),
            obtener_valor(fila, "nombre"),
            normalizar_correo(obtener_valor(fila, "correo")),
            obtener_valor(fila, "carrera") or "No disponible",
            obtener_valor(fila, "division", "dirección", "direccion") or "No disponible",
            obtener_valor(fila, "curso"),
            obtener_valor(fila, "modalidad"),
            fecha_iso(obtener_valor(fila, "fecha_actualizacion", "fecha")),
            obtener_valor(fila, "duracion", "duración"),
            _float_or_none(obtener_valor(fila, "minutos_num")),
            obtener_valor(fila, "motivo"),
            obtener_valor(fila, "archivo_origen"),
            obtener_valor(fila, "hora_unio", "hora a la que se unió"),
            fecha_hora_actual(),
        ),
    )


def insertar_ingesta(conexion: sqlite3.Connection, fila: dict[str, Any]) -> None:
    mensaje_id = obtener_valor(fila, "mensaje_id", "mensaje id")
    recurso_id = obtener_valor(fila, "recurso_id", "recurso id")
    archivo = obtener_valor(fila, "archivo")
    key = "|".join([mensaje_id, recurso_id, archivo]) or f"sin_key|{fecha_hora_actual()}"
    ahora = fecha_hora_actual()

    conexion.execute(
        """
        INSERT INTO ingestas (
            ingesta_key, tipo, mensaje_id, recurso_id, archivo, origen, asunto,
            fecha_reunion, fecha_descarga, estado, detalle, creado_en, actualizado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ingesta_key) DO UPDATE SET
            estado = excluded.estado,
            detalle = excluded.detalle,
            actualizado_en = excluded.actualizado_en
        """,
        (
            key,
            obtener_valor(fila, "tipo"),
            mensaje_id,
            recurso_id,
            archivo,
            obtener_valor(fila, "origen"),
            obtener_valor(fila, "asunto"),
            fecha_iso(obtener_valor(fila, "fecha_reunion")),
            obtener_valor(fila, "fecha_descarga"),
            obtener_valor(fila, "estado"),
            obtener_valor(fila, "detalle"),
            ahora,
            ahora,
        ),
    )


def _float_or_none(valor: Any) -> float | None:
    texto = limpiar(valor).replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def importar_usuarios(conexion: sqlite3.Connection, ruta: Path, tipo: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        id_externo = obtener_valor(fila, "id", "idPerson", "matricula", "matrícula")
        nombre = obtener_valor(fila, "nombre", "Nombre")
        correo = obtener_valor(fila, "correo", "correo electrónico", "email")
        carrera = obtener_valor(fila, "carrera")
        division = obtener_valor(fila, "division", "dirección", "direccion")

        if not any([id_externo, nombre, correo]):
            continue

        upsert_persona(
            conexion,
            tipo=tipo,
            id_externo=id_externo,
            nombre=nombre,
            correo=correo,
            carrera=carrera,
            division=division,
        )
        total += 1
    return total


def importar_capacitaciones(conexion: sqlite3.Connection, ruta: Path, tipo: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        curso = obtener_valor(fila, "curso")
        modalidad = obtener_valor(fila, "modalidad")
        if not curso or not modalidad:
            continue

        upsert_capacitacion(
            conexion,
            tipo=tipo,
            id_externo=obtener_valor(fila, "id", "idPerson", "id_externo"),
            nombre=obtener_valor(fila, "nombre"),
            correo=obtener_valor(fila, "correo"),
            carrera=obtener_valor(fila, "carrera") or "No disponible",
            division=obtener_valor(fila, "division", "dirección", "direccion") or "No disponible",
            curso=curso,
            modalidad=modalidad,
            fecha_actualizacion=obtener_valor(fila, "fecha_actualizacion", "fecha"),
            fuente="csv_historico",
            archivo_origen=ruta.name,
        )
        total += 1
    return total


def importar_auxiliares(conexion: sqlite3.Connection, ruta: Path, tipo: str, tabla: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        insertar_auxiliar(conexion, tabla, tipo=tipo, fila=fila)
        total += 1
    return total


def importar_ingestas(conexion: sqlite3.Connection, ruta: Path) -> int:
    total = 0
    for fila in leer_csv(ruta):
        insertar_ingesta(conexion, fila)
        total += 1
    return total


def importar_cursos_base(conexion: sqlite3.Connection) -> int:
    total = 0
    for orden, curso in enumerate(CURSOS_MAESTROS, start=1):
        upsert_curso(conexion, tipo="maestro", nombre=curso, orden=orden)
        total += 1
    upsert_curso(conexion, tipo="alumno", nombre=CURSO_ALUMNOS, orden=1)
    total += 1
    return total


def importar_horarios_maestros(conexion: sqlite3.Connection, ruta: Path = MAESTROS_HORARIOS_PATH) -> int:
    total = 0
    for fila in leer_csv(ruta):
        curso = obtener_valor(fila, "curso")
        if not curso:
            continue
        curso_id = upsert_curso(conexion, tipo="maestro", nombre=curso)
        ahora = fecha_hora_actual()
        conexion.execute(
            """
            INSERT INTO sesiones (
                tipo, curso_key, curso, modalidad, fecha, hora_inicio, hora_fin, fuente,
                archivo_origen, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "maestro",
                curso_id,
                curso,
                obtener_valor(fila, "modalidad") or "A distancia",
                fecha_iso(obtener_valor(fila, "fecha")),
                obtener_valor(fila, "hora_inicio", "hora inicio"),
                obtener_valor(fila, "hora_fin", "hora fin"),
                "horarios_cursos",
                ruta.name,
                ahora,
                ahora,
            ),
        )
        total += 1
    return total


def resumen_bd(conexion: sqlite3.Connection) -> dict[str, int]:
    tablas = [
        "personas",
        "cursos",
        "sesiones",
        "capacitaciones",
        "pendientes_revision",
        "descartados",
        "ingestas",
    ]
    return {
        tabla: conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in tablas
    }

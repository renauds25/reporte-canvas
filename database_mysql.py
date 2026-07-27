from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from database import (
    ALUMNOS_CAPACITACIONES_PATH,
    ALUMNOS_DESCARTADOS_PATH,
    ALUMNOS_MEET_DESCARGADOS_PATH,
    ALUMNOS_PENDIENTES_PATH,
    ALUMNOS_USUARIOS_PATH,
    CURSO_ALUMNOS,
    CURSOS_MAESTROS,
    MAESTROS_CAPACITACIONES_PATH,
    MAESTROS_DESCARTADOS_MEET_PATH,
    MAESTROS_HORARIOS_PATH,
    MAESTROS_PENDIENTES_MEET_PATH,
    MAESTROS_USUARIOS_PATH,
    capacitacion_key,
    curso_key,
    fecha_hora_actual,
    fecha_iso,
    fecha_para_reporte,
    leer_csv,
    limpiar,
    normalizar,
    normalizar_correo,
    normalizar_nombre_curso,
    obtener_valor,
    persona_key,
)

BASE_DIR = Path(__file__).resolve().parent

CAPACITACIONES_API_FUENTES_PERSISTENTES = {
    "api_capacitaciones",
    "api_capacitaciones_en_linea",
}
INGESTAS_API_ORIGENES_PERSISTENTES = {
    "api_directa",
    "api_capacitaciones",
    "api_capacitaciones_en_linea",
}


def _env_bool(nombre: str, default: str = "1") -> bool:
    return os.getenv(nombre, default).strip().lower() in {"1", "true", "yes", "si", "sí"}


def mysql_configurada() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip() or os.getenv("DB_HOST", "").strip())


def resolver_ssl_ca_path() -> Path | None:
    """Resuelve la ruta del certificado CA para Azure Database for MySQL.

    Si DB_SSL_CA es relativo, se busca primero relativo a la raíz del proyecto
    y después dentro de ./certs. Para Azure se recomienda usar
    DigiCertGlobalRootG2.crt.pem.
    """
    valor = os.getenv("DB_SSL_CA", "DigiCertGlobalRootG2.crt.pem").strip()
    if not valor:
        return None

    ruta = Path(valor)
    candidatos = [ruta] if ruta.is_absolute() else [BASE_DIR / ruta, BASE_DIR / "certs" / ruta]
    for candidato in candidatos:
        if candidato.exists():
            return candidato.resolve()

    if _env_bool("DB_SSL_REQUIRED", "1"):
        raise RuntimeError(
            "No se encontró el certificado SSL CA para MySQL. "
            f"Configura DB_SSL_CA o coloca {valor} en la raíz del proyecto."
        )

    return None


def normalizar_mysql_url(url: str | None = None):
    raw = (url or os.getenv("DATABASE_URL") or "").strip()
    if raw:
        if raw.startswith("mysql://"):
            raw = "mysql+pymysql://" + raw[len("mysql://"):]
        elif raw.startswith("mysql+pymysql://"):
            pass
        else:
            raise RuntimeError(
                "DATABASE_URL debe usar mysql+pymysql://... para Azure MySQL "
                "o configura DB_HOST, DB_NAME, DB_USER y DB_PASSWORD."
            )

        url_obj = make_url(raw)
        if "charset" not in url_obj.query:
            url_obj = url_obj.update_query_dict({"charset": "utf8mb4"})
        return url_obj

    host = os.getenv("DB_HOST", "").strip()
    database = os.getenv("DB_NAME", "").strip()
    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "")
    port = int(os.getenv("DB_PORT", "3306"))

    faltantes = [nombre for nombre, valor in {
        "DB_HOST": host,
        "DB_NAME": database,
        "DB_USER": user,
        "DB_PASSWORD": password,
    }.items() if not valor]

    if faltantes:
        raise RuntimeError("Faltan variables MySQL en el entorno: " + ", ".join(faltantes))

    return URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"charset": "utf8mb4"},
    )


def crear_engine_mysql(url: str | None = None):
    connect_args: dict[str, Any] = {}
    ssl_ca = resolver_ssl_ca_path()
    if ssl_ca:
        connect_args["ssl"] = {"ca": str(ssl_ca)}

    return create_engine(
        normalizar_mysql_url(url),
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
        connect_args=connect_args,
    )


def ejecutar(conexion, sql: str, params: dict[str, Any] | None = None):
    return conexion.execute(text(sql), params or {})


def _crear_indice(conexion, sql: str) -> None:
    try:
        ejecutar(conexion, sql)
    except (OperationalError, ProgrammingError) as exc:
        mensaje = str(exc).lower()
        if "duplicate key name" in mensaje or "already exists" in mensaje:
            return
        raise


def inicializar_mysql(conexion) -> None:
    sentencias = [
        """
        CREATE TABLE IF NOT EXISTS personas (
            persona_key VARCHAR(512) PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            id_externo VARCHAR(128),
            nombre TEXT,
            correo VARCHAR(255),
            carrera VARCHAR(255),
            division VARCHAR(255),
            activo TINYINT NOT NULL DEFAULT 1,
            es_base TINYINT NOT NULL DEFAULT 0,
            creado_en VARCHAR(32) NOT NULL,
            actualizado_en VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS usuarios_base (
            usuario_base_id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            persona_key VARCHAR(512),
            id_externo VARCHAR(128),
            nombre TEXT,
            correo VARCHAR(255),
            carrera VARCHAR(255),
            division VARCHAR(255),
            creado_en VARCHAR(32) NOT NULL,
            CONSTRAINT fk_usuarios_base_persona FOREIGN KEY(persona_key) REFERENCES personas(persona_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS cursos (
            curso_key VARCHAR(512) PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            nombre VARCHAR(255) NOT NULL,
            orden INTEGER,
            activo TINYINT NOT NULL DEFAULT 1,
            creado_en VARCHAR(32) NOT NULL,
            actualizado_en VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS sesiones (
            sesion_id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            curso_key VARCHAR(512),
            curso VARCHAR(255),
            modalidad VARCHAR(128),
            fecha VARCHAR(32),
            hora_inicio VARCHAR(32),
            hora_fin VARCHAR(32),
            fuente VARCHAR(128),
            archivo_origen VARCHAR(255),
            asunto_gmail TEXT,
            mensaje_id VARCHAR(255),
            creado_en VARCHAR(32) NOT NULL,
            actualizado_en VARCHAR(32) NOT NULL,
            CONSTRAINT fk_sesiones_curso FOREIGN KEY(curso_key) REFERENCES cursos(curso_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS capacitaciones (
            capacitacion_key VARCHAR(768) PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            persona_key VARCHAR(512),
            curso_key VARCHAR(512),
            sesion_id INTEGER,
            id_externo VARCHAR(128),
            nombre TEXT,
            correo VARCHAR(255),
            carrera VARCHAR(255),
            division VARCHAR(255),
            curso VARCHAR(255) NOT NULL,
            modalidad VARCHAR(128) NOT NULL,
            fecha_actualizacion VARCHAR(32),
            duracion_minutos DOUBLE,
            fuente VARCHAR(128),
            archivo_origen VARCHAR(255),
            creado_en VARCHAR(32) NOT NULL,
            actualizado_en VARCHAR(32) NOT NULL,
            CONSTRAINT fk_capacitaciones_persona FOREIGN KEY(persona_key) REFERENCES personas(persona_key),
            CONSTRAINT fk_capacitaciones_curso FOREIGN KEY(curso_key) REFERENCES cursos(curso_key),
            CONSTRAINT fk_capacitaciones_sesion FOREIGN KEY(sesion_id) REFERENCES sesiones(sesion_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS pendientes_revision (
            pendiente_id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            id_externo VARCHAR(128),
            nombre TEXT,
            correo VARCHAR(255),
            carrera VARCHAR(255),
            division VARCHAR(255),
            curso VARCHAR(255),
            modalidad VARCHAR(128),
            fecha_actualizacion VARCHAR(32),
            duracion VARCHAR(128),
            minutos_num DOUBLE,
            motivo VARCHAR(255),
            archivo_origen VARCHAR(255),
            hora_unio VARCHAR(64),
            creado_en VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS descartados (
            descartado_id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
            tipo VARCHAR(32) NOT NULL,
            id_externo VARCHAR(128),
            nombre TEXT,
            correo VARCHAR(255),
            carrera VARCHAR(255),
            division VARCHAR(255),
            curso VARCHAR(255),
            modalidad VARCHAR(128),
            fecha_actualizacion VARCHAR(32),
            duracion VARCHAR(128),
            minutos_num DOUBLE,
            motivo VARCHAR(255),
            archivo_origen VARCHAR(255),
            hora_unio VARCHAR(64),
            creado_en VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS ingestas (
            ingesta_key VARCHAR(768) NOT NULL UNIQUE,
            tipo VARCHAR(32),
            mensaje_id VARCHAR(255),
            recurso_id TEXT,
            archivo VARCHAR(512),
            origen VARCHAR(64),
            asunto TEXT,
            fecha_reunion VARCHAR(32),
            fecha_descarga VARCHAR(64),
            estado VARCHAR(64),
            detalle TEXT,
            creado_en VARCHAR(64),
            actualizado_en VARCHAR(64)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ]

    for sentencia in sentencias:
        ejecutar(conexion, sentencia)

    indices = [
        "CREATE INDEX idx_personas_tipo ON personas(tipo)",
        "CREATE INDEX idx_personas_correo ON personas(correo)",
        "CREATE INDEX idx_personas_id_externo ON personas(id_externo)",
        "CREATE INDEX idx_personas_tipo_es_base ON personas(tipo, es_base)",
        "CREATE INDEX idx_usuarios_base_tipo ON usuarios_base(tipo)",
        "CREATE INDEX idx_usuarios_base_correo ON usuarios_base(correo)",
        "CREATE INDEX idx_usuarios_base_id_externo ON usuarios_base(id_externo)",
        "CREATE INDEX idx_cursos_tipo ON cursos(tipo)",
        "CREATE INDEX idx_sesiones_tipo_fecha ON sesiones(tipo, fecha)",
        "CREATE INDEX idx_sesiones_curso ON sesiones(curso_key)",
        "CREATE INDEX idx_capacitaciones_tipo ON capacitaciones(tipo)",
        "CREATE INDEX idx_capacitaciones_persona ON capacitaciones(persona_key)",
        "CREATE INDEX idx_capacitaciones_curso ON capacitaciones(curso_key)",
        "CREATE INDEX idx_pendientes_tipo ON pendientes_revision(tipo)",
        "CREATE INDEX idx_pendientes_motivo ON pendientes_revision(motivo)",
        "CREATE INDEX idx_descartados_tipo ON descartados(tipo)",
        "CREATE INDEX idx_descartados_motivo ON descartados(motivo)",
        "CREATE INDEX idx_ingestas_tipo_estado ON ingestas(tipo, estado)",
    ]
    for indice in indices:
        _crear_indice(conexion, indice)



def leer_capacitaciones_api_persistentes_mysql(conexion) -> list[dict[str, Any]]:
    try:
        filas = ejecutar(
            conexion,
            """
            SELECT
                tipo, id_externo, nombre, correo, carrera, division, curso, modalidad,
                fecha_actualizacion, duracion_minutos, fuente, archivo_origen
            FROM capacitaciones
            WHERE LOWER(COALESCE(fuente, '')) IN ('api_capacitaciones', 'api_capacitaciones_en_linea')
            """,
        ).mappings().all()
        return [dict(fila) for fila in filas]
    except Exception:
        return []


def leer_auxiliares_api_persistentes_mysql(conexion, tabla: str) -> list[dict[str, Any]]:
    if tabla not in {"pendientes_revision", "descartados"}:
        return []

    try:
        filas = ejecutar(
            conexion,
            f"""
            SELECT
                id_externo, nombre, correo, carrera, division, curso, modalidad,
                fecha_actualizacion, duracion, minutos_num, motivo, archivo_origen, hora_unio
            FROM {tabla}
            WHERE tipo = 'maestro'
              AND LOWER(COALESCE(archivo_origen, '')) LIKE 'api_capacitaciones%%'
            """
        ).mappings().all()
        return [dict(fila) for fila in filas]
    except Exception:
        return []


def restaurar_capacitaciones_api_persistentes_mysql(conexion, filas: list[dict[str, Any]]) -> int:
    total = 0
    for fila in filas:
        upsert_capacitacion_mysql(
            conexion,
            tipo=fila.get("tipo") or "maestro",
            id_externo=fila.get("id_externo") or "",
            nombre=fila.get("nombre") or "",
            correo=fila.get("correo") or "",
            carrera=fila.get("carrera") or "No disponible",
            division=fila.get("division") or "No disponible",
            curso=fila.get("curso") or "",
            modalidad=fila.get("modalidad") or "En línea",
            fecha_actualizacion=fila.get("fecha_actualizacion") or "",
            duracion_minutos=fila.get("duracion_minutos"),
            fuente=fila.get("fuente") or "api_capacitaciones_en_linea",
            archivo_origen=fila.get("archivo_origen") or "",
        )
        total += 1
    return total


def restaurar_auxiliares_api_persistentes_mysql(conexion, tabla: str, filas: list[dict[str, Any]]) -> int:
    total = 0
    for fila in filas:
        insertar_auxiliar_mysql(conexion, tabla, tipo="maestro", fila=fila)
        total += 1
    return total



def reiniciar_mysql(conexion) -> None:
    """Reinicia datos derivados de CSV sin borrar ingestas de API directa."""
    tablas = [
        "descartados",
        "pendientes_revision",
        "capacitaciones",
        "sesiones",
        "usuarios_base",
        "cursos",
        "personas",
    ]

    ejecutar(conexion, "SET FOREIGN_KEY_CHECKS = 0")
    try:
        for tabla in tablas:
            ejecutar(conexion, f"DELETE FROM {tabla}")
        for tabla in ["descartados", "pendientes_revision", "sesiones", "usuarios_base"]:
            ejecutar(conexion, f"ALTER TABLE {tabla} AUTO_INCREMENT = 1")
    finally:
        ejecutar(conexion, "SET FOREIGN_KEY_CHECKS = 1")

    ejecutar(
        conexion,
        """
        DELETE FROM ingestas
        WHERE LOWER(COALESCE(origen, '')) NOT IN ('api_directa', 'api_capacitaciones', 'api_capacitaciones_en_linea')
        """,
    )


def upsert_persona_mysql(
    conexion,
    *,
    tipo: str,
    id_externo: str = "",
    nombre: str = "",
    correo: str = "",
    carrera: str = "",
    division: str = "",
    es_base: bool = False,
) -> str:
    tipo = limpiar(tipo).lower()
    id_externo = limpiar(id_externo)
    nombre = limpiar(nombre)
    correo = normalizar_correo(correo)
    carrera = limpiar(carrera) or "No disponible"
    division = limpiar(division) or "No disponible"
    key = persona_key(tipo, id_externo, correo, nombre)
    ahora = fecha_hora_actual()
    es_base_val = 1 if es_base else 0

    ejecutar(
        conexion,
        """
        INSERT INTO personas (
            persona_key, tipo, id_externo, nombre, correo, carrera, division, es_base, creado_en, actualizado_en
        ) VALUES (
            :persona_key, :tipo, :id_externo, :nombre, :correo, :carrera, :division, :es_base, :creado_en, :actualizado_en
        )
        ON DUPLICATE KEY UPDATE
            id_externo = COALESCE(NULLIF(VALUES(id_externo), ''), personas.id_externo),
            nombre = COALESCE(NULLIF(VALUES(nombre), ''), personas.nombre),
            correo = COALESCE(NULLIF(VALUES(correo), ''), personas.correo),
            carrera = CASE
                WHEN VALUES(carrera) != '' AND VALUES(carrera) != 'No disponible' THEN VALUES(carrera)
                ELSE personas.carrera
            END,
            division = CASE
                WHEN VALUES(division) != '' AND VALUES(division) != 'No disponible' THEN VALUES(division)
                ELSE personas.division
            END,
            es_base = CASE
                WHEN VALUES(es_base) = 1 THEN 1
                ELSE personas.es_base
            END,
            actualizado_en = VALUES(actualizado_en)
        """,
        {
            "persona_key": key,
            "tipo": tipo,
            "id_externo": id_externo,
            "nombre": nombre,
            "correo": correo,
            "carrera": carrera,
            "division": division,
            "es_base": es_base_val,
            "creado_en": ahora,
            "actualizado_en": ahora,
        },
    )
    return key


def upsert_curso_mysql(conexion, *, tipo: str, nombre: str, orden: int | None = None) -> str:
    tipo = limpiar(tipo).lower()
    nombre = normalizar_nombre_curso(tipo, nombre)
    if not nombre:
        return ""

    key = curso_key(tipo, nombre)
    ahora = fecha_hora_actual()

    ejecutar(
        conexion,
        """
        INSERT INTO cursos (curso_key, tipo, nombre, orden, creado_en, actualizado_en)
        VALUES (:curso_key, :tipo, :nombre, :orden, :creado_en, :actualizado_en)
        ON DUPLICATE KEY UPDATE
            nombre = VALUES(nombre),
            orden = COALESCE(VALUES(orden), cursos.orden),
            actualizado_en = VALUES(actualizado_en)
        """,
        {
            "curso_key": key,
            "tipo": tipo,
            "nombre": nombre,
            "orden": orden,
            "creado_en": ahora,
            "actualizado_en": ahora,
        },
    )
    return key


def upsert_capacitacion_mysql(
    conexion,
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
    persona = upsert_persona_mysql(
        conexion,
        tipo=tipo,
        id_externo=id_externo,
        nombre=nombre,
        correo=correo,
        carrera=carrera,
        division=division,
    )
    curso_id = upsert_curso_mysql(conexion, tipo=tipo, nombre=curso)
    key = capacitacion_key(tipo, id_externo, correo, nombre, curso, modalidad)
    ahora = fecha_hora_actual()

    ejecutar(
        conexion,
        """
        INSERT INTO capacitaciones (
            capacitacion_key, tipo, persona_key, curso_key, id_externo, nombre, correo,
            carrera, division, curso, modalidad, fecha_actualizacion, duracion_minutos,
            fuente, archivo_origen, creado_en, actualizado_en
        ) VALUES (
            :capacitacion_key, :tipo, :persona_key, :curso_key, :id_externo, :nombre, :correo,
            :carrera, :division, :curso, :modalidad, :fecha_actualizacion, :duracion_minutos,
            :fuente, :archivo_origen, :creado_en, :actualizado_en
        )
        ON DUPLICATE KEY UPDATE
            persona_key = VALUES(persona_key),
            curso_key = VALUES(curso_key),
            id_externo = COALESCE(NULLIF(VALUES(id_externo), ''), capacitaciones.id_externo),
            nombre = COALESCE(NULLIF(VALUES(nombre), ''), capacitaciones.nombre),
            correo = COALESCE(NULLIF(VALUES(correo), ''), capacitaciones.correo),
            carrera = COALESCE(NULLIF(VALUES(carrera), ''), capacitaciones.carrera),
            division = COALESCE(NULLIF(VALUES(division), ''), capacitaciones.division),
            fecha_actualizacion = CASE
                WHEN COALESCE(VALUES(fecha_actualizacion), '') >= COALESCE(capacitaciones.fecha_actualizacion, '') THEN VALUES(fecha_actualizacion)
                ELSE capacitaciones.fecha_actualizacion
            END,
            duracion_minutos = COALESCE(VALUES(duracion_minutos), capacitaciones.duracion_minutos),
            fuente = VALUES(fuente),
            archivo_origen = COALESCE(NULLIF(VALUES(archivo_origen), ''), capacitaciones.archivo_origen),
            actualizado_en = VALUES(actualizado_en)
        """,
        {
            "capacitacion_key": key,
            "tipo": tipo,
            "persona_key": persona,
            "curso_key": curso_id,
            "id_externo": limpiar(id_externo),
            "nombre": limpiar(nombre),
            "correo": normalizar_correo(correo),
            "carrera": limpiar(carrera) or "No disponible",
            "division": limpiar(division) or "No disponible",
            "curso": limpiar(curso),
            "modalidad": limpiar(modalidad),
            "fecha_actualizacion": fecha_iso(fecha_actualizacion),
            "duracion_minutos": duracion_minutos,
            "fuente": limpiar(fuente),
            "archivo_origen": limpiar(archivo_origen),
            "creado_en": ahora,
            "actualizado_en": ahora,
        },
    )

    return key


def _float_or_none(valor: Any) -> float | None:
    texto = limpiar(valor).replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def importar_cursos_base_mysql(conexion) -> int:
    total = 0
    for orden, curso in enumerate(CURSOS_MAESTROS, start=1):
        upsert_curso_mysql(conexion, tipo="maestro", nombre=curso, orden=orden)
        total += 1
    upsert_curso_mysql(conexion, tipo="alumno", nombre=CURSO_ALUMNOS, orden=1)
    total += 1
    return total


def importar_usuarios_mysql(conexion, ruta: Path, tipo: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        id_externo = obtener_valor(fila, "id", "idPerson", "matricula", "matrícula")
        nombre = obtener_valor(fila, "nombre", "Nombre")
        correo = obtener_valor(fila, "correo", "correo electrónico", "email")
        carrera = obtener_valor(fila, "carrera")
        division = obtener_valor(fila, "division", "dirección", "direccion")

        if not any([id_externo, nombre, correo]):
            continue

        key = upsert_persona_mysql(
            conexion,
            tipo=tipo,
            id_externo=id_externo,
            nombre=nombre,
            correo=correo,
            carrera=carrera,
            division=division,
            es_base=True,
        )
        ejecutar(
            conexion,
            """
            INSERT INTO usuarios_base (
                tipo, persona_key, id_externo, nombre, correo, carrera, division, creado_en
            ) VALUES (
                :tipo, :persona_key, :id_externo, :nombre, :correo, :carrera, :division, :creado_en
            )
            """,
            {
                "tipo": limpiar(tipo).lower(),
                "persona_key": key,
                "id_externo": limpiar(id_externo),
                "nombre": limpiar(nombre),
                "correo": normalizar_correo(correo),
                "carrera": limpiar(carrera) or "No disponible",
                "division": limpiar(division) or "No disponible",
                "creado_en": fecha_hora_actual(),
            },
        )
        total += 1
    return total


def importar_capacitaciones_mysql(conexion, ruta: Path, tipo: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        curso = normalizar_nombre_curso(tipo, obtener_valor(fila, "curso"))
        modalidad = obtener_valor(fila, "modalidad")
        if not curso or not modalidad:
            continue

        upsert_capacitacion_mysql(
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
            fuente=obtener_valor(fila, "origen", "fuente") or "csv_historico",
            archivo_origen=ruta.name,
        )
        total += 1
    return total


def insertar_auxiliar_mysql(conexion, tabla: str, *, tipo: str, fila: dict[str, Any]) -> None:
    if tabla not in {"pendientes_revision", "descartados"}:
        raise ValueError("Tabla auxiliar inválida")

    ejecutar(
        conexion,
        f"""
        INSERT INTO {tabla} (
            tipo, id_externo, nombre, correo, carrera, division, curso, modalidad,
            fecha_actualizacion, duracion, minutos_num, motivo, archivo_origen, hora_unio, creado_en
        ) VALUES (
            :tipo, :id_externo, :nombre, :correo, :carrera, :division, :curso, :modalidad,
            :fecha_actualizacion, :duracion, :minutos_num, :motivo, :archivo_origen, :hora_unio, :creado_en
        )
        """,
        {
            "tipo": limpiar(tipo).lower(),
            "id_externo": obtener_valor(fila, "id", "id_externo"),
            "nombre": obtener_valor(fila, "nombre"),
            "correo": normalizar_correo(obtener_valor(fila, "correo")),
            "carrera": obtener_valor(fila, "carrera") or "No disponible",
            "division": obtener_valor(fila, "division", "dirección", "direccion") or "No disponible",
            "curso": normalizar_nombre_curso(tipo, obtener_valor(fila, "curso")),
            "modalidad": obtener_valor(fila, "modalidad"),
            "fecha_actualizacion": fecha_iso(obtener_valor(fila, "fecha_actualizacion", "fecha")),
            "duracion": obtener_valor(fila, "duracion", "duración"),
            "minutos_num": _float_or_none(obtener_valor(fila, "minutos_num")),
            "motivo": obtener_valor(fila, "motivo"),
            "archivo_origen": obtener_valor(fila, "archivo_origen"),
            "hora_unio": obtener_valor(fila, "hora_unio", "hora a la que se unió"),
            "creado_en": fecha_hora_actual(),
        },
    )


def importar_auxiliares_mysql(conexion, ruta: Path, tipo: str, tabla: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        insertar_auxiliar_mysql(conexion, tabla, tipo=tipo, fila=fila)
        total += 1
    return total


def importar_ingestas_mysql(conexion, ruta: Path) -> int:
    total = 0
    for fila in leer_csv(ruta):
        mensaje_id = obtener_valor(fila, "mensaje_id", "mensaje id")
        recurso_id = obtener_valor(fila, "recurso_id", "recurso id")
        archivo = obtener_valor(fila, "archivo")
        key = "|".join([mensaje_id, recurso_id, archivo]) or f"sin_key|{fecha_hora_actual()}"
        ahora = fecha_hora_actual()

        ejecutar(
            conexion,
            """
            INSERT INTO ingestas (
                ingesta_key, tipo, mensaje_id, recurso_id, archivo, origen, asunto,
                fecha_reunion, fecha_descarga, estado, detalle, creado_en, actualizado_en
            ) VALUES (
                :ingesta_key, :tipo, :mensaje_id, :recurso_id, :archivo, :origen, :asunto,
                :fecha_reunion, :fecha_descarga, :estado, :detalle, :creado_en, :actualizado_en
            )
            ON DUPLICATE KEY UPDATE
                estado = VALUES(estado),
                detalle = VALUES(detalle),
                actualizado_en = VALUES(actualizado_en)
            """,
            {
                "ingesta_key": key,
                "tipo": obtener_valor(fila, "tipo"),
                "mensaje_id": mensaje_id,
                "recurso_id": recurso_id,
                "archivo": archivo,
                "origen": obtener_valor(fila, "origen"),
                "asunto": obtener_valor(fila, "asunto"),
                "fecha_reunion": fecha_iso(obtener_valor(fila, "fecha_reunion")),
                "fecha_descarga": obtener_valor(fila, "fecha_descarga"),
                "estado": obtener_valor(fila, "estado"),
                "detalle": obtener_valor(fila, "detalle"),
                "creado_en": ahora,
                "actualizado_en": ahora,
            },
        )
        total += 1
    return total


def importar_horarios_maestros_mysql(conexion, ruta: Path = MAESTROS_HORARIOS_PATH) -> int:
    total = 0
    for fila in leer_csv(ruta):
        curso = normalizar_nombre_curso("maestro", obtener_valor(fila, "curso"))
        if not curso:
            continue

        curso_id = upsert_curso_mysql(conexion, tipo="maestro", nombre=curso)
        ahora = fecha_hora_actual()
        ejecutar(
            conexion,
            """
            INSERT INTO sesiones (
                tipo, curso_key, curso, modalidad, fecha, hora_inicio, hora_fin, fuente,
                archivo_origen, creado_en, actualizado_en
            ) VALUES (
                :tipo, :curso_key, :curso, :modalidad, :fecha, :hora_inicio, :hora_fin,
                :fuente, :archivo_origen, :creado_en, :actualizado_en
            )
            """,
            {
                "tipo": "maestro",
                "curso_key": curso_id,
                "curso": curso,
                "modalidad": obtener_valor(fila, "modalidad") or "A distancia",
                "fecha": fecha_iso(obtener_valor(fila, "fecha")),
                "hora_inicio": obtener_valor(fila, "hora_inicio", "hora inicio"),
                "hora_fin": obtener_valor(fila, "hora_fin", "hora fin"),
                "fuente": "horarios_cursos",
                "archivo_origen": ruta.name,
                "creado_en": ahora,
                "actualizado_en": ahora,
            },
        )
        total += 1
    return total


def resumen_mysql(conexion) -> dict[str, int]:
    tablas = [
        "personas",
        "usuarios_base",
        "cursos",
        "sesiones",
        "capacitaciones",
        "pendientes_revision",
        "descartados",
        "ingestas",
    ]
    return {
        tabla: ejecutar(conexion, f"SELECT COUNT(*) FROM {tabla}").scalar_one()
        for tabla in tablas
    }


def migrar_csv_a_mysql(reiniciar: bool = True) -> dict[str, int]:
    engine = crear_engine_mysql()
    with engine.begin() as conexion:
        inicializar_mysql(conexion)
        capacitaciones_api_preservadas = leer_capacitaciones_api_persistentes_mysql(conexion) if reiniciar else []
        pendientes_api_preservados = leer_auxiliares_api_persistentes_mysql(conexion, "pendientes_revision") if reiniciar else []
        descartados_api_preservados = leer_auxiliares_api_persistentes_mysql(conexion, "descartados") if reiniciar else []

        if reiniciar:
            reiniciar_mysql(conexion)

        cursos_base_total = importar_cursos_base_mysql(conexion)
        resultado = {
            "cursos_base": cursos_base_total,
            "cursos_base_maestros": len(CURSOS_MAESTROS),
            "cursos_base_alumnos": 1,
            "usuarios_maestros": importar_usuarios_mysql(conexion, MAESTROS_USUARIOS_PATH, "maestro"),
            "usuarios_alumnos": importar_usuarios_mysql(conexion, ALUMNOS_USUARIOS_PATH, "alumno"),
            "capacitaciones_maestros": importar_capacitaciones_mysql(conexion, MAESTROS_CAPACITACIONES_PATH, "maestro"),
            "capacitaciones_alumnos": importar_capacitaciones_mysql(conexion, ALUMNOS_CAPACITACIONES_PATH, "alumno"),
            "horarios_maestros": importar_horarios_maestros_mysql(conexion),
            "pendientes_maestros": importar_auxiliares_mysql(conexion, MAESTROS_PENDIENTES_MEET_PATH, "maestro", "pendientes_revision"),
            "descartados_maestros": importar_auxiliares_mysql(conexion, MAESTROS_DESCARTADOS_MEET_PATH, "maestro", "descartados"),
            "pendientes_alumnos": importar_auxiliares_mysql(conexion, ALUMNOS_PENDIENTES_PATH, "alumno", "pendientes_revision"),
            "descartados_alumnos": importar_auxiliares_mysql(conexion, ALUMNOS_DESCARTADOS_PATH, "alumno", "descartados"),
            "ingestas_meet": importar_ingestas_mysql(conexion, ALUMNOS_MEET_DESCARGADOS_PATH),
        }

        resultado["capacitaciones_api_preservadas"] = restaurar_capacitaciones_api_persistentes_mysql(conexion, capacitaciones_api_preservadas)
        resultado["pendientes_api_preservados"] = restaurar_auxiliares_api_persistentes_mysql(conexion, "pendientes_revision", pendientes_api_preservados)
        resultado["descartados_api_preservados"] = restaurar_auxiliares_api_persistentes_mysql(conexion, "descartados", descartados_api_preservados)

        resultado.update({f"tabla_{tabla}": total for tabla, total in resumen_mysql(conexion).items()})
        return resultado


def leer_usuarios_reporte_mysql(tipo: str) -> list[dict[str, str]]:
    engine = crear_engine_mysql()
    tipo = limpiar(tipo).lower()
    with engine.begin() as conexion:
        inicializar_mysql(conexion)
        filas = ejecutar(
            conexion,
            """
            SELECT id_externo, nombre, correo, carrera, division
            FROM usuarios_base
            WHERE tipo = :tipo
            ORDER BY nombre
            """,
            {"tipo": tipo},
        ).mappings().all()

    return [
        {
            "id": limpiar(fila["id_externo"]),
            "nombre": limpiar(fila["nombre"]),
            "correo": normalizar_correo(fila["correo"]),
            "carrera": limpiar(fila["carrera"]) or "No disponible",
            "division": limpiar(fila["division"]) or "No disponible",
        }
        for fila in filas
        if limpiar(fila["id_externo"]) or limpiar(fila["nombre"]) or limpiar(fila["correo"])
    ]


def leer_capacitaciones_reporte_mysql(tipo: str) -> list[dict[str, str]]:
    engine = crear_engine_mysql()
    tipo = limpiar(tipo).lower()
    with engine.begin() as conexion:
        inicializar_mysql(conexion)
        filas = ejecutar(
            conexion,
            """
            SELECT id_externo, nombre, correo, carrera, division, curso, modalidad, fecha_actualizacion, fuente, archivo_origen
            FROM capacitaciones
            WHERE tipo = :tipo
            ORDER BY fecha_actualizacion DESC, actualizado_en DESC
            """,
            {"tipo": tipo},
        ).mappings().all()

    return [
        {
            "id": limpiar(fila["id_externo"]),
            "nombre": limpiar(fila["nombre"]),
            "correo": normalizar_correo(fila["correo"]),
            "carrera": limpiar(fila["carrera"]) or "No disponible",
            "division": limpiar(fila["division"]) or "No disponible",
            "curso": limpiar(fila["curso"]),
            "modalidad": limpiar(fila["modalidad"]),
            "fecha_actualizacion": fecha_para_reporte(fila["fecha_actualizacion"]),
            "origen": limpiar(fila.get("fuente", "")) if hasattr(fila, "get") else limpiar(fila["fuente"]),
            "archivo_origen": limpiar(fila.get("archivo_origen", "")) if hasattr(fila, "get") else limpiar(fila["archivo_origen"]),
        }
        for fila in filas
        if (limpiar(fila["id_externo"]) or limpiar(fila["nombre"]) or limpiar(fila["correo"]))
        and limpiar(fila["curso"])
        and limpiar(fila["modalidad"])
    ]



def leer_ingestas_recientes_mysql(limite: int = 12) -> list[dict[str, Any]]:
    engine = crear_engine_mysql()
    with engine.connect() as conexion:
        result = ejecutar(
            conexion,
            """
            SELECT
                ingesta_key, tipo, mensaje_id, recurso_id, archivo, origen, asunto,
                fecha_reunion, fecha_descarga, estado, detalle, creado_en, actualizado_en
            FROM ingestas
            WHERE LOWER(COALESCE(origen, '')) IN ('api_directa', 'api_capacitaciones', 'api_capacitaciones_en_linea')
            ORDER BY actualizado_en DESC, creado_en DESC
            LIMIT :limite
            """,
            {"limite": limite},
        )
        return [dict(row._mapping) for row in result]

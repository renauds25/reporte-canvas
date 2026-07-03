from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from datetime import datetime

from sqlalchemy import create_engine, text

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
    obtener_valor,
    persona_key,
)

BASE_DIR = Path(__file__).resolve().parent


def normalizar_database_url(url: str | None = None) -> str:
    raw = (url or os.getenv("DATABASE_URL") or "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL no está definido.")

    # Render y Heroku a veces entregan postgres://; SQLAlchemy prefiere postgresql+psycopg2://
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg2://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg2://" + raw[len("postgresql://"):]

    return raw


def crear_engine_postgres(url: str | None = None):
    return create_engine(
        normalizar_database_url(url),
        pool_pre_ping=True,
        future=True,
    )


def ejecutar(conexion, sql: str, params: dict[str, Any] | None = None):
    return conexion.execute(text(sql), params or {})


def inicializar_postgres(conexion) -> None:
    sentencias = [
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
            es_base INTEGER NOT NULL DEFAULT 0,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_personas_tipo ON personas(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_personas_correo ON personas(correo)",
        "CREATE INDEX IF NOT EXISTS idx_personas_id_externo ON personas(id_externo)",
        "CREATE INDEX IF NOT EXISTS idx_personas_tipo_es_base ON personas(tipo, es_base)",
        """
        CREATE TABLE IF NOT EXISTS usuarios_base (
            usuario_base_id SERIAL PRIMARY KEY,
            tipo TEXT NOT NULL,
            persona_key TEXT,
            id_externo TEXT,
            nombre TEXT,
            correo TEXT,
            carrera TEXT,
            division TEXT,
            creado_en TEXT NOT NULL,
            FOREIGN KEY(persona_key) REFERENCES personas(persona_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_usuarios_base_tipo ON usuarios_base(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_usuarios_base_correo ON usuarios_base(correo)",
        "CREATE INDEX IF NOT EXISTS idx_usuarios_base_id_externo ON usuarios_base(id_externo)",
        """
        CREATE TABLE IF NOT EXISTS cursos (
            curso_key TEXT PRIMARY KEY,
            tipo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            orden INTEGER,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_cursos_tipo ON cursos(tipo)",
        """
        CREATE TABLE IF NOT EXISTS sesiones (
            sesion_id SERIAL PRIMARY KEY,
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
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_sesiones_tipo_fecha ON sesiones(tipo, fecha)",
        "CREATE INDEX IF NOT EXISTS idx_sesiones_curso ON sesiones(curso_key)",
        """
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
            duracion_minutos DOUBLE PRECISION,
            fuente TEXT,
            archivo_origen TEXT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY(persona_key) REFERENCES personas(persona_key),
            FOREIGN KEY(curso_key) REFERENCES cursos(curso_key),
            FOREIGN KEY(sesion_id) REFERENCES sesiones(sesion_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_capacitaciones_tipo ON capacitaciones(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_capacitaciones_persona ON capacitaciones(persona_key)",
        "CREATE INDEX IF NOT EXISTS idx_capacitaciones_curso ON capacitaciones(curso_key)",
        """
        CREATE TABLE IF NOT EXISTS pendientes_revision (
            pendiente_id SERIAL PRIMARY KEY,
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
            minutos_num DOUBLE PRECISION,
            motivo TEXT,
            archivo_origen TEXT,
            hora_unio TEXT,
            creado_en TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_pendientes_tipo ON pendientes_revision(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_pendientes_motivo ON pendientes_revision(motivo)",
        """
        CREATE TABLE IF NOT EXISTS descartados (
            descartado_id SERIAL PRIMARY KEY,
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
            minutos_num DOUBLE PRECISION,
            motivo TEXT,
            archivo_origen TEXT,
            hora_unio TEXT,
            creado_en TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_descartados_tipo ON descartados(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_descartados_motivo ON descartados(motivo)",
        """
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
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ingestas_tipo_estado ON ingestas(tipo, estado)",
    ]

    for sentencia in sentencias:
        ejecutar(conexion, sentencia)


def reiniciar_postgres(conexion) -> None:
    ejecutar(
        conexion,
        """
        TRUNCATE TABLE
            descartados,
            pendientes_revision,
            capacitaciones,
            sesiones,
            cursos,
            usuarios_base,
            personas,
            ingestas
        RESTART IDENTITY CASCADE
        """,
    )


def upsert_persona_pg(
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
        ON CONFLICT(persona_key) DO UPDATE SET
            id_externo = COALESCE(NULLIF(EXCLUDED.id_externo, ''), personas.id_externo),
            nombre = COALESCE(NULLIF(EXCLUDED.nombre, ''), personas.nombre),
            correo = COALESCE(NULLIF(EXCLUDED.correo, ''), personas.correo),
            carrera = CASE
                WHEN EXCLUDED.carrera != '' AND EXCLUDED.carrera != 'No disponible' THEN EXCLUDED.carrera
                ELSE personas.carrera
            END,
            division = CASE
                WHEN EXCLUDED.division != '' AND EXCLUDED.division != 'No disponible' THEN EXCLUDED.division
                ELSE personas.division
            END,
            es_base = CASE
                WHEN EXCLUDED.es_base = 1 THEN 1
                ELSE personas.es_base
            END,
            actualizado_en = EXCLUDED.actualizado_en
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


def upsert_curso_pg(conexion, *, tipo: str, nombre: str, orden: int | None = None) -> str:
    tipo = limpiar(tipo).lower()
    nombre = limpiar(nombre)
    if not nombre:
        return ""

    key = curso_key(tipo, nombre)
    ahora = fecha_hora_actual()

    ejecutar(
        conexion,
        """
        INSERT INTO cursos (curso_key, tipo, nombre, orden, creado_en, actualizado_en)
        VALUES (:curso_key, :tipo, :nombre, :orden, :creado_en, :actualizado_en)
        ON CONFLICT(curso_key) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            orden = COALESCE(EXCLUDED.orden, cursos.orden),
            actualizado_en = EXCLUDED.actualizado_en
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


def upsert_capacitacion_pg(
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
    persona = upsert_persona_pg(
        conexion,
        tipo=tipo,
        id_externo=id_externo,
        nombre=nombre,
        correo=correo,
        carrera=carrera,
        division=division,
    )
    curso_id = upsert_curso_pg(conexion, tipo=tipo, nombre=curso)
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
        ON CONFLICT(capacitacion_key) DO UPDATE SET
            persona_key = EXCLUDED.persona_key,
            curso_key = EXCLUDED.curso_key,
            id_externo = COALESCE(NULLIF(EXCLUDED.id_externo, ''), capacitaciones.id_externo),
            nombre = COALESCE(NULLIF(EXCLUDED.nombre, ''), capacitaciones.nombre),
            correo = COALESCE(NULLIF(EXCLUDED.correo, ''), capacitaciones.correo),
            carrera = COALESCE(NULLIF(EXCLUDED.carrera, ''), capacitaciones.carrera),
            division = COALESCE(NULLIF(EXCLUDED.division, ''), capacitaciones.division),
            fecha_actualizacion = CASE
                WHEN COALESCE(EXCLUDED.fecha_actualizacion, '') >= COALESCE(capacitaciones.fecha_actualizacion, '') THEN EXCLUDED.fecha_actualizacion
                ELSE capacitaciones.fecha_actualizacion
            END,
            duracion_minutos = COALESCE(EXCLUDED.duracion_minutos, capacitaciones.duracion_minutos),
            fuente = EXCLUDED.fuente,
            archivo_origen = COALESCE(NULLIF(EXCLUDED.archivo_origen, ''), capacitaciones.archivo_origen),
            actualizado_en = EXCLUDED.actualizado_en
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


def importar_cursos_base_pg(conexion) -> int:
    total = 0
    for orden, curso in enumerate(CURSOS_MAESTROS, start=1):
        upsert_curso_pg(conexion, tipo="maestro", nombre=curso, orden=orden)
        total += 1
    upsert_curso_pg(conexion, tipo="alumno", nombre=CURSO_ALUMNOS, orden=1)
    total += 1
    return total


def importar_usuarios_pg(conexion, ruta: Path, tipo: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        id_externo = obtener_valor(fila, "id", "idPerson", "matricula", "matrícula")
        nombre = obtener_valor(fila, "nombre", "Nombre")
        correo = obtener_valor(fila, "correo", "correo electrónico", "email")
        carrera = obtener_valor(fila, "carrera")
        division = obtener_valor(fila, "division", "dirección", "direccion")

        if not any([id_externo, nombre, correo]):
            continue

        key = upsert_persona_pg(
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


def importar_capacitaciones_pg(conexion, ruta: Path, tipo: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        curso = obtener_valor(fila, "curso")
        modalidad = obtener_valor(fila, "modalidad")
        if not curso or not modalidad:
            continue

        upsert_capacitacion_pg(
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


def insertar_auxiliar_pg(conexion, tabla: str, *, tipo: str, fila: dict[str, Any]) -> None:
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
            "curso": obtener_valor(fila, "curso"),
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


def importar_auxiliares_pg(conexion, ruta: Path, tipo: str, tabla: str) -> int:
    total = 0
    for fila in leer_csv(ruta):
        insertar_auxiliar_pg(conexion, tabla, tipo=tipo, fila=fila)
        total += 1
    return total


def importar_ingestas_pg(conexion, ruta: Path) -> int:
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
            ON CONFLICT(ingesta_key) DO UPDATE SET
                estado = EXCLUDED.estado,
                detalle = EXCLUDED.detalle,
                actualizado_en = EXCLUDED.actualizado_en
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


def importar_horarios_maestros_pg(conexion, ruta: Path = MAESTROS_HORARIOS_PATH) -> int:
    total = 0
    for fila in leer_csv(ruta):
        curso = obtener_valor(fila, "curso")
        if not curso:
            continue

        curso_id = upsert_curso_pg(conexion, tipo="maestro", nombre=curso)
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


def resumen_postgres(conexion) -> dict[str, int]:
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


def migrar_csv_a_postgres(reiniciar: bool = True) -> dict[str, int]:
    engine = crear_engine_postgres()
    with engine.begin() as conexion:
        inicializar_postgres(conexion)
        if reiniciar:
            reiniciar_postgres(conexion)

        resultado = {
            "cursos_base": importar_cursos_base_pg(conexion),
            "usuarios_maestros": importar_usuarios_pg(conexion, MAESTROS_USUARIOS_PATH, "maestro"),
            "usuarios_alumnos": importar_usuarios_pg(conexion, ALUMNOS_USUARIOS_PATH, "alumno"),
            "capacitaciones_maestros": importar_capacitaciones_pg(conexion, MAESTROS_CAPACITACIONES_PATH, "maestro"),
            "capacitaciones_alumnos": importar_capacitaciones_pg(conexion, ALUMNOS_CAPACITACIONES_PATH, "alumno"),
            "horarios_maestros": importar_horarios_maestros_pg(conexion),
            "pendientes_maestros": importar_auxiliares_pg(conexion, MAESTROS_PENDIENTES_MEET_PATH, "maestro", "pendientes_revision"),
            "descartados_maestros": importar_auxiliares_pg(conexion, MAESTROS_DESCARTADOS_MEET_PATH, "maestro", "descartados"),
            "pendientes_alumnos": importar_auxiliares_pg(conexion, ALUMNOS_PENDIENTES_PATH, "alumno", "pendientes_revision"),
            "descartados_alumnos": importar_auxiliares_pg(conexion, ALUMNOS_DESCARTADOS_PATH, "alumno", "descartados"),
            "ingestas_meet": importar_ingestas_pg(conexion, ALUMNOS_MEET_DESCARGADOS_PATH),
        }
        resultado.update({f"tabla_{tabla}": total for tabla, total in resumen_postgres(conexion).items()})
        return resultado


def leer_usuarios_reporte_postgres(tipo: str) -> list[dict[str, str]]:
    engine = crear_engine_postgres()
    tipo = limpiar(tipo).lower()
    with engine.begin() as conexion:
        inicializar_postgres(conexion)
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


def leer_capacitaciones_reporte_postgres(tipo: str) -> list[dict[str, str]]:
    engine = crear_engine_postgres()
    tipo = limpiar(tipo).lower()
    with engine.begin() as conexion:
        inicializar_postgres(conexion)
        filas = ejecutar(
            conexion,
            """
            SELECT id_externo, nombre, correo, carrera, division, curso, modalidad, fecha_actualizacion
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
        }
        for fila in filas
        if (limpiar(fila["id_externo"]) or limpiar(fila["nombre"]) or limpiar(fila["correo"]))
        and limpiar(fila["curso"])
        and limpiar(fila["modalidad"])
    ]

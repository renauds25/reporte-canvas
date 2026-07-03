from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from database import (  # noqa: E402
    ALUMNOS_CAPACITACIONES_PATH,
    ALUMNOS_DESCARTADOS_PATH,
    ALUMNOS_MEET_DESCARGADOS_PATH,
    ALUMNOS_PENDIENTES_PATH,
    ALUMNOS_USUARIOS_PATH,
    DATABASE_PATH,
    MAESTROS_CAPACITACIONES_PATH,
    MAESTROS_DESCARTADOS_MEET_PATH,
    MAESTROS_PENDIENTES_MEET_PATH,
    MAESTROS_USUARIOS_PATH,
    conectar_bd,
    importar_auxiliares,
    importar_capacitaciones,
    importar_cursos_base,
    importar_horarios_maestros,
    importar_ingestas,
    importar_usuarios,
    inicializar_bd,
    reiniciar_datos,
    resumen_bd,
)


def usar_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


def migrar_csv_a_sqlite(reiniciar: bool = True, db_path: Path = DATABASE_PATH) -> dict[str, int]:
    with conectar_bd(db_path) as conexion:
        inicializar_bd(conexion)
        if reiniciar:
            reiniciar_datos(conexion)

        resultado = {
            "backend": "sqlite",
            "cursos_base": importar_cursos_base(conexion),
            "usuarios_maestros": importar_usuarios(conexion, MAESTROS_USUARIOS_PATH, "maestro"),
            "usuarios_alumnos": importar_usuarios(conexion, ALUMNOS_USUARIOS_PATH, "alumno"),
            "capacitaciones_maestros": importar_capacitaciones(conexion, MAESTROS_CAPACITACIONES_PATH, "maestro"),
            "capacitaciones_alumnos": importar_capacitaciones(conexion, ALUMNOS_CAPACITACIONES_PATH, "alumno"),
            "horarios_maestros": importar_horarios_maestros(conexion),
            "pendientes_maestros": importar_auxiliares(conexion, MAESTROS_PENDIENTES_MEET_PATH, "maestro", "pendientes_revision"),
            "descartados_maestros": importar_auxiliares(conexion, MAESTROS_DESCARTADOS_MEET_PATH, "maestro", "descartados"),
            "pendientes_alumnos": importar_auxiliares(conexion, ALUMNOS_PENDIENTES_PATH, "alumno", "pendientes_revision"),
            "descartados_alumnos": importar_auxiliares(conexion, ALUMNOS_DESCARTADOS_PATH, "alumno", "descartados"),
            "ingestas_meet": importar_ingestas(conexion, ALUMNOS_MEET_DESCARGADOS_PATH),
        }
        resultado.update({f"tabla_{tabla}": total for tabla, total in resumen_bd(conexion).items()})
        return resultado


def migrar_csv_a_bd(reiniciar: bool = True, db_path: Path = DATABASE_PATH) -> dict[str, int]:
    if usar_postgres():
        from database_postgres import migrar_csv_a_postgres

        resultado = migrar_csv_a_postgres(reiniciar=reiniciar)
        resultado["backend"] = "postgresql"
        return resultado

    return migrar_csv_a_sqlite(reiniciar=reiniciar, db_path=db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra los CSV actuales a la base de datos configurada.")
    parser.add_argument(
        "--append",
        action="store_true",
        help="No borra los datos actuales de la BD antes de importar. Por defecto se reinicia la BD.",
    )
    parser.add_argument(
        "--db",
        default=str(DATABASE_PATH),
        help="Ruta del archivo SQLite cuando no se usa DATABASE_URL. Por defecto: data/reporte_canvas.db",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    resultado = migrar_csv_a_bd(reiniciar=not args.append, db_path=db_path)

    if usar_postgres():
        print("Base de datos PostgreSQL generada/actualizada desde DATABASE_URL.")
    else:
        print(f"Base de datos SQLite generada/actualizada: {db_path}")

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

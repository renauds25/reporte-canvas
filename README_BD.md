# Base de datos local SQLite

Esta fase agrega una base local SQLite sin reemplazar todavía el flujo actual de CSV.

La app sigue funcionando con los CSV como fuente principal. La BD se usa como respaldo estructurado y como preparación para migrar después a una base de datos de producción.

## Archivo generado

La migración crea este archivo:

```text
data/reporte_canvas.db
```

Ese archivo es local y no se debe subir a GitHub.

## Crear o actualizar la BD manualmente

Desde la carpeta del proyecto:

```bat
python migrar_csv_a_bd.py
```

o también:

```bat
python app.py migrar-bd
```

Ambos comandos toman los CSV actuales y llenan las tablas:

```text
personas
cursos
sesiones
capacitaciones
pendientes_revision
descartados
ingestas
```

Por defecto, la migración limpia la BD y la vuelve a crear desde los CSV actuales. Esto es correcto en esta fase porque los CSV siguen siendo la fuente principal.

## Sincronización automática después de Meet

A partir de esta versión, cuando se ejecuta:

```bat
python app.py actualizar-meet
```

el sistema hace dos cosas:

```text
1. Descarga y procesa los reportes nuevos de Meet.
2. Sincroniza data/reporte_canvas.db desde los CSV actualizados.
```

Por lo tanto, también queda sincronizada cuando corre:

```bat
actualizar_meet.bat
```

La BD no reemplaza todavía los CSV; queda actualizada como respaldo y preparación para la siguiente fase.

## Sincronizar solo la BD

Si quieres actualizar únicamente la BD desde los CSV actuales, sin tocar Gmail:

```bat
python app.py sincronizar-bd
```

También funcionan estos alias:

```bat
python app.py migrar-bd
python app.py bd
python app.py db
```

## Importar sin borrar lo que ya existe

Si quieres importar encima sin borrar:

```bat
python migrar_csv_a_bd.py --append
```

## Validación rápida

Después de migrar, puedes revisar conteos con:

```bat
python -c "import sqlite3; con=sqlite3.connect('data/reporte_canvas.db'); print(con.execute('select count(*) from capacitaciones').fetchone()[0]); con.close()"
```

## Siguiente fase

Después de validar la sincronización, el siguiente paso será hacer que:

```text
Gmail/Meet → guarde directo en BD → exporte CSV de respaldo
```

y después que el reporte lea directamente desde la BD.


## Lectura del reporte desde SQLite

A partir de esta versión, la app intenta leer los reportes desde:

```text
data/reporte_canvas.db
```

Si la base no existe, está vacía o ocurre un error al leerla, la app vuelve automáticamente a los CSV como respaldo.

Para desactivar temporalmente la lectura desde BD y forzar CSV, agrega en `.env`:

```env
READ_REPORTS_FROM_DB=0
```

Para volver a usar SQLite:

```env
READ_REPORTS_FROM_DB=1
```

Cada vez que se ejecuta:

```bat
python app.py actualizar-meet
```

el sistema actualiza los CSV y después sincroniza la BD. También puedes sincronizar solo la BD con:

```bat
python app.py sincronizar-bd
```

La tabla `usuarios_base` conserva la lista base completa de usuarios de maestros y alumnos, mientras que `personas` guarda las personas normalizadas para cruces y deduplicación interna.


---

# Modo híbrido SQLite / PostgreSQL

A partir de esta versión, el proyecto puede trabajar con dos motores de base de datos:

```text
Local sin configuración extra → SQLite
Render / producción con DATABASE_URL → PostgreSQL
```

## Cómo decide qué base usar

La app revisa la variable de entorno:

```env
DATABASE_URL=
```

Si `DATABASE_URL` existe y tiene valor, usa PostgreSQL.

Si `DATABASE_URL` no existe, usa SQLite local:

```text
data/reporte_canvas.db
```

## Flujo recomendado

```text
Desarrollo local:
CSV → SQLite → reporte local

Producción en Render:
CSV / automatización Meet → PostgreSQL → reporte en Render
```

Los CSV siguen existiendo como respaldo y como fuente de sincronización.

## Dependencias nuevas

Se agregaron estas dependencias:

```text
SQLAlchemy
psycopg[binary]
```

Instálalas con:

```bat
python -m pip install -r requirements.txt
```

## Probar local con SQLite

Sin configurar `DATABASE_URL`, corre:

```bat
python app.py sincronizar-bd
python app.py
```

Debe seguir usando:

```text
data/reporte_canvas.db
```

## Probar con PostgreSQL

Cuando tengas una base PostgreSQL, agrega en `.env` algo como:

```env
DATABASE_URL=postgresql://usuario:password@host:puerto/base
```

También acepta URLs tipo:

```env
DATABASE_URL=postgres://usuario:password@host:puerto/base
```

El sistema las normaliza automáticamente para SQLAlchemy usando el driver `psycopg` de Psycopg 3.

Después corre:

```bat
python app.py sincronizar-bd
```

Eso creará las tablas en PostgreSQL y cargará los datos desde los CSV.

## En Render

En Render se debe configurar la variable de entorno:

```env
DATABASE_URL=<Internal Database URL de Render PostgreSQL>
```

La app detectará esa variable y usará PostgreSQL en lugar de SQLite.

## Nota importante

SQLite sigue siendo útil para pruebas locales, pero para Render conviene usar PostgreSQL porque los archivos locales del servidor pueden perderse o reiniciarse con despliegues. La base PostgreSQL persiste fuera del sistema de archivos del servicio web.

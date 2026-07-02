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

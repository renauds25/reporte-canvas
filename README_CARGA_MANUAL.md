# Carga manual de datos

El sistema ya usa PostgreSQL/SQLite como base de datos, pero los CSV siguen siendo el respaldo editable y la forma más segura de corregir datos manualmente.

## Regla recomendada

No edites la base de datos directamente, salvo que sea una emergencia técnica.

Flujo recomendado:

1. Edita o reemplaza el CSV correspondiente.
2. Corre `python app.py sincronizar-bd`.
3. La app actualiza la base de datos desde los CSV.
4. La app regenera el cache de reportes.

## Qué archivo editar según el caso

### Agregar o corregir maestros

Edita:

```text
data/usuarios.csv
```

Columnas esperadas:

```csv
id,nombre,correo,carrera,division
```

Después corre:

```bat
python app.py sincronizar-bd
```

### Agregar o corregir alumnos

Edita:

```text
data/alumnos/usuarios.csv
```

Columnas esperadas:

```csv
id,nombre,correo
```

Después corre:

```bat
python app.py sincronizar-bd
```

### Agregar una capacitación manual de maestros

Edita:

```text
data/capacitaciones.csv
```

Columnas esperadas:

```csv
id,nombre,correo,carrera,division,curso,modalidad,fecha_actualizacion
```

Después corre:

```bat
python app.py sincronizar-bd
```

### Agregar una capacitación manual de alumnos

Edita:

```text
data/alumnos/capacitaciones.csv
```

Columnas esperadas:

```csv
id,nombre,correo,curso,modalidad,fecha_actualizacion
```

Después corre:

```bat
python app.py sincronizar-bd
```

### Agregar o corregir horarios de maestros

Edita:

```text
data/maestros/horarios_cursos.csv
```

Columnas esperadas:

```csv
curso,modalidad,fecha,hora_inicio,hora_fin
```

Usa fecha en formato:

```text
AAAA-MM-DD
```

Ejemplo:

```csv
CANVAS 6. EXÁMENES Y SPEEDGRADER.,A distancia,2026-08-25,09:00,12:00
```

Después corre:

```bat
python app.py sincronizar-bd
```

## Carga desde el panel admin

También puedes usar `/admin/panel` para subir CSV de usuarios, capacitaciones o asistencia Meet. Cuando subes desde el panel, el sistema también sincroniza la base de datos y regenera el cache.

## Base de datos directa

La base de datos no se recomienda para edición manual diaria porque puedes saltarte validaciones, duplicar llaves o dejar datos inconsistentes.

La base de datos debe ser la fuente consultada por la página, pero los cambios manuales deben entrar por CSV o por el panel admin.

## Verificar actualizaciones API

En `/admin/panel` aparece la sección:

```text
Historial de actualizaciones Meet
```

Ahí puedes revisar si un envío de Apps Script llegó, si fue procesado y cuántos registros fueron válidos, pendientes o descartados.

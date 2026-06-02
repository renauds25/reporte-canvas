# Reporte Integral de Capacitaciones Canvas LMS

Aplicación Flask para mostrar un reporte de capacitaciones Canvas LMS desde archivos CSV.

## Ejecutar localmente

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Reporte:

```text
http://127.0.0.1:5000
```

Panel admin:

```text
http://127.0.0.1:5000/admin
```

## Acceso al reporte

La página principal pide contraseña.

Contraseña local por defecto:

```text
canvas-2026
```

En Render se recomienda configurarla como variable de entorno:

```text
REPORT_PASSWORD=tu_contraseña
SECRET_KEY=una_clave_larga_aleatoria
```

## Acceso admin

Contraseña local por defecto:

```text
hgjt8329
```

En Render se recomienda configurarla como variable de entorno:

```text
ADMIN_PASSWORD=tu_contraseña_admin
```

## CSV de capacitaciones

Formato recomendado:

```csv
id,nombre,correo,curso,modalidad,fecha_actualizacion
```

También funciona sin correo:

```csv
id,nombre,curso,modalidad,fecha_actualizacion
```

## CSV de usuarios

Formato para base maestra:

```csv
id,nombre,correo
```

## Notas de conteo

- Las listas muestran todos los registros por modalidad.
- El total de cursos registrados cuenta cursos únicos por persona usando `id + curso`.
- El avance por curso cuenta usuarios únicos por curso.

# Reporte Integral de Capacitaciones Canvas LMS

Aplicación Flask para mostrar un reporte público de capacitaciones Canvas LMS desde archivos CSV.

## Ejecutar localmente

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Reporte público:

```text
http://127.0.0.1:5000
```

Panel admin:

```text
http://127.0.0.1:5000/admin
```

Contraseña inicial:

```text
canvas-admin
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

## Cambios de esta versión

- Color institucional naranja `#ff5900`.
- El reporte público no muestra el control de calidad de datos.
- La información sensible de ID y correo se oculta en las listas públicas.
- Cada curso muestra 15 registros por página.
- Los seis cursos se muestran en tarjetas: 1, 2 y 3 arriba; 4, 5 y 6 abajo en pantalla amplia.
- El panel admin conserva la descarga de registros que no coinciden y usuarios sin iniciar.

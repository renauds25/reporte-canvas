# API privada para recibir asistencias de Google Meet

Esta fase permite que Apps Script mande el CSV de asistencia directo a la app, sin reenviar correos a `ct3d` ni depender del botón/descarga desde Gmail.

El flujo nuevo queda así:

```text
Google Meet genera asistencia
↓
Apps Script en cte/cie abre el Google Sheet
↓
Apps Script convierte la asistencia a CSV
↓
Apps Script envía el CSV por POST a la app
↓
Flask procesa alumnos o maestros
↓
Actualiza CSV de respaldo
↓
Sincroniza SQLite/PostgreSQL
↓
Regenera cache de reportes
```

## Variables de entorno necesarias en Render

En el servicio web de Render agrega:

```env
MEET_API_TOKEN=un_token_largo_y_secreto
MEET_API_DIRECT_ENABLED=1
READ_REPORTS_FROM_DB=1
DATABASE_URL=Internal Database URL de Render Postgres
```

`MEET_API_TOKEN` debe ser el mismo valor que uses en Apps Script. No lo subas a GitHub.

## Endpoint nuevo

```text
POST /api/meet/asistencia
```

Acepta JSON con:

```json
{
  "tipo": "alumnos",
  "subject": "Registros de la reunión: 1 jul 2026 a las 5:10 PM CST",
  "ingesta_id": "id-unico-del-correo-o-reunion",
  "filename": "asistencia.csv",
  "csv": "Nombre,Apellido,Correo electrónico,Duración..."
}
```

También acepta `tipo = "maestros"`.

La autenticación va en header:

```text
Authorization: Bearer TU_TOKEN
```

Si `ingesta_id` se repite, la app no vuelve a procesar ese CSV.

## Prueba rápida local

En tu `.env` local puedes agregar temporalmente:

```env
MEET_API_TOKEN=prueba123
MEET_API_DIRECT_ENABLED=1
```

Luego ejecuta:

```bat
python app.py
```

Y prueba salud del endpoint:

```bat
curl http://127.0.0.1:5000/api/meet/health
```

## Apps Script directo

Usa el archivo:

```text
apps_script_meet_directo.gs
```

En cada cuenta origen cambia:

```javascript
const TIPO_REPORTE = "alumnos";
```

o:

```javascript
const TIPO_REPORTE = "maestros";
```

Recomendación:

```text
cie@iest.edu.mx → alumnos
cte@iest.edu.mx → maestros
```

En Apps Script configura una propiedad del script:

```text
MEET_API_TOKEN = el mismo token que pusiste en Render
```

Después ejecuta una vez `procesarReportesMeetDirecto()` para autorizar y prueba. Cuando funcione, puedes crear los activadores con `crearActivadoresJornada()`.

## Importante

Esta primera versión directa todavía conserva los CSV como respaldo y hace una sincronización completa a BD después de procesar cada CSV. Más adelante podemos optimizar para que el guardado sea directo a PostgreSQL y los CSV sean solo exportación.

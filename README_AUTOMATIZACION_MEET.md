# Automatización Google Meet para alumnos

Esta versión mantiene la carga manual de CSV de Google Meet y agrega una opción para descargar los reportes automáticamente desde Gmail.

## Archivos importantes

- `data/alumnos/usuarios.csv`: base de alumnos con columnas `id,nombre,correo`.
- `data/alumnos/capacitaciones.csv`: reporte curado de alumnos.
- `data/alumnos/pendientes_revision.csv`: registros con correo faltante, correo no encontrado en base o duración no válida.
- `data/alumnos/descartados_menos_30_min.csv`: registros menores a 30 minutos.
- `data/alumnos/insumos_meet/`: reportes descargados desde Gmail o subidos manualmente.
- `data/alumnos/meet_descargados.csv`: control de correos/reportes ya procesados para evitar duplicados.

## Instalación de dependencias

Ejecuta:

```bash
python -m pip install -r requirements.txt
```

## Configuración de Google

La automatización usa OAuth de Google. No usa ni guarda tu contraseña.

1. En Google Cloud, crea un proyecto.
2. Activa Gmail API y Google Drive API.
3. Crea credenciales OAuth de tipo aplicación de escritorio.
4. Descarga el archivo JSON.
5. Guárdalo en la raíz del proyecto con este nombre:

```text
credentials.json
```

El primer uso abrirá una ventana del navegador para autorizar el acceso. Después se generará:

```text
token_gmail.json
```

No subas `credentials.json` ni `token_gmail.json` a GitHub. Ya están agregados en `.gitignore`.

## Uso desde el panel admin

Entra al panel admin y usa la sección:

```text
Módulo alumnos → Automatización Gmail / Google Meet
```

La búsqueda predeterminada es:

```text
from:meetings-noreply@google.com subject:"Registros de la reunión" newer_than:60d
```

El sistema descarga reportes de Meet que vengan como adjunto CSV o como enlace de Google Sheets en el correo.

## Uso desde terminal

También puedes ejecutar:

```bash
python app.py descargar-meet-alumnos
```

O:

```bash
python app.py actualizar-alumnos
```

Ambos comandos descargan los reportes nuevos desde Gmail, los guardan en `data/alumnos/insumos_meet/` y actualizan el reporte de alumnos.

## Variables opcionales en `.env`

```env
ALUMNOS_CURSO_OFICIAL=CURSO DE ALUMNOS
ALUMNOS_MINUTOS_MINIMOS=30
GMAIL_MEET_QUERY=from:meetings-noreply@google.com subject:"Registros de la reunión" newer_than:60d
GMAIL_MEET_MAX_RESULTS=25
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token_gmail.json
```

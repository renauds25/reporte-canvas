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
subject:"Asistencia procesada" has:attachment newer_than:60d -label:meet_python_descargado -label:meet_python_error
```

El sistema prioriza los correos generados por Apps Script que llegan con CSV adjunto. Después de descargarlos correctamente, agrega en Gmail la etiqueta `meet_python_descargado` para no volver a procesar el mismo correo. Si un correo falla o no trae CSV adjunto, agrega la etiqueta `meet_python_error`.

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
GMAIL_MEET_QUERY=subject:"Asistencia procesada" has:attachment newer_than:60d -label:meet_python_descargado -label:meet_python_error
GMAIL_MEET_MAX_RESULTS=25
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token_gmail.json
GMAIL_MEET_PROCESSED_LABEL=meet_python_descargado
GMAIL_MEET_ERROR_LABEL=meet_python_error
GMAIL_MEET_MOVE_PROCESSED_FILES=1
```


## Flujo recomendado con Apps Script

El descargador de Gmail ahora prioriza correos con CSV adjunto generados por Apps Script.

Asuntos esperados:

- `[MEET ALUMNOS] Asistencia procesada - ...` → descarga y procesa en `data/alumnos/insumos_meet/`.
- `[MEET MAESTROS] Asistencia procesada - ...` → descarga en `data/maestros/insumos_meet/` para procesamiento posterior con horarios de cursos.

Búsqueda recomendada:

```text
subject:"Asistencia procesada" has:attachment newer_than:60d
```

Por defecto ya no intenta descargar el Google Sheet original desde Drive. Esto evita errores 404 o permisos cuando los correos fueron reenviados desde otras cuentas. Si necesitas volver a activar el intento por Drive, agrega al `.env`:

```text
GMAIL_MEET_DRIVE_FALLBACK=1
```


## Control anti-duplicados en Gmail

La descarga automática usa dos controles para no repetir archivos:

1. Etiqueta en Gmail: `meet_python_descargado`.
2. Registro local: `data/alumnos/meet_descargados.csv`.

Cuando un correo se descarga correctamente, el sistema lo etiqueta en Gmail. La próxima búsqueda excluye esa etiqueta, por lo que ya no vuelve a descargar el mismo adjunto.

Si un correo no trae CSV o falla, se etiqueta como `meet_python_error` para que no bloquee futuras ejecuciones. Puedes quitar esa etiqueta manualmente en Gmail si quieres volver a intentar descargarlo.

Después de procesar archivos de alumnos descargados desde Gmail, los CSV se mueven a:

```text
data/alumnos/insumos_meet/procesados/
```

Así la carpeta principal de insumos queda más limpia, pero conservas respaldo histórico de los CSV.

### Importante si ya autorizaste antes

Esta versión necesita permiso de Gmail para modificar etiquetas. Si ya habías autorizado con la versión anterior, borra `token_gmail.json` y vuelve a ejecutar la automatización para autorizar los nuevos permisos.

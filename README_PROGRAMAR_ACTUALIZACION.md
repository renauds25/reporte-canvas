# Automatización de actualización Meet y publicación en Render

Este proyecto ya puede actualizar los reportes de Meet sin presionar el botón del panel admin.

## Comandos disponibles

Actualizar reportes Meet desde Gmail:

```bash
python app.py actualizar-meet
```

Este comando hace lo mismo que el botón del admin:

1. Busca correos nuevos de Meet en Gmail.
2. Descarga CSV adjuntos de `[MEET ALUMNOS]` y `[MEET MAESTROS]`.
3. Procesa alumnos y maestros.
4. Etiqueta correos como procesados o con error.
5. Actualiza los CSV del proyecto.

También se incluyeron dos archivos para Windows:

```text
actualizar_meet.bat
actualizar_meet_y_render.bat
```

## Archivo 1: actualizar_meet.bat

Úsalo cuando solo quieras actualizar los archivos locales:

```bat
actualizar_meet.bat
```

## Archivo 2: actualizar_meet_y_render.bat

Úsalo cuando quieras actualizar los datos, hacer commit y subir a GitHub:

```bat
actualizar_meet_y_render.bat
```

Este archivo:

1. Ejecuta `python app.py actualizar-meet`.
2. Agrega a Git los CSV importantes de `data/`.
3. Si hay cambios, hace commit.
4. Ejecuta `git push`.
5. Render desplegará la actualización si el servicio tiene Auto-Deploy activado para esa rama.

## Programarlo con el Programador de tareas de Windows

Primero prueba manualmente:

```bat
actualizar_meet_y_render.bat
```

Si funciona, puedes crear una tarea programada desde CMD como administrador.

Cambia la ruta por la de tu proyecto:

```bat
schtasks /Create /TN "Reporte Canvas - Actualizar Meet" /TR "\"C:\Users\renaud.santos\Documents\Canvas\junio julio\reporte-canvas-pruebas\actualizar_meet_y_render.bat\"" /SC DAILY /ST 08:30 /RI 90 /DU 12:00 /F
```

Eso intenta correr la actualización cada 90 minutos durante 14 horas, empezando a las 07:10.

Horarios aproximados:

```text
08:30
10:00
11:30
13:00
14:30
16:00
17:30
19:00
20:30
```

## Requisitos

La computadora donde se programe la tarea debe:

- Estar encendida.
- Tener internet.
- Tener Python y dependencias instaladas.
- Tener acceso a `credentials.json` y `token_gmail.json`.
- Tener Git configurado para poder hacer `git push` sin pedir contraseña.

## Archivos que no deben subirse

No subas estos archivos a GitHub:

```text
.env
credentials.json
token_gmail.json
token.json
__pycache__/
*.pyc
```

Ya están considerados en `.gitignore`.

## Sobre Render

Hay dos formas de publicar los cambios:

### Opción recomendada: Auto-Deploy por GitHub

Si Render está conectado a tu repo y tiene Auto-Deploy activado, cada `git push` a la rama conectada dispara un despliegue automático.

En este caso no necesitas hacer nada extra en Render.

### Opción alternativa: Deploy Hook

Si Render no tiene Auto-Deploy activado, puedes usar un Deploy Hook de Render.

Por ahora no es necesario si el `git push` ya actualiza tu servicio.

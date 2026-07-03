@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo Actualizar Meet + publicar cambios para Render
echo Carpeta: %CD%
echo ===============================================

python app.py actualizar-meet
if errorlevel 1 (
    echo.
    echo ERROR: No se pudo actualizar Meet. No se hara commit ni push.
    exit /b 1
)

echo.
echo Preparando cambios de datos para Git...

git add data/capacitaciones.csv
git add data/usuarios.csv
git add data/alumnos/capacitaciones.csv
git add data/alumnos/usuarios.csv
git add data/alumnos/pendientes_revision.csv
git add data/alumnos/descartados_menos_30_min.csv
git add data/alumnos/meet_descargados.csv
git add data/maestros/horarios_cursos.csv
git add data/maestros/pendientes_revision_meet.csv
git add data/maestros/descartados_menos_30_min_meet.csv

git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo No hay cambios nuevos para publicar.
    exit /b 0
)

echo.
echo Creando commit de actualizacion...
git commit -m "Actualizar reportes Meet %DATE% %TIME%"
if errorlevel 1 (
    echo ERROR: No se pudo crear el commit.
    exit /b 1
)

echo.
echo Enviando cambios a GitHub...
git push
if errorlevel 1 (
    echo ERROR: No se pudo hacer git push.
    exit /b 1
)

echo.
echo Listo. Si Render tiene Auto-Deploy activado para esta rama, se desplegara automaticamente.
exit /b 0

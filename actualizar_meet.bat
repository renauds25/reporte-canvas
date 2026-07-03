@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo Actualizando reportes Meet desde Gmail
echo Carpeta: %CD%
echo ===============================================

python app.py actualizar-meet
if errorlevel 1 (
    echo.
    echo ERROR: No se pudo actualizar Meet.
    exit /b 1
)

echo.
echo Actualizacion Meet terminada correctamente.
exit /b 0

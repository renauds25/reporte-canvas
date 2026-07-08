# Reporte Canvas LMS

Flujo principal actual:

1. Google Meet genera el reporte de asistencia.
2. Apps Script en CIE/CTE convierte el archivo a CSV.
3. Apps Script manda el CSV a `/api/meet/asistencia`.
4. La app procesa alumnos o maestros.
5. Se actualiza PostgreSQL/SQLite y el cache del reporte.
6. El panel admin muestra el historial de ingestas.

## Comandos útiles

```bat
python app.py
```

```bat
python app.py sincronizar-bd
```

```bat
python app.py regenerar-cache
```

## Carga manual

Para cambios grandes, reemplaza los CSV directamente en `data/` y después ejecuta:

```bat
python app.py sincronizar-bd
```

Si actualizaste PostgreSQL de Render desde tu computadora, entra al panel admin publicado y usa **Regenerar cache**.

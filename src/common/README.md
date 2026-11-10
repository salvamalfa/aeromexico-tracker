# Utilidades compartidas de Airlines Tracker

Estos módulos dan al pipeline una forma común de guardar fuentes, consultar
proveedores y registrar incidencias. Así cada conector conserva la misma
trazabilidad sin volver a implementar esas tareas.

## Responsabilidad

| Módulo | Comportamiento |
|---|---|
| [storage.py](storage.py) | Guarda originales Bronze con SHA-256 y metadatos. Reutiliza contenido idéntico y conserva una nueva versión cuando cambia un documento lógico. |
| [quality.py](quality.py) | Añade incidencias al registro de calidad con fuente, tipo, gravedad y filas afectadas. |
| [http.py](http.py) | Aplica límites de solicitudes por fuente, reintentos de errores transitorios e identificación del cliente. |
| [logging.py](logging.py) | Configura los registros de ejecución compartidos. |

El almacenamiento escribe el manifiesto de procedencia en `_manifest.jsonl`
y los cambios de contenido en `_restatements.jsonl`. Las incidencias de calidad
se añaden sin sobrescribir las anteriores; `log_issue_once` evita repetir
una incidencia con la misma firma.

## Entradas / salidas

- **Entradas:** bytes, respuestas y eventos que entregan los módulos de
  [ingesta](../ingest/README.md), [extracción](../parse/README.md),
  [transformación](../transform/README.md) y [ejecución](../pipeline/README.md).
- **Salidas:** archivos y manifiestos en `data/bronze/`, registros locales
  en `data/quality/` y mensajes de ejecución, según la función invocada.

## Puntos de entrada

Es una biblioteca sin comando propio. Sus consumidores importan los módulos,
por ejemplo `from src.common import storage` o `from src.common import quality`.
Las rutas se resuelven con [la configuración del proyecto](../config.py).

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_storage.py tests/test_quality.py tests/test_http.py tests/test_logging.py
```

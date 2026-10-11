# F2.8 · Presentación por referencia · 2026-10-11
- [presentation.py](../../src/conversational_analytics/presentation.py) valida displays, fuentes y referencias de tabla/gráfica por turno; genera fallback desde filas tool ya validadas.
- [worker.py](../../src/conversational_analytics/worker.py) elimina marcas desconocidas, persiste solo objetos citados en `message.completed` y el historial.
- [display.ts](../../web/src/views/chat/display.ts) dibuja datos del servidor, conserva `null`, convierte fracciones a porcentaje una sola vez y marca estimaciones.
- [markdown.ts](../../web/src/views/chat/markdown.ts) mantiene el respaldo Markdown; referencias repetidas se deduplican por URL.
- Verificación local sin proveedor: 6 pruebas focalizadas de presentación + 7 del worker; `web` check, 151 pruebas Vitest y build completan correctamente.
- Las herramientas F2.3/F2.4 pueden entregar `display` singular con `display_id`, `kind`, `columns`, `rows`, `value_kind` y `source(s)`; el worker acepta ese contrato.
- No se ejecutó API de pago ni se activó/publicó un dataset o análisis; el prompt de marcadores se integra después de la activación aprobada.

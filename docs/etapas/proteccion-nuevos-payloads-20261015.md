# Nuevos payloads: dependencias de aprobación (15 octubre 2026)

La revisión de Mercado detectó que su constructor nuevo de demanda aeroportuaria no entraba en `entity_adapter.code_version()`. Aunque el exportador sí estaba incluido, una modificación posterior del constructor podía conservar la huella previa. Se cierra el hueco incluyendo los tres módulos nuevos que determinan los payloads públicos de estas propuestas: `src/dashboard/market_demand.py`, `src/dashboard/news.py` y `src/conversational_analytics/news_projection.py` cuando existen en la rama independiente.

La condición exacta de `require_current_presentation()` permanece igual. La aprobación de una versión anterior no pasa después de modificar esos archivos, añadirlos o borrarlos. Se añaden seis regresiones con archivos temporales; no se escribe sobre los análisis ni se cambia una aprobación. El selector del diagnóstico se mantiene idéntico al de producción, y el reporte se vuelve a generar desde el código corregido.

Esto refuerza la protección; no modifica las tesis, el Gold, los recibos o pins del chat, las candidatas, cron ni la publicación. Las 68 afirmaciones y payloads numéricos se vuelven a contrastar en el reporte posterior. La nueva huella sigue requiriendo revisión/aprobación técnica antes de exportar. Las previews ya advierten ese bloqueo; su interfaz y datos no cambian por esta corrección del guard.

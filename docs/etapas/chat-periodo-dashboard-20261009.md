# Periodo por omisión del chat · 9 oct 2026

La [UI ya enviaba la selección](../../web/src/views/chat/context.ts); algunos casos históricos del [benchmark](../../src/conversational_analytics/evaluation_live.py) omitían `context`, que el harness sustituye por `{}`.
El prompt del proveedor ahora prioriza periodo explícito, seguimiento conversacional inequívoco, selección del dashboard y aclaración si falta periodo.
Esta regla solo resuelve el periodo: no deduce métrica, entidad, segmento, mercado, denominador ni fuente ambiguos.
Baseline de producción: [prompt en `135e89e`](https://github.com/salvamalfa/aeromexico-tracker/blob/135e89e/src/conversational_analytics/providers/_openai_helpers.py).
Regla propuesta: [código en `6e95005`](https://github.com/salvamalfa/aeromexico-tracker/blob/6e95005/src/conversational_analytics/providers/_openai_helpers.py).
El cambio conserva los fixtures, ratings, datos, aprobaciones y modelo; no hubo llamadas al modelo ni evaluaciones pagadas.
La prueba mock verifica la consulta trimestral `2026Q2` con contexto real; no mide seguimiento del modelo.
Las sesiones guardan el hash de instrucciones; si cambia, una nueva sesión rehidrata el historial y el borrado de la anterior queda en cola.

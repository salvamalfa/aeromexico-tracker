# Chat analítico de Airline Tracker

El chat consulta una proyección permitida de los JSON públicos publicados en
`site/data/v1`. El servicio fija cada turno a un `data_version` y un
`semantic_version`; no abre el warehouse, bronze o silver. Python valida el
plan estructurado, hace los cálculos deterministas y entrega valores con unidad,
disponibilidad y referencias. El proveedor solo redacta y puede pedir las
herramientas permitidas.

La interfaz y el backend deben tomar la pestaña, tarjeta y filtros como contexto
no confiable y validado. El contexto puede resolver una pregunta, pero nunca
concede permisos o amplía cobertura. Los filtros propios de una tarjeta tienen
precedencia explícita sobre el estado global; si entran en conflicto se pide
aclaración. No se reparte un total por rutas sin evidencia, no se confunde
Aeroméxico consolidado con Aerovías aislada, y una ausencia conserva el estado
`missing` en vez de convertirse en cero.

El catálogo inicial distingue `company_passengers` de `afac_passengers`, razón
por la cual “pasajeros” puede requerir aclaración. Los porcentajes se guardan
como fracción y se muestran como porcentaje; los campos `*_pp` ya están en
puntos porcentuales. Ocupación, RASK y CASK de Industria se conservan como
razones ponderadas publicadas. Ver las fichas de [métricas](../../config/chat/metrics.yaml)
y [entidades](../../config/chat/entities.yaml). El catálogo habilita 11 métricas
versionadas (8 fichas adicionales permanecen en inventario sin activar)
y el registry expone siete herramientas de consulta controlada.
FastAPI sirve historial y turnos por SSE, con almacenamiento SQLite local y
sesiones del proveedor aisladas tras el adaptador.

## Estado de entrega

| Hito | Estado al 4 oct 2026 |
|---|---|
| H1 — semántica revisada | Conciliación técnica completa y 12 referencias estáticas verificadas; la revisión del dueño queda pendiente explícitamente. |
| H2 — demo sin consumo | Backend, 11 métricas, siete herramientas, SSE y panel implementados y verificados. El fallo preexistente del diagnóstico de etapa 12 sigue documentado aparte. |
| H3 — chat real local | Acceso confirmado con una sonda y consultas reales con herramientas y fuentes. El uso se recupera por lecturas oficiales; los errores y su consumo quedan registrados en la validación real. |
| H4 — modelo elegido | Comparación live autorizada en curso; requiere revisar los resultados de los candidatos y superar el gate de calidad. No hay modelo elegido. |
| H5 — piloto publicado | Una contraseña del dueño preparada fuera de Git. Hostinger Business no admite este backend Python; requiere un servidor separado, retención y validación HTTPS desde Pages. |

Para evaluación, cobertura, gates y límites, consulta [evaluaciones y presupuesto](evaluaciones-presupuesto.md).
Para instalación, operación y el diseño propuesto de una instancia persistente,
consulta [operaciones](operations.md). Los ejemplos de prompt no son el holdout:
`tests/fixtures/chat_evals/holdout.json` tiene preguntas reservadas y valores
estáticos verificados contra el snapshot publicado.

Para el hosting actual, consulta la [guía de VPS Hostinger](hostinger-vps.md).

La [validación real](../etapas/airline-tracker-validacion-real-20261004.md) y la
[guía de Data Sharing](data-sharing.md) detallan resultados, cobertura y
límites diarios propuestos.

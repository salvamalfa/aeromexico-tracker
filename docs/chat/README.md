# Chat analítico de Airline Tracker

La revisión vigente para el periodo por omisión del chat está en
[la bitácora de etapa (9 oct 2026)](../etapas/chat-periodo-dashboard-20261009.md).

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

La presentación por referencia agrega `DisplayRegistry` al límite del worker:
la respuesta cita tablas y gráficas validadas del mismo turno, que el frontend
renderiza desde los valores persistidos sin otra consulta al modelo. El estado
local de F2.8 y sus verificaciones están en el [reporte de etapa](../etapas/chat-f2-8-presentacion-20261011.md).

El índice versionado contiene siete pasajes de reportes y tres fichas de
noticias aprobados por el dueño. La activación de las herramientas de evidencia
con R2 está activa y verificada en Railway. Cada
resultado entrega `references` con su URL exacta y
una etiqueta de empresa, periodo/página o medio/fecha/título; el proveedor las
conserva en las fuentes del turno y agrupa etiquetas que comparten URL.

El catálogo inicial distingue `company_passengers` de `afac_passengers`, razón
por la cual “pasajeros” puede requerir aclaración. Los porcentajes se guardan
como fracción y se muestran como porcentaje; los campos `*_pp` ya están en
puntos porcentuales. Ocupación, RASK y CASK de Industria se conservan como
razones ponderadas publicadas. Ver las fichas de [métricas](../../config/chat/metrics.yaml)
y [entidades](../../config/chat/entities.yaml). El catálogo habilita 11 métricas
versionadas (8 fichas adicionales permanecen en inventario sin activar).
El contrato operativo documentado para Railway permite hasta 16 llamadas de
herramienta por turno; el default local es 8.
FastAPI sirve historial y turnos por SSE, con almacenamiento SQLite local y
sesiones del proveedor aisladas tras el adaptador.

## Estado de entrega

R2 está activo en Railway con `gpt-6.1-sol`, esfuerzo `low` y verbosidad
`medium`. El despliegue `6889bc94-da81-4294-b2bd-a8fc5d14fbe7` sobre `30a931d`
terminó `SUCCESS`; health respondió 200 con worker/admisión activos y
`route_queries`, `business_metric_queries`, `evidence_search` habilitados.
Prompt efectivo y pins: [cierre operativo](../etapas/chat-fase2-cierre-operativo-20261012.md).

La fase 2 está implementada. Stage 3 completó 30 casos/34 mensajes con costo
estimado registrado de US$2.626185; la revisión del dueño calificó 16 correctos
y 14 problemas. De las 13 notas de periodo, 12 corresponden a ejecuciones sin
contexto; la interfaz ya transmite automáticamente la selección del dashboard.
No se interpreta este resultado como prueba de que el selector real se ignore.

El dueño autorizó ajustar R2 sin repetir la evaluación pagada. El prompt debe
priorizar el periodo seleccionado, explicitar el periodo utilizado y recuperar
pasajes ingleses para consultas en español. R1 permanece predeterminado y las
capacidades nuevas apagadas por omisión; producción selecciona R2 explícitamente.
La fase 2 está implementada y activa, con despliegue verificado. No se repitió
la evaluación pagada ni se acreditó el gate original de 70 casos/safety.
No hay acción pendiente del dueño. Consulta [operaciones](operations.md) y el
[brief del dueño](fase-2-decision-dueno.md).

### Registro histórico al 8 de octubre de 2026

| Hito | Estado |
|---|---|
| H1 — semántica revisada | Catálogo aprobado por el dueño para el MVP (`review_status: owner_approved_mvp`, PR #87). |
| H2 — demo sin consumo | Backend, 11 métricas, siete herramientas, SSE y panel implementados y verificados. |
| H3 — chat real local | Acceso confirmado previamente con consultas reales, herramientas y fuentes; el uso de esas sesiones se recuperó por lecturas oficiales. |
| H4 — modelo elegido | El dueño eligió `gpt-6.1-sol` con esfuerzo `low`; producción usa R2 ajustado
y aprobado. Health confirmó SHA-256 efectivo
`cec193aa10dff802d5578da00777b5b56c74bfcc71aeccaf1ea718c07cc763b1`.
Se conservan los topes actuales. Las conversaciones
OpenAI existentes requieren una nueva conversación para aplicar cambios de
configuración. El default local sigue siendo `CHAT_MAX_TOOL_CALLS=8`; producción
documenta 16. No se ejecutaron consultas de pago.

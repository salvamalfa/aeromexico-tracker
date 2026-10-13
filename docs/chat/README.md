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
| H4 — modelo elegido | El dueño eligió `gpt-6.1-sol`. Topes diarios vigentes: US$5 por usuario y US$5 global (US$3 hasta el 8 de octubre); hasta 16 llamadas de herramienta por turno. La evidencia histórica disponible no valida el prompt actual y no se aprobó un gate de calidad. |
| H5 — MVP en producción | Backend HTTPS en Railway con contraseña (un solo dueño), proveedor OpenAI y admisión habilitada; panel visible en Pages. El 8 de octubre el dueño obtuvo respuestas reales correctas: una aclaración y la de market share 2026 con tabla. |

La activación se integró con los PRs
[#102](https://github.com/salvamalfa/aeromexico-tracker/pull/102),
[#103](https://github.com/salvamalfa/aeromexico-tracker/pull/103) y
[#104](https://github.com/salvamalfa/aeromexico-tracker/pull/104); los 112
archivos de datos, contratos y `analysis_manifest` no cambiaron. El 8 de
octubre, [#107](https://github.com/salvamalfa/aeromexico-tracker/pull/107) hizo
que un turno detenido por un límite local cancele el turno del proveedor y
registre su uso real, y [#108](https://github.com/salvamalfa/aeromexico-tracker/pull/108)
renderiza tablas en el chat. Railway solo redespliega cuando cambia un archivo
listado en `railway.toml` (watch paths).

Un turno fallido del 8 de octubre (`0fc9308d…`, `tool_call_limit`) conserva
una reserva de US$1.50 que cuenta contra el tope diario; solo se concilia si
el dueño lo pide.

La evidencia histórica de Sol registró 31 respuestas correctas de 31
respuestas disponibles; 10 de 12 preguntas soportadas tuvieron respuesta
correcta. No demuestra calidad del prompt actual ni significa que el gate haya
pasado. El dueño aceptó el MVP con límites conocidos. El monto reportado de
US$2.72 gastados al 7 de octubre no está reconciliado contra el ledger; no es
un saldo contable ni representa el consumo actual verificado. S14 conserva
`NULL`/desconocido, que nunca se interpreta como cero.

Las respuestas correctas del 8 de octubre son observaciones de uso, no una
validación de calidad del prompt. Consulta la [fase 2](fase-2-agente-analitico.md), el
[traspaso operativo](traspaso-activacion-mvp-20261006.md), el
[reporte de activación](../etapas/chat-mvp-activacion-20261007.md), las
[correcciones de recuperación](../etapas/chat-recuperacion-correcciones-20261008.md),
el [diagnóstico de límites](../etapas/chat-limite-herramientas-presupuesto-20261008.md)
y el [reporte de tablas](../etapas/chat-tablas-presentacion-20261008.md).

El [adaptador Agents API](../arquitectura/airline-tracker-agents-api.md)
describe la integración con el proveedor. Diagramas interactivos de la
arquitectura actual: [anatomía del chat](../arquitectura/anatomia-chat.html) y
[anatomía de las herramientas](../arquitectura/anatomia-herramientas.html).

Para evaluación, cobertura, gates y límites, consulta [evaluaciones y presupuesto](evaluaciones-presupuesto.md).
Para instalación local y operación, consulta [operaciones](operations.md). Los
ejemplos de prompt no son el holdout: `tests/fixtures/chat_evals/holdout.json`
tiene preguntas reservadas y valores estáticos verificados contra el snapshot
publicado.

El backend de producción corre en Railway; consulta la
[guía de configuración del backend](railway.md). La elección de hosting quedó
registrada en la [comparación de Railway y VPS](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/hosting-options.md),
ya archivada.

## Recuperar un turno `provider_error`

`scripts/chat/reconcile_failed_turn.py` permite recuperar un único turno local
fallido cuando el SDK conserva el turno exacto como completado. La ejecución
predeterminada es de solo lectura local y muestra metadatos mínimos, sin
pregunta, respuesta ni identificadores. `--apply` exige el turno, dueño,
conversación, sesión y turno exactos del proveedor, y las versiones de datos y
semántica copiadas del estado local. Confirma que la vista previa lo marca
elegible antes de aplicar.

La aplicación solo hace GET del turno y sus ítems ya existentes. Verifica que
el turno devuelto sea exactamente el solicitado, que esté completado y tenga
uso conocido, y que las llamadas a herramientas correspondan a resultados ya
guardados localmente. No envía entrada al proveedor ni reactiva el worker. La
respuesta queda en la base privada; stdout y los eventos de operación solo
indican el resultado. Se conservan el evento original `turn.failed` y el
registro de uso es idempotente.

El método transaccional vuelve a comprobar propietario, conversación,
versiones, sesión, turno, estado y ausencia de un turno posterior, respuesta
previa, cancelación, timeout o eliminación de sesión. Si alguno cambió, no
aplica la recuperación. No edites ni incluyas la base, los argumentos privados
o la respuesta en el repositorio.

La pregunta original del 7 de octubre, que quedó `provider_error`, no se ha
recuperado ni se ha comprobado como elegible para esa operación. No ejecutes la
recuperación ni vuelvas a enviarla sin pedido explícito del dueño.

La [validación real](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-validacion-real-20261004.md) y la
[guía de Data Sharing](data-sharing.md) detallan resultados, cobertura y
límites diarios y la importación del consumo de evaluaciones.

## F2.0 · Modelo y esfuerzo fijados

La configuración versionada en [`../../config/chat/models.json`](../../config/chat/models.json)
define capacidades y precios de `gpt-6-luna` y `gpt-6.1-sol`. El servicio
valida `CHAT_REASONING_EFFORT` y `CHAT_TEXT_VERBOSITY`, los envía explícitamente
al crear una sesión Agents API y registra modelo, esfuerzo y verbosidad en
SQLite para cada turno. `/api/chat/health` reporta la selección y el número
teórico de reservas mínimas que cabe bajo los topes configurados. El cálculo no
es una cota de facturación porque no hay límite de salida acumulado que cubra
un turno de hasta 16 herramientas; consulta [operaciones](operations.md).

El dueño eligió `gpt-6.1-sol` con esfuerzo `low`; producción usa R2 ajustado
y aprobado. Railway verificó el despliegue `6889bc94-da81-4294-b2bd-a8fc5d14fbe7`,
`SUCCESS`, commit `30a931d166ffc4864a10316dbdc65c8db9382f18`;
health 200 confirmó el SHA-256 efectivo
`cec193aa10dff802d5578da00777b5b56c74bfcc71aeccaf1ea718c07cc763b1`.
Se conservan los topes actuales. Las conversaciones
OpenAI existentes requieren una nueva conversación para aplicar cambios de
configuración. El default local sigue siendo `CHAT_MAX_TOOL_CALLS=8`; producción
documenta 16. No se ejecutaron consultas de pago.

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

Cuando se habilite la búsqueda aprobada de reportes o noticias, cada resultado
también entrega `references` con su URL exacta y una etiqueta de empresa,
periodo/página o medio/fecha/título. El proveedor las conserva en las fuentes
del turno y agrupa etiquetas que comparten URL; la capacidad continúa apagada
mientras `approved-index.json` no tenga registros aprobados.

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

El MVP sigue activo en Railway. El 12 de octubre de 2026 se verificó el despliegue
`dd97b38e-383b-48ab-9fab-ca5bf0f78c70` con `gpt-6.1-sol`, esfuerzo `low`,
verbosidad `medium`, prompt `r1-final` (SHA-256 efectivo
`439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5`) y
snapshot `d9c4e56d04ad67be5dff6d6e9f7f6615f4f4be985ec1e5ee59781a7735007037`;
health respondió 200 y la admisión/worker estaban activos. No se hizo ninguna
consulta pagada durante la verificación.

F2.3–F2.9 están preparados en el [PR #120](https://github.com/salvamalfa/aeromexico-tracker/pull/120),
que sigue en revisión y no está desplegado. Las capacidades nuevas siguen
cerradas: rutas, métricas financieras y búsqueda de evidencia usan flags
false; el índice de evidencia aprobado está vacío. R1 sigue activo, así que no
se requiere volver a aprobar R1 ni las preguntas, rúbrica o modelo/esfuerzo.
R2 y los contenidos propuestos aún requieren decisión; Stage 3 requiere
presupuesto nuevo. Su preflight offline estima US$7.06–7.23 para 30 casos/34
mensajes y propone una reserva máxima de US$8; el saldo actual es desconocido y
solo reduce la recarga necesaria, no la reserva. La campaña no está aprobada ni
financiada. Consulta la
[cotización vigente](revision-fase-2/F2.9-etapa-3-presupuesto-actual.md), el
[resumen de decisiones](fase-2-decision-dueno.md) y el
[reporte de activación](../etapas/chat-f2-0-activacion-20261012.md).

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

El dueño eligió `gpt-6.1-sol` con esfuerzo `low` y aprobó el prompt evaluado en
F2.9 etapa 2. Railway confirmó esta configuración en el despliegue
`dd97b38e-383b-48ab-9fab-ca5bf0f78c70`, estado `SUCCESS`, commit
`60e741b4b4c70ba2d092061f571b924690afcfcd`; `/api/chat/health` respondió 200.
La fuente versionada del prompt tiene SHA-256
`33b8f7a0900869812d98bba57daa2ce3ea2f6b5c02a86a7eb3b8e830c7f7694b`; el texto
efectivo que suma la regla de periodo evaluada tiene SHA-256
`439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5`, que
reportará `/api/chat/health`. Se conservan los topes actuales. Las conversaciones
OpenAI existentes requieren una nueva conversación para aplicar cambios de
configuración. El default local sigue siendo `CHAT_MAX_TOOL_CALLS=8`; producción
documenta 16. No se ejecutaron consultas de pago.

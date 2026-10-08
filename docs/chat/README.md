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

## Estado de entrega al 8 de octubre de 2026

| Hito | Estado |
|---|---|
| H1 — semántica revisada | Catálogo aprobado por el dueño para el MVP (`review_status: owner_approved_mvp`, PR #87). |
| H2 — demo sin consumo | Backend, 11 métricas, siete herramientas, SSE y panel implementados y verificados. |
| H3 — chat real local | Acceso confirmado previamente con consultas reales, herramientas y fuentes; el uso de esas sesiones se recuperó por lecturas oficiales. |
| H4 — modelo elegido | El dueño eligió `gpt-6.1-sol`, con topes diarios de US$3 por usuario y US$3 global. La evidencia histórica disponible no valida el prompt actual y no se aprobó un gate de calidad. |
| H5 — piloto publicado | Backend HTTPS en Railway con contraseña, proveedor OpenAI y admisión habilitada; panel visible en Pages. Se comprobaron una vez el login y la lectura del historial desde Pages con las credenciales del dueño; la pregunta original quedó `provider_error`, sin respuesta de asistente. Sin reenvío ni respuesta nueva validada. |

PRs [#102](https://github.com/salvamalfa/aeromexico-tracker/pull/102),
[#103](https://github.com/salvamalfa/aeromexico-tracker/pull/103) y
[#104](https://github.com/salvamalfa/aeromexico-tracker/pull/104) están fusionados.
CI [37792230297](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/37792230297)
y Pages [37792230531](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/37792230531)
terminaron correctamente. La fuente publicada es `5e5d024`; los 112 archivos de
datos, contratos y `analysis_manifest` no cambiaron.

La evidencia histórica de Sol registró 31 respuestas correctas de 31
respuestas disponibles; 10 de 12 preguntas soportadas tuvieron respuesta
correcta. No demuestra calidad del prompt actual ni significa que el gate haya
pasado. El dueño aceptó el MVP con límites conocidos. El monto reportado de
US$2.72 gastados al 7 de octubre no está reconciliado contra el ledger; no es
un saldo contable ni representa el consumo actual verificado. S14 conserva
`NULL`/desconocido, que nunca se interpreta como cero.

**Siguiente comprobación:** sesión desde el teléfono con la computadora apagada
para confirmar login e historial, sin reenviar el turno fallido. Una pregunta
nueva, si el dueño la decide, debe documentarse como observación separada y no
como validación de calidad. La fase 2 no está iniciada; solo empieza por pedido
expreso del dueño. Consulta el [traspaso operativo](traspaso-activacion-mvp-20261006.md)
y el [reporte de activación](../etapas/chat-mvp-activacion-20261007.md).

Diagramas interactivos de la arquitectura actual:
[anatomía del chat](../arquitectura/anatomia-chat.html) y
[anatomía de las herramientas](../arquitectura/anatomia-herramientas.html).

Para evaluación, cobertura, gates y límites, consulta [evaluaciones y presupuesto](evaluaciones-presupuesto.md).
Para instalación, operación y el diseño propuesto de una instancia persistente,
consulta [operaciones](operations.md). Los ejemplos de prompt no son el holdout:
`tests/fixtures/chat_evals/holdout.json` tiene preguntas reservadas y valores
estáticos verificados contra el snapshot publicado.

Para el piloto en Railway, consulta la [guía de configuración del backend](railway.md).
Como alternativa, consulta la [guía de VPS Hostinger](hostinger-vps.md).
Para el uso intermitente de un único usuario, consulta la
[comparación de Railway Free, Hobby y VPS](hosting-options.md).

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

La pregunta fallida mencionada en el estado del 8 de octubre no se ha
recuperado ni se ha comprobado como elegible para esa operación. No ejecutes la
recuperación ni vuelvas a enviarla sin pedido explícito del dueño.

La [validación real](../etapas/airline-tracker-validacion-real-20261004.md) y la
[guía de Data Sharing](data-sharing.md) detallan resultados, cobertura y
límites diarios y la importación del consumo de evaluaciones.

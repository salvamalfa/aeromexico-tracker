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

| Hito | Estado al 6 oct 2026 |
|---|---|
| H1 — semántica revisada | Catálogo aprobado por el dueño para el MVP (`review_status: owner_approved_mvp`, PR #87). |
| H2 — demo sin consumo | Backend, 11 métricas, siete herramientas, SSE y panel implementados y verificados. |
| H3 — chat real local | Acceso confirmado con consultas reales con herramientas y fuentes; uso recuperado por lecturas oficiales. |
| H4 — modelo elegido | Comparación terminada (Luna 7/9, Sol 9/10, Astra 8/9 parcial; ninguno llega al 95%). El dueño entregó sus calificaciones el 7 oct; faltan el gate de calidad y su elección de modelo y tope. |
| H5 — piloto publicado | Backend en Railway con HTTPS, contraseña y `mock`; admisión cerrada. Listo para activar por configuración y publicar el panel. |

Para activar el MVP, sigue el [traspaso de activación](traspaso-activacion-mvp-20261006.md).
Después del MVP sigue la [fase 2: agente analítico para negocio](fase-2-agente-analitico.md).

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

La [validación real](../etapas/airline-tracker-validacion-real-20261004.md) y la
[guía de Data Sharing](data-sharing.md) detallan resultados, cobertura y
límites diarios y la importación del consumo de evaluaciones.

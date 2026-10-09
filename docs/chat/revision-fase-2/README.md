# Revisión agrupada de fase 2

Este paquete reúne F2.0–F2.2 para revisión del dueño antes de fijar cambios de fase 2. Los documentos de propuesta y los PRs siguen en borrador. El prompt activo, el runtime y producción no cambiaron; no se ejecutaron evaluaciones en vivo ni llamadas pagadas.

## Entrega y documentos

| Paquete | Estado | Documento inmutable y PR |
|---|---|---|
| F2.0 · modelo y esfuerzo | Código y migración preparados para revisión; no integrado. | [Migración, validación y catálogo de modelos/tarifas](https://github.com/salvamalfa/aeromexico-tracker/blob/1a9d287e8eeef2d14fba70159a24ee3a3e1ecb10/docs/etapas/chat-f2-0-modelo-esfuerzo-20261008.md) · [PR borrador #111](https://github.com/salvamalfa/aeromexico-tracker/pull/111). |
| F2.1 · prompt | Texto completo propuesto; `SYSTEM_INSTRUCTIONS` permanece intacto. | [Prompt completo, comparación con el vigente y revisión offline](https://github.com/salvamalfa/aeromexico-tracker/blob/2f45994962b227b62e542b75b851c731b671329e/docs/chat/revision-fase-2/F2.1-prompt-propuesto.md) · [PR borrador agrupado #110](https://github.com/salvamalfa/aeromexico-tracker/pull/110). |
| F2.2 · preguntas, rúbrica y harness | 30 preguntas de negocio y rúbrica propuestas; `safety_current` deriva los 40 casos del holdout sin editar el original. Sin evaluación en vivo. | [30 preguntas y rúbrica](https://github.com/salvamalfa/aeromexico-tracker/blob/e534f3abf59ba12b1ee4c4baa3448571a0df3b57/docs/chat/revision-fase-2/F2.2-conjunto-propuesto.md) · [reporte de etapa](https://github.com/salvamalfa/aeromexico-tracker/blob/e534f3abf59ba12b1ee4c4baa3448571a0df3b57/docs/etapas/chat-f2-2-conjunto-evaluacion-20261009.md) · [fixture de negocio](https://github.com/salvamalfa/aeromexico-tracker/blob/e534f3abf59ba12b1ee4c4baa3448571a0df3b57/tests/fixtures/chat_evals/business_proposed.json) · [corte `safety_current`](https://github.com/salvamalfa/aeromexico-tracker/blob/e534f3abf59ba12b1ee4c4baa3448571a0df3b57/tests/fixtures/chat_evals/safety_current.json) · [estimación de presupuesto](https://github.com/salvamalfa/aeromexico-tracker/blob/e534f3abf59ba12b1ee4c4baa3448571a0df3b57/docs/chat/estimacion-f2-9-presupuesto.md) ([JSON reproducible](https://github.com/salvamalfa/aeromexico-tracker/blob/e534f3abf59ba12b1ee4c4baa3448571a0df3b57/docs/chat/estimacion-f2-9-presupuesto.json)) · [PR borrador #112](https://github.com/salvamalfa/aeromexico-tracker/pull/112). |
| F2.3–F2.9 | Pendientes de sus propios paquetes, decisiones y validaciones. | No se presentan como implementados ni aprobados por esta entrega. |

## Decisiones para el dueño

1. **F2.1:** aprobar o editar el prompt completo antes de fijarlo en el runtime. El borrador se limita a las siete herramientas actuales.
2. **F2.2:** revisar las 30 preguntas y la rúbrica; confirmar el corte `safety_current` derivado. El fixture histórico `holdout.json` queda intacto.
3. **Presupuesto:** decidir si autoriza empezar la etapa 1 con una reserva de **US$3** o ajustar su alcance/reserva. El saldo actual de API es desconocido y está sin conciliar; antes de cualquier etapa con costo se debe confirmar el saldo disponible y cargar solo `max(0, reserva − saldo confirmado)`. El dato histórico de aproximadamente US$7 no es saldo actual.

La proyección sin caché para las tres etapas es **US$28.87–52.79**; con un escenario modelado de 80% de cache hit es **US$10.69–22.49**. La referencia de **US$73** incluye US$3–5 de desarrollo y 25% de margen sobre el extremo alto; es planificación global, no una autorización ni un tope de factura. Las reservas orientativas separadas son etapa 1 **US$3**, etapa 2 **US$11** y etapa 3 **US$54**. Cada etapa requiere su propia decisión y presupuesto: sus corridas/reanudaciones comparten ledger dentro de esa etapa, y la etapa 3 se recalcula tras el piloto. El margen operativo no limita una solicitud ya iniciada ni garantiza el máximo de factura.

## Validación y límites

- F2.0: 887 pruebas públicas pasaron; 6 omitidas, 79 excluidas por marcadores y 14 subpruebas. Pasaron smoke del runtime sin llamadas al proveedor, Ruff y `git diff --check`; los checks `test` y `web` del PR #111 pasaron.
- F2.1: prompt íntegro comparado offline con el contrato vigente y el registry de siete herramientas; no se activó.
- F2.2: 953 pruebas públicas pasaron; 6 omitidas, 79 excluidas por marcadores y 14 subpruebas. También pasaron 94 pruebas focalizadas, 79 de QA, Ruff, smoke, compilación y `git diff --check`. Los checks `test` y `web` se pueden consultar en el [PR #112](https://github.com/salvamalfa/aeromexico-tracker/pull/112).

La estimación usa tarifas de contexto corto y rangos modelados, no una cotización ni mediciones live; el tamaño por solicitud, el cache write, posibles tarifas de contexto largo y el saldo de API actual son desconocidos. Ningún paquete de esta entrega activa código, cambia producción, aprueba datos o autoriza por sí mismo el gasto de una etapa. F2.3–F2.9 permanecen pendientes.

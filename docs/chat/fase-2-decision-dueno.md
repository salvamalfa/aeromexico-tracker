# Fase 2 del chat · acciones del dueño

R2, cuatro métricas, siete pasajes, tres fichas y la reserva Stage 3 ya están aprobados: [decisión](../decisiones/20261012-chat-fase2-r2-contenido-stage3.md). No hace falta repetir esa aprobación.

N01 se intentó el 12 oct, 23:39 UTC; HTTP 400 antes de crear sesión. No hay respuesta ni registro del consumo; ledger `stopped_unknown_spend`. Confirma 0 tokens/US$0 o informa tokens y costo reales en [Usage](https://platform.openai.com/usage). No reintentar hasta conciliar el consumo.

Para CI, configura en [GitHub Actions Variables](https://github.com/salvamalfa/aeromexico-tracker/settings/variables/actions): `CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256` = `644eb640124297fc63b306836607aea6e4b0be424b85e67b902cc9f5407153ae`.

Configura también `CHAT_EVIDENCE_APPROVED_INDEX_SHA256` = `1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f`. Luego continúa [PR #126](https://github.com/salvamalfa/aeromexico-tracker/pull/126) según la decisión aprobada; no se vuelve a pedir aprobación.

Los JSON de los 30 casos no están disponibles; gasto real y saldo siguen desconocidos. Producción mantiene R1/Sol low y las capacidades apagadas: [bitácora del intento](../etapas/chat-fase2-stage3-intento-20261012.md).

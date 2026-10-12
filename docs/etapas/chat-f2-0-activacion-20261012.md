# Activación F2.0 · Sol low en Railway · 12 oct 2026

El 12 de octubre se verificó el despliegue Railway
`dd97b38e-383b-48ab-9fab-ca5bf0f78c70` (commit
`60e741b4b4c70ba2d092061f571b924690afcfcd`, estado `SUCCESS`). El servidor
inició a las 03:42:36 UTC y `GET /api/chat/health` respondió 200 a las 03:44
UTC.

Health reportó `gpt-6.1-sol`, `reasoning_effort=low`,
`text_verbosity=medium`, R1 (`r1-final`, SHA-256 efectivo
`439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5`) y snapshot
`d9c4e56d04ad67be5dff6d6e9f7f6615f4f4be985ec1e5ee59781a7735007037`. El worker
y la admisión estaban activos; `minimum_reservation_turns_per_day=2`. Railway
actualizó solo las variables `CHAT_MODEL=gpt-6.1-sol` y
`CHAT_REASONING_EFFORT=low`; la verbosidad y los topes permanecieron como
estaban.

La verificación fue de health y estado de despliegue; no se hizo una pregunta
pagada. Esto confirma F2.0 en producción, no la calidad del prompt ni la
activación de las funciones F2.3–F2.8. Los flags de rutas, métricas financieras
y evidencia siguen apagados; R2 no está aprobado, el índice de evidencia sigue
vacío y Stage 3 requiere un presupuesto nuevo. La fase 2 queda abierta hasta
resolver y completar esas decisiones.

# Stage 3 · intento y conciliación pendiente · 12 oct 2026

- A las 23:39 UTC se intentó una solicitud N01. Respondió HTTP 400
  (`BadRequestError`) antes de crear Session ID; no hubo respuesta ni token
  usage. El ledger quedó `stopped_unknown_spend`; no se reintenta hasta
  conciliar consumo.
- GET read-only de modelo respondió 200 (`gpt-6.1-sol`); GET administrativo de
  usage respondió 403. Ya se pidió al dueño confirmar 0 tokens/US$0 o el uso y
  costo registrados en Platform Usage.
- CI falla porque faltan dos GitHub Actions variables; la lectura API de
  variables del repositorio respondió 403. Configurar según el [brief del
  dueño](../chat/fase-2-decision-dueno.md).
- No están disponibles los JSON de los 30 casos. Producción sigue R1/Sol low,
  con las nuevas capacidades apagadas; no se cambió runtime ni se activó nada.
- [PR #126](https://github.com/salvamalfa/aeromexico-tracker/pull/126) queda
  como continuación tras conciliar el intento y configurar variables. Las
  aprobaciones registradas se conservan; no se pide aprobar contenido otra vez.

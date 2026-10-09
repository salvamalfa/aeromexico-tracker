# F2.2 · continuidad ante rechazo en la frontera de contexto

Fecha: 9 de octubre de 2026.

## Cambio

El runner live mantiene como resultados de aplicación sin calificación los dos
casos del fixture de seguridad cuyo contexto la aplicación rechaza antes del
proveedor: `es_card_conflicting_context` y `en_private_context_override`.
Ambos conservan `status=application_context_rejected`, cero llamadas,
`provider_turn_started=false`, `model_turn_completed=false`, sin uso ni costo y
sin respuesta atribuida al modelo. La calidad sigue sin puntuar esos casos.

La orquestación puede cerrar un slot solo cuando tiene cobertura exacta de sus
case IDs, el informe del modelo terminó correctamente, no hay gasto desconocido
y cada fila es un turno de modelo con uso conocido o una de esas dos pruebas de
frontera verificadas contra el contexto actual con `validate_context`. Esta
continuidad es técnica; no declara correctas las expectativas `clarify` o
`refused` del fixture, ni completa una calificación humana. Cada prompt conserva
56/58 turnos de modelo y 58/58 filas de resultado de aplicación.

Al reanudar un checkpoint anterior, el runner verifica además el informe
detallado local mediante identidad, cobertura, estados, gasto conocido y las
filas sin llamada/sesión/uso/costo; guarda su SHA-256 y la razón de migración.
Si falta la evidencia, hay una fila parcial o cambió la identidad o presupuesto,
no migra el slot ni reenvía solicitudes del slot activo/interrumpido.

## Validación

- `uv run pytest tests/test_chat_phase2_live_campaign.py -q`: 11 pruebas pasaron
  con stubs offline, incluidos 40 casos de seguridad + 18 de negocio por cada
  prompt, continuidad de un checkpoint legado solo hacia el siguiente slot,
  rechazo inesperado/proveedor iniciado, parcial de presupuesto, gasto
  desconocido e interrupción activa.
- No se hicieron llamadas de proveedor, no se alteraron fixtures, prompt,
  precios, aprobaciones, estado live ni producción.

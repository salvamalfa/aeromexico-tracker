# Correcciones a la recuperación de turnos del chat (8 oct 2026)

Revisión independiente de los PRs #102 a #105, hecha porque Codex agotó su cuota
de revisiones. El hallazgo pendiente de Codex en #103 (la marca de falla no era
atómica con `fail_turn`) ya estaba resuelto en el head integrado: si la marca no
se guarda, el turno queda como `provider_guard_error`, que no es reconciliable.

## Qué cambió

- **Respuesta truncada.** Si el stream se cortaba sin evento terminal y la
  recuperación encontraba el turno completado pero sin texto final, se guardaba
  el texto parcial recibido por streaming como respuesta completa (por ejemplo,
  «La ocupación fue de 8»). Ahora el texto recuperado reemplaza a los fragmentos
  y, sin texto recuperado, no queda ninguno: el turno falla con su uso conocido y
  sigue siendo reconciliable.
- **Uso no leído tras una conexión caída.** La ruta de error genérico recuperaba
  la respuesta, pero no consultaba el uso cuando faltaba. El turno conservaba su
  reserva de gasto para siempre. Con Sol (US$1.50 por reserva y tope de US$3),
  dos turnos así bloqueaban todas las preguntas del día.
- **Orden de completado y consulta de uso.** Tras un error del proveedor, el uso
  se consultaba hasta 30 s antes de avisar al worker que el turno terminó. Cerca
  del límite de tiempo, el watchdog podía marcar como `timeout` un turno con
  respuesta recuperada.
- Las tres rutas de recuperación comparten `finish_recovered_completion` (en
  `_openai_recovery.py`): primero avisan la terminación y después leen el uso
  faltante, igual que la ruta normal del stream.
- **Identificador `"None"`.** Un evento de sesión nueva sin turno guardaba el
  texto `"None"` como identificador del turno del proveedor. Ahora no se guarda
  nada.

## Validación

- Cuatro pruebas nuevas en `tests/test_chat_openai_recovery_paths.py`. Las
  cuatro fallan con el código anterior y pasan con el nuevo.
- Suite pública completa: 868 aprobadas.
- `ruff check --select F` sobre `src` y `scripts`; todos los módulos dentro del
  límite de 600 líneas.

## Límites

- No cambia el modelo, el prompt, los límites, los datos publicados ni `site/`.
- La pregunta fallida del 7 de octubre no se recupera ni se reenvía.
- Al integrar en `master`, Railway redespliega el backend automáticamente.

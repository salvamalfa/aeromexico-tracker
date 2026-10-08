# Chat: límite de herramientas, reserva sin vencimiento y ajustes de Railway

Fecha: 8 de octubre de 2026. Alcance: diagnóstico de la segunda pregunta real
del dueño, ajustes de configuración en Railway pedidos por el dueño y
correcciones de código. No cambia datos publicados, contratos ni
`analysis_manifest`.

## Qué vio el dueño

1. Primera pregunta (turno `05f7c79f…`): el agente pidió una aclaración
   correcta (acumulado enero–junio o 2T26; nacionales o totales).
2. Respuesta del dueño: «acumulado enero–junio de 2026, solo nacionales». El
   agente escribió su plan y el turno terminó en error («Reintentar»).
3. Reintento: «El servicio rechazó la pregunta: daily cost budget exhausted».

## Causa comprobada en los logs de Railway

- El segundo turno (`0fc9308d…`) falló a los 40 segundos con
  `OpenAIProviderError; reason=tool_call_limit`: el modelo pidió una novena
  consulta y el límite era `CHAT_MAX_TOOL_CALLS=8`. La pregunta (acumulado de
  2026 y semestres anteriores, más participación sobre el total) necesita más
  de ocho consultas con las herramientas actuales.
- El turno fallido se cortó a la mitad, sin uso reportado por el proveedor.
  El worker lo marcó con uso desconocido y conservó toda su reserva
  (US$1.50 = 150,000 tokens a la tarifa de salida). Una reserva de uso
  desconocido **no vence**: cuenta contra el tope de ese día y de todos los
  siguientes hasta que alguien la concilie.
- El reintento a los 20 segundos recibió 429. El tope diario era US$3; el
  ledger del día ya tenía US$0.64 del turno fallido del 7 de octubre (ChatGPT
  registró ese uso el 8 a las 13:58 UTC, con fecha de uso del 8), más el costo
  de la aclaración, más la reserva sin vencimiento de US$1.50. Una pregunta
  nueva necesita reservar otros US$1.50: 0.64 + 1.50 + 1.50 = 3.64 > 3.

No fue un agotamiento real de saldo. Fue un error del límite de herramientas,
que además dejó apartado su peor caso de costo.

La pregunta original del 7 de octubre también terminó con exactamente 8
resultados de herramienta persistidos (`persisted_tool_result_count: 8` en el
diagnóstico de ChatGPT). Entonces no se registraba el motivo, así que no queda
demostrado, pero es muy probable que la causa haya sido la misma.

## Costo registrado frente a costo real

El ledger valora la entrada a US$2 por millón y la salida a US$10 por millón,
sin descuento por tokens en caché. En el turno del 7 de octubre, 295,854 de
311,198 tokens de entrada venían de caché, así que el ledger (US$0.64)
sobreestima lo que factura OpenAI. Es una cota conservadora deliberada. El
gasto real debe verificarse en la sección de uso de OpenAI Platform y no
deducirse de este documento.

## Cambios en Railway (pedidos por el dueño el 8 de octubre)

| Variable o ajuste | Antes | Ahora | Motivo |
| --- | --- | --- | --- |
| `CHAT_DAILY_COST_BUDGET_USER_USD` | 3 | 5 | margen para dos o tres preguntas al día con la reserva pendiente |
| `CHAT_DAILY_COST_BUDGET_GLOBAL_USD` | 3 | 5 | igual al tope por usuario (un solo usuario) |
| `CHAT_MAX_TOOL_CALLS` | 8 | 16 | la pregunta del dueño excedió 8 consultas |
| Watch paths del servicio | todo el repo | entradas de la imagen | los merges de documentación o de `web/` ya no reinician el chat |

El despliegue `7ccae673` terminó en SUCCESS y `/api/chat/health` respondió
`ok`, proveedor `openai`, admisión habilitada. `CHAT_MAX_TURN_SECONDS` sigue
en 180: ocho consultas tomaron unos 40 segundos.

Límites que siguen vigentes:

- La reserva de US$1.50 del turno `0fc9308d…` sigue apartada; no se concilió.
  Solo se concilia si el dueño lo pide, con `scripts/chat/reconcile_failed_turn.py`
  o el procedimiento de ChatGPT.
- Con 16 consultas, un turno puede reenviar más contexto (ocho consultas ya
  sumaron unos 311 mil tokens de entrada). El costo registrado de un turno
  largo puede superar su reserva de US$1.50; el tope diario se revisa al
  admitir el turno, no durante su ejecución.
- El peor caso mensual del ledger pasa de unos US$90 a unos US$150. El
  respaldo recomendado es un límite de presupuesto mensual en OpenAI Platform.

## Correcciones de código

1. **Uso de turnos detenidos por un límite local.** Cuando un turno falla por
   `tool_call_limit`, `turn_timeout`, `tool_result_limit` o
   `provider_terminal_failed` sin uso conocido, el worker cancela el turno en
   la sesión del proveedor, lee su uso final con la misma rutina que ya usaba
   el evaluador (`recover_usage_after_cancel`) y lo registra. Así libera la
   reserva. Si el uso sigue desconocido tras la espera acotada (30 s), la
   reserva se conserva: desconocido nunca se convierte en cero. Antes, el
   turno quedaba esperando una acción en la sesión de OpenAI y su reserva
   nunca se liberaba.
2. **Logs de Uvicorn.** El arranque usa una configuración de logging que manda
   los mensajes INFO de Uvicorn a stdout y deja WARNING o más en stderr.
   Railway marcaba como «error» todo lo que llegaba por stderr, incluidos los
   mensajes normales de arranque y apagado.
3. **`railway.toml`.** Versiona los watch paths del servicio como config as
   code. `tests/test_railway_watch_patterns.py` comprueba que todo archivo que
   copia `Dockerfile.chat` esté cubierto y que un cambio solo de documentación
   o de `web/` no redespliegue el chat.
4. **`AGENTS.md`.** Regla de revisión cruzada entre agentes para PRs de código
   cuando Codex no revisa.

## Validación

- `tests/test_chat_openai_recovery_paths.py`: dos pruebas nuevas, una para el
  uso registrado tras cancelar y otra para la reserva conservada cuando el uso
  sigue desconocido. Ambas fallan sin el cambio del worker.
- `tests/test_chat_runtime_logging.py`: INFO a stdout y ERROR a stderr; la
  configuración por defecto de Uvicorn no se modifica.
- `tests/test_railway_watch_patterns.py`: se comprobó que falla al quitar un
  patrón.
- Suite completa y `ruff` antes del push.

## Siguiente paso del dueño

Reenviar la pregunta («compara el acumulado enero–junio de 2026, solo
pasajeros nacionales»). Si vuelve a fallar por el límite de consultas, el
problema es de diseño de las herramientas: una pregunta así debería resolverse
con pocas consultas. Eso corresponde a la fase 2 (F2.3, métricas totales y
comparaciones), no a seguir subiendo el límite.

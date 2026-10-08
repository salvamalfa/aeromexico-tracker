# Airline Tracker chat — remediación de auditoría y contraseña

Fecha: 4 de octubre de 2026. Continúa
[`airline-tracker-implementacion-20261003.md`](airline-tracker-implementacion-20261003.md)
y el traspaso [`docs/archivo/chat-mvp/traspaso-claude-20261003.md`](traspaso-claude-20261003.md).
Lo hizo Claude Code en la misma rama y PR (#81). El entorno de Claude no ofrece
subagentes GPT-6 Luna; el trabajo se hizo sin ellos.

## Qué cambió y por qué

Se corrigieron los hallazgos de la auditoría publicada en el PR #81, y se
cambió la autenticación del piloto por decisión del dueño: **una contraseña**
en vez de tokens bearer.

| Hallazgo | Corrección | Prueba |
|---|---|---|
| Modo `local` detrás de un proxy inverso dejaba la API abierta (peer y `Host` loopback). | Rechaza `Forwarded`, `X-Forwarded-*` y `X-Real-IP` con 403; `CHAT_PROVIDER=openai` exige `CHAT_AUTH_MODE=password` salvo `CHAT_ALLOW_LOCAL_OPENAI=true`. | `test_chat_api.py` |
| Token bearer escrito por el usuario. | Modo `password`: hash scrypt con sal (stdlib), `POST /login` → sesión opaca de 12 h (solo su SHA-256 en SQLite), `POST /logout`, rotación del hash invalida sesiones, 5 fallos por cliente / 15 min y 50 globales / h con `429` + `Retry-After`, IP de `X-Forwarded-For` solo desde `CHAT_TRUSTED_PROXY`. Subcomando `hash-password [--generate]`. | `test_chat_api.py`, `test_chat_integration.py` |
| `compare_metrics` invertía el signo según el orden y fallaba con periodos repetidos. | Ordena cronológicamente; rechaza periodos iguales o mezcla mes/trimestre con `PlanValidationError`. | `test_chat_tools.py` |
| El panel no retomaba turnos `pending` (buscaba `queued`/`in_progress`). | Tipos alineados con el backend (`pending`/`running`). | smoke de navegador |
| Una sesión nueva del proveedor perdía el historial (tras reinicio o borrado remoto). | Se envía `conversation_history` acotado (8 mensajes, 2 000 caracteres c/u, 8 000 total), marcado como no confiable en las instrucciones. Una sesión existente no lo reenvía. | `test_chat_openai_turns.py` |
| Un `ValueError`/`KeyError` del registry tumbaba el turno entero. | Errores de argumentos se persisten y se devuelven al modelo como `tool_result` con `success=false`; los errores de almacenamiento siguen fallando el turno. | `test_chat_worker.py`, `test_chat_openai_turns.py` |
| SQLite síncrono dentro de handlers `async`; SSE sin duración máxima. | Endpoints `def` (threadpool), SSE y middleware usan `run_in_threadpool`; una sola consulta de eventos + estado; cada conexión SSE dura como máximo `max_turn_seconds + 30` s y el cliente reconecta. | `test_chat_integration.py` |
| Uso real de turnos fallidos o cancelados nunca se registraba. | Si el proveedor reporta uso en `turn.failed`/`turn.cancelled`, se contabiliza en `usage_daily` y se libera la reserva. Sin uso reportado, la reserva conservadora sigue todo el día. | `test_chat_worker.py`, `test_chat_openai_turns.py` |
| La UI podía quedar "En proceso" para siempre. | El contador de reconexión se reinicia con cada evento; al agotarse se consulta el estado real del turno y se libera el compositor. | Vitest + smoke |
| El contexto cambiaba con el hover. | Solo clic o foco explícito en la tarjeta fijan el contexto. | revisión de código |
| Clave de deltas `item_id_index` (inexistente en el SDK). | Se usa `item_id`. | `test_chat_openai.py` |
| Límite del sobre (12 000 bytes) solo en el proveedor. | También se valida al admitir: `422` antes de reservar cuota. | `test_chat_openai_turns.py` |
| `Content-Length` evitable con `Transfer-Encoding: chunked`. | POST sin `Content-Length` → `411`; login ≤ 1 KB. | `test_chat_api.py` |
| Retención encolaba borrado remoto de conversaciones conservadas. | Mismo predicado para encolar y borrar. | `test_chat_storage.py` |
| SSE: `payload.type`/`seq` podían sobrescribir `event:`/`id:`. | Los campos SSE mandan. | `transport.test.ts` |
| `_active_sessions` crecía sin límite. | Conjunto por turno. | — |
| `max_concurrent_global` sugería paralelismo. | Documentado como límite de cola (pendientes + en curso; un worker). | — |
| `define: { global }` cambiaba el bundle público. | Solo aplica a `vite` (serve). Sin él, `vite build` produce exactamente `index-DJFAXsLk.js`, `bootstrap-DuyBWib0.js` e `index-BqgCH9Q3.css` de master. | `cmp` contra `site/` |

### `site/` vuelve a ser el de master

Como el build de producción de esta rama es byte a byte igual al publicado,
`site/` se restauró desde `origin/master` (el PR ya no modifica `site/`) y
`python -m src.publish.verify site/` lo valida. La versión de datos del chat es
el SHA-256 de `site/publication_manifest.json`, así que el holdout se volvió a
fijar a la del manifiesto publicado:

- datos: `de3c4d404837b8c19d306c301cd5647cc955d26215a45bc0c8f8b7bed00db668`
  (antes `388d3437…`, el manifiesto regenerado del commit `dcb3a95`);
- semántica: `d43faaad53a352cbbfea194c6ffa978ebef8bce6a4d403cc52553158fcb11b2a` (sin cambio).

Los 112 archivos de `site/data/v1/` y el `analysis_manifest` son los de master;
no se ejecutó el gate ni se tocó ninguna aprobación.

## Segunda auditoría (agente independiente)

Un agente nuevo, sin el contexto de esta sesión, auditó los cambios anteriores
y reprodujo siete defectos. Todos se corrigieron. Cada prueba nueva falla con
el código previo y pasa con el corregido.

| Defecto | Corrección | Prueba |
|---|---|---|
| El límite global de intentos fallidos se revisaba antes de verificar la contraseña: 50 contraseñas erróneas por hora desde cualquier IP bloqueaban al dueño con la contraseña correcta. | Solo el límite por cliente bloquea; el global queda como umbral de alerta (log de error). | `test_failures_from_many_addresses_never_lock_out_the_owner` |
| Logins concurrentes se saltaban el límite por cliente, y cada scrypt usa 32 MiB. | El intento se registra como fallo en una transacción `BEGIN IMMEDIATE` antes de verificar y se borra si acierta; un semáforo limita a 2 verificaciones simultáneas (503 si espera > 10 s). | `test_concurrent_wrong_logins_cannot_exceed_the_per_client_limit`, `test_successful_login_does_not_consume_the_failure_budget` |
| Una respuesta recuperada tras un stream cortado se guardaba duplicada (texto completo + delta parcial), regresión de la clave `item_id`. | La recuperación descarta los deltas parciales. | `test_recovered_answer_replaces_partial_deltas_instead_of_appending` |
| El panel podía abrir dos streams del mismo turno (401 al cancelar y nuevo login, doble clic en el lanzador): el texto salía duplicado. | `listen()` aborta el stream anterior; el transporte deja de despachar en cuanto la señal se aborta; `ensureConversation` es de un solo vuelo. | `bootstrap.test.ts` |
| Si borrar la conversación fallaba durante un turno, el compositor quedaba bloqueado. | El stream sigue hasta que el borrado tiene éxito; si falla con el turno ya cancelado, se liquida desde el estado del servidor. | `bootstrap.test.ts` |
| `logout` y `DELETE` respondían 204 con cuerpo `null`, lo que rompe keep-alive con uvicorn (h11). | `Response(status_code=204)` sin cuerpo. Verificado además contra uvicorn real. | `test_no_content_responses_have_no_body` |
| El cliente SSE rechazaba un replay válido si llegaba en un solo bloque de más de 128 000 caracteres. | El límite se aplica solo al fragmento incompleto tras despachar los eventos completos. | `transport.test.ts` |

También se corrigieron tres puntos menores que señaló: el cierre de sesión ya
no olvida la conversación guardada, y un turno fallido sin texto muestra una
burbuja con "Reintentar". El tercero queda documentado: si dos usuarios se
configuran con la misma contraseña, ninguno puede entrar (identidad ambigua);
con una sola contraseña del dueño no aplica.

## Validación

| Comando | Resultado |
|---|---|
| `pytest -q tests/test_chat_*.py tests/test_repo_budgets.py` | 64 passed tras la segunda auditoría. |
| `pytest -m "not local_data and not browser" -q` (CI `test`) | 621 passed, 6 skipped. |
| `npm run check`, `npm run test`, `npm run build` (CI `web`) | Limpios; 89 Vitest. Build idéntico a `site/assets/`. |
| Smokes de navegador (chat, página, vuelos) | 9 passed con el Chromium preinstalado. El smoke del chat cubre contraseña incorrecta/correcta, que la contraseña no queda en el DOM ni en `localStorage`, reanudación de un turno `pending` tras recargar y sesión vencida. |
| `evaluation --audit-snapshot` | 12/12 con la versión re-fijada. |
| `ruff check` / `ruff format --check` del paquete y pruebas del chat | Limpios. Módulos ≤ 600 líneas Python y ≤ 400 TypeScript. |

## Estado de H3–H5

| Hito | Estado |
|---|---|
| H3 — chat real local | Bloqueado: `OPENAI_API_KEY` **no está disponible** en el entorno de Claude (comprobado sin mostrar valores). La sonda autorizada no se ejecutó; no hubo gasto. |
| H4 — modelo elegido | Pendiente de H3. Presupuesto autorizado intacto: US$10 para sonda + 40 preguntas × 3 candidatos. |
| H5 — piloto | Código de autenticación listo (contraseña única del dueño). Falta host persistente, que requiere autorización específica para contratarse; el panel sigue apagado en el sitio. |

## Límites

- La contraseña real no se generó en este cambio: debe generarse con
  `hash-password --generate` y entregarse solo al dueño, nunca en Git ni en el PR.
- Un atacante con muchas direcciones IP puede probar 5 contraseñas por IP cada
  15 minutos; el umbral global solo alerta. La contraseña generada (24
  caracteres aleatorios, ~144 bits) hace inviable la fuerza bruta.
- El texto previo a una llamada de herramienta ("voy a consultar…") sigue
  concatenado a la respuesta final; se evaluará con la sonda real antes de
  cambiar la extracción.
- La reserva de cuota (~42 000 tokens / US$0.64 por turno con los valores por
  defecto) no es una cota superior en bucles de agente; el tope diario es
  operativo, no una garantía de factura. Se calibrará con la sonda.

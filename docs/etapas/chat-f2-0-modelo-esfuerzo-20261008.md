# Chat F2.0: modelo, esfuerzo y reservas conservadoras

Fecha local del dueño: 8 de octubre de 2026. Verificación de documentación
oficial: 9 de octubre de 2026 UTC. Alcance: fijar y reportar los parámetros de
inferencia de los candidatos Luna y Sol para la fase 2, con validación local y
sin consultas facturables.

## Resultado

- `config/chat/models.json` versiona capacidades, precios estándar, caché y
  prima de contexto largo para `gpt-6-luna` y `gpt-6.1-sol`. Es JSON para que
  `Snapshot.semantic_version` siga describiendo solo métricas y definiciones de
  negocio; ese cálculo incluye YAML de `config/chat/`, no este catálogo del
  runtime.
- `CHAT_REASONING_EFFORT` y `CHAT_TEXT_VERBOSITY` se validan al cargar la
  configuración. El esfuerzo por omisión es `medium`, que coincide con el
  valor efectivo por omisión de ambos modelos; la verbosidad explícita por
  omisión también es `medium`. La selección se envía en cada creación de
  sesión por `agent.reasoning.effort` y `agent.text.verbosity`.
- La base guarda modelo, esfuerzo y verbosidad por conversación y por turno.
  También fija el proveedor para evitar que una sesión remota OpenAI quede
  desincronizada tras insertar turnos mock; conversaciones antiguas con una
  sesión remota se reconocen como OpenAI para ese control. Para el caso ambiguo
  (`provider IS NULL` con `provider_session_id` presente), se conserva el
  rechazo a `mock` antes de encolar o reservar: el ID local basta para evitar
  mezclar una respuesta mock en un historial remoto. No se intenta recuperar ni
  consultar la sesión. Filas legacy sin ID de sesión no quedan bloqueadas por
  esta regla.
  El health reporta los valores activos y la cantidad teórica de reservas
  mínimas que cabe bajo los topes diarios. Los informes de evaluación deben
  atribuir cada respuesta a su combinación `modelo@esfuerzo` y su verbosidad.
- Las conversaciones creadas antes de F2.0 no tienen settings locales fijados.
  Conservan historial de lectura, pero nuevas preguntas requieren conversación
  nueva. También hace falta conversación nueva cuando cambie modelo, esfuerzo
  o verbosidad. La aplicación nunca envía input a una sesión remota con una
  selección anterior que el ledger local no pueda confirmar.
- Si un turno estaba en cola y el entorno cambia antes de ejecutarlo, el worker
  lo falla antes de llamar al proveedor y registra uso conocido cero, liberando
  la reserva. Los turnos `running` que sobreviven a un reinicio siguen la
  recuperación conservadora existente: no se reejecutan ni se declaran uso
  cero.

## Capacidades y precios verificados

| Modelo | Esfuerzos aceptados por catálogo | Input / cached / cache write / output USD por millón |
|---|---|---|
| `gpt-6-luna` | `none`, `low`, `medium`, `high`, `xhigh`, `max` | 0.10 / 0.01 / 0.125 / 0.50 |
| `gpt-6.1-sol` | `low`, `medium`, `high`, `xhigh`, `max` | 2 / 0.10 / 2.50 / 10 |

El esquema `AgentTextParam` del SDK documenta verbosidad `low`, `medium` y
`high`. Las fichas oficiales documentan cache writes a 1.25× del input sin
caché, y una tarifa long-context por encima de
272,000 tokens de entrada: input 2× y output 1.5× para toda la solicitud. El
ledger conservador cobra los inputs confirmados como si todos fueran cache
writes; si la entrada supera el umbral usa además la prima long-context. La
reserva cobra todos los tokens al mayor precio catalogado, hasta output de
contexto largo. Esto cubre los multiplicadores documentados dentro del volumen
reservado, pero no garantiza el gasto: Agents API no expone un máximo acumulado
de tokens de salida para todo el turno.

Con una reserva mínima de 150,000 tokens y topes operativos documentados de
US$5 por usuario y global, la admisión puede apartar hasta 13 reservas Luna
(US$0.1125 cada una; limita el cupo de 2 millones de tokens) o 2 reservas Sol
(US$2.25 cada una). La estimación dinámica puede reservar más. El default de
código local `CHAT_MAX_TOOL_CALLS=8` sigue siendo distinto de las 16 consultas
del límite operativo documentado para producción; este cambio no modificó el
default ni afirmó que Railway haya cambiado.

## Fuentes e implementación

- [Modelo gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Modelo gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Agents API sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions)
- [Configuración de agentes y sesiones existentes](https://developers.openai.com/api/docs/guides/agents-api/configuration)
- OpenAI Python SDK 3.13.0, instalado desde el `uv.lock` del proyecto y
  revisado localmente. Sus tipos `SessionCreateParams.Agent`,
  `AgentReasoningParam` y `AgentTextParam` aceptan exactamente los campos
  usados. La guía de sesiones permite cambiar modelo y esfuerzo en una sesión
  existente, pero no verbosidad; por ello se exige nueva conversación al
  cambiar cualquiera de los tres valores.

Se agregó la copia JSON al Dockerfile para que el launcher desplegado valide el
mismo catálogo. No se modificó el prompt vigente ni los datos del dashboard.
No se consultó OpenAI, no se gastó presupuesto y no se cambiaron variables ni
sesiones de Railway. Las reservas históricas desconocidas permanecen intactas.

## Validación offline

- `tests/test_chat_f20_model_settings.py`: catálogo, valores por omisión,
  rechazo de combinaciones inválidas y precios no coincidentes, costos por
  contexto largo, persistencia por conversación/turno, migración SQLite,
  deduplicación y reserva liberada al cambiar el runtime antes del envío.
- `tests/test_chat_token_policy.py`, `tests/test_chat_openai.py`,
  `tests/test_chat_openai_recovery_paths.py`, `tests/test_chat_integration.py`,
  `tests/test_chat_api.py`, `tests/test_chat_railway_runtime.py`,
  `tests/test_chat_openai_shutdown_authorization.py`,
  `tests/test_chat_worker_limits.py` y `tests/test_chat_worker_shutdown.py`.
- Resultado focalizado final: 86 pruebas pasaron, incluidas las rutas de
  recuperación y apagado que fijan explícitamente el proveedor mock en sus
  conversaciones y turnos sintéticos.
- Subconjunto público de CI (`pytest -m "not local_data and not browser" -q`):
  887 pruebas pasaron, 6 omitidas, 79 excluidas por marcador y 14 subpruebas
  pasaron. `scripts.check_chat_runtime` pasó sin llamadas al proveedor; Ruff
  pasó en `src/` y `scripts/`; `git diff --check` quedó limpio.
- El warehouse local no está presente, así que las pruebas marcadas
  `local_data` no se ejecutaron. El Chromium local tampoco está instalado; la
  corrida integral local no pudo completar los smoke tests marcados `browser`.
  El job `web` de CI instala Chromium y ejecuta esa regresión en el PR.

Pendiente: evaluación de calidad, latencia y uso real en F2.9. Las preguntas
de esa etapa requieren autorización de presupuesto por separado. El prompt y
los casos de evaluación se agrupan para revisión humana según el plan de fase 2.

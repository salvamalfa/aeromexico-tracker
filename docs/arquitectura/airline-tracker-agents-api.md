# Adaptador Agents API de Airline Tracker

El piloto usa el cliente Python oficial `openai==3.13.0` y la Agents API con
`environment.type="none"`. No instala `openai-agents`, no crea un entorno de
ejecución y no permite shell, búsqueda web ni herramientas ajenas a las siete
funciones de consulta definidas en `src/conversational_analytics/tools/`.

La integración vive en
[`src/conversational_analytics/providers/openai.py`](../../src/conversational_analytics/providers/openai.py).
El resto del servicio usa la misma interfaz que el proveedor simulado. Las
llamadas a datos se ejecutan en el worker local contra el snapshot publicado y
validado; OpenAI no recibe el warehouse.

## Selección y configuración

El proveedor predeterminado sigue siendo `mock`. Para habilitar OpenAI se debe
configurar explícitamente `CHAT_PROVIDER=openai`, `CHAT_OPENAI_ENABLED=true`,
un `CHAT_MODEL` con el identificador elegido por el responsable del proyecto,
`OPENAI_API_KEY` y los precios de entrada/salida por millón de tokens mediante
`CHAT_INPUT_COST_PER_MILLION` y `CHAT_OUTPUT_COST_PER_MILLION`. No hay un modelo
predeterminado. `ChatConfig.from_env()` falla al iniciar si faltan los controles
requeridos; tener una variable de clave presente no valida que la cuenta tenga
acceso a Agents API.

Instala solo las dependencias del piloto de chat:

```sh
uv sync --extra chat
```

Con datos públicos de `site/` disponibles, el servicio local arranca con:

```sh
uv run --extra chat python -m src.conversational_analytics --host 127.0.0.1 --port 8765
```

La ejecución del proveedor OpenAI realiza consumo de API. No ejecutar una
prueba en vivo ni elegir precios/modelo para producción sin la autorización de
presupuesto específica del proyecto. La suite normal usa fakes tipados y no
requiere credenciales ni llamadas pagadas.

## Sesiones y turnos

Una conversación local comienza sin sesión del proveedor. Como la API exige
entrada inicial para `environment.type="none"`, el primer mensaje se envía con
`sessions.create(..., input=..., stream=True)`; el ID real se guarda en SQLite
en cuanto aparece. Para mensajes siguientes el adaptador abre
`sessions.events.stream(session_id)` antes de enviar
`agent.session.input.message`. Reutiliza una clave de idempotencia por turno
lógico en los envíos de seguimiento. El cliente se configura con reintentos
automáticos desactivados; ante un timeout ambiguo el adaptador recupera el
estado guardado de sesión/turno y no reenvía el mensaje.

El worker conserva el historial visible en SQLite. Registra el ID de sesión;
los metadatos privados `provider.metadata` relacionan el ID de turno y los
eventos del proveedor con el turno local, y el dispatcher guarda cada resultado
de herramienta antes de entregarlo al agente usando `(turn_id, call_id)`. Los
IDs de proveedor no son autorización ni se publican al navegador. La interfaz
recibe eventos propios persistidos por el servicio y puede recuperarlos tras
perder la conexión.

El adaptador requiere `agent.session.turn.completed` para declarar éxito.
`agent.session.turn.failed` marca error, `agent.session.turn.cancelled` marca
cancelación, e `agent.session.idle` por sí solo no completa el turno. Si el
stream se interrumpe, lee estado, turnos e items guardados para recuperar el
resultado y no duplica la entrada. Los límites locales configurables controlan
duración, cantidad de herramientas y bytes de cada resultado. Cancelar usa el
evento `agent.session.input.cancel`; borrar una conversación intenta borrar
también la sesión del proveedor y encola la eliminación si el servicio no está
disponible.

## Semántica y datos confiables

El prompt estable instruye al agente a consultar el catálogo y las definiciones
antes de proponer un plan. El contexto del dashboard de cada mensaje viaja como
un sobre JSON separado de las instrucciones confiables, así un periodo o filtro
nuevo reemplaza el contexto anterior dentro de la misma sesión. El texto de la
pregunta y los resultados de herramientas/fuentes se tratan como datos, no como
instrucciones. La herramienta local valida IDs, periodos, dimensiones,
agregaciones y versión de snapshot antes de leer datos.

Las funciones permitidas son `get_data_catalog`, `get_metric_definition`,
`query_metrics`, `compare_metrics`, `get_time_series`,
`get_source_references` y `get_dashboard_context`. Las referencias y cualquier
estructura de gráfica proceden de resultados deterministas del worker, no de
enlaces o valores inventados en la respuesta del modelo.

## Verificación y límites actuales

La versión del SDK queda fijada en el extra opcional `chat` de `pyproject.toml`
y en `uv.lock`. `tests/test_chat_openai.py` valida eventos tipados del SDK,
llamadas de herramientas, contexto de seguimiento, terminales fallidos/cancelados,
recuperación tras desconexión, cancelación y borrado. Estas pruebas no verifican
permisos reales, disponibilidad del modelo, tarifas ni acceso de la cuenta al
endpoint Agents API. La autorización de uso pagado y la selección del modelo del
dashboard siguen pendientes.

Contrato consultado el 4 de octubre de 2026: [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview),
[sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions),
[events](https://developers.openai.com/api/docs/guides/agents-api/sessions/events) y
[function tools](https://developers.openai.com/api/docs/guides/agents-api/tools/functions).
También se verificaron los modelos de eventos del wheel público `openai==3.13.0`.

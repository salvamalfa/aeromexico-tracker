# Backend del chat de Airlines Tracker

Servicio FastAPI opcional sobre la publicación verificada de `site/`. El
registro de herramientas consulta y calcula sobre datos públicos; SQLite guarda
conversaciones, resultados y eventos. No abre el almacén privado del proyecto.
La [guía del chat](../../docs/chat/README.md) explica el uso desde el dashboard y
la [arquitectura](../../docs/arquitectura/airline-tracker-agents-api.md) muestra
el ciclo del modelo y las herramientas.

## Instalación local

Ejecuta desde la raíz del repositorio, con la publicación `site/` disponible:

```sh
uv sync --extra chat
uv run --extra chat python -m src.conversational_analytics --host 127.0.0.1 --port 8765
```

El modo predeterminado `mock` consulta el mismo registro determinista que el
adaptador del modelo y presenta sus valores sin llamadas pagadas. No inventa
respuestas para datos ausentes. El CLI local escucha en loopback; el estado
queda en `~/.local/state/airline-tracker/chat.sqlite3`, configurable con
`CHAT_STATE_PATH`. La [guía de operación](../../docs/chat/operations.md)
documenta el entorno bloqueado, la interfaz local y el despliegue.

## Proveedores y configuración

`openai` requiere `CHAT_PROVIDER=openai`, `CHAT_OPENAI_ENABLED=true`,
`CHAT_MODEL` explícito y `OPENAI_API_KEY` en el entorno privado del servidor.
Los valores de `CHAT_REASONING_EFFORT` y `CHAT_TEXT_VERBOSITY` se validan con
[`config/chat/models.json`](../../config/chat/models.json). Los precios proceden
de ese catálogo; si se configuran `CHAT_INPUT_COST_PER_MILLION` o
`CHAT_OUTPUT_COST_PER_MILLION`, deben coincidir con los precios versionados.

Las capacidades adicionales se habilitan por separado:

| Variable | Capacidad |
|---|---|
| `CHAT_ENABLE_ROUTE_TOOLS` | `query_routes` y `find_shared_routes`. |
| `CHAT_ENABLE_BUSINESS_METRIC_TOOLS` | `query_business_metrics` y `get_business_metric_definition`. |
| `CHAT_ENABLE_EVIDENCE_TOOLS` | `search_reports` y `search_news` sobre el índice aprobado. |
| `CHAT_ENABLE_OFFICIAL_ROUTE_TOOLS` | `query_official_routes`, con `CHAT_OFFICIAL_ROUTE_DATASET_SHA256` fijado al mapa autorizado. |

Las tres primeras capacidades requieren un prompt compatible con su aprobación;
el código conserva R1 y las capacidades apagadas por omisión. Modelo, prompt y
versiones efectivas se consultan en el servicio. El ejemplo de
[variables de entorno](../../config/chat/runtime.example.env) y
[`config.py`](config.py) son la referencia completa. Las credenciales no se
incluyen en Git ni en la compilación de Vite.

## Contrato HTTP

| Ruta | Resultado |
|---|---|
| `GET /api/chat/health` | Estado del servicio, worker, proveedor, admisión, modo de autenticación y versión de datos. En OpenAI añade modelo, esfuerzo, verbosidad y reservas mínimas que caben en los presupuestos. Es pública en modo contraseña; no informa sobre secretos. |
| `POST /api/chat/login`, `POST /api/chat/logout` | Crean o revocan la sesión de acceso; véase la autenticación abajo. |
| `POST /api/chat/conversations` | Crea una conversación con datos, semántica y configuración del modelo fijados. En OpenAI registra modelo, esfuerzo y verbosidad en SQLite y en la respuesta. |
| `GET /api/chat/conversations/{id}` | Devuelve versiones, mensajes visibles y estados de turnos. Comprueba propietario. |
| `DELETE /api/chat/conversations/{id}` | Cancela el trabajo activo, solicita borrar la sesión remota y elimina mensajes y eventos locales. |
| `POST /api/chat/conversations/{id}/messages` | Acepta `{content,client_message_id,context}` y devuelve `{turn_id,status,deduplicated}`. Repetir el ID devuelve el turno original; sólo se admite un turno activo por conversación. |
| `GET /api/chat/turns/{id}/events?after=N` | Transmite eventos SSE persistidos. `id` es la secuencia del turno; `Last-Event-ID` permite reanudar una conexión. |
| `POST /api/chat/turns/{id}/cancel` | Solicita cancelar el turno y devuelve su estado. |

Las rutas de conversaciones y turnos verifican al propietario en cada petición.
`context` debe cumplir `semantic.context.validate_context`. El flujo emite
`turn.queued`, `turn.started`, `message.delta`, `message.completed`
(`content`, `references`, `chart`), `tool.started`, `tool.completed` y un
estado terminal: `turn.completed`, `turn.failed` o `turn.cancelled`.
Los identificadores del proveedor no forman parte del flujo público.

## Autenticación y límites

El modo `local` admite únicamente conexiones, `Host` y orígenes de loopback.
Rechaza `Forwarded`, `X-Forwarded-*` y `X-Real-IP`: un proxy podría hacer
que cualquier cliente pareciera local. Para combinarlo con OpenAI se necesita
`CHAT_ALLOW_LOCAL_OPENAI=true` en la máquina del dueño.

Un backend desplegado usa `CHAT_AUTH_MODE=password`:

- `CHAT_PASSWORDS_JSON` contiene entradas `{"user_id", "password_hash"}`.
  El comando `python -m src.conversational_analytics hash-password` calcula
  hashes scrypt con sal; `--generate` muestra una contraseña aleatoria y su
  hash una sola vez. Ambos se conservan fuera de Git.
- `POST /api/chat/login` recibe `{"password"}` y devuelve
  `{session, expires_at}`. Se almacena sólo el SHA-256 de la sesión, con
  caducidad `CHAT_SESSION_TTL_HOURS` (12 horas por omisión). Rotar el hash del
  usuario invalida sus sesiones; `POST /api/chat/logout` revoca la sesión.
- Excepto `GET /api/chat/health`, las rutas requieren
  `Authorization: Bearer <session>`. `CHAT_ALLOWED_ORIGINS` es obligatorio:
  orígenes HTTPS sin rutas o los orígenes locales de desarrollo expresamente
  permitidos por la configuración. La sesión viaja por cabecera y queda sólo
  en memoria del navegador; no se usan cookies.
- Cinco intentos fallidos por cliente en 15 minutos devuelven `429` con
  `Retry-After`. Cincuenta fallos globales en una hora generan una alerta,
  sin bloquear todos los accesos.
- `X-Forwarded-For` sólo se acepta desde un par incluido en
  `CHAT_TRUSTED_PROXY`, con IP o red CIDR local, privada o compartida. Se lee
  desde la derecha, omitiendo saltos confiables. El lanzador de Railway usa
  por omisión `100.64.0.0/10`.

Los cuerpos POST se limitan por bytes recibidos, incluso sin `Content-Length`
o con transferencia por fragmentos. Se rechazan longitudes declaradas
inválidas o distintas de las recibidas. La lectura tiene plazo máximo y el
cuerpo de acceso admite hasta 1 KB.

Las variables `CHAT_*` controlan presupuestos diarios de tokens y costo,
mensajes, herramientas, duración, admisión y retención.
`CHAT_MAX_CONCURRENT_GLOBAL` limita la suma de turnos pendientes y activos:
un único worker los ejecuta en orden. El número de reservas informado por
health no equivale a un saldo de facturación. Los detalles de consumo y cierre
están en [operación](../../docs/chat/operations.md).

## Versiones y recuperación

Las conversaciones conservan `data_version` y `semantic_version`. Si cambian,
el historial sigue disponible, pero otro turno devuelve un conflicto y exige
una conversación nueva. OpenAI fija también modelo, esfuerzo y verbosidad;
las conversaciones antiguas sin esos campos o con otra configuración tampoco
admiten preguntas nuevas.

Una llamada interrumpida por reinicio del proceso se marca fallida y se
cancela o elimina su sesión remota. El turno ambiguo no se repite. Los eventos
SSE persistidos permiten recuperar el historial sin generar otra entrada.

### Recuperar un turno `provider_error`

`scripts/chat/reconcile_failed_turn.py` puede recuperar un turno local fallido
si el proveedor conserva ese turno exacto completado. Por omisión sólo consulta
el estado local y muestra metadatos mínimos, sin pregunta, respuesta ni
identificadores. `--apply` exige petición explícita del dueño, vista previa
elegible e identidad exacta de usuario, conversación, sesión, turno y versiones.

La aplicación sólo hace GET del turno y sus elementos existentes. Comprueba
estado completado, uso conocido y resultados de herramientas ya guardados.
La transacción rechaza cambios de identidad o versión, turnos posteriores,
respuesta previa, cancelación, tiempo agotado o sesión eliminada. Conserva
`turn.failed`, registra el uso de forma idempotente y guarda la respuesta sólo
en la base privada. No envía otra pregunta ni reactiva el worker.

La pregunta histórica del 7 de octubre no quedó acreditada como recuperable.
Su existencia no autoriza aplicar el procedimiento ni volver a enviarla.

## Mapa de vuelos regulares

`query_official_routes` consulta exclusivamente
`data/v1/official-routes.json`, contrato `official_route_network_v1`. Su
activación es independiente de las herramientas de rutas anteriores.
El catálogo incluye la versión exacta; un contexto oficial rechaza
`query_routes` y `find_shared_routes` para evitar mezclar evidencias.

El botón **Pregunta** de `route-flow-map` adjunta el trimestre global y
`map_dataset_version`, `map_scope`, `map_grain`, `map_months`,
`map_carriers` y, cuando corresponde, `map_region`. La vista general de
Mercado envía esos filtros incluso sin tarjeta; las demás tarjetas conservan
su propio contexto.

`dataset_version` es el SHA-256 del contenido canónico excluyendo ese campo.
`Snapshot` comprueba también el hash de los bytes completos y el contrato del
manifiesto. La herramienta rechaza una versión o meses distintos de los
publicados. La [activación en Railway](../../docs/chat/railway.md#activar-el-mapa-oficial)
requiere la misma versión que sirve la interfaz.

- Nacional e Internacional usan pares de ciudades AFAC, todas las aerolíneas
  y ninguna celda ciudad × operador. No admiten filtro de aerolínea.
  Internacional excluye Estados Unidos geográfico; admite Canadá,
  Centroamérica y Caribe —incluidos Puerto Rico e Islas Vírgenes—,
  Sudamérica, Europa y Asia.
- EEUU usa pares de aeropuertos BTS y una selección no vacía de Grupo
  Aeroméxico, Volaris y Viva; omitirla selecciona las tres. Aerovías y Connect
  conservan identificadores y cifras separados. Incluye vuelos regulares de
  pasajeros y carga, clases F y G, y excluye charter L y P.
- Los argumentos explícitos prevalecen sobre el contexto. Cambiar de ámbito
  no hereda filtros exclusivos del anterior. `region: "all"` elimina el
  filtro internacional; `region: null` u omisión heredan la región del
  contexto. Otra región explícita la reemplaza.
- Una selección sin observaciones devuelve `missing` y totales nulos, sin
  sustituir el trimestre. Un trimestre sin red publicada exige meses adjuntos
  vacíos. El orden de aerolíneas no cambia el significado de la selección.
- Las filas conservan comparación publicada, meses y motivo de ausencia.
  `comparison.comparison_months` mantiene los meses del año actual;
  `comparison_calendar` identifica por separado el trimestre y los meses del
  anterior. La cobertura y los totales de la selección se conservan aunque
  el límite de transporte recorte el detalle de rutas.

Las pruebas `tests/test_chat_official_routes*.py` cubren herramienta, API,
worker, almacenamiento, sesiones simuladas, hashes y contenedor mínimo. Usan
cifras sintéticas, sin claves ni preguntas pagadas; no aprueban un dataset.

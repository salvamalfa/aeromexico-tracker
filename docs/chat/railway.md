# Railway: backend de producción

Este perfil despliega solo el backend del chat, activo en producción desde el
8 de octubre de 2026 (servicio `aeromexico-tracker`, proyecto
`soothing-possibility`, volumen `/data`). Railway usa `Dockerfile.chat`
mediante el ajuste de servicio `RAILWAY_DOCKERFILE_PATH=Dockerfile.chat`; la
imagen instala el grupo bloqueado `chat-runtime`,
verifica el snapshot público que el repositorio ya publica y arranca Uvicorn en
`0.0.0.0:$PORT`. No ejecuta el pipeline de datos ni incluye warehouse, bronce,
plata, `analysis_runs`, credenciales o pruebas. El frontend sigue en Pages y
debe usar la URL HTTPS de este servicio.

No uses `railway.json` para crear este servicio. Railway documenta que Config as
Code está deprecado y que los servicios nuevos no pueden adoptarlo; validar el
JSON contra el esquema legado no demuestra que Railway vaya a aplicarlo.
Configura el Dockerfile y las opciones de deploy en el servicio de Railway.
Los watch paths del servicio (Settings → Build) se configuraron el 8 de octubre
de 2026: Railway redespliega el chat únicamente cuando cambia uno de esos
archivos, así que un merge solo de documentación o de `web/` no lo reinicia.
`railway.toml` guarda la misma lista versionada, y
`tests/test_railway_watch_patterns.py` comprueba que cubra todo lo que copia
`Dockerfile.chat`. Como Config as Code está deprecado (corte el 1 de diciembre
de 2026), no dependas de que Railway lea ese archivo: si agregas un `COPY`,
agrega su patrón en `railway.toml` **y** en la configuración del servicio.

## Activar el mapa oficial

La nueva herramienta queda preparada y apagada por omisión. El paso final de
entrega requiere la aprobación del dueño para la versión exacta de los datos,
según [AGENTS.md](../../AGENTS.md). Un build, una prueba sintética o la aprobación
de código no reemplazan esa decisión. No se han modificado variables ni
despliegues de Railway durante la preparación del backend.

Después de esa aprobación:

1. Publica el dataset oficial mediante el gate del proyecto con su contrato y
   manifiesto exactos. Verifica `site/` y el JSON servido en Pages.
2. Prepara la imagen del chat con ese mismo `site/`, incluido
   `src/dashboard/official_routes_contract.py` y `official_routes_geo.py`. Estos
   helpers no cargan pandas en el chat; el constructor y sus insumos quedan fuera.
3. Conserva el prompt R2 y sus recibos aprobados. Configura juntos
   `CHAT_ENABLE_OFFICIAL_ROUTE_TOOLS=true` y
   `CHAT_OFFICIAL_ROUTE_DATASET_SHA256=<dataset_version aprobado>`. El segundo
   valor es el digest canónico del payload excluyendo únicamente su propio
   campo `dataset_version`; no es el hash de todos los bytes del archivo.
   Snapshot verifica ese segundo hash, distinto, contra el manifiesto.
4. Incluye ambos helpers `src/dashboard/official_routes_*.py` en los watch paths reales
   del servicio, además de la lista versionada de `railway.toml`. Despliega la
   imagen final. Mantén las banderas y los pins existentes de métricas y noticias.
5. Comprueba health: `official_route_queries` debe estar en
   `enabled_capabilities`, y `official_route_dataset_version` debe coincidir con
   el `dataset_version` servido y el chip de Mercado. Verifica primero con
   llamadas directas y proveedor falso; no consumas el modelo real sin
   autorización específica. Las conversaciones anteriores requieren una nueva
   conversación por el cambio explícito de `snapshot_version` y semántica.

Un pin distinto o un contrato no verificable impide iniciar la herramienta.
Para desactivarla, usa `CHAT_ENABLE_OFFICIAL_ROUTE_TOOLS=false`; el catálogo
deja de exponerla. Esto no revierte la versión de los datos publicada ni cambia
las consultas históricas. No marques la entrega como activada hasta comprobar
la misma versión en interfaz y backend.

## Configuración de una sola instancia

En **Variables** del servicio agrega:

```text
RAILWAY_DOCKERFILE_PATH=Dockerfile.chat
```

Producción tiene R2 activo con `gpt-6.1-sol`, esfuerzo `low` y verbosidad
`medium`; rutas, métricas financieras y evidencia están habilitadas. Stage 3
terminó y recibió revisión del dueño. El despliegue, hashes efectivos y pins
verificados están en el [cierre operativo](../etapas/chat-fase2-cierre-operativo-20261012.md).

Para reconstruir esta selección, configura explícitamente `CHAT_PROMPT_VERSION=r2-proposed`,
el recibo de `config/chat/prompt_approval.json` y su pin externo, además de las
banderas autorizadas. Conserva modelo, tarifas y topes actuales; verifica en
`/api/chat/health` el hash del prompt y las capacidades, y usa una conversación
nueva. Esta comprobación no requiere una pregunta pagada.

Las cuatro métricas financieras conservan el recibo
`config/chat/business-metrics-approval-receipt.json` y el pin canónico externo
`CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256`. El índice conserva siete
pasajes y tres fichas aprobados y el pin `CHAT_EVIDENCE_APPROVED_INDEX_SHA256`.
Nunca derives los pins de confianza del archivo desplegado; el runtime falla
cerrado si no coinciden con los aprobados externamente.

Railway usa `Dockerfile` automáticamente si está en la raíz, pero `Dockerfile.chat`
es un nombre personalizado y requiere esa variable, según su [documentación de
Dockerfiles](https://docs.railway.com/builds/dockerfiles#custom-dockerfile-path).

En **Settings** del servicio configura el perfil de producción:

| Opción | Valor |
|---|---|
| Healthcheck path | `/api/chat/health` |
| Healthcheck timeout | `300` segundos |
| Réplicas | `1` |
| Serverless / dormir cuando esté inactivo | Activado |
| Región | SFO (región ya seleccionada en el servicio) |
| Deployment overlap | `0` segundos |
| Deployment draining | `230` segundos |
| Restart policy | `On Failure` |
| Restart retries | `3` |

Al iniciar Uvicorn su cierre, el launcher detiene inmediatamente los nuevos
claims antes de esperar conexiones SSE existentes. Uvicorn espera como máximo
5 segundos por ellas. El turno puede ejecutar hasta 180 segundos y, si la
respuesta terminal no trae uso, el worker permite hasta 30 segundos para una
consulta GET de uso del mismo turno, sin enviar entradas nuevas. Reserva además
10 segundos para estado local, SQLite y limpieza; con el máximo de ejecución,
el drenaje del worker es 220 segundos. El drenaje Railway de 230 segundos deja
5 segundos antes y después de ese presupuesto (5 + 220 + 5). Una configuración
`CHAT_MAX_TURN_SECONDS` menor reduce proporcionalmente la espera del worker;
el launcher rechaza valores mayores de 180 segundos en vez de recortarlos.

El código permite por defecto 8 llamadas de herramienta por turno; producción
usa `CHAT_MAX_TOOL_CALLS=16`. Agotar las llamadas o el tiempo de ejecución deja
el turno fallido; desde PR #107 el worker cancela el turno del proveedor y
registra su uso real. La consulta de uso no cambia el estado fallido ni
reintenta la respuesta. Si el uso no queda confirmado, su reserva se
mantiene. La cancelación del proveedor al vencer es best effort y no garantiza
que el remoto la acepte. La gracia permite finalizar trabajo y conciliar uso;
no demuestra que la respuesta del modelo sea correcta. Comprueba el drenaje real
en el host antes de confiar en él.

Adjunta un volumen persistente de **500 MB** montado en `/data`. La base SQLite
queda en `/data/chat.sqlite3`; el launcher restringe
los permisos del volumen a `0700` y valida que sea escribible antes de iniciar.
El contenedor necesita privilegios para ajustar permisos del volumen Railway.
No escales a múltiples réplicas: SQLite y la cola en memoria pertenecen a una instancia.
El build aislado instala el lock congelado solo para `chat-runtime`; CI valida
el lock completo con `uv sync --locked`. El Dockerfile de producción usa una
instrucción `RUN` estándar sin sintaxis experimental ni montaje BuildKit.
Si un build local necesita confiar en una CA de un proxy TLS, se puede derivar
una variante temporal por stdin, sin crear ni guardar otro Dockerfile. El
comando requiere que `SSL_CERT_FILE` señale el bundle de CA pública que se
quiere confiar. Solo monta ese archivo como secreto durante `uv sync`; TLS
permanece validado y la CA no se copia a ninguna capa:

```sh
set -o pipefail
: "${SSL_CERT_FILE:?set SSL_CERT_FILE to the trusted CA bundle path}"
python - <<'PY' | DOCKER_BUILDKIT=1 docker build --secret id=proxy_ca,src="$SSL_CERT_FILE" -f- -t chat-runtime:local-proxy-ca .
from pathlib import Path

source = Path("Dockerfile.chat").read_text(encoding="utf-8")
plain = "RUN uv sync --frozen --only-group chat-runtime --no-install-project"
secret = '''RUN --mount=type=secret,id=proxy_ca,required=false \\
    if [ -f /run/secrets/proxy_ca ]; then \\
        SSL_CERT_FILE=/run/secrets/proxy_ca uv sync --frozen --only-group chat-runtime --no-install-project; \\
    else \\
        uv sync --frozen --only-group chat-runtime --no-install-project; \\
    fi'''
if source.count(plain) != 1:
    raise SystemExit("Dockerfile.chat runtime install instruction changed")
print("# syntax=docker/dockerfile:1\n" + source.replace(plain, secret), end="")
PY
```

Esta variante sirve solo para builds locales; no la selecciones en Railway. El
intento remoto anterior falló antes de construir la imagen y no identificó la
causa.
El endpoint `/api/chat/health` sirve como healthcheck de arranque; Railway lo
usa para aceptar el deploy nuevo, pero no monitoriza salud después. No se usa
un monitor externo que despierte la app durante el periodo de inactividad.
Uvicorn conserva `proxy_headers=False`; la aplicación solo usa
`X-Forwarded-For` para el límite de intentos de login cuando el peer directo es
confiable. El launcher fija `CHAT_TRUSTED_PROXY=100.64.0.0/10`, basado en el
rango compartido RFC 6598. En el despliegue sano actual, cuatro solicitudes ya
registradas por Uvicorn (health, preflight, petición sin autenticar y origen
inválido) vieron un peer dentro de ese CIDR. Es evidencia de este despliegue,
no un contrato permanente de Railway. Aún no se verificó cómo forma o reemplaza
Railway la cadena `X-Forwarded-For` ni cuál dirección selecciona la aplicación
para limitar intentos de login.

La comprobación del peer ASGI (`request.client.host`) se hizo solo como un
resultado booleano para cuatro solicitudes ya registradas; las cuatro quedaron
dentro de `100.64.0.0/10`. No se guardaron IPs ni encabezados. Esto no demuestra
la selección del cliente reenviado. Para verificar esa selección, usa un
entorno o base de prueba y confirma que el `client` guardado por un único fallo
de login queda fuera del CIDR; muestra solo un booleano, nunca la IP ni el
encabezado completo. No consumas intentos fallidos en el login real para esta
prueba. Si se activa una CDN, repite ambas comprobaciones en aislamiento y no
amplíes los rangos confiables sin evidencia del peer.

`CHAT_TRUSTED_PROXY` acepta IPs sueltas o redes CIDR solo dentro de rangos
loopback, privados o compartidos; rechaza rangos públicos.

Variables base en el panel de Railway, nunca en Git. `CHAT_PROVIDER` y
`CHAT_ADMISSION_ENABLED` muestran los valores seguros del primer deploy; los de
producción están en [Activación del MVP](#activación-del-mvp):

```text
CHAT_AUTH_MODE=password
CHAT_PASSWORDS_JSON=[{"user_id":"owner","password_hash":"<hash-scrypt>"}]
CHAT_ALLOWED_ORIGINS=https://<origen-https-del-frontend>
CHAT_PROVIDER=mock
CHAT_ADMISSION_ENABLED=false
CHAT_RETENTION_DAYS=30
CHAT_STATE_PATH=/data/chat.sqlite3
```

El launcher también fija esos valores seguros por defecto para proveedor,
admisión, retención y ruta: sin variables explícitas, el servicio arranca en
`mock` con la admisión cerrada. Rechaza modo local, más de un usuario,
retención distinta de 30 días, ruta fuera del volumen, puerto inválido, un
volumen no escribible, un turno mayor de 180 segundos y una configuración
OpenAI incompleta (sin `CHAT_OPENAI_ENABLED=true`, `CHAT_MODEL` o precios) o
cuya reserva mínima no quepa en los topes diarios en dólares. Para preparar solo el hash de
contraseña en un entorno local confiable, ejecuta
`python -m src.conversational_analytics hash-password`; el comando lee la
contraseña sin eco y entrega el hash. Guarda el hash en el gestor de variables
de Railway. Nunca pongas la contraseña ni el hash en un archivo commiteado.

El primer deploy usó deliberadamente `mock` con la admisión cerrada para
comprobar login, historial y conectividad sin inferencia ni gasto. Encender
OpenAI fue un cambio explícito de variables autorizado por el dueño con modelo,
precios y topes (sección siguiente); cambiar el modelo, los precios o los topes
sigue requiriendo su autorización.

## Activación del MVP

El MVP se activó con estos pasos; la activación quedó comprobada el 8 de
octubre de 2026 (ver el [traspaso de activación](https://github.com/salvamalfa/aeromexico-tracker/blob/7ff22ed473d748808dde808d3dd2c63f9916b269/docs/chat/traspaso-activacion-mvp-20261006.md)).
Se conservan como referencia para reconstruir el servicio. Antes, el dueño
calificó los cortes en `review.html` y eligió modelo y topes; el agente que
administra Railway y la API key ejecutó los pasos.

1. **Variables de Railway** (panel del servicio, nunca en Git), además de las de
   arriba. Valores vigentes:

   ```text
   CHAT_PROVIDER=openai
   CHAT_OPENAI_ENABLED=true
   CHAT_MODEL=gpt-6.1-sol
   OPENAI_API_KEY=<clave del proyecto>
   CHAT_INPUT_COST_PER_MILLION=2
   CHAT_OUTPUT_COST_PER_MILLION=10
   CHAT_ADMISSION_ENABLED=true
   CHAT_DAILY_COST_BUDGET_USER_USD=5
   CHAT_DAILY_COST_BUDGET_GLOBAL_USD=5
   CHAT_MAX_TOOL_CALLS=16
   ```

   Los topes eran US$3 hasta el 8 de octubre, cuando el dueño pidió subirlos a
   US$5 y subir `CHAT_MAX_TOOL_CALLS` de 8 a 16. Tarifas normales por millón
   documentadas: Luna 0.10/0.50, Sol 6.1 2/10, Astra 10/50. La reserva mínima
   se cobra a la tarifa de salida: Sol 6.1 reserva US$1.50 por turno, que no
   cabe en el valor por defecto de US$1, así que el servicio no arranca sin
   topes explícitos mayores que esa reserva más el gasto diario esperado.
2. `CHAT_ALLOWED_ORIGINS` incluye `https://salvamalfa.github.io`.
3. Tras desplegar, `/api/chat/health` reporta `provider` `openai` y
   `admission_enabled` `true`. Si el arranque falla, el log indica qué variable
   falta; no hay llamada al proveedor antes de una pregunta.
4. **Panel en Pages:** `VITE_CHAT_ENABLED=true` en `web/.env.production` (la
   URL de la API ya está ahí), con commit de ese cambio: el gate rechaza
   entradas de compilación sin commit bajo `web/`. Las variables `VITE_CHAT_*`
   exportadas en la shell sobrescriben el archivo; compruébalo antes de
   publicar. La publicación usa `src.publish` con el registro ya aprobado y
   `src.publish.verify site/`, con `site/` como segundo commit del PR. El panel
   queda visible para todos; escribir requiere la contraseña.
5. Se probaron login, historial y preguntas reales desde Pages. La prueba desde
   el teléfono con la computadora apagada queda como comprobación opcional del
   dueño.

**Rollback inmediato:** `CHAT_ADMISSION_ENABLED=false` en Railway cierra la
admisión sin redeploy del sitio; el panel sigue visible y cada pregunta se
rechaza con `chat admission is disabled`.

### Control de gasto en dos capas

1. **Tope diario de la app (dólares).** `CHAT_DAILY_COST_BUDGET_USER_USD` y
   `CHAT_DAILY_COST_BUDGET_GLOBAL_USD` (US$5 en producción; US$1 si no se
   definen) se cambian en las variables de Railway, sin tocar código. Al agotarse, el panel muestra que el
   servicio rechazó la pregunta (`daily cost budget exhausted`) hasta las 00:00
   UTC (18:00 de Ciudad de México).
   El cupo de tokens (2,000,000 diarios) solo frena consumos desbocados.
2. **Respaldo en OpenAI Platform.** El dueño lo configura en la cuenta, no en el
   repo. La opción que corta con certeza es crédito prepagado **sin recarga
   automática**: al agotarse el saldo, la API rechaza las llamadas y el chat
   muestra un error del proveedor. Platform también ofrece presupuestos o
   alertas por proyecto; verifica en la configuración del proyecto si cortan
   las solicitudes o solo avisan. Esos límites son mensuales o por saldo, no
   diarios.

El incentivo de Data Sharing puede reducir la factura, pero ningún control
depende de él (ver `data-sharing.md`).

## Verificación después del deploy

Estado comprobado el 8 de octubre de 2026: el despliegue `7ccae673` terminó en
SUCCESS y `/api/chat/health` responde `200` por HTTPS con estado `ok`, worker
listo, autenticación `password`, proveedor `openai` y admisión habilitada. Una
petición de conversaciones sin autenticar recibe `401` y CORS permite el origen
de Pages; un origen no permitido recibió `403`. El dueño comprobó login e
historial desde Pages y obtuvo respuestas reales correctas. No se documentó
una prueba específica de persistencia del volumen tras reiniciar Railway.
Comprueba en logs solo estado del worker y errores de arranque; no copies
sesiones, hashes ni contenido privado a tickets. Railway debe construir desde
el Dockerfile de este repo; no selecciones Railpack ni el CLI local
loopback-only.

PR #83 eliminó `railway.json` y la dependencia de Config as Code para servicios
nuevos. Su primer intento de build falló con una validación genérica de
Dockerfile y sin información que permita identificar la causa. PR #84 corrigió
el Dockerfile y el runtime; después de integrarlo se quitó del servicio el pin
de fuente antiguo para que siguiera la rama `master`, y el despliegue saludable
posterior usó la fuente actual. No atribuyas el fallo anterior a una causa
específica: no hay evidencia de ella.

Referencias oficiales: [Config as Code](https://docs.railway.com/config-as-code)
(deprecado; no disponible para servicios nuevos), [Dockerfiles
personalizados](https://docs.railway.com/builds/dockerfiles#custom-dockerfile-path),
[healthchecks](https://docs.railway.com/deployments/healthchecks),
[deployment teardown](https://docs.railway.com/deployments/deployment-teardown),
[restart policy](https://docs.railway.com/deployments/restart-policy),
[Serverless](https://docs.railway.com/guides/cut-idle-costs-serverless) y
[volúmenes](https://docs.railway.com/volumes).


### Origen exacto de la preview local (revisión del 1 de noviembre de 2026)

El endpoint `/api/chat/health` respondió 200 sin Origin. La misma petición con
`Origin: http://127.0.0.1:5173` respondió 403 y `origin not allowed`. Por tanto,
la preview local queda fuera de la lista permitida del servicio; no demuestra
que falte una clave del proveedor ni que se necesite otra.

En la misma revisión, el origen publicado `https://salvamalfa.github.io`
recibió 200 en salud y en el preflight de conversaciones, con
`Access-Control-Allow-Origin` exacto. La lectura de conversaciones sin sesión
recibió 401 (`login required`). El worker estaba activo con contraseña,
R2/Sol low y admisión abierta. Esta comprobación no envió preguntas al modelo.

El código preparado admite exclusivamente `http://127.0.0.1:5173` y
`http://localhost:5173` como excepciones HTTP cuando están escritos de forma
explícita en `CHAT_ALLOWED_ORIGINS`. No se habilitan por defecto. Otros puertos,
hosts parecidos, rutas y comodines siguen rechazados. Se conserva la sesión
con contraseña y la lista HTTPS del dashboard publicado.

Para completar el despliegue normal:

1. Integrar la entrega revisada por el PR habitual y esperar el despliegue
   automático de Railway del commit integrado. No cargar el árbol local ni
   reutilizar una imagen anterior. Antes de integrar, la prueba de archivos
   Docker debe cargar el snapshot desde el contenido aislado de la imagen.
   Los exportadores se cargan cuando se solicitan para que el lector del chat
   no dependa de los generadores del pipeline.
2. Confirmar en GitHub el estado `success` de `soothing-possibility / production`
   para ese commit y comprobar que salud devuelve el `snapshot_version` esperado
   del sitio nuevo. El último despliegue observado antes de esta entrega era
   `7cd54fa4ebd646042c4987c4f139a0ae19c10ac0`, marcado exitoso por
   `railway-app[bot]` el 31 de octubre. Esto no acredita el despliegue de los
   cambios locales del 1 de noviembre.
3. Para permitir también la preview local, reconectar el plugin Railway. La
   consulta `list_projects` devolvió `UNAUTHORIZED` y exige reautenticación.
   No había CLI Railway ni autenticación local configurada. Este bloqueo impide
   leer o cambiar la lista remota; el origen publicado ya está permitido.
4. Leer el valor actual de `CHAT_ALLOWED_ORIGINS`, conservar todos sus orígenes
   y añadir `http://127.0.0.1:5173,http://localhost:5173`. Conservar también
   `https://salvamalfa.github.io`. No modificar contraseñas, autenticación,
   proveedor, modelo, cuotas ni otras variables. El backend anterior rechaza
   HTTP incluso si se añade al entorno, por lo que la variable sola no resuelve
   el problema.
5. Verificar preflight 200 desde los orígenes admitidos, 401 en conversaciones
   sin sesión y GET de salud 403 desde otro puerto o dominio. Un preflight
   rechazado devuelve 400. Confirmar después el login con la sesión habitual
   del dueño; no se hizo una consulta pagada para este cambio.

La compilación normal de Pages lee `web/.env.production`, con
`VITE_CHAT_ENABLED=true` y
`VITE_CHAT_API_URL=https://aeromexico-tracker-production.up.railway.app/api/chat`.
Las variables de la shell siguen teniendo precedencia. El índice de evidencia
del chat y su pin externo tienen aprobación propia: publicar noticias en el
dashboard no activa sus candidatos en el corpus del chat. El dueño aprobó las
23 noticias del lote `907971ca`; incorporar ese lote al corpus exige conservar
su recibo exacto y actualizar el pin mediante el proceso normal de publicación.

El campo de salud `evidence_index_sha256` mide los bytes del archivo; el pin
`CHAT_EVIDENCE_APPROVED_INDEX_SHA256` mide el JSON canónico. Son identidades
distintas: el índice anterior de diez registros tenía hash de bytes
`5fba922f7b6186a5ee0c31d9f678c3222a11fb50e9cf7d5b2f26b62212516672`
y pin canónico
`1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f`.
Compara cada valor con su referencia correspondiente después del despliegue.

Esta configuración está preparada y probada localmente. No se desplegó, no se
amplió la lista remota y no se crearon credenciales. Responsable del pendiente:
el coordinador de la entrega, tras reconectar Railway y cerrar la revisión.

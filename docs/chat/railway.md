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

## Configuración de una sola instancia

En **Variables** del servicio agrega:

```text
RAILWAY_DOCKERFILE_PATH=Dockerfile.chat
```

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
octubre de 2026 (ver el [traspaso de activación](traspaso-activacion-mvp-20261006.md)).
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

# Railway: backend piloto

Este perfil despliega solo el backend del chat. Railway usa `Dockerfile.chat`
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

## Configuración de una sola instancia

En **Variables** del servicio agrega:

```text
RAILWAY_DOCKERFILE_PATH=Dockerfile.chat
```

Railway usa `Dockerfile` automáticamente si está en la raíz, pero `Dockerfile.chat`
es un nombre personalizado y requiere esa variable, según su [documentación de
Dockerfiles](https://docs.railway.com/builds/dockerfiles#custom-dockerfile-path).

En **Settings** del servicio configura el perfil del piloto:

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

Se permiten hasta 8 llamadas de herramienta por turno. Agotar las llamadas o el
tiempo de ejecución deja el turno fallido; la consulta de uso no cambia ese
estado ni reintenta la respuesta. Si el uso no queda confirmado, su reserva se
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

Añade estas variables de entorno en el panel de Railway, nunca en Git:

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
admisión, retención y ruta. Rechaza modo local, OpenAI, admisión habilitada,
retención distinta de 30 días, ruta fuera del volumen, puerto inválido o un
volumen no escribible. Para preparar solo el hash de
contraseña en un entorno local confiable, ejecuta
`python -m src.conversational_analytics hash-password`; el comando lee la
contraseña sin eco y entrega el hash. Guarda el hash en el gestor de variables
de Railway. Nunca pongas la contraseña ni el hash en un archivo commiteado.

El modo `mock` y la admisión de turnos deshabilitada son deliberados para el
primer deploy: permiten comprobar login, historial y conectividad sin inferencia
ni gasto. Habilitar un proveedor pagado requiere completar los gates de modelo,
precios, consumo, presupuesto y credenciales en una etapa posterior.

## Verificación después del deploy

El despliegue actual responde `200` por HTTPS en `/api/chat/health` y al
preflight desde Pages. Una petición de conversaciones sin autenticar recibió
`401` con CORS para el origen permitido; un origen no permitido recibió `403`.
El servicio informa autenticación `password`, proveedor `mock` y admisión
apagada. Estas comprobaciones no hicieron login del dueño ni crearon una
conversación. La autenticación del dueño, persistencia del volumen tras
reiniciar Railway y acceso desde teléfono con la computadora apagada siguen
pendientes. El smoke de la imagen local con el runtime de PR #84, anterior a la
última corrección del adaptador OpenAI, usó contraseña sintética y verificó
login, historial, permisos y persistencia tras reiniciar el contenedor local,
sin red ni llamadas al proveedor; no sustituye las pruebas remotas. Comprueba
en logs solo estado del worker y errores de arranque; no copies sesiones,
hashes ni contenido privado a tickets. Railway debe construir desde el
Dockerfile de este repo; no selecciones Railpack ni el CLI local loopback-only.

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

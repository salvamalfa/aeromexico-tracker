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
| Deployment draining | `100` segundos |
| Restart policy | `On Failure` |
| Restart retries | `3` |

Adjunta un volumen persistente de **500 MB** montado en `/data`. La base SQLite
queda en `/data/chat.sqlite3`; el launcher restringe
los permisos del volumen a `0700` y valida que sea escribible antes de iniciar.
El contenedor necesita privilegios para ajustar permisos del volumen Railway.
No escales a múltiples réplicas: SQLite y la cola en memoria pertenecen a una instancia.
El build aislado instala el lock congelado solo para `chat-runtime`; CI valida
el lock completo con `uv sync --locked`. En entornos locales detrás de un proxy
TLS, se puede suministrar una CA pública al paso de build como secreto BuildKit
opcional (`--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt`). Se
monta solo durante `uv sync`; no se copia a la imagen y TLS permanece validado.
El endpoint `/api/chat/health` sirve como healthcheck de arranque; Railway lo
usa para aceptar el deploy nuevo, pero no monitoriza salud después. No se usa
un monitor externo que despierte la app durante el periodo de inactividad.
Uvicorn conserva `proxy_headers=False`; solo el límite de intentos de login
resuelve la IP del cliente. El edge de Railway es la única entrada al contenedor
y llega desde el espacio compartido `100.64.0.0/10` (RFC 6598); Railway reemplaza
el `X-Forwarded-For` que envía el cliente. Sin confiar en ese edge, todos los
clientes comparten su dirección y cinco contraseñas erróneas de cualquier
persona bloquearían el login del dueño durante 15 minutos. Por eso el launcher
fija `CHAT_TRUSTED_PROXY=100.64.0.0/10` por defecto: la API recorre
`X-Forwarded-For` desde la derecha, omite saltos dentro de esa red y usa la
primera dirección restante. `CHAT_TRUSTED_PROXY` acepta IPs sueltas o redes
CIDR solo dentro de rangos loopback, privados o compartidos; rechaza rangos
públicos. Si se activa la CDN de Railway, verifica en los logs que el límite
siga viendo IPs de clientes y no de la CDN.

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

Confirma que el deploy responde `200` en `/api/chat/health`, que el login desde
el origen HTTPS configurado funciona, y que conversaciones siguen disponibles
después de reiniciar una vez la instancia. Comprueba en los logs solo el estado
del worker y los errores de arranque; no copies sesiones, hashes ni contenido
privado a tickets. Railway debe construir desde el Dockerfile de este repo; no
selecciones Railpack ni un comando que invoque el CLI local loopback-only.

Referencias oficiales: [Config as Code](https://docs.railway.com/config-as-code)
(deprecado; no disponible para servicios nuevos), [Dockerfiles
personalizados](https://docs.railway.com/builds/dockerfiles#custom-dockerfile-path),
[healthchecks](https://docs.railway.com/deployments/healthchecks),
[deployment teardown](https://docs.railway.com/deployments/deployment-teardown),
[restart policy](https://docs.railway.com/deployments/restart-policy),
[Serverless](https://docs.railway.com/guides/cut-idle-costs-serverless) y
[volúmenes](https://docs.railway.com/volumes).

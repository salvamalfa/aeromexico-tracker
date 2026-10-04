# Backend del chat en un VPS de Hostinger

El plan actual **Hosting Web Empresarial** puede seguir alojando el otro sitio.
Este backend es Python/FastAPI y necesita un **VPS Linux separado con root**:
Hostinger documenta Python solo en VPS; la compatibilidad de algunas apps
Node.js con Web Empresarial/Cloud no aplica a este servicio. No migres el sitio
actual al VPS ni cambies sus registros raíz `@`/`www`. La guía no contrata,
configura DNS ni despliega nada.

## Requisitos concretos

- Ubuntu 24.04 LTS con SSH/root, una IP pública y puertos 80/443 disponibles.
- Python 3.13 (`>=3.13,<3.14`), instalado por `uv`, y dependencias del extra
  `chat` instaladas desde `uv.lock`.
- Una sola instancia del CLI del proyecto. Este arranca Uvicorn y su worker en
  el mismo proceso; no iniciar varios workers/procesos.
- El checkout fijado incluye el snapshot público completo `site/`. El proceso
  lee el código y snapshot desde una release de solo lectura; SQLite queda en
  un directorio persistente independiente, escribible solo por `airline-chat`.
- El repo no tiene un mínimo de CPU/RAM medido. Empieza con un VPS Linux
  compatible y observa recursos antes de dimensionar para más usuarios.

## Preparar una release

Los comandos son para quien administre el VPS. Usa un hostname propio como
`api.ejemplo.com`; si vive bajo el dominio del sitio existente, añade solo un
registro para ese subdominio y conserva `@` y `www`.

Instala paquetes, crea un usuario de servicio sin login y separa los
directorios: releases propiedad de root, datos/SQLite propiedad del servicio.

```bash
sudo apt update
sudo apt install -y git curl nginx certbot python3-certbot-nginx
sudo useradd --system --create-home \
  --home-dir /var/lib/airline-tracker-chat \
  --shell /usr/sbin/nologin airline-chat
sudo install -d -o airline-chat -g airline-chat -m 0700 \
  /var/lib/airline-tracker-chat
sudo install -d -o root -g root -m 0755 /opt/airline-tracker/releases
```

Clona el repo público en una release candidata, fija el SHA completo que ya
esté aprobado e integrado y haz el árbol de solo lectura. No despliegues la
punta de una rama mutable. Cambia el marcador por ese SHA real:

```bash
sudo git clone https://github.com/salvamalfa/aeromexico-tracker.git \
  /opt/airline-tracker/releases/candidate
sudo git -C /opt/airline-tracker/releases/candidate \
  checkout --detach SHA_COMPLETO_APROBADO_POST_MERGE
sudo chown -R root:root /opt/airline-tracker/releases/candidate
sudo chmod -R a-w /opt/airline-tracker/releases/candidate
sudo ln -s /opt/airline-tracker/releases/candidate /opt/airline-tracker/current
```

El servicio solo necesita leer `site/`; nunca copies el warehouse privado ni
reconstruyas los datos en el VPS. Instala `uv`, Python 3.13 y el entorno fuera
del checkout, bajo la cuenta del servicio:

```bash
sudo -u airline-chat -H sh -lc '
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  uv python install 3.13
  cd /opt/airline-tracker/current
  UV_PROJECT_ENVIRONMENT=/var/lib/airline-tracker-chat/venv \
    uv sync --locked --no-dev --extra chat
'
```

`site/` y el código quedan `root:root`, legibles por el servicio pero no
escribibles. El entorno virtual y los archivos de datos quedan en
`/var/lib/airline-tracker-chat`, cuyo propietario es `airline-chat`.

## Configurar autenticación, estado y retención

Genera el hash en una máquina confiable; el comando muestra una contraseña una
sola vez, para guardarla en un gestor de contraseñas:

```bash
uv run --all-extras python -m src.conversational_analytics hash-password --generate
```

Como root, crea `/etc/airline-tracker-chat.env` con modo `0600`. Sustituye el
marcador por el hash scrypt real; no guardes la contraseña ni el hash en el
repo. El origen permitido es el **origin** de Pages, sin ruta del repo ni slash
final. El valor de retención debe decidirse antes de abrir el servicio; `30`
es el default actual y borra conversaciones expiradas cada hora, por lo que no
es una decisión implícita segura.

```ini
CHAT_PROVIDER=mock
CHAT_AUTH_MODE=password
CHAT_PASSWORDS_JSON='[{"user_id":"owner","password_hash":"<HASH_SCRYPT>"}]'
CHAT_ALLOWED_ORIGINS=https://salvamalfa.github.io
CHAT_TRUSTED_PROXY=127.0.0.1
CHAT_STATE_PATH=/var/lib/airline-tracker-chat/chat.sqlite3
CHAT_SNAPSHOT_ROOT=/opt/airline-tracker/current/site
CHAT_RETENTION_DAYS=<RETENCION_ACORDADA_EN_DIAS>
CHAT_ADMISSION_ENABLED=true
```

Para configurar la retención, reemplaza el marcador con días enteros acordados
(por ejemplo `30` solo si esa política fue elegida). SQLite, su journal/WAL y
el lock del worker permanecen juntos en `/var/lib/airline-tracker-chat/`. Esa
carpeta es privada para el usuario del servicio. Haz backup consistente con el
servicio detenido o mediante una herramienta SQLite; conserva/restaura la base
y sidecars como un conjunto. Prueba la restauración antes del piloto.

## Servicio systemd

Crea `/etc/systemd/system/airline-tracker-chat.service`:

```ini
[Unit]
Description=Airline Tracker chat API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=airline-chat
Group=airline-chat
WorkingDirectory=/opt/airline-tracker/current
EnvironmentFile=/etc/airline-tracker-chat.env
ExecStart=/var/lib/airline-tracker-chat/venv/bin/python -m src.conversational_analytics --host 127.0.0.1 --port 8765 --log-level info
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadOnlyPaths=/opt/airline-tracker/current
ReadWritePaths=/var/lib/airline-tracker-chat

[Install]
WantedBy=multi-user.target
```

`ExecStart` usa Python del entorno virtual; no necesita `uv` al arrancar. Activa
el servicio y verifica la salud local. El puerto 8765 debe quedar solo en
loopback, nunca abierto en firewall:

```bash
sudo chown root:root /etc/airline-tracker-chat.env
sudo chmod 0600 /etc/airline-tracker-chat.env
sudo systemctl daemon-reload
sudo systemctl enable --now airline-tracker-chat
sudo systemctl status airline-tracker-chat
sudo journalctl -u airline-tracker-chat -n 50 --no-pager
curl -fsS http://127.0.0.1:8765/api/chat/health
```

El health esperado debe indicar `status: ok`, snapshot disponible y worker
activo. Para cambiar entorno, hacer `systemctl restart airline-tracker-chat`;
si cambia el unit file, primero `systemctl daemon-reload`. Para desplegar otra
release, prepara/valida el SHA, cambia el symlink `current` y reinicia. El
rollback vuelve a apuntar el symlink a la release anterior y reinicia; no
restaures una base SQLite antigua sobre un esquema nuevo.

## Subdominio, Nginx y HTTPS

Cuando se autorice el DNS, crea únicamente un registro `A` para el subdominio
API apuntando a la IP del VPS; no cambies `@` o `www`. Abre SSH, HTTP y HTTPS en
el firewall de Hostinger y en UFW. Instala esta configuración en
`/etc/nginx/sites-available/airline-tracker-chat`, sustituyendo hostname:

```nginx
server {
    listen 80;
    server_name api.ejemplo.com;
    client_max_body_size 128k;

    location /api/chat/ {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Forwarded "";
        proxy_request_buffering on;
        proxy_buffering off;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
    }
}
```

Nginx fija la IP reenviada al socket remoto directo, sin conservar una cadena
`X-Forwarded-For` que pudiera aportar el cliente. Uvicorn escucha solo en
loopback y `CHAT_TRUSTED_PROXY=127.0.0.1`. `proxy_buffering off` permite que
SSE fluya; el buffering de request queda activado para preservar el
`Content-Length`, que la API exige en POST. La app maneja CORS; no agregues
cabeceras CORS manuales en Nginx.

```bash
sudo ln -s /etc/nginx/sites-available/airline-tracker-chat \
  /etc/nginx/sites-enabled/airline-tracker-chat
sudo nginx -t
sudo systemctl reload nginx
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
```

Apunta DNS y espera propagación antes de pedir certificado. Certbot puede
instalar HTTPS y redirección HTTP→HTTPS:

```bash
sudo certbot --nginx --redirect -d api.ejemplo.com
sudo certbot renew --dry-run
sudo systemctl status certbot.timer
```

Confirma desde Internet que `https://api.ejemplo.com/api/chat/health` responde
200. Comprueba también la preflight desde una terminal; la respuesta debe
contener `Access-Control-Allow-Origin: https://salvamalfa.github.io`, permitir
`POST` y los headers solicitados. La app permite
`GET, POST, DELETE, OPTIONS`, los headers `Authorization`, `Content-Type` y
`Last-Event-ID`, y expone `Content-Type` y `Retry-After`:

```bash
curl -i -X OPTIONS 'https://api.ejemplo.com/api/chat/login' \
  -H 'Origin: https://salvamalfa.github.io' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Desde el sitio
Pages actual, antes de habilitar el widget, puedes probar en DevTools el health,
login y una sesión desechable: el siguiente snippet pide la contraseña en un
prompt, no imprime el token y elimina la conversación de prueba al terminar.
Sustituye el hostname:

```js
(async () => {
  const api = "https://api.ejemplo.com/api/chat";
  const health = await fetch(`${api}/health`);
  if (!health.ok) return console.log({ health: health.status });
  const login = await fetch(`${api}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: prompt("Contraseña del chat") }),
  });
  if (!login.ok) return console.log({ health: health.status, login: login.status });
  const { session } = await login.json();
  const headers = { Authorization: `Bearer ${session}`, "Content-Type": "application/json" };
  const created = await fetch(`${api}/conversations`, {
    method: "POST", headers, body: "{}",
  });
  const conversation = created.ok ? await created.json() : null;
  const deleted = conversation
    ? await fetch(`${api}/conversations/${encodeURIComponent(conversation.id)}`, {
        method: "DELETE", headers,
      })
    : null;
  const logout = await fetch(`${api}/logout`, {
    method: "POST", headers, body: "{}",
  });
  console.log({ health: health.status, login: login.status, create: created.status,
    delete: deleted?.status, logout: logout.status });
})();
```

La prueba debe ejecutarse en una pestaña de la Pages publicada, no en una
página local con otro origin. Espera health 200, login 200, creación 201,
borrado 204 y logout 204. Si falla, mantén el flag del chat apagado. `CHAT_ALLOWED_ORIGINS`
permite exactamente el origin Pages (sin path); CORS no sustituye el login.

Antes de habilitar el panel público también deben cumplirse la revisión
semántica del dueño (H1), la selección de modelo con los gates de calidad (H4)
y la retención y prueba del piloto desde teléfono con la computadora apagada
(H5). La prueba técnica anterior no concede ninguna de esas aprobaciones.
Mantén `VITE_CHAT_ENABLED=false` mientras quede un gate pendiente.

Una vez cumplidos esos requisitos se habilita el frontend en el build aprobado
con `VITE_CHAT_ENABLED=true` y `VITE_CHAT_API_URL=https://api.ejemplo.com/api/chat`.
El gate de publicación compila `web/` y vuelve a generar `site/`; usa el
expediente aprobado requerido por el proceso:

```bash
VITE_CHAT_ENABLED=true \
VITE_CHAT_API_URL=https://api.ejemplo.com/api/chat \
  uv run python -m src.publish \
    --record analysis_runs/drafts/EXPEDIENTE_APROBADO.json --out site/
uv run python -m src.publish.verify site/
```

El flag y URL son públicos; nunca incluyas secretos en variables Vite. Esta
receta explica la secuencia, pero no ejecuta gate ni publica Pages.

## Costos

El VPS es independiente del plan Hosting Web Empresarial que conserva el sitio.
Con `CHAT_PROVIDER=mock`, el chat no hace llamadas pagadas a OpenAI. Para
habilitar OpenAI luego, el proveedor factura aparte según modelo y uso; la key
permanece solo en el entorno privado del servidor. Los presupuestos del backend
son estimaciones operativas, no un techo garantizado de factura.

## Referencias oficiales

- Hostinger: [lenguajes y frameworks compatibles](https://www.hostinger.com/support/which-programming-languages-and-frameworks-are-supported-at-hostinger/) (Python requiere root y se admite solo en VPS).
- Hostinger: [apps Node.js en Web Empresarial/Cloud](https://www.hostinger.com/support/how-to-deploy-a-nodejs-website-in-hostinger/) (Node.js, no Python).
- Hostinger: [VPS autoadministrado](https://www.hostinger.com/support/8852150-what-is-a-self-managed-vps-at-hostinger/) y [Flask con Gunicorn/Nginx en Ubuntu 24.04](https://www.hostinger.com/support/10725412-how-to-install-flask-on-ubuntu-24-04/) (referencia Python persistente; este proyecto usa Uvicorn).
- Hostinger: [apuntar un dominio a un VPS](https://www.hostinger.com/support/1583227-how-to-point-a-domain-to-your-vps-at-hostinger/) y [SSL en VPS](https://www.hostinger.com/support/6360129-how-to-install-ssl-on-vps-at-hostinger/).
- Proyecto: [operación del chat](operations.md) y [CLI/API](../../src/conversational_analytics/README.md).

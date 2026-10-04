# Railway: backend piloto

Este perfil despliega solo el backend del chat. Railway usa `Dockerfile.chat`
mediante `railway.json`; la imagen instala el grupo bloqueado `chat-runtime`,
verifica el snapshot público que el repositorio ya publica y arranca Uvicorn en
`0.0.0.0:$PORT`. No ejecuta el pipeline de datos ni incluye warehouse, bronce,
plata, `analysis_runs`, credenciales o pruebas. El frontend sigue en Pages y
debe usar la URL HTTPS de este servicio.

## Configuración de una sola instancia

En Railway configura una instancia y un volumen persistente montado en
`/data`. La base SQLite queda en `/data/chat.sqlite3`; el launcher restringe
los permisos del volumen a `0700` y valida que sea escribible antes de iniciar.
El contenedor necesita privilegios para ajustar permisos del volumen Railway.
No escales a múltiples réplicas: SQLite y la cola en memoria pertenecen a una instancia.
El build aislado instala el lock congelado solo para `chat-runtime`; CI valida
el lock completo con `uv sync --locked`. En entornos locales detrás de un proxy
TLS, se puede suministrar una CA pública al paso de build como secreto BuildKit
opcional (`--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt`). Se
monta solo durante `uv sync`; no se copia a la imagen y TLS permanece validado.
El endpoint `/api/chat/health` sirve como healthcheck de arranque; no se usa un
monitor externo que despierte la app durante el periodo de inactividad.
Uvicorn ignora cabeceras reenviadas para resolver IPs porque la lista exacta de
proxies confiables no está configurada. Detrás del proxy de Railway, el límite
de intentos de login puede agrupar conexiones bajo la IP del proxy; no configures
`CHAT_TRUSTED_PROXY` con rangos amplios para evitarlo.

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

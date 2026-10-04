# Operación del chat

## Instalación local

La instalación bloqueada que se documenta para el chat es:

```bash
uv sync --all-extras --all-groups --locked
uv run --all-extras python -m src.conversational_analytics --help
```

`CHAT_PROVIDER` queda en `mock` de forma predeterminada. El servicio puede
arrancarse y comprobarse localmente sin API key. Las claves `CHAT_*` y sus
valores permitidos están descritos en [`config/chat/runtime.example.env`](../../config/chat/runtime.example.env);
el ejemplo contiene nombres solamente. Inicia el backend local:

```bash
uv run --all-extras python -m src.conversational_analytics --host 127.0.0.1 --port 8765
```

Desde `web/`, inicia la interfaz:

```bash
VITE_CHAT_ENABLED=true VITE_CHAT_API_URL=http://127.0.0.1:8765/api/chat npm run dev
```

La interfaz GitHub Pages es estática, así que su petición a un backend de otro
origen necesita proxy HTTPS, CORS limitado al origen publicado y una prueba de
autenticación del navegador. CORS no autentica usuarios.

En local, usar `CHAT_AUTH_MODE=local` solamente con una instancia no expuesta a
la red. El modo `bearer` debe resolver un token a un usuario; el servidor guarda
hashes SHA-256 de tokens, no los tokens en claro. No incluir secretos en Vite,
logs, commits, fixtures o reportes.

## Diseño viable para un piloto de una instancia

Una instalación de piloto viable usa un servidor Linux persistente que el dueño
controle, con un volumen local durable. No requiere elegir ni contratar ahora
un proveedor. Ejecutar un proceso FastAPI y su worker mediante una unidad
`systemd`; fijar el checkout/release y entorno Python, reiniciar al fallar y
esperar cierre ordenado. El worker debe vivir más que la conexión SSE del
navegador y reanudar o marcar como fallidos los turnos tras reinicio. SQLite y
sus archivos WAL residen juntos bajo `/var/lib/airline-tracker-chat/`; respaldar
según política acordada y comprobar permisos de lectura exclusivos del usuario
del servicio.

Poner un proxy TLS delante del servidor ASGI con certificados renovables,
HSTS, límite de cuerpo, timeouts compatibles con SSE y forwarding de IP solo
desde el proxy confiable. Publicar solamente la API, no el puerto de SQLite.
El frontend usa `VITE_CHAT_API_URL` inyectada al compilar. Antes
de habilitarlo desde Pages, probar preflight CORS y una sesión real desde el
origen exacto, además de rechazos para origen/token no autorizados. Si no se
puede autenticar a los usuarios del dashboard, mantener desactivado el panel
público.

### Identidad, cuotas, retención y proveedor

- Dar un bearer distinto por persona o piloto y mapearlo a un `user_id` estable.
  Rotar o revocar el token reemplazando su hash configurado. No usar una key
  compartida en frontend.
- Conservar los límites configurables por usuario y globales de tokens/costo,
  concurrencia, tamaño, llamadas de herramienta y tiempo del turno. Rechazar un
  segundo turno activo de la misma conversación con un estado visible.
- Definir retención de conversaciones antes del piloto. El valor de ejemplo es
  30 días, no una decisión de política. El borrado debe eliminar el historial
  local, la sesión administrada y sus referencias del proveedor según las
  capacidades y los términos vigentes; documentar cualquier estado que el
  proveedor no permita borrar.
- Registrar el `provider_session_id`, el uso reportado por cada llamada, costo
  estimado, latencia, errores y caché si el proveedor lo informa. El consumo
  reportado puede llegar tarde o estar incompleto y no garantiza un techo de
  factura. El backend debe admitir límites propios y pausar turnos si exceden
  el presupuesto operativo.
- No asumir que `environment.type="none"` elimina almacenamiento del proveedor
  o equivale a Zero Data Retention. Confirmar condiciones de retención,
  residencia, borrado y acceso vigentes antes de habilitar datos de usuarios.

### Health, despliegue y rollback

`GET /api/chat/health` debe mostrar solamente disponibilidad, versión de la aplicación,
estado de snapshot y capacidad del worker; nunca nombres de secretos ni su
presencia por variable individual. Alertar si snapshot o worker no están listos,
si hay turnos fallidos, si la cola crece, si se exceden cuotas o si queda poco
espacio en disco. Una instancia puede tener un solo worker y rechazar exceso de
concurrencia; no requiere escalado a cero.

Mantener cada versión de aplicación como release separada y configuración fuera
del checkout. El rollback consiste en apuntar `systemd` a la versión estable
anterior, recargar y reiniciar, y apagar el flag Vite del chat si falla la API.
No revertir SQLite copiando una base vieja sobre una nueva: hacer copia con la
aplicación detenida o mediante mecanismo consistente, conservar esquema y
comprobar migraciones antes del despliegue. Probar restauración y borrado antes
de abrir el piloto.

Esta es una receta de destino revisable, no una infraestructura creada o
validada. H5 seguirá pendiente hasta decidir quién administra el host, quiénes
son usuarios, retención y acceso autorizado a la API.

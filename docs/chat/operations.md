# Operación del chat

## Instalación local

Para ejecutar solo el backend, sin instalar el pipeline ni herramientas de
desarrollo, usa `uv sync --locked --only-group chat-runtime`. En ese entorno,
ejecuta el CLI con `.venv/bin/python -m src.conversational_analytics` (Windows:
`.venv\Scripts\python.exe`). Para desarrollar y correr pytest, conserva la
instalación completa de abajo. No alternes perfiles sobre un entorno que otra
corrida esté usando; asigna `UV_PROJECT_ENVIRONMENT` a un directorio separado.

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
la red. El servidor rechaza en modo local cualquier petición con cabeceras de
proxy (`Forwarded`, `X-Forwarded-*`, `X-Real-IP`), y no arranca con
`CHAT_PROVIDER=openai` en modo local salvo `CHAT_ALLOW_LOCAL_OPENAI=true` en la
máquina del dueño. No incluir secretos en Vite, logs, commits, fixtures o
reportes.

### Contraseña

El piloto usa `CHAT_AUTH_MODE=password` con **una sola contraseña**, del dueño
(`user_id` `owner`), hasta que se decida dar acceso a más personas:

1. Generar la contraseña y su hash, en la máquina del dueño:
   `uv run --all-extras python -m src.conversational_analytics hash-password --generate`.
   Imprime una vez `password:` y `password_hash:`. Guardar la contraseña en un
   gestor de contraseñas. Sin `--generate`, el comando pide una contraseña
   propia (mínimo 12 caracteres) sin eco e imprime solo el hash.
2. En el entorno del servidor, fuera del repositorio:
   `CHAT_PASSWORDS_JSON=[{"user_id":"owner","password_hash":"scrypt$15$8$1$…"}]`,
   `CHAT_ALLOWED_ORIGINS=https://salvamalfa.github.io` y, si hay proxy TLS en el
   mismo host, `CHAT_TRUSTED_PROXY=127.0.0.1`.
3. Rotar: generar otro hash, reemplazarlo y reiniciar. Las sesiones emitidas
   con el hash anterior dejan de valer.

Nunca escribir la contraseña ni su hash en Git, en el PR, en comentarios, logs
o fixtures. El panel pide la contraseña al abrirse; la sesión (12 h) vive solo
en memoria del navegador, así que recargar la página la vuelve a pedir. Tras 5
intentos fallidos desde un mismo cliente en 15 minutos el login responde 429. Por
encima de 50 fallos globales por hora el servidor registra un error para
alertar, pero no bloquea a nadie: un bloqueo global permitiría a cualquiera
dejar fuera al dueño.

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

En el launcher Railway, Uvicorn detiene los nuevos claims antes de esperar las
conexiones SSE y les da hasta 5 segundos para cerrar. El perfil permite hasta 8
llamadas de herramienta y 180 segundos de ejecución del turno. Una respuesta
terminal sin uso confirmado puede tener hasta 30 segundos adicionales para una
consulta GET del uso del mismo turno; no se envían entradas nuevas. El worker
reserva otros 10 segundos para estado local, SQLite y limpieza. Al máximo, su
espera es de 220 segundos; Railway debe permitir 230 segundos en total: 5 de
conexiones + 220 del worker + 5 de margen. Si `CHAT_MAX_TURN_SECONDS` se reduce,
el launcher calcula el drenaje con ese valor; rechaza un valor superior a 180.

Al agotar el límite de ejecución, el turno queda fallido aunque la cancelación
remota se intente y luego se confirme uso. La conciliación GET puede completar
la contabilidad de un turno terminal, pero no reabre ni repite su respuesta. Si
el uso no se confirma, permanece desconocido con la reserva retenida. La gracia
de cierre no demuestra la calidad de una respuesta del modelo.

Poner un proxy TLS delante del servidor ASGI con certificados renovables,
HSTS, límite de cuerpo, timeouts compatibles con SSE y forwarding de IP solo
desde el proxy confiable. Publicar solamente la API, no el puerto de SQLite.
El frontend usa `VITE_CHAT_API_URL` inyectada al compilar. Antes
de habilitarlo desde Pages, probar preflight CORS y una sesión real desde el
origen exacto, además de rechazos para origen/token no autorizados. Si no se
puede autenticar a los usuarios del dashboard, mantener desactivado el panel
público.

### Consumo de evaluaciones y otros procesos

El control principal de gasto es un **tope diario en dólares**: US$1 por
usuario y US$1 global por defecto (`CHAT_DAILY_COST_BUDGET_USER_USD`,
`CHAT_DAILY_COST_BUDGET_GLOBAL_USD`), configurable en Railway sin cambiar
código. El cupo de tokens queda en 2,000,000 diarios por usuario y global solo
como freno ante un consumo desbocado. Antes de cada turno OpenAI se reservan al
menos 150,000 tokens, o la estimación dinámica si es mayor. La reserva monetaria
cobra todos esos tokens a la tarifa de salida, porque Agents API no admite un
límite de tokens de salida: con Luna (US$0.10/US$0.50 por millón) reserva
US$0.075; con Sol 6.1 (US$2/US$10), US$1.50, que no cabe en US$1. Con el consumo
medido (~US$0.004 por pregunta de Luna), US$1 al día alcanza para unas 215
preguntas.

La demo `mock` reserva tokens pero no dólares y registra su uso a US$0: no
hace llamadas pagadas ni consume el tope. Estos controles no
sustituyen la factura ni verifican créditos de Data Sharing; el incentivo es un
posible ahorro, no el control de gasto. El servicio rechaza al arrancar una
configuración OpenAI cuya reserva mínima no quepa en el presupuesto monetario
por usuario o global. Configura las tarifas normales del modelo elegido; los
límites monetarios no se ajustan solos. Como respaldo fuera de la app, usa los
límites de OpenAI Platform (ver `railway.md`, «Control de gasto en dos capas»).

Para incluir evaluaciones u otro proceso del proyecto, prepara un JSON privado
con contadores confirmados y un identificador contable estable por intento o
agregado **sin solapamiento**. No incluyas prompts, respuestas, contexto ni IDs
del proveedor. Nunca importes nuevamente un turno que ya contabiliza esta base.
Ejemplo de formato con valores ilustrativos:

```json
{
  "version": 1,
  "entries": [
    {"accounting_id": "eval-0001", "owner_id": "owner",
     "usage_date": "2026-10-04", "status": "known",
     "input_tokens": 40000, "output_tokens": 500,
     "estimated_cost_usd": 0.00425},
    {"accounting_id": "eval-0002", "owner_id": "owner",
     "usage_date": "2026-10-04", "status": "unknown",
     "reserved_tokens": 150000, "reserved_cost_usd": 1.5}
  ]
}
```

Usa fechas UTC de la evidencia contable. Primero valida el archivo sin abrir ni
modificar SQLite; este paso muestra la propuesta, sin comprobar conflictos con
registros que ya existan. Después aplica a la **misma base** usada por el chat:

```bash
python -m src.conversational_analytics import-usage \
  --file /ruta/privada/consumo.json --state-path /ruta/privada/chat.sqlite3
python -m src.conversational_analytics import-usage \
  --file /ruta/privada/consumo.json --state-path /ruta/privada/chat.sqlite3 --apply
```

La aplicación valida conflictos y escribe el lote en una transacción.
La validación incluye los totales existentes y resultantes por día, sumados
entre propietarios, y las reservas de todos los días: rechaza desbordamientos
de enteros o costos antes de confirmar un lote.
Repetir un registro idéntico no suma consumo otra vez; un registro conocido no admite
reescritura ni vuelve a desconocido. Para conciliar un registro `unknown`, usa
su mismo ID, propietario y fecha con `status: known`, contadores y costo
confirmados. Un lote inválido no aplica parcialmente. Los registros conocidos
suman a las cuotas de su fecha UTC; un desconocido bloquea globalmente la
admisión, aun si su fecha es anterior, y permanece hasta su conciliación.
También pausa el inicio de turnos que ya estuvieran en cola; no reenvía ni
reconstruye turnos que el proveedor ya haya recibido. Por eso `--apply` rechaza
un lote que agregue filas `unknown` nuevas a la base salvo que se pase
`--allow-admission-block`; volver a listar una fila `unknown` ya guardada o
conciliarla como `known` no lo requiere. El resumen del dry-run indica
`unknown_blocks_admission`.

**S14 queda fuera de la base del chat.** El turno de evaluación de Sol con uso
desconocido (S14) pertenece al expediente de la comparación y a su presupuesto
de US$10, no a las cuotas diarias del chat. No lo importes como `unknown` a la
base de Railway: pausaría todas las admisiones. Si se concilia con Usage,
puede registrarse como `known` con su fecha UTC original.

El importador no recupera Usage de OpenAI ni detecta cargas externas. Mantén
`CHAT_ADMISSION_ENABLED=false` mientras un proceso separado esté activo y
actualiza su registro antes de reabrir el chat. El dueño indicó que por ahora
la organización solo usa este proyecto; si eso cambia, incorpora también el
consumo de los nuevos proyectos. Conserva el expediente acumulado de la
comparación y sus archivos originales; importar contadores no reanuda el
experimento ni autoriza nuevas llamadas.

### Identidad, cuotas, retención y proveedor

- Una contraseña por persona si se abre a más usuarios, cada una mapeada a un
  `user_id` estable en `CHAT_PASSWORDS_JSON`; las cuotas por usuario aplican a
  ese `user_id`. Rotar o revocar reemplazando o quitando su hash. No usar una
  key compartida en frontend.
- Conservar los límites configurables por usuario y globales de tokens/costo,
  concurrencia, tamaño, llamadas de herramienta y tiempo del turno. Rechazar un
  segundo turno activo de la misma conversación con un estado visible.
- El dueño acordó el 4 de octubre de 2026 una retención de **30 días** para las
  conversaciones del backend. El borrado debe eliminar el historial
  local, la sesión administrada y sus referencias del proveedor según las
  capacidades y los términos vigentes; documentar cualquier estado que el
  proveedor no permita borrar.
- Las reservas cuyo uso aún se desconoce se mantienen en el control de cuotas
  aunque cruce la medianoche UTC. Al borrar una conversación manualmente o por
  retención, el almacenamiento transfiere cualquier reserva terminal sin
  conciliación a un registro contable mínimo e independiente del historial.
  Guarda propietario, fecha de reserva, cantidad reservada y estado; cuando
  llega una notificación de uso confirmado, registra tokens y costo una sola
  vez y libera la reserva, incluso si ya se borró el turno. Antes de borrar el
  contenido o solicitar el borrado remoto, reconcilia el turno del proveedor
  cuando sea posible. No hay una consulta automática posterior que resuelva
  tombstones; sin evidencia confirmada, la reserva permanece retenida y no se
  reinicia por UTC ni por retención. No conserva prompts, respuestas, contexto,
  eventos ni identificadores del proveedor en ese registro. Las reservas de
  turnos activos siguen asociadas a sus turnos mientras estos sigan activos.
- El borrado por retención conserva ese registro mínimo antes de eliminar el
  historial local. Si falla la eliminación remota, su solicitud se agrega a
  una cola durable separada y se reintenta; una falla temporal no revierte el
  borrado local ni elimina la reserva contable pendiente.
- Registrar el `provider_session_id`, el uso reportado por cada llamada, costo
  estimado, latencia, errores y caché si el proveedor lo informa. El consumo
  reportado puede llegar tarde o estar incompleto y no garantiza un techo de
  factura. El backend debe admitir límites propios y pausar turnos si exceden
  el presupuesto operativo. El día UTC en que se confirma el uso es una fecha
  contable estimada; no necesariamente coincide con la fecha de solicitud o
  facturación del proveedor.
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
validada. H5 seguirá pendiente hasta disponer de un host administrado, acordar la
retención y superar las pruebas HTTPS desde Pages. El acceso inicial será
únicamente para el dueño, con la contraseña preparada fuera de Git.

### Cierre ordenado del worker

Al cerrar el proceso, el worker deja de reclamar turnos nuevos y espera hasta
`CHAT_MAX_TURN_SECONDS + 30 + 10` segundos: ejecución, conciliación GET de uso
terminal y finalización local. Con el límite hosted de 180 segundos, el worker
dispone de 220 segundos y Railway necesita 230 segundos incluyendo 5 segundos
para conexiones y 5 de margen. Una configuración inferior acorta la espera; una
superior a 180 se rechaza al arrancar. Si vence el plazo de ejecución, el turno
queda fallido por timeout antes de solicitar cancelación remota; confirmar uso
después puede liberar su reserva, pero no completa ni vuelve a ejecutar el
turno. La cancelación remota es de mejor esfuerzo. El uso que siga desconocido
conserva la reserva. Si el límite vence después de reclamar un turno pero antes
de iniciar entrada al proveedor, se registra cero uso confirmado y se libera su
reserva porque no hubo solicitud remota.

# Preparación y estado del backend en Railway

## Problema y resultado

El dueño creó la cuenta de Railway y vinculó GitHub con el repositorio. El
primer despliegue automático, antes del PR #83, falló durante `Railpack prepare`
al no detectar un punto de entrada del backend en la raíz. El PR #83 se integró
en `master` y sus checks `test` y `web` quedaron verdes. Un despliegue real de
esa configuración sí se intentó después, pero falló en `BUILD_IMAGE` con el
mensaje genérico `The Dockerfile failed validation`; el servicio no llegó a un
estado saludable.

El PR #83 preparó un build Docker explícito para la API con el perfil bloqueado
`chat-runtime`, el snapshot publicado y un arranque que escucha el puerto de la
plataforma. El CLI local conserva su restricción a loopback. El perfil remoto
exige contraseña, conserva SQLite en un volumen persistente y usa proveedor
simulado con admisión desactivada. La documentación oficial
de Railway establece que los servicios nuevos no pueden usar Config as Code;
se elimina `railway.json` y la selección del Dockerfile/opciones de deploy se
configura en el servicio.

El dueño acordó **30 días de retención del historial en el backend**. Esto no
modifica las condiciones de retención de OpenAI o Data Sharing. La contabilidad
mínima sin textos permanece y las reservas desconocidas no se borran por el
cambio de día o la eliminación del historial.

## Continuidad de la comparación

El dueño aportó la traza del turno fallido: rechazo del sistema de seguridad,
con `usage: null`. Se conserva como consumo desconocido, sin convertirlo en
cero ni repetir la pregunta. Después autorizó una excepción para continuar los
casos todavía no intentados. Posteriormente autorizó asumir cargo cero para
ese único fallo a efectos del presupuesto operativo acumulado de US$10,
conservando el consumo observado como desconocido y el intento en el historial.
El supuesto del dueño se registra separado de los costos calculados con uso
confirmado; no se presenta como una factura ni como tokens cero observados. La excepción es exclusiva para ese registro;
cualquier nuevo consumo desconocido vuelve a pausar la corrida.

Las cifras, la autorización y los identificadores se conservan en el expediente
privado. Las respuestas crudas, los secretos y los IDs del proveedor no se
publican. Se conservan las tarifas normales y no se presume gratuidad de Agents
API con herramientas ni cobertura del incentivo para gpt-6.1-sol.

## Condiciones de activación

La revisión semántica del dueño sigue en curso. El chat público permanece
apagado hasta cumplir calidad, revisión semántica y pruebas de HTTPS,
autenticación, CORS, persistencia y acceso desde teléfono con la computadora
apagada. No se contrata Hobby ni se modifica el DNS de formamx.com. Una
configuración preparada o un build válido no demuestra un despliegue saludable.

## Verificación

La imagen Docker local se construyó con el grupo `chat-runtime` bloqueado y
Python 3.13 slim; instaló 25 paquetes y no instaló las dependencias de
analítica. La primera prueba de build encontró que `uv sync --locked` también
intentaba resolver metadatos de una dependencia opcional ajena al perfil; el
Dockerfile usa `uv sync --frozen` para instalar el lock existente, mientras CI
sigue verificando el lock completo con `--locked`. La CA del proxy del entorno
local se montó como secreto temporal de BuildKit solo durante ese paso; TLS
permaneció validado y la CA no se copió a ninguna capa. El build normal de
Railway no depende de esa CA opcional.

El `railway.json` anterior validaba contra el esquema publicado, pero eso no
demostraba que Railway lo aplicase a un servicio nuevo; Config as Code está
deprecado y no está disponible para servicios nuevos. Tras el PR #83 se
aplicaron al servicio remoto los 19 cambios autorizados de variables,
configuración y volumen. Incluyen `RAILWAY_DOCKERFILE_PATH` para `Dockerfile.chat`,
healthcheck `/api/chat/health` con timeout 300 s, una réplica, región SFO,
Serverless activo, overlap 0 s, draining 100 s, restart `On Failure` con tres
reintentos y volumen persistente de 500 MB en `/data`. Los valores secretos no
se reproducen en esta documentación. La aplicación de ajustes no implica que el
servicio haya desplegado correctamente: el intento real posterior falló en
`BUILD_IMAGE`.

Las ocho pruebas focales del launcher pasaron, al igual que Ruff, formato y
comprobación del diff. El smoke completo de runtime con la variante local CA
verificó `PORT` dinámico, healthcheck, rechazo `401` sin autenticar, login,
creación de conversación, admisión cerrada (`429`, cero turnos iniciados), cero
llamadas al proveedor, volumen con permisos `0700`, SQLite y sidecars con
`0600`, exclusión de secretos de la imagen y persistencia tras reiniciar el
contenedor. No hubo llamadas al proveedor. Este resultado corresponde a la
variante local BuildKit/CA; no demuestra aceptación del `RUN` de producción
simplificado ni del builder remoto.

El error remoto no proporcionó detalle que identificara la causa. Como ajuste
de compatibilidad, el Dockerfile de producción elimina la directiva `#syntax` y
el montaje opcional de secreto BuildKit, y usa un `RUN uv sync --frozen`
estándar. Es una hipótesis de simplificación: no demuestra cuál fue la causa del
rechazo ni que Railway acepte ya la imagen. El build y smoke de runtime
completos con la variante BuildKit y CA temporal para el proxy terminaron
correctamente; esa evidencia cubre el entorno local, no el builder remoto. La
prueba completa del `RUN` de producción simplificado y su aceptación remota
siguen pendientes. No hay un despliegue Railway saludable ni aceptación remota
confirmada. La validación TLS del build local se mantiene. Para resolver certificados de un
proxy TLS solo en builds locales, se conserva una variante BuildKit privada con
permisos `0700` para el directorio y `0600` para el archivo bajo
`.state/outputs/railway-docker-compatibility/`; no es el Dockerfile de producción
ni se copia a la imagen.

El smoke completo de runtime descrito arriba pasó con la variante local CA;
todavía falta repetirlo con el `RUN` de producción simplificado y obtener
aceptación del builder remoto. Hubo un intento real de despliegue, pero falló en
`BUILD_IMAGE`; aún no existe un servicio Railway saludable. Después de conseguir
un despliegue aceptado, seguirán pendientes
la prueba HTTPS desde Pages, CORS con el origen final, login desde teléfono con
la computadora apagada y persistencia tras reiniciar el volumen remoto. El código
de cierre ordenado ahora tiene pruebas offline de drenaje, timeout y uso tardío;
el drenaje en el host Railway sigue sin verificarse. El chat permanece con
`mock` y admisión apagada mientras los gates semánticos y de calidad siguen
pendientes.

La entrega sigue AGENTS.md: PR, CI, revisión, merge y seguimiento de master.
Los archivos de datos publicados y las aprobaciones del Analysis Agent se
conservan.

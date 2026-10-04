# Preparación del backend para Railway

## Problema y resultado

El dueño creó la cuenta de Railway, vinculó GitHub y el repositorio. La conexión
funcionó; el despliegue automático del commit que integra el PR #82 falló en
`Railpack prepare` antes de arrancar el servicio, al no detectar un punto de
entrada del backend en la raíz del proyecto.

La continuación prepara un build Docker explícito para la API con el perfil
bloqueado `chat-runtime`, el snapshot publicado y un arranque que escucha el
puerto de la plataforma. El CLI local conserva su restricción a loopback. La
instancia hospedada exige contraseña, conserva SQLite en un volumen persistente
y empieza con proveedor simulado y admisión desactivada.

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

La configuración `railway.json` valida contra el esquema oficial. Las ocho
pruebas focales del launcher pasaron, al igual que Ruff, formato y comprobación
del diff. El smoke del contenedor completo verificó: arranque con `PORT`
dinámico, snapshot y worker disponibles, rechazo `401` sin autenticar, login
correcto, admisión deshabilitada, volumen con permisos `0700`, base SQLite y
sidecars con `0600`, ausencia de secretos incluidos y persistencia de una
conversación tras reiniciar el contenedor. No hubo llamadas al proveedor.

Esto verifica la imagen y el servicio en Docker local; todavía no hay un deploy
real en Railway. Por tanto, siguen pendientes la prueba HTTPS desde Pages,
CORS con el origen final, login desde teléfono con la computadora apagada y la
persistencia en el volumen Railway. El smoke tampoco ejercitó el drenaje de un
turno largo en curso: antes de habilitar un proveedor pagado se debe comprobar
explícitamente ese comportamiento. El chat permanece con `mock` y admisión
apagada mientras la revisión semántica y los gates de gasto/calidad siguen
pendientes.

La entrega sigue AGENTS.md: PR, CI, revisión, merge y seguimiento de master.
Los archivos de datos publicados y las aprobaciones del Analysis Agent se
conservan.

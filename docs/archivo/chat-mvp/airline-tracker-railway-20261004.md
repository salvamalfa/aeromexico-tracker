# Preparación y estado del backend en Railway

## Problema y resultado

El dueño creó la cuenta de Railway y vinculó GitHub con el repositorio. El
primer despliegue automático, antes del PR #83, falló durante `Railpack prepare`
al no detectar un punto de entrada del backend en la raíz. Un despliegue de la
configuración de PR #83 falló históricamente en `BUILD_IMAGE` con el mensaje
genérico `The Dockerfile failed validation`; no dejó información suficiente
para identificar la causa. PR #83 eliminó `railway.json` y la dependencia de
Config as Code para servicios nuevos. Después, PR #84 corrigió el Dockerfile y
el runtime de producción. Tras integrar PR #84, se quitó del servicio el pin de
fuente antiguo para que siguiera la rama `master`, y el servicio desplegó
correctamente. La falla anterior queda como antecedente, no como diagnóstico
del despliegue actual.

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

PR #84 se integró en `master` como `326d4c8`. Su CI pasó: 746 pruebas Python,
6 omitidas, 77 no seleccionadas, 95 Vitest y 9 comprobaciones de navegador. El
bot no dejó hallazgos abiertos y los hilos de revisión quedaron resueltos.

El despliegue actual siguió el commit exacto de `master` y está saludable en
<https://aeromexico-tracker-production.up.railway.app>. La prueba HTTPS devolvió
`200` en `/api/chat/health`; la respuesta indica auth `password`, proveedor
`mock` y admisión desactivada. El preflight desde Pages respondió `200`; una
petición de conversaciones sin autenticar devolvió `401` con CORS para el
origen permitido y un origen inválido recibió `403`. No se hizo login del dueño,
no se creó conversación remota y no se enviaron inputs al proveedor. El servicio
usa una réplica, volumen de 500 MB montado en `/data`, región SFO y suspensión
serverless; la retención configurada del historial es de 30 días.

La comprobación de solo lectura usó cuatro filas existentes de logs de acceso
Uvicorn: para health, preflight, petición sin autenticar y origen inválido, el
peer ASGI cayó dentro de `100.64.0.0/10` en 4 de 4 casos. Solo se conservó el
resultado booleano; no se guardaron IPs ni encabezados. Esto confirma la red del
peer en las solicitudes observadas, no garantiza el contrato de Railway ni
verifica qué dirección de `X-Forwarded-For` selecciona la aplicación. No se
probaron contraseñas incorrectas en la cuenta real.

El smoke de la imagen local con el runtime de PR #84, anterior a la última
corrección del adaptador OpenAI, usó una contraseña scrypt sintética, volumen
temporal y red deshabilitada. Verificó puerto dinámico, auth requerida,
login, creación e historial de conversación tras reiniciar el contenedor,
admisión deshabilitada con `429`, cero llamadas al proveedor, permisos `0700`
para `/data`, `0600` para SQLite y sus sidecars, y ausencia de rutas privadas en
la imagen. Otro smoke local con proveedor falso mantuvo un SSE activo durante
SIGTERM, detuvo nuevos claims, dejó el segundo turno pendiente y registró una
sola vez el uso tardío del turno activo. Estas pruebas no sustituyen login del
dueño ni reinicio del volumen remoto.

La corrección de compatibilidad del Dockerfile de producción usa un `RUN`
estándar con `uv sync --frozen`; el despliegue saludable confirma que Railway
aceptó la imagen y arrancó esa configuración. La variante BuildKit que monta una
CA temporal solo sirve para el entorno local y no se usa en producción. La
explicación y el comando reproducible están en [`docs/chat/railway.md`](../../chat/railway.md).

## Gates pendientes

H1 sigue pendiente de la revisión semántica del dueño; la reconciliación técnica
no equivale a aprobación. H4 no tiene modelo seleccionado: siguen pendientes
la cobertura suficiente, la calificación humana y los gates de calidad. H5 ya
tiene el backend HTTPS y el volumen persistente configurados, autenticación
preparada y retención acordada, pero falta que el dueño complete un login remoto
y verifique la persistencia del volumen tras reiniciar el servicio y el acceso
desde el teléfono con la computadora apagada. La integración del chat en el
frontend público y el proveedor pagado siguen apagados;
el proveedor permanece en `mock` y la admisión de turnos deshabilitada. El
resultado técnico de este despliegue no aprueba calidad ni autoriza activar el
chat público o gasto de inferencia.

La entrega sigue AGENTS.md: PR, CI, revisión, merge y seguimiento de `master`.
Los archivos de datos publicados y las aprobaciones del Analysis Agent se
conservan.

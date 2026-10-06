# Revisión del MVP y entrega de la interfaz

Fecha: 4 de octubre de 2026. Esta etapa permite al dueño revisar la comparación
terminal y comprobar el acceso protegido. Mantiene apagado el chat público.

## Decisiones recibidas

La decisión explícita del dueño en este chat, el 4 de octubre de 2026, fue:
«Confirmo estas definiciones [...] esta primera versión que sirva como MVP me
parece correcta [...] por el momento esta bien». Aceptó el catálogo y su alcance
como MVP, con ampliación posterior. Grupo Aeroméxico incluye Connect en
las métricas económicas trimestrales; industria suma Aeroméxico, Volaris y Viva;
las series de compañía y AFAC permanecen separadas; participación conserva su
universo AFAC y los cambios se expresan en puntos porcentuales. ASK y economía
unitaria conservan las unidades publicadas. No se habilitan métricas de rutas o
Vuelos, ni se transforman faltantes en cero.

El catálogo registra `owner_approved_mvp`. Su nueva versión semántica es
`0b8de07ff211ca1ba984bd87281a2d68950a3e36268909b2121a7ed6b35e0365`.
Cambió el metadato de revisión, no los datos, métricas o definiciones. La fixture
y los reportes de comparación anteriores conservan su versión original. Una
conversación abierta con la versión anterior recibe `snapshot_changed`; el
holdout congelado no debe ejecutarse contra esta versión distinta.

El dueño también confirmó los límites propuestos: 200.000 tokens diarios por
usuario y globales, reserva de 170.000 y US$0,10 diarios para Luna, o reserva de
80.000 y US$2 diarios para Sol. Su aplicación sigue condicionada a la selección
y calidad del modelo. No se presume Data Sharing gratuito, no se modifica el
presupuesto acumulado de US$10 ni se inicia otro experimento pagado.

## Revisión humana

`review.html` contiene solamente una interfaz vacía. El dueño importa el JSON
ciego privado generado desde la hoja terminal existente: 40 preguntas, 120
combinaciones y 74 respuestas finales disponibles. La interfaz muestra el
resultado esperado, permite calificar y anotar cada respuesta, filtra el avance
y exporta las calificaciones sin incorporar las respuestas. La clave de los
candidatos queda separada. Datos y notas permanecen en el navegador; no hay
solicitudes de red desde esa interfaz.

El exportador valida la estructura y la identidad del corte, evita sobrescribir
archivos y escribe el JSON en un directorio privado. No reproduce preguntas ni
modifica snapshots, reportes, rúbricas originales o contabilidad. La
[guía de revisión](../chat/revision-respuestas.md) describe el flujo.

El exportador conserva los controles Unix de permisos en Linux/macOS. En
Windows nativo no interpreta `st_mode` como una ACL ni exige los bits `0600`;
el dueño debe usar una carpeta con acceso privado en su cuenta de Windows.
La escritura exclusiva y la comprobación del contenido se mantienen en ambas
plataformas, sin sobrescribir el corte existente.
También acepta saltos de línea CRLF: normaliza solamente el texto usado para
analizar los encabezados, mientras conserva el SHA-256 de los bytes originales.

## Acceso y calidad

`access.html` permite comprobar el estado, verificar la contraseña y cerrar la
sesión contra la API HTTPS existente. No crea turnos ni habilita inferencia.
La contraseña inicial se entrega en un archivo privado; Railway recibe solo su
hash. La sesión del navegador permanece en memoria. El bundle público incluye
la dirección `https://aeromexico-tracker-production.up.railway.app`: la API es
accesible por HTTPS y exige contraseña en sus rutas protegidas. Publicar esta
página permite comprobar el acceso, pero no habilita inferencia.

La revisión automática también detectó que repetir el login podía reemplazar
el único token local sin cerrar la sesión anterior. El cliente ahora impide un
segundo login mientras existe una sesión o una solicitud en curso. Un fallo al
cerrar sesión conserva el token en memoria para poder confirmar el cierre.

La comprobación remota descubrió que el middleware anterior devolvía HTTP 411
a solicitudes legítimas del login detrás de Railway. El límite ahora se aplica
a los bytes recibidos, incluidos cuerpos sin `Content-Length` o enviados en
fragmentos. Conserva el límite específico del login, rechaza cuerpos excesivos
y longitudes inválidas, y acota el tiempo de lectura antes de analizar el JSON.
No elimina la autenticación ni las comprobaciones de origen.
La revisión de Codex y Claude detectó además que el límite leía cuerpos antes
de autenticar las rutas protegidas. Se corrigió el orden: un cliente sin sesión
recibe 401 sin lectura del cuerpo; origen y frontera local se comprueban antes
de esa lectura. El login público conserva sus límites y el plazo de lectura.

El diagnóstico offline de los cuatro fallos puntuados encontró tres consultas
con alcance incorrecto y un caso que requiere juzgar el texto de la respuesta.
No encontró valores numéricos erróneos en las filas esperadas que sí se
obtuvieron. El contrato de instrucciones y herramientas ahora prioriza el
alcance explícito de la pregunta y comprueba que las filas devueltas correspondan
a la métrica, entidad, fuente y periodo solicitados. Si el alcance es ambiguo,
debe aclararlo; no debe sustituir una serie cercana.

Las pruebas de contrato verifican ese comportamiento sin llamadas al proveedor.
No prueban que un modelo cumpla el gate de calidad. Las cifras Luna 7/9, Sol
9/10 y Astra 8/9 corresponden al contrato de instrucciones anterior; los
resultados originales permanecen intactos y no se recalifican con estas
instrucciones. Antes de elegir un modelo hace falta validar la calidad del
contrato nuevo mediante un plan separado, sin repetir intentos del corte
congelado ni exceder el presupuesto autorizado. El dueño aún
debe revisar las respuestas y decidir el modelo; cualquier validación pagada
nueva requiere un plan y presupuesto concretos autorizados.

## Fronteras de esta entrega

El subtotal normal conocido sigue en US$8,101306; el saldo operativo de
US$1,898694 no cubre la siguiente reserva de Astra de US$1,90. No se repiten
sondas o casos ni se reinician contadores. El uso histórico desconocido conserva
su estado y su reserva original, con la excepción operativa acotada ya dada por
el dueño. No se declara factura completa ni costo cero de Agents API con tools.

La publicación reutiliza el expediente de análisis ya aprobado. Debe conservar
el `analysis_manifest` y todos los hashes de `site/data/v1/`. No cambia periodos,
fuentes, DNS, plan de hosting ni evidencia candidata. La comprobación personal
desde teléfono sigue pendiente hasta que el dueño la realice.

## Verificación local

La suite pública de Python pasó con 773 pruebas y un skip de preview ausente;
las comprobaciones focales posteriores del exportador también pasaron. La
revisión y el acceso pasaron 19 pruebas Vitest, además de la comprobación de
TypeScript. Once pruebas de navegador cubrieron el dashboard existente, chat
simulado y la nueva revisión en escritorio y móvil. El smoke nuevo comprobó
texto XSS inerte, exportación sin respuestas, recuperación local, ausencia de
peticiones de datos y de desbordamiento horizontal.

La revisión independiente detectó y corrigió la asociación de calificaciones a
contenido modificado y la sobrescritura de guardados ilegibles: esos guardados
se conservan y la sesión ofrece exportación en memoria. La salida privada
terminal conserva su hash y las casillas humanas originales siguen vacías.

# Interfaz de revisión por cortes

La interfaz de revisión ahora acepta un único paquete versionado con varios
cortes. La persona revisora carga ese archivo una vez, cambia de corte desde
la misma página y califica las respuestas disponibles. Cada corte conserva su
propio denominador, sus estados de respuesta faltante y el significado local
de sus alias. Los errores, esperas y espacios no intentados se muestran como
estados; no se convierten en respuestas ni en aprobaciones.

El paquete usa `schema_version: 1`. Cada corte incluye el texto JSON fuente en
`dataset_json`; `dataset_sha256` se calcula sobre los bytes UTF-8 literales de
esa cadena antes de validarla. Así, cambios de espacios, orden de claves o
representación numérica cambian el hash sin depender de una reserialización.
El digest `source_sha256` debe coincidir con el `dataset_id` validado. Se
conserva la importación anterior de un conjunto individual de esquema 1.

Las calificaciones del paquete usan esquema 2 y quedan vinculadas al hash del
archivo exacto y al hash de cada corte. El guardado local es opcional, está
desactivado por defecto y se separa por paquete y corte. Al importar
calificaciones con el guardado activado, se escribe el estado de todos los
cortes, incluso una lista vacía cuando se borraron calificaciones. Si el
navegador rechaza una escritura, el trabajo permanece en memoria, la interfaz
avisa del fallo y mantiene disponible la exportación.

Al activar el guardado después de trabajar sin él, las calificaciones en
memoria prevalecen para los espacios editados y se combinan con las guardadas
no modificadas. Importar un archivo de calificaciones reemplaza el conjunto en
memoria de forma explícita y evita que el caché anterior restaure entradas
eliminadas. Antes de cambiar a otro conjunto o paquete válido, la interfaz
solicita confirmación si hay calificaciones en memoria; cancelar conserva el
archivo, corte, hash y calificaciones actuales. Volver a seleccionar el mismo
archivo exacto conserva el progreso sin preguntar.

## Validación y publicación

El código validado corresponde al commit
`d0dc4adfb765bc879aff27c7c1aea254527c8d8e`. TypeScript pasó con `npm run
check`; Vitest pasó con 20 archivos y 125 pruebas. La auditoría independiente
de las correcciones de conservación de calificaciones no encontró hallazgos.
El gate utilizó el registro de análisis de 2T26 ya aprobado y compiló con la
función de chat desactivada. `src.publish.verify site/` confirmó los 123
archivos resultantes.

La prueba de navegador de recuperación también verifica que el guardado
empieza desactivado, no restaura calificaciones hasta que la persona lo activa
y recupera el progreso guardado al volver a activarlo. La misma selección de
11 pruebas de navegador que ejecuta CI pasó localmente con Chromium después
de este ajuste.

El manifiesto de análisis coincide con la línea base previa y los 112 archivos
de `site/data/v1/` conservan sus hashes. Las 11 pruebas de navegador de CI y el
verificador del sitio compilado pasaron en localhost: revisión vacía en
escritorio y móvil, acceso sin consultas ni sesión y dashboard sin chat.
No hubo errores de consola, página o assets, ni solicitudes que no fueran GET.
La verificación pública se realiza después del éxito del workflow de Pages.
El cambio no incluye respuestas privadas, calificaciones humanas ni una
selección de modelo.

## Correcciones posteriores de caché para el PR 90

La revisión posterior encontró casos adicionales al activar el guardado local
después de trabajar con él desactivado. Ahora las ediciones por pregunta se
combinan sobre las calificaciones guardadas de cada corte; las calificaciones
previas no editadas se conservan y se guardan todos los cortes, incluidos los
inactivos. Una importación de calificaciones sigue siendo autoritativa: los
cortes vacíos reemplazan y limpian el caché anterior.

Un error al leer o escribir el caché conserva el aviso mientras el guardado
siga activado y mantiene las calificaciones en memoria y la exportación
disponibles. Una lectura fallida no marca el corte como cargado ni permite
sobrescribir contenido dañado al reactivar el guardado. Al exportar durante un
error, la interfaz confirma la exportación y advierte que el guardado local
sigue indisponible.

La verificación de estas correcciones pasó con Vitest (21 archivos, 131
pruebas), TypeScript y el control del límite de 400 líneas por módulo;
`bootstrap.ts` queda en 399 líneas. Los resultados de CI/Pages y la auditoría
independiente corresponden al ciclo actualizado del PR.

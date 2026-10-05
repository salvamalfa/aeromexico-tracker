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

## Validación y publicación

El código validado corresponde al commit
`99c1a9ab90e92b9fa6bee5b09c6f624de804fe10`. TypeScript pasó con `npm run
check`; Vitest pasó con 20 archivos y 122 pruebas. La auditoría independiente
de la interfaz no encontró hallazgos. El gate de publicación utilizó el
registro de análisis de 2T26 ya aprobado y compiló con la función de chat
desactivada. `src.publish.verify site/` confirmó el sitio resultante.

La publicación está en el commit de artefactos `93f440c9cdf8592ffed71308678b9467635d2249`.
El manifiesto de análisis coincide con la línea base previa y los 112 archivos
de `site/data/v1/` conservan sus hashes. El cambio no incluye respuestas
privadas, calificaciones humanas ni una selección de modelo.

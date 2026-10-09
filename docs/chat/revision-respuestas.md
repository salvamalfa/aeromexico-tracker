# Revisión privada de respuestas

La interfaz `review.html` permite revisar la comparación sin publicar sus
respuestas. La página publicada contiene solamente la interfaz vacía; el dueño
carga un archivo JSON privado desde su dispositivo. No envía el archivo,
calificaciones ni notas a un servidor, y no hace solicitudes a OpenAI.

## Revisar y guardar

1. Abre `review.html` en el sitio y carga el archivo privado. Acepta tanto el
   archivo individual de esquema 1 como un paquete de esquema 1. Un paquete
   reúne varios cortes versionados en un único JSON; el selector cambia entre
   ellos sin volver a cargar archivos.
2. Para cada respuesta disponible, revisa la pregunta y el resultado esperado,
   elige correcta, con problema o no evaluable, y explica los problemas en las notas.
   Una combinación sin respuesta permanece fuera del progreso y muestra el estado
   declarado por ese corte: sin respuesta, error terminal, en espera o no intentada.
3. Cada corte tiene su propio progreso y sus propios alias ciegos. A y B solo
   identifican candidatos dentro de ese corte; no implican que el alias refiera
   al mismo candidato en otro corte. Los totales siempre corresponden al corte
   seleccionado.
4. El guardado automático del navegador es opcional y está desactivado al abrir
   la página. Puedes activarlo explícitamente; sus claves incluyen el hash del
   archivo exacto y el identificador, versión y hash del conjunto de cada corte.
   Sin storage, la revisión sigue en memoria y se puede exportar.
5. Pulsa **Exportar todas las calificaciones** y conserva el único JSON
   descargado. En un paquete incluye todos los cortes, incluso los que no tienen
   calificaciones, y liga cada lista al hash exacto del paquete y al hash de su
   conjunto. Puedes importarlo después en otro navegador o dispositivo.

El guardado del navegador puede desaparecer al borrar sus datos o cerrar una
sesión privada. El archivo exportado contiene calificaciones y notas, nunca las
respuestas. Conserva el paquete exacto: un hash distinto se rechaza y las
calificaciones no se aplican a otro corte. La relación entre alias y candidatos
queda fuera de la interfaz y de ambas exportaciones.

## Contrato del paquete de revisión

El lector valida el esquema completo antes de mostrar respuestas. Un paquete es
un objeto JSON estricto con `schema_version: 1`, `bundle_id`, `bundle_version`,
`title` y `cuts`. Cada corte contiene `cut_id`, `version`, `label`,
`disposition` (`terminal`, `complete` o `partial`), `source_sha256`,
`dataset_sha256`, `dataset_json` y `slot_dispositions`. `dataset_json` es una
cadena con el texto JSON literal del conjunto de revisión de esquema 1
(`dataset_id`, preguntas, candidatos anónimos A/B/C (dos o tres por pregunta)
y `available_count`). Los espacios con respuesta nula marcados como rechazo
por contexto de aplicación se muestran como no evaluables y no admiten
calificación. El lector
calcula `dataset_sha256` sobre los bytes UTF-8 de esa cadena exacta antes de
interpretarla; espacios, orden de claves y representaciones numéricas forman
parte del hash. Esto evita volver a serializar datos y mantiene interoperabilidad
con el texto fuente original. `source_sha256` es el digest de vinculación a
fuentes que expone el conjunto y debe coincidir con `dataset_id`; no es
necesariamente el hash de un archivo fuente individual. El texto JSON anidado
tiene un límite de 9 MB dentro del límite de 10 MB del paquete.

El paquete declara exactamente un estado para cada espacio sin respuesta y
ninguno para los candidatos con texto: `no_answer`, `failed`, `held` o
`not_attempted`. Esto evita presentar un error o una combinación en espera como
una respuesta revisada. La interfaz solo permite calificar respuestas no nulas.
Los identificadores de corte deben ser únicos y cada objeto tiene una lista
cerrada de campos; no se admiten propiedades de mapeo, identidad de modelo o
metadatos adicionales.

Las calificaciones de paquete usan `schema_version: 2` e incluyen el hash de
bytes del archivo de paquete cargado, más una entrada por corte con su versión,
`dataset_id`, `dataset_sha256` y calificaciones. Se rechazan un paquete distinto,
un corte duplicado o faltante, identificadores en conflicto y hashes inválidos.
Los archivos antiguos de conjunto y calificaciones de esquema 1 siguen
funcionando como una revisión de un único conjunto.

La pregunta y las respuestas se muestran como mensajes intercalados por turno,
con los alias A/B/C visibles. El formato anterior, sin marcadores de turno,
conserva el texto completo como una pregunta y una respuesta. Las respuestas
admiten Markdown seguro para facilitar la lectura; el texto original completo
queda disponible en un desplegable. La referencia presenta los valores o
criterios disponibles y conserva el detalle completo en otro desplegable. La
interfaz no ejecuta HTML incluido en los mensajes.

Importar una hoja de calificaciones valida su versión, el conjunto de respuestas,
el SHA-256 de los bytes del archivo importado y sus identificadores antes de
aplicar cambios. La interfaz no declara aprobación humana mientras queden
respuestas pendientes.

## Preparación del archivo privado

El exportador del repositorio convierte una hoja ciega terminal ya existente;
no vuelve a ejecutar preguntas ni modifica resultados, facturas o contadores:

```text
uv run python -m scripts.chat.export_review_dataset --help
```

La salida pertenece a `.state/` y se crea con escritura exclusiva. En POSIX,
el exportador exige que la hoja fuente tenga modo `0600`, fija el directorio de
salida en `0700` y el JSON en `0600`, y comprueba esos modos al verificar una
salida existente. Windows no ofrece esos bits POSIX como control de ACL: el
exportador no puede garantizar que el archivo o directorio sea privado allí.
Windows conserva la protección ACL heredada del usuario y del directorio; usa
una ubicación con ACL restringida al usuario actual para la hoja y la salida.
La escritura exclusiva evita reemplazar un archivo existente, pero no restringe
quién puede leerlo. Nunca debe copiarse a `web/public/`, `site/`, un commit o un
comentario del PR.

## Acceso al chat

La página separada `access.html` permite comprobar la contraseña de la API con
HTTPS. Mantiene la sesión solamente en memoria y permite cerrarla. No crea
preguntas ni habilita el chat. La contraseña inicial se entrega en un archivo
privado; el servidor recibe únicamente su hash para configurarla.

El dueño confirmó el significado del catálogo y el alcance como MVP el 4 de
octubre de 2026. Después calificó las respuestas de la comparación con esta
interfaz y eligió `gpt-6.1-sol`; el MVP está activo en producción desde el 8
de octubre de 2026. No se aprobó un gate de calidad. La
[fase 2](fase-2-agente-analitico.md) reutiliza `review.html` para calificar su
conjunto de evaluación de negocio.

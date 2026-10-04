# Revisión privada de respuestas

La interfaz `review.html` permite revisar la comparación sin publicar sus
respuestas. La página publicada contiene solamente la interfaz vacía; el dueño
carga un archivo JSON privado desde su dispositivo. No envía el archivo,
calificaciones ni notas a un servidor, y no hace solicitudes a OpenAI.

## Revisar y guardar

1. Abre `review.html` en el sitio y usa **Archivo de respuestas JSON** para elegir el
   archivo privado entregado por el agente. El corte terminal contiene 40
   preguntas y 74 respuestas disponibles, agrupadas como candidatos A, B y C.
2. Para cada respuesta disponible, revisa la pregunta y el resultado esperado,
   elige correcta, con problema o no evaluable, y explica los problemas en las notas.
   Una combinación sin respuesta permanece fuera del progreso de revisión.
3. Usa los filtros para regresar a las respuestas pendientes. Las calificaciones
   se guardan en el navegador para ese conjunto concreto de respuestas.
4. Pulsa **Exportar calificaciones** y conserva el JSON descargado. Puedes
   importarlo de nuevo para continuar en otro navegador o dispositivo. Entrega
   ese archivo al agente cuando quieras que procese tu revisión.

El guardado del navegador puede desaparecer al borrar sus datos o cerrar una
sesión privada. El archivo exportado contiene calificaciones y notas; conserva
también el archivo de respuestas por separado. La clave que relaciona los
candidatos con los modelos queda fuera de la interfaz y de ambas exportaciones.

El resultado esperado presenta etiquetas, porcentajes y unidades para facilitar
la revisión; el detalle completo queda en un desplegable. Las respuestas y la
referencia se muestran como texto sin ejecutar
HTML. Importar una hoja de calificaciones valida su versión, el conjunto de
respuestas, el SHA-256 de los bytes del archivo importado y sus identificadores
antes de aplicar cambios. La interfaz no
declara aprobación humana mientras queden respuestas pendientes.

## Preparación del archivo privado

El exportador del repositorio convierte una hoja ciega terminal ya existente;
no vuelve a ejecutar preguntas ni modifica resultados, facturas o contadores:

```text
uv run python -m scripts.chat.export_review_dataset --help
```

La salida pertenece a `.state/`, con permisos privados y escritura exclusiva.
Nunca debe copiarse a `web/public/`, `site/`, un commit o un comentario del PR.

## Acceso al piloto

La página separada `access.html` permite comprobar la contraseña de la API con
HTTPS. Mantiene la sesión solamente en memoria y permite cerrarla. No crea
preguntas ni habilita el chat. La contraseña inicial se entrega en un archivo
privado; el servidor recibe únicamente su hash para configurarla.

El dueño confirmó el significado del catálogo y el alcance como MVP el 4 de
octubre de 2026, y confirmó los límites diarios propuestos. Estas decisiones
no sustituyen la revisión de respuestas, la selección del modelo ni el gate de
calidad. La activación del chat sigue pendiente de esas verificaciones.

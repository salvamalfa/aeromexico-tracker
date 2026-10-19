# Noticias: ajustes de revisión visual del 18 de octubre de 2026

PR #136, rama `codex/news-strategy-20261015`, base original master
`40a63d1905afde97ae8e3f8671c8217aafacc4aa`. Se inspeccionaron los tres PNG
anotados del dueño antes de editar. El PR sigue en borrador, sin integrar ni
publicar, sin tocar las ramas o artefactos de la integración de Vuelos.

## Cambios y decisiones

Se retiran los bloques introductorios, aprobación/descarga de paquete y textos
al pie señalados. El contador se reduce al número de noticias. La preview
retira también el bloque de siete ejemplos y los avisos añadidos al cuerpo
por su generador. El chat simulado conserva su identificación explícita en
las respuestas; no se presenta como una consulta generativa en vivo.

Se conservan las tarjetas, resúmenes originales, temas, estado de aprobación,
publicación, fecha del hecho, primera captura, fuentes y hashes. Los filtros de
mes, tema, aerolínea, palabras y disponibilidad en el chat siguen funcionando.
El botón de información del título muestra la cobertura parcial bajo demanda,
también desde móvil y teclado. Las respuestas del chat conservan la navegación
que valida corpus, hash, ID y cita antes de abrir una tarjeta.

No cambia el corpus: tres fichas aprobadas y once candidatas; septiembre tiene
cuatro historias de las tres aerolíneas y octubre sigue siendo parcial al corte
del 15 de octubre. Retirar los controles visibles de aprobación no aprueba ni
activa las candidatas. El paquete existente se conserva en documentación y datos.

## Verificación y límites

Se comprueban filtros, estados vacíos, URLs seguras, navegación verificada,
arranque mientras carga el dashboard, responsive y chat con API/worker real y
proveedor mock explícito. Las previews aisladas mantienen el chat offline
identificado; no se hacen nuevas llamadas de pago. Los resultados exactos de
CI, revisión Codex, capturas desktop/móvil y versiones de Library se adjuntan
al PR y al traspaso, identificando el commit completo.

## Pendientes

La aprobación de diseño queda condicionada a estos ajustes y no equivale a
aprobar el corpus, la presentación técnica o la publicación. Vincular la
presentación técnica final a los nuevos commits se resuelve por separado.
Skills por fuente, coordinador mensual/trimestral, Noticias mensual,
aprobaciones y limpieza futura permanecen pendientes. No se habilita cron.

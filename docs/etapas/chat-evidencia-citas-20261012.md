# Enlaces de evidencia de fase 2 · 12 oct 2026

Las búsquedas de reportes y noticias aprobados ya exponen `references` en el
formato que consume el adaptador del proveedor. Así, los enlaces de cada hit
llegan a la lista de fuentes de la respuesta; al compartir URL, se conserva una
sola entrada con las etiquetas de las páginas o fichas encontradas. Los
reportes incluyen empresa, periodo y página; las noticias, medio, título y
fecha.

La prueba de integración recorre el índice fixture, el registro de herramientas
y `references_from_results`, y comprueba las URL exactas. Las pruebas focales de
índice y presentación pasaron (24). `git diff --check` no reportó errores.

El índice aprobado real permanece vacío y `CHAT_ENABLE_EVIDENCE_TOOLS` conserva
su valor por omisión `false`; los fixtures de prueba no cambian este estado.

# UI de revisión ciega con cuatro candidatos · F2.9
Fecha: 10 de octubre de 2026.
- El piloto F2.9 compara cuatro candidatos por pregunta y requiere alias anónimos A–D.
- La UI acepta conjuntos de 2, 3 o 4 candidatos; A–D se asignan por pregunta/corte y mantienen compatibilidad con A/B y A/B/C.
- Las calificaciones y el progreso siguen vinculados al conjunto cargado; el mapeo de aliases no aparece en la UI ni en la exportación.
- Validación local: 157 pruebas web y `npm run check` pasaron.
- `src.publish` y `src.publish.verify site` pasaron con la aprobación existente.
- Los 112 hashes de `site/data/v1/` y el `analysis_manifest` permanecen idénticos a la publicación anterior.
- Reportes, respuestas y clave del piloto permanecen en almacenamiento local privado; no se incorporaron a Git ni a `site/`.
- El mapeo/selección de candidatos y los resultados del piloto no se han publicado.

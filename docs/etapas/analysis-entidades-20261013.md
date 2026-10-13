# Lectura trimestral por entidad · 13 de octubre de 2026

La Lectura ejecutiva podía mostrar el análisis aprobado de Aeroméxico, pero las otras entidades no tenían una identidad de publicación propia. Ahora evidencia, registro, auditoría, aprobación, manifest y consumidor identifican cada tesis mediante `(entity_key, period_id, version)`.

Los nuevos registros usan `analysis_runs/drafts/{entity}/{period}/{version}.json` y sus payloads `data/v1/analysis/{entity}/{period}.json`. Aeroméxico conserva el esquema y la ruta originales `data/v1/analysis/2026Q2.json`. El ledger mantiene las solicitudes humanas pendientes hasta una auditoría favorable de la versión exacta. Los expedientes y la procedencia humana permanecen en el respaldo privado; el sitio recibe exclusivamente texto aprobado y citas públicas.

El adaptador admite las cápsulas revisadas de Viva, Volaris e Industria para 2T26. Antes de consumir verifica los hashes de cápsulas, originales y metadatos de captura, ejecuta extractores offline fijados por hash, compara cálculos y texto, y exige auditoría independiente y autorización vigente. La huella de implementación incluye los módulos compartidos de validación, identidad y cálculo de panel, además del lock de dependencias. Cambiar implementación, texto o evidencia exige una versión y auditoría nuevas.

El frontend valida entidad/periodo/versión, mantiene caché por identidad y descarta respuestas anteriores al cambiar selección. Los enlaces `?entity=VIVA_AEROBUS&period=2026Q2` y equivalentes abren la tesis elegida. Cierra el diálogo al cambiar entidad y conserva la selección al compartir la URL.

## Validación y publicación

La auditoría independiente revisa las 50 afirmaciones y reproduce 577 nodos con 262 valores nativos. Incluye números, unidades, comparaciones, respaldo semántico, causalidad, contradicciones, redacción, linaje y corte temporal. El perímetro de Volaris se respalda con el pasaje de consolidación y subsidiarias del original SEC seleccionado.

El gate recibe cuatro registros exactos, con el de Aeroméxico existente, y `src.publish.verify` comprueba artefactos, contratos, identidad y hashes. La comparación del sitio generado preserva los 114 payloads públicos existentes byte por byte; solo añade tres payloads de análisis. La prueba Chromium del entorno cloud comprueba las cuatro entidades en escritorio y móvil, texto completo, citas, periodo/corte y cambios rápidos de selección. No utiliza una sesión de navegador personal.

Antes de integrar se requieren suite completa, checks `test` y `web` del último commit y todos los hilos de revisión atendidos. Después del merge se comprueban Pages, el backend y el sitio público. El PR público es #131 y los expedientes privados están en #25 y #26; los resultados finales de CI y despliegue se conservan en esos PRs.

## Límites vigentes

- Selección retrospectiva al 2026-10-13, sin declarar disponibilidad histórica al 2026-07-13. Las expectativas conservan la fecha de cada informe.
- Viva mantiene explícita la diferencia entre 1T26 publicado y semestre menos 2T26: USD 1,212,000 en gastos, EBIT, EBITDA y EBITDAR. No se reexpresa silenciosamente; saldos y resultados conservan el carácter reportado/no auditado.
- Industria es el panel de los tres grupos, con definiciones de pasajeros y ocupación y geografías diferentes. Las sumas financieras no eliminan transacciones entre empresas y no son una consolidación contable del panel.
- Las descomposiciones de ingreso/costo y mezcla son contables; no identifican efectos causales de moneda, motores, precios o coberturas.
- El fixture de evaluación Stage 2 conserva su versión aprobada histórica. Un snapshot nuevo debe detectar drift; publicar estas tesis no autoriza reversionar ese fixture, calificar Stage 3 ni consumir un proveedor pagado.

Procedimientos vigentes: `src/analysis_agent/README.md`, `src/publish/README.md` y `docs/cloud-development.md`. El respaldo privado registra actualizaciones parciales del expediente sin presentar el warehouse histórico como actualizado.

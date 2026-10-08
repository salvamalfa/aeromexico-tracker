# Propuesta de la fase 2 del chat (7 oct 2026)

## Qué cambió

- **Documento de diseño:** nuevo `docs/chat/fase-2-agente-analitico.md`, con
  las decisiones del dueño, el problema, la arquitectura propuesta, los
  paquetes F2.1–F2.9, los límites y la estimación de costo de las evaluaciones.
- **Traspaso de activación:** registra las calificaciones entregadas, que el MVP
  se activa sin cambios, qué hacer si el gate no pasa y el saldo de la API.
- **Diagramas:** las dos páginas interactivas se copiaron como HTML autónomo en
  `docs/arquitectura/`, y sus PNG y GIF en `docs/assets/chat/`.
- **Documentación:** `ROADMAP.md`, `README.md`, `docs/chat/README.md` y
  `CHANGELOG.md`.

## Por qué

Al calificar `review.html`, el dueño concluyó que el holdout mide seguridad,
pero no utilidad para analistas y ejecutivos. Las preguntas se escribieron
desde el catálogo y con jerga técnica. Decidió activar primero el MVP tal como
está y dejar documentada la siguiente etapa para que la implemente otro agente.

## Cómo se validó

- Solo cambian documentación y recursos estáticos; ningún archivo de `src/`,
  `web/`, `contracts/`, `config/` ni `site/`.
- Los PNG y GIF se generaron con Chromium (Playwright) a partir de los HTML
  versionados.
- Las cifras de costo salen de la validación real del 4 de octubre y de las
  tarifas registradas en `docs/chat/evaluaciones-presupuesto.md`.

## Límites

- La estimación de la fase 2 es de referencia, no una cotización. El agente
  debe recalcularla con `--dry-run` y las tarifas del día, y el dueño debe
  aprobarla antes de gastar.
- Los HTML de `docs/arquitectura/` no se publican en Pages: en GitHub se ven
  como código y hay que abrirlos en un navegador.

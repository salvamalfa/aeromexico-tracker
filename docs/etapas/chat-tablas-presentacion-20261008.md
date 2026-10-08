# Chat: tablas en las respuestas y presentación por referencia

Fecha: 8 de octubre de 2026. Alcance: renderizado de tablas en el chat del
MVP y diseño de presentación para la fase 2. No cambia datos, contratos,
`analysis_manifest` ni el backend.

## Qué pasó

La primera respuesta real con tabla («¿Cómo se ve el market share de las
aerolíneas en 2026?») se mostró como renglones sueltos con las barras `|`
visibles. El renderizador seguro de `web/src/views/chat/markdown.ts` solo
conocía párrafos, listas, títulos, negritas, cursivas y ligas.

## Cambios

- **MVP:** `renderSafeMarkdown` reconoce tablas estilo GitHub:
  - estructura: encabezado, separador y filas;
  - tolera renglones vacíos entre filas;
  - respeta la alineación del separador;
  - acota el tamaño a 12 columnas y 60 filas;
  - en pantallas angostas la tabla se desplaza de lado.

  Las celdas pasan por el mismo renderizado seguro del resto del texto. No se
  agrega ninguna nota a las tablas (decisión del dueño).
- **Fase 2:** `docs/chat/fase-2-agente-analitico.md` incorpora:
  - las decisiones del dueño del 8 de octubre: se conserva el aviso de avance
    de una oración; decimales con punto; fuentes sin duplicar;
  - el caso real como criterio de aceptación;
  - el diseño de F2.8, presentación por referencia: las herramientas devuelven
    la tabla validada y el modelo solo escribe su marca, sin vuelta extra al
    modelo;
  - la comparación de costo contra una herramienta clásica;
  - los ajustes al borrador del prompt y a la calificación.

## Validación

- `markdown.test.ts`: ocho pruebas nuevas. Cubren el caso real (con renglones
  vacíos entre filas), barras en texto normal y HTML en celdas, y los
  siete casos de la revisión de Codex. Cada prueba de esos casos falla sin su
  corrección.
- `vitest`: 147 aprobadas. `tsc --noEmit` limpio.

## Publicación

Autorizada por el dueño el 8 de octubre. El respaldo privado
(`aeromexico-tracker-data`, 26 sep) se restauró en la sesión; su warehouse no
tenía la entidad `INDUSTRY` que espera el código actual, así que se
reconstruyó localmente con `src.rebuild`. Los archivos versionados que
reescribió esa reconstrucción (gold, modelos, notas de EDA) se descartaron
sin commit. Después:

- `src.publish` con el análisis 2026Q2 ya aprobado (`186ba823…`) generó
  `site/` desde el commit `bdc4c5e` (`code_commit` del manifiesto publicado),
  que incluye las correcciones del parser de tablas pedidas por la revisión de
  Codex: tablas consecutivas, filas sobre el límite, tablas sin `|` inicial,
  divisor `---` después de la tabla, barras y diagonales invertidas escapadas y
  texto separado por un renglón vacío;
- `src.publish.verify site/` pasó;
- los 112 archivos de `site/data/v1/`, los contratos y el `analysis_manifest`
  son idénticos byte a byte a la publicación anterior. Solo cambiaron los
  archivos compilados de la página, `index.html` y el manifiesto.

Ninguna aprobación se creó ni cambió.

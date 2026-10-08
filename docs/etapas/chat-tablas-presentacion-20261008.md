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

- `markdown.test.ts`: dos pruebas nuevas, una con el caso real (con renglones
  vacíos entre filas) y otra con barras en texto normal y HTML dentro de
  celdas.
- `vitest`: 141 aprobadas. `tsc --noEmit` limpio.

## Publicación

El cambio solo se ve en Pages cuando `site/` se reconstruye con el gate y el
análisis 2026Q2 ya aprobado (`186ba823…`), comprobando que los hashes de
`site/data/v1/` y el `analysis_manifest` no cambien. Ese paso queda pendiente
en el PR #108 hasta que el entorno permita ejecutar el gate.

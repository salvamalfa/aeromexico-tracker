# Cierre técnico F2.5–F2.7 · 11 oct 2026

Esta bitácora registra los artefactos concretos que sustituyen el estado inicial
de scaffold descrito en
[`chat-f25-f27-evidencia-20261011.md`](chat-f25-f27-evidencia-20261011.md).
La bitácora inicial se mantiene inalterada como fotografía histórica; el estado
vigente está resumido en
[`F2.5–F2.7: revisión de candidatos`](https://github.com/salvamalfa/aeromexico-tracker/blob/dfa207c73d2eef4fa1b9de2bacd9da56d8586063/docs/chat/revision-fase-2/F2.5-F2.7-candidatos-20261011.md).

## Artefactos preparados

- F2.5 incluye siete extractos revisables de reportes oficiales de Aeroméxico,
  Volaris y Viva Aerobus para Q1/Q2 2026, con página, sección, URL, hash de
  captura y fragmento limitado. El caso sobre combustible enlaza los valores
  reportados y la atribución explícita del reporte. Para las capturas HTML de
  Volaris se conserva `byte_identity_mismatch_pending_review`; un hash distinto
  por sí solo no se interpreta como restatement.
- F2.6 incluye tres fichas breves originales basadas en metadatos de notas de
  FlightGlobal sobre resultados/combustible de Aeroméxico y Volaris. Contienen
  fecha, titular, resumen acotado, entidades, temas, enlace y hash; no incluyen
  texto completo de terceros. El recolector acepta metadatos en dry-run y crea
  un manifest cerrado al solicitarlo expresamente.
- F2.7 propone una regla versionada y un caso de prueba con tres capas citadas:
  dato reportado, atribución expresa de la empresa y contexto de noticia. La
  regla prohíbe inferir causalidad por coincidencia temporal y no modifica el
  prompt aprobado.
- El índice de producción sigue vacío. Las herramientas solo leen registros
  cuyo recibo coincide con el candidato, el hash de fuente, el extracto/resumen
  y `candidate_content_sha256`. Este último canoniza todos los campos
  semánticos, incluida cada parte de la cita y los campos de búsqueda; cambiar
  página, URL, empresa, periodo, titular, fecha o tema invalida el recibo. El
  contrato permite activar el gate con un recibo válido, pero no se creó ni
  simuló ninguno real.
- El workflow de noticias tiene solo `workflow_dispatch`, sin programación ni
  notificaciones. Valida que la ruta de metadatos resuelva dentro del inbox,
  que no cruce symlinks ni `..`, y que el archivo esté seguido por Git. La
  imagen del chat copia el índice aprobado vacío; los manifests candidatos no
  se incorporan al runtime.

## Validación y límites

`uv run pytest tests/test_evidence_index.py tests/test_railway_watch_patterns.py
-q` pasó con 13 pruebas. Cubren búsqueda con citas de páginas distintas,
filtros, rechazo de candidatos sin recibo o con recibo desligado, mutaciones de
metadatos, límites de fichas y vigilancia de los archivos copiados a la imagen.
Todos los candidatos siguen `owner_review_required`; no se activó la capacidad,
no se cambió el prompt aprobado y no se publicó información nueva.

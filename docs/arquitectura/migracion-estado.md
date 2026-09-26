# Estado de la migración a Vite + TypeScript y GitHub Pages

Fuente única de verdad del avance. Plan técnico:
[`auditoria-arquitectura-20260926.md`](auditoria-arquitectura-20260926.md) §4–§5.

**La migración P0–P8 está cerrada y completa (ver bitácora, 26-sep-2026,
"Migración completa"). No debe resumirse ni reabrirse**: `fusionado` y
`completado` son estados terminales. El único trabajo abierto es la tabla
["Remediación de la auditoría"](#remediación-de-la-auditoría-26-sep-2026) al
final de este documento (paquetes R1–R5).

## Cómo retomar

1. `git fetch origin` y abrir la tabla "Remediación de la auditoría" (al final
   de este documento): el primer paquete marcado **pendiente** o **en curso**
   es el que sigue. Ignora la tabla de paquetes P0–P8: todos están en un
   estado terminal (**fusionado** o **completado**) y ninguno se retoma.
2. Si tiene PR abierto, leer el PR y su último commit; si está **en curso**,
   continuar desde el último commit de la rama.
3. La sesión principal coordina; cada paquete lo ejecuta el subagente
   `migrador` (`.claude/agents/migrador.md`, Sonnet, esfuerzo medio).
4. Al cambiar de estado, actualizar esta tabla y subirla en el mismo commit.

Rama de trabajo: `claude/aerodata-box-international-7en30g`. Tras cada fusión
se reinicia desde `master`.

## Decisiones del dueño (26 de septiembre de 2026)

- Vite + TypeScript aprobado; Node forma parte del proyecto.
- GitHub Pages reemplaza a Streamlit; la app de Streamlit se retira completa.
- Se reescribe la historia de git para quitar peso (último paquete).
- Subagentes Sonnet en esfuerzo medio; nunca Opus para la ejecución.
- Pasos manuales del dueño: activar Pages (Settings → Pages → Source: GitHub
  Actions) en P6 y borrar la app en share.streamlit.io en P7.

## Paquetes

| Paquete | Alcance | Estado | PR | Siguiente paso |
|---|---|---|---|---|
| P0 | Fusionar #46, republicar el integrado con el total en el panel, tracker y agente | fusionado | #46 | — |
| P1 | Pruebas y CI (auditoría fase 0) | fusionado | #47 | — |
| P2 | Higiene y mapa del repo (fase 1) | fusionado | #48 | — |
| P3 | Contratos de datos y privacidad (fase 2) | fusionado | #49 | — |
| P4a | Front-end en archivos reales: vista Vuelos en `web/` con ES modules y paridad (fase 3) | fusionado | #50 | — |
| P4b | Front-end en archivos reales: lectura ejecutiva y demás pestañas (fase 3) | fusionado | #51 | — |
| P5 | Vite + TypeScript (fase 4) | fusionado | #52 | — |
| P6a | Citas del análisis exportadas y Vuelos cargado al abrir su pestaña (estado de trimestre único) | fusionado | #53 | — |
| P6b | Gate de publicación sobre `site/`, `verify.py` y workflow de GitHub Pages (fase 5) | fusionado | #54 | — (Pages activo: https://salvamalfa.github.io/aeromexico-tracker/) |
| P7 | Retiro de Streamlit y de la ruta HTML heredada | fusionado | #55 | hecho: el dueño borró la app en share.streamlit.io (confirmado 2026-09-26) |
| P8a | Aligerar el árbol: `bridge_record_lineage.parquet` con zstd y escritores alineados | fusionado | #56 | — |
| P8b | Reescritura del historial con `git filter-repo` y push forzado (coordinador) | completado | — | — |

## Bitácora

- 2026-09-26 · P0 iniciado.
- 2026-09-26 · P0 fusionado (#46). P1 iniciado.
- 2026-09-26 · P1 listo: CI pública 494 pruebas en 34 s sin datos locales; suite local 449 s → 152 s; `build_flight_payload()` 10.5 s → 2.4 s (diferencias de 1 ULP en ocupación por orden de suma). Falla previa: `test_stage12_diagnosis`.
- 2026-09-26 · P1 fusionado (#47, CI verde en 61 s). P2 iniciado.
- 2026-09-26 · P2 listo: REPO_MAP.md, README por paquete, ruff en 4 módulos, presupuesto de 600 líneas (13 excepciones), docs de etapa movidos. CI pública 501 pruebas.
- 2026-09-26 · P2 fusionado (#48, CI verde). P3 iniciado.
- 2026-09-26 · P3 listo: esquemas v1 (flights, executive), privacy.yaml con prueba negativa, exportador `src/web_export` (29 archivos, máx. 634 KB), insumos requeridos en `config/web_inputs.yaml`. CI pública 517 pruebas.
- 2026-09-26 · P3 fusionado (#49, CI verde). P4 dividido en P4a (Vuelos) y P4b (ejecutivo y demás pestañas) para sesiones más cortas. P4a iniciado.
- 2026-09-26 · P4a listo: `web/` con Vuelos en 12 módulos ES (≤ 228 líneas), datos por `fetch`, paridad 100 % contra el publicado (22 trimestres, 4 regiones, MEX/CUN, meses). Implementación duplicada con `flights.js` hasta P5. Plotly 3.7.0 vendorizado temporalmente (4.7 MB).
- 2026-09-26 · P4a fusionado (#50, CI verde). P4b iniciado.
- 2026-09-26 · P4b listo: página completa en `web/` (pestañas, lectura ejecutiva, economía, Vuelos), exportador de análisis de solo lectura vía `consumer_payload`. Paridad 100 % en texto, KPIs y gráficas, salvo las citas en superíndice.
  **Pendiente obligatorio para P6:** las citas (`<sup><a class="source-note">`) salen de `verified_inputs()` y aún no se exportan; P6 debe exportarlas (solo metadatos de fuentes públicas autorizadas) antes del corte a Pages para no perderlas.
- 2026-09-26 · P4b fusionado (#51, CI verde). P5 iniciado.
- 2026-09-26 · P5 listo: `web/` en Vite 7 + TypeScript estricto, tipos generados de los contratos, Plotly parcial (se borró el vendorizado de 4.7 MB), 43 pruebas Vitest, build determinista, job `web` en CI. Carga inicial: código 1.42 MB (0.47 MB gzip); con datos, 2.49 MB (0.73 MB gzip) contra 7.2 MB del publicado. **Pendiente menor para P6:** unificar el estado de trimestre de ejecutivo y Vuelos para cargar Vuelos solo al abrir su pestaña (bajaría la carga inicial a menos de 2 MB).
- 2026-09-26 · P5 fusionado (#52, CI `test` y `web` verdes). P6 dividido en P6a (citas y carga diferida de Vuelos) y P6b (gate y Pages). P6a iniciado.
- 2026-09-26 · P6a listo: citas exportadas por la misma vía verificada que stage18, paridad 100 % sin excepciones; estado de trimestre único; Vuelos carga al abrir su pestaña. Carga inicial 1.51 MB (0.49 MB gzip).
- 2026-09-26 · P6a fusionado (#53, CI `test` y `web` verdes). P6b iniciado.
- 2026-09-26 · P6b listo: `src/publish` (gate con la misma verificación que stage18, manifiesto SHA-256, recibo), `verify.py` con 6 pruebas negativas, workflow `pages.yml`, `site/` generado del expediente aprobado 2T26 (34 archivos, ~3.7 MB), paridad con el publicado.
- 2026-09-26 · P6b fusionado (#54, CI verde). P7 iniciado.
- 2026-09-26 · P7 listo: ~28,000 líneas retiradas (app Streamlit, `static/`, `stage18`/`reader_ui`, HTML heredado y sus pruebas, 17 dependencias). Una sola implementación de cada vista (`web/`) y una sola ruta de publicación (`src/publish`). Commit de archivo con Streamlit: `e645d3e` (no se pudo subir etiqueta desde este entorno; tras P8b este commit ya no existe, ver "Mapeo de commits tras la reescritura" abajo). CI pública 487 pruebas; locales 62 + 8 de navegador.
- 2026-09-26 · P7 fusionado (#55, CI verde). P8 dividido: P8a (árbol más ligero, PR normal) y P8b (reescritura del historial). P8a iniciado.
- 2026-09-26 · Pages activado por el dueño; despliegue manual correcto; los 34 archivos servidos coinciden byte a byte con el manifiesto.
- 2026-09-26 · P8a listo: todos los Gold se escriben con zstd (`write_parquet_atomic`), 43 tablas reescritas con contenido idéntico comprobado; `data/gold` 92.9 → 51 MB (linaje 61.8 → 32.1 MB). Corregida regresión del mapa (topología fijada, sin peticiones a cdn.plot.ly) y `site/` republicado con el mismo expediente aprobado.
- 2026-09-26 · P8a fusionado (#56, CI verde; hallazgo de Codex sobre escritores Gold internacionales corregido).
- 2026-09-26 · P8b completado: `git filter-repo --strip-blobs-with-ids` quitó los 49 blobs > 1 MB que ya no están en el árbol de `master` (HTML generados, versiones viejas de Parquet, Plotly vendorizado). Árbol final de `master` idéntico (`9981a6d…`). Push forzado de `master` y de las 7 ramas `claude/*`. Clon nuevo: `.git` 173 MB → 76 MB. No se alcanzó la meta de < 40 MB: el árbol vigente ya pesa ~74 MB empaquetado (Gold 51 MB, prototipos del Analysis Agent ~25 MB); bajarlo más exige sacar `bridge_record_lineage.parquet` del árbol público (decisión del dueño). Los clones anteriores deben volver a clonarse. Pages redesplegado; los 34 archivos servidos coinciden con el manifiesto.
- 2026-09-26 · **Migración completa.** Sitio: https://salvamalfa.github.io/aeromexico-tracker/. Publicar: `python -m src.publish --record <expediente aprobado> --out site/` con instrucción explícita del dueño; CI verifica y despliega.

## Remediación de la auditoría (26-sep-2026)

Fuente: `auditoria-arquitectura-20260926.md` §4–§5 (revisión posterior a la
migración completa). Cada paquete lo ejecuta el subagente `migrador`.

| Paquete | Alcance | Estado |
|---|---|---|
| R1 | Barreras de publicación (A2, A3, A7, A10) | fusionado (#58) |
| R2 | Exportación de análisis (A4–A6) | fusionado (#59) |
| R3 | Trazabilidad y documentación (A8, A11, A12) | fusionado (#60) |
| R4 | Dependencias web (A9) | fusionado (#61) |
| R5 | Limpieza histórica (opcional, decisión del dueño) | fusionado (#62) |

A1 (protección de rama) es una acción del dueño, no de un agente.

- 26-sep-2026: R2 en curso (rama `claude/upbeat-brahmagupta-g1orp2`). A6:
  `discover_approved_manifest`/`_load_record`/`export_period`/`export_analysis`
  derivan el directorio de drafts de `root` (`root.parent / "drafts"`) en vez
  de leer el `DRAFTS_ROOT` de módulo; el comportamiento por defecto
  (`flow.ROOT`) no cambia. A5: `discover_approved_manifest` rechaza más de
  una versión aprobada/publicada del mismo `period_id` con un error claro, y
  `src/publish/gate.py::load_records` rechaza dos `--record` del mismo
  `period_id` antes de cualquier trabajo. A4: `export_analysis` construye
  cada `analysis/<period_id>.json` en un directorio temporal junto a
  `out_dir/analysis` y lo intercambia atómicamente al final, así que una
  revocación (o un manifiesto vacío) no deja archivos de periodos previos.
  Pruebas nuevas en `tests/test_web_export_analysis_isolation.py`.
- 26-sep-2026: R2 fusionado (#59). R3 iniciado (rama
  `claude/upbeat-brahmagupta-g1orp2`): A11, la "Migración completa" P0–P8 se
  marca cerrada arriba (estados `fusionado`/`completado` terminales); A8, el
  commit de archivo de Streamlit se corrige de `e645d3e` (no sobrevivió a la
  reescritura de P8b) a su equivalente `3b9f1cc` tras la reescritura; A12,
  README y REPO_MAP.md se corrigen para reflejar el conteo real de tablas
  Gold y la ruta de publicación vigente (`src.publish` → `site/` →
  `pages.yml`).
- 26-sep-2026: R3 fusionado (#60). R4 iniciado (rama
  `claude/upbeat-brahmagupta-g1orp2`): A9, `npm audit` en `web/` pasa de 5
  avisos (Vite 7.1.12 alto, Vitest 3.2.4/`@vitest/mocker` moderado,
  `maplibre-gl` vía `plotly.js` crítico) a 2 (`@vitest/mocker` moderado y
  `maplibre-gl` crítico) tras actualizar `vite` → 7.3.6 y `vitest` → 3.2.7
  (parches dentro del mismo major). Los dos avisos restantes solo tienen
  arreglo con un major breaking (`vitest@5.0.2`, `plotly.js@4.1.1`) y no
  llegan al bundle publicado: `vitest` es `devDependency` (no se sirve en
  `site/`) y `web/src/lib/plotly.ts` no registra las trazas
  `choroplethmapbox`/`scattermapbox` que importan `maplibre-gl` — verificado
  con `grep maplibre dist/assets/*.js` (0 coincidencias) tras `npm run
  build`. `npm run check`, `npm test` (51 tests) y dos `npm run build`
  consecutivos (mismos hashes) en verde; ver "Dependencias y avisos de
  seguridad" en `web/README.md` para el detalle y la comparación con
  `site/assets/` (CSS idéntico, JS con hash distinto solo por un comentario
  de licencia que el nuevo esbuild omite, sin cambio de comportamiento).
- 26-sep-2026: R4 fusionado (#61). R5 iniciado (rama
  `claude/upbeat-brahmagupta-g1orp2`): retirados del árbol
  `prototypes/archive/Aeromexico Tracker anterior.html`,
  `prototypes/etapa-18/*.html` (5 archivos),
  `prototypes/etapa-17/propuesta_texto_usuario.html`,
  `src/analysis_agent/stage18_preview.py` (su único consumidor) y
  `src/dashboard/navigation.py` (duplicado sin más uso que su propia
  prueba; ver `web/` para el equivalente vigente) junto con la prueba que
  solo lo ejercitaba; ~30.2 MB retirados del árbol de trabajo (medido con
  `du`/tamaños de blob antes del borrado), recuperables del historial git
  en el commit 14836f2 (`git show 14836f2:<ruta> > archivo`). Referencias en
  docs actualizadas con nota de retiro
  (`docs/analysis-agent/analista-v1.md`, `docs/etapas/etapa-18-reporte.md`,
  `src/dashboard/README.md`). Además, el dueño confirmó el 2026-09-26 que la
  app de Streamlit en share.streamlit.io ya fue borrada y que no hay
  credenciales históricas que revocar (ambos eran pendientes fuera del
  repo señalados por la auditoría); fila de P7 arriba actualizada a "hecho".
- 26-sep-2026: R5 fusionado (#62). Con esto, **A8 y A10 quedan cerrados**: el
  código de ambos ya estaba fusionado (R3 #60, R1 #58), y lo que faltaba —
  republicar `site/` con un `code_commit` resoluble contra `master` post-P8b
  y correr la validación estricta con datos privados (`pytest
  --require-local-data`, `validate_stage8`) — se hizo en esta sesión desde un
  checkout local reorganizado en `Aeromexico Tracker\aeromexico-tracker\`
  (ver `docs/cloud-development.md`). El checkout venía desactualizado
  (basado en el `master` previo a la reescritura de P8b, 78 commits sin
  equivalente exacto pero con el mismo árbol salvo blobs grandes); se
  respaldó en la rama `backup/pre-rewrite-master` y el tag
  `backup-pre-rewrite-20260926` antes de alinearlo a `origin/master` con
  `git checkout -B master origin/master`.
- 26-sep-2026: decisión del dueño (salvamalfa): se revoca la versión
  aprobada `26bc9135…` de 2026Q2 (aprobada 2026-09-06 14:55) y se publica en
  su lugar `186ba823…` (aprobada 2026-09-06 15:44, agrega el claim
  `summary_activity` y explicita cifras en `operations_level` y
  `finance_definition`). Revocación registrada con
  `src.analysis_agent.lifecycle revoke` y
  `analysis_runs/REVOCACION-2026Q2-26bc9135.json`. Al republicar `site/` se
  descubrió que `src/web_export/writer.py` y `src/publish/manifest.py`
  escribían el JSON con `path.write_text(... + "\n")` sin `newline="\n"`:
  en Windows Python traduce ese salto de línea final a `\r\n`, así que
  `publication_manifest.json` quedaba 1 byte más grande por archivo que el
  blob que `.gitattributes` (`* text=auto eol=lf`) realmente commitea —
  `src.publish.verify` pasaba en Windows pero la CI (Linux) fallaba. Corregido
  en salvamalfa/aeromexico-tracker#65 (fusionado, `beadd46`). `site/`
  republicado con `python -m src.publish --record
  analysis_runs/drafts/2026Q2/186ba823….json --out site/` sobre ese commit;
  `code_commit` del manifiesto = `beadd46e41fb14a8d865d84da0daa44a29e2cc05`,
  verificado con `git cat-file -t` y confirmado en vivo en
  https://salvamalfa.github.io/aeromexico-tracker/publication_manifest.json.
  PR de solo `site/`: salvamalfa/aeromexico-tracker#64 (fusionado, `bc5e5dc`).

### Mapeo de commits tras la reescritura (P8b)

La reescritura de historial de P8b (`git filter-repo
--strip-blobs-with-ids`) cambió el hash de todo el historial de `master` al
quitar blobs > 1 MB. Correspondencia conocida:

- `e645d3e` (commit de archivo de P7, app Streamlit y ruta HTML heredada,
  ver bitácora de P7 arriba) → `3b9f1ccb843ec2c8ee5c98c6949b77976a1e7bcf`
  (`3b9f1cc`). Mismo árbol de código relevante (`streamlit_app.py`,
  `src/dashboard/app.py` verificados presentes), pero la reescritura pudo
  haber quitado HTML generado grande de ese árbol; no asumir que las HTML
  viejas siguen accesibles ahí.
- El `code_commit` del manifiesto publicado (`site/publication_manifest.json`)
  era `28935219de5c586d39ddd6f3e500dcb33f3f9b0e`, anterior a la reescritura de
  P8b y sin commit correspondiente en `master` post-reescritura. **Corregido**
  en la publicación autorizada por el dueño del 26-sep-2026 (ver bitácora de
  R5 arriba): `code_commit` ahora es `beadd46e41fb14a8d865d84da0daa44a29e2cc05`,
  HEAD de `master` en el momento de publicar, ya con el fix de CRLF/LF de
  #65 aplicado (A8/A10 cerrados).

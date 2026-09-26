# P7 · Retiro de Streamlit y de la ruta HTML heredada · 26 sep 2026

## Alcance

Fase 7 de `docs/arquitectura/auditoria-arquitectura-20260926.md`: retirar la
app Streamlit y el generador de un solo HTML integrado, dejando `web/` como
la única implementación de cada vista y `src/publish`/`site/` como la única
ruta de publicación. Decisión del dueño: Streamlit se retira por completo;
GitHub Pages (`site/`, `.github/workflows/pages.yml`) es el único sitio
publicado desde ahora. **El último commit de `master` que aún contiene la
app Streamlit y la ruta HTML heredada es `e645d3e`** — referencia de archivo,
ya que no se pudo empujar una etiqueta git desde este entorno.

## Inventario retirado

Solo usado por Streamlit o por la ruta HTML de un solo archivo:

- `streamlit_app.py` (entrypoint público, servía `static/` con `st.iframe`).
- App Streamlit multipágina: `src/dashboard/app.py`, `pages/` (11 módulos),
  `components/` (8 módulos), `theme.py`, `navigation.py::PAGE_SPECS`
  (se conservó solo `READER_TAB_SPECS`).
- Ruta "Estructura de datos": `src/dashboard/structure_html.py`,
  `structure_metadata.py`, `structure_presentation.py`, y sus validadores
  `validate_stage10.py`, `validate_stage11.py`.
- Consumidor HTML integrado: `src/analysis_agent/stage18.py::consumer_html`
  + `publish`, `src/analysis_agent/reader_ui.py`, y el script de un solo uso
  `close_stage18.py`.
- Renderizadores HTML de Vuelos/ejecutivo:
  `src/dashboard/executive_summary_html.py`, `src/dashboard/build_stage11.py`,
  y la mitad de renderizado HTML de `src/dashboard/flights_html.py`
  (`render_flights_html`, `render_flights_panel`, `standalone_flight_payload`,
  `integrated_flights_css`, `write_flights_html`) y `build_flights.py`.
- `static/aeromexico_tracker.html` (la copia servida) y `.streamlit/`.
- Prototipos generados por esa ruta: `prototypes/etapa-11/` (todo el
  directorio, `build_stage11.py`) y `prototypes/vuelos/vuelos_revision.html`
  (`build_flights.py`). Los prototipos de las etapas 12–18 del Analysis
  Agent (evidencia, cálculo, revisión editorial) **no** se tocaron: son
  parte del flujo de aprobación que sigue vigente.
- Activos: `src/dashboard/assets/{flights,executive_summary,data_structure,
  style}.{js,css}`. Se conservaron `world_110m.topojson`/`.meta.json` y
  `ne_110m_admin_0_countries.geojson` (geometría del mapa, insumo real de
  `flights.py`/`web_export`).
- `docs/deploy-streamlit.md` (guía de despliegue en Streamlit Community
  Cloud).
- Dependencias: `streamlit==1.62.0`, `streamlit-echarts==0.4.0` (y, vía
  `uv lock`, 15 paquetes transitivos: altair, blinker, httptools,
  itsdangerous, prettytable, pydeck, pyecharts, python-multipart,
  simplejson, starlette, toml, uvicorn, watchdog). `plotly` (Python) se
  conservó: lo usa `src/analytics/build_notebook.py`.
- `.github/workflows/refresh.yml`: se quitó el paso que corría
  `validate_stage10`/`validate_stage8`.
- `justfile`: recetas `dashboard` (Streamlit) y `stage11-prototype`
  (`build_stage11`).
- Pruebas: `tests/test_stage10_structure.py`, `test_stage18_integration.py`
  (su semántica de rechazo ya está cubierta, independientemente, por
  `test_publish_gate.py`), `test_flights_frontend_interactions.py`
  (superada por las pruebas Playwright de `web/`),
  `test_public_html_entrypoint.py`.

**~28,000 líneas eliminadas** (61 archivos en el primer commit de este
paquete), sin contar el segundo commit de correcciones/documentación.

## Qué se conservó y por qué

- `src/dashboard/executive_summary.py` y `flights.py`: constructores de
  payload puros, sin HTML — los usa `src/web_export` y `src/publish/gate.py`
  directamente, sin cambios.
- `src/dashboard/flights_html.py`: se redujo a solo
  `integration_flight_payload()`, la lista blanca de columnas que
  `src/web_export/flights.py` importa.
- `src/dashboard/build_flights.py`: se redujo a reconstruir el payload y su
  evidencia candidata (`flight_evidence.py`), sin el HTML de revisión.
- `src/dashboard/data.py`: se conservaron `query_df`/`connection`/
  `data_as_of` (consultas DuckDB en memoria sobre Parquet) para
  `check_manual_freshness.py`, quitando `@st.cache_data`/`@st.cache_resource`
  de Streamlit por `functools.lru_cache`.
- `src/dashboard/validate_stage8.py`: se conservaron solo sus controles de
  datos (contratos, interpretaciones de métricas, anclas 2T26,
  incertidumbre del forecast, salud de datos, frescura AFAC, controles del
  workflow) — es un paso `REQUIRED` del DAG en `src/pipeline/registry.py`
  (`dashboard.materialize_stage9` depende de él), así que no podía
  desaparecer sin romper `just rebuild`/`src.rebuild`. Se quitaron sus
  controles Streamlit (`AppTest` por página, tiempos de render, contraste
  WCAG sobre `theme.py`, greps sobre `components/*.py`) porque ya no hay
  páginas ni tema que verificar.
- `src/analysis_agent/lifecycle.py` y todo el ledger de aprobación: sin
  cambios. `src/publish/gate.py` ya usaba exactamente estas funciones desde
  P6b, no `stage18`/`reader_ui`, así que retirar ambos módulos no le quitó
  nada.
- Citas en superíndice: `src/web_export/analysis.py` ya tenía su propio
  port de `reader_ui.py::cite()` desde P6a (no importaba el módulo en
  tiempo de ejecución, solo lo mencionaba en comentarios) — no hubo que
  mover ninguna función.

## Reparación no anticipada: el manifiesto de análisis

`src/web_export/analysis.py::read_manifest` leía el `#analysis-manifest`
que `stage18.consumer_html` embebía en `static/aeromexico_tracker.html`
para saber qué periodos exportar. Al borrar ese archivo, tanto el CLI
`python -m src.web_export` como `tests/test_web_page_parity.py` (ver abajo)
quedaban rotos sin remedio. Se sustituyó por
`discover_approved_manifest(root)`: recorre `analysis_runs/drafts/`,
verifica cada registro con `lifecycle.state()` y devuelve `{period_id,
version}` para todo lo que el ledger local tiene **actualmente aprobado o
publicado** — los mismos estados que `consumer_payload` exige. Un clon
público sin `analysis_runs/` obtiene simplemente un manifiesto vacío, igual
que antes. Se quitó el flag `--published-html`, ya sin sentido.

## Pruebas de paridad contra `static/`: reemplazadas (tarea 3)

`tests/test_web_page_parity.py`, `test_web_flights_parity.py` y la versión
anterior de `test_site_parity.py` comparaban dos renders (la página
Streamlit publicada contra `web/dist/`, o contra `site/`). Con `static/`
retirado no queda una segunda página con la que comparar. Se borraron los
primeros dos y se reescribió `test_site_parity.py` para comparar `site/`
contra sus propias fuentes de verdad:

- `test_site_flights_and_executive_data_match_a_fresh_export` (sin
  navegador): `recombine_flights(site/data/v1)` y `executive.json` igualan
  bit a bit un `src.web_export` fresco sobre el warehouse actual; cada
  `analysis/<periodo>.json` se recompara contra `export_period()` si el
  registro sigue aprobado localmente.
- Tres pruebas Playwright que abren `site/` sola y comparan lo que muestra
  contra el payload real, no contra un segundo render: cambio de pestañas,
  KPIs de economía contra `executive_payload["views"]` (los valores
  `display_value` ya vienen formateados del payload; el margen unitario se
  recalcula igual que `kpis.ts`), y el texto narrativo de lectura contra
  `export_period()` — incluida la inserción de citas en superíndice, para
  lo cual se portó `applyCitations()` a texto plano
  (`_with_citation_labels`).

**Hueco de cobertura aceptado:** `test_switching_quarters_before_opening_
flights_survives_the_lazy_mount` (P6a, en el `test_web_flights_parity.py`
borrado) probaba que el store compartido de trimestre (`web/src/state/
period.ts`) sigue sincronizado si Vuelos se abre después de cambiar de
trimestre en la pestaña de lectura. Nada de esa lógica cambió en P7; la
prueba dependía de comparar contra `static/` y no se reconstruyó (el
fixture sintético de `tests/fixtures/web/` solo tiene un trimestre). Queda
documentado en `web/README.md` como pendiente de un fixture multi-trimestre.

## Documentación actualizada

`README.md`, `REPO_MAP.md`, `AGENTS.md`, `docs/cloud-development.md`,
`src/dashboard/README.md`, `src/analysis_agent/README.md`,
`src/web_export/README.md`, `src/publish/README.md`, `web/README.md`. Se
borró `docs/deploy-streamlit.md`. `CLAUDE.md` no tenía referencias que
corregir.

**Pendiente manual del dueño:** borrar la app en
[share.streamlit.io](https://share.streamlit.io/) (Streamlit Community
Cloud) — este paquete no tiene acceso a esa cuenta.

## Verificación

- `uv run pytest -m "not local_data and not browser" -q` → 487 passed.
- `uv run pytest --require-local-data -q -m "local_data and not browser"` →
  62 passed, 1 fallo previo aceptado (`test_stage12_diagnosis`, un mismatch
  de hash del warehouse ajeno a este paquete).
- `uv run pytest --require-local-data -q -m browser` → 8 passed (incluye
  las 3 nuevas de `test_site_parity.py`).
- `cd web && npm run check && npm run test && npm run build` → sin errores
  (51 pruebas Vitest, build determinista).
- `uv run python -m src.publish.verify site/` → `site is valid.`
- `uv run pytest -q tests/test_repo_budgets.py` → 3 passed (se quitó la
  entrada de `structure_metadata.py`, que ya no existe).
- `uv lock` retiró `streamlit`/`streamlit-echarts` y 15 paquetes
  transitivos; `uv sync --all-extras --all-groups` los desinstaló.

## Riesgo residual

- El hueco de cobertura del store de trimestre compartido, arriba.
- `src/dashboard/validate_stage8.py` no tiene una prueba dedicada en
  `tests/` (tampoco la tenía antes de P7); solo se ejerce vía
  `just dashboard-validate`/el DAG de `src.rebuild`.

## Siguiente paso

Actualizar `docs/arquitectura/migracion-estado.md` (tabla + bitácora):
marcar P7 listo y avanzar a **P8 · Peso de git y reescritura de historia**.

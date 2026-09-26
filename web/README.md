# `web/`

Vite + TypeScript front-end for the whole published page — shared header,
period stepper, and the reader-tabs shell around three views (Lectura
ejecutiva, Economía unitaria, Vuelos) — loading the v1 payload split by
`src/web_export/` via `fetch`. See
`docs/arquitectura/auditoria-arquitectura-20260926.md` §4.2–4.3 and Fase 3–4,
and `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` for Vuelos' history.
P4a/P4b built this as plain ES modules (`.js`); P5 converted every module to
strict TypeScript and put Vite in front of it (`package.json`, `vite.config.ts`,
`tsconfig.json`) — no visible behaviour changed, see "Paridad" below.

## Responsabilidad

- One implementation of each view — the same ones the currently published
  `static/aeromexico_tracker.html` shows in its integrated mode — as real
  `.html`/`.ts`/`.css` files instead of Python f-strings, so a human or an
  agent can edit them directly. `src/dashboard/flights_html.py`,
  `src/dashboard/executive_summary_html.py`, `src/analysis_agent/
  reader_ui.py` and their JS assets still generate that published page
  unchanged; this package does not touch them or `static/`.
- `index.html` is the whole page: the shared `<header>`/period stepper,
  the `.reader-tabs` shell (`#tab-reading`/`#tab-economy`/`#tab-flights`
  and their `role=tabpanel` sections), and each view's markup, copied from
  the *published* integrated page's DOM (inspect
  `static/aeromexico_tracker.html`, not the Python f-strings). Its entry
  script is `<script type="module" src="src/main.ts">`; Vite compiles that
  graph, there is no separate build step invoked by hand.
- TypeScript ES modules under `src/views/<view>/*.ts` (≤ 400 lines each, see
  `tests/test_repo_budgets.py`), `strict: true` (`tsconfig.json`):
  - `shell/tabs.ts`: the tab controller (click + arrow/Home/End keys,
    dispatches `reader-tab-visible` after resizing any Plotly graph the
    now-visible panel holds), ported from the inline `<script>`
    `src/analysis_agent/reader_ui.py::refine` appends.
  - `executive/{state,narrative,bootstrap}.ts`: fetch
    `data/v1/executive.json` (records + views, shared by the
    reading *and* economy tabs, exactly like the published page's one
    `executive_summary.js` drives both) and, per period,
    `data/v1/analysis/<period_id>.json` — the export of
    `src/web_export/analysis.py` — to render the approved-analysis summary
    and the full-analysis dialog (`#analysis-full`, re-filled per period
    rather than one `<dialog>` per period like the published page, since
    this view fetches lazily). A period with no exported file (no
    approved analysis, or a dev build run with `--allow-missing-analysis`)
    shows the same "Análisis pendiente de aprobación" placeholder text.
  - `economy/{kpis,charts,table}.ts`: the 4 KPI cards (RASK, CASK, ASK,
    Margen unitario — `load_factor_reported`/`passengers` are in the
    payload but never rendered here either, matching what
    `reader_ui.py::refine` drops from the published page), the three
    Plotly charts (unit economics, volume vs. RASK, load factor vs. RASK)
    and the by-quarter disclosure table, ported from
    `src/dashboard/assets/executive_summary.js`.
  - `flights/*.ts` (unchanged behaviour from P4a, converted to TypeScript
    in P5): `state.ts` (mutable state + lazy per-period fetch/cache),
    `dom.ts` (formatting), `domestic.ts`/`regions.ts` (mode switches),
    `coverage.ts` (route coverage dots/icons), `volume.ts` (network volume
    line), `table.ts` (route table + airport tooltip), `search.ts`
    (airport search box), `map.ts` (the Plotly flow map), `network.ts`
    (mode/period orchestration), `mix.ts` (passenger mix chart),
    `quarter.ts` (global quarter selection), `bootstrap.ts` (mounts the
    view and wires `#period-prev`/`#period-next` — see "Mount order"
    below).
  - `main.ts`: mounts the tab shell, then `views/executive`, then
    `views/flights` (via a dynamic `import()`, see "Tamaño del bundle"
    below), in that order (see "Mount order" below).
  - `types/domain.ts`: hand-written types for the in-memory shapes the
    views work with (routes, airports, networks, quarter/executive
    records). `types/generated/*.ts` are generated from
    `contracts/web/*.schema.json` by `npm run gen:types` — never edit
    them by hand; `types/generated.test.ts` (vitest) fails if they are
    stale vs. the schemas.
  - `lib/plotly.ts`: the partial Plotly bundle these views import instead
    of a global `window.Plotly` — see "Plotly" below.
- CSS is split per view: `styles/base.css` (design tokens, page-wide
  resets, and everything shared by all three tabs — the `.page-shell`/
  `.hero`/period-stepper/`.reader-tabs` the published page's shared header
  and tab shell use), `views/executive/executive.css` (narrative card,
  analysis summary/dialog), `views/economy/economy.css` (KPI grid, chart
  cards, disclosure table) and `views/flights/flights.css` (unchanged from
  P4a, scoped under `.flights-view`).

### Plotly

P4a/P4b vendored the full Plotly bundle at `vendor/plotly-3.7.0.min.js`
(MIT, 4.7 MB, matching the version the published page embeds via
`plotly.offline.get_plotlyjs()` — see `src/analysis_agent/reader_ui.py`).
P5 deleted that vendored file. `src/lib/plotly.ts` now imports
`plotly.js/lib/core` plus only the trace types these views actually use —
`bar`/`scatter` (economy charts, the passenger-mix chart) and
`scattergeo`/`choropleth` (the Vuelos flow map) — and `Plotly.register()`s
them, through `npm`'s `plotly.js` package (pinned in `package.json`) and
Vite's bundler instead of a `<script>` tag. Every view imports `Plotly`
from `src/lib/plotly.ts`, never from a global `window.Plotly`. The
published page never uses ECharts or any other charting library; this
keeps the same Plotly 3.x major version so rendering stays identical (see
"Paridad" below). Deliberately excluded: `choroplethmapbox`/
`scattermapbox` (unused by any view here, and the only source of the
`npm audit` findings in the `plotly.js` dependency tree at this pin, via
`maplibre-gl` — not reachable at runtime through this partial import).

### Estado de trimestre compartido y carga diferida de Vuelos (P6a)

The published page's own `#period-prev`/`#period-next` are shared by two
independent scripts: `executive_summary.js` attaches its own click
listener, then `src/dashboard/assets/flights.js` attaches a second,
independent one to the same buttons (there is only one stepper in the
DOM) — every click fires both, in attachment order, each keeping its own
`periodIndex`. P4a/P4b/P5 ported that structure as-is: `views/executive`
and `views/flights` each kept their own `periodIndex` and their own
listeners on the same buttons, and `web/src/main.ts` mounted
`views/flights` right after `views/executive` on every page load so the
two stayed in lockstep — this only worked because both quarter lists
happen to hold the same 22 quarters in the same order (see the P5 tracker
entry in `docs/arquitectura/migracion-estado.md`), and it meant
`views/flights`' data (`quarters.json`, world geometry, network files)
always loaded even for a reader who never opens the Vuelos tab.

P6a replaced that with one shared store, `web/src/state/period.ts`: it
owns the selected index and the *single* pair of click listeners on
`#period-prev`/`#period-next` (`wireStepper()`, wired once by
`views/executive/bootstrap.ts`, since the executive view always mounts
first). `views/executive/bootstrap.ts` and `views/flights/bootstrap.ts`
each `subscribe()` to it instead of keeping their own listeners; a
subscriber is notified in subscription order on every move, so the
executive view still renders before Vuelos on each click — the same
attachment-order guarantee the published page's two independent
listeners gave, now expressed as subscriber order instead. Each view
still keeps its own `periodIndex` field (`views/executive/state.ts`,
`views/flights/state.ts`) pointing into its *own* records/quarters array
— `views/{executive,flights}/bootstrap.ts` re-derive it by `period_id`
lookup every time the shared store moves, rather than assuming the two
arrays share one index space.

Because the store keeps the selected `period_id`, not just an index,
`views/flights/bootstrap.ts` (mounted lazily, see next) can join *after*
several quarter switches on the reading tab and immediately pick up
`currentPeriodId()` — this is exactly what
`test_switching_quarters_before_opening_flights_survives_the_lazy_mount`
in `tests/test_web_flights_parity.py` checks against the published page:
switch quarters on the reading tab, *then* open Vuelos for the first
time, then switch again.

**Carga inicial de Vuelos**: `web/src/main.ts` no longer mounts
`views/flights` unconditionally on load. It listens for the same
`reader-tab-visible` `CustomEvent` `views/shell/tabs.ts` already
dispatches on every tab switch (`views/flights/bootstrap.ts` itself used
it to resize Plotly graphs) and mounts Vuelos — `import()`, `loadQuarters()`
and all — the first time `panel-flights` becomes visible; a reader who
never opens that tab never fetches `quarters.json`, the world geometry or
any network file, and never even downloads the `bootstrap-*.js` chunk.
See "Tamaño del bundle" below for what this drops from the initial
transfer.

### Citations (closed gap, P6a)

The published reading tab adds a superscript citation link
(`<sup><a class="source-note">`) next to some numbers in the analysis text
— see `src/analysis_agent/reader_ui.py::cite`. P4b/P5 shipped without it:
building that link needs `verified_inputs()` (excerpts, source URLs,
calculation lineage), which `src/web_export/analysis.py` did not read.
P6a closed this gap: `src/web_export/analysis.py` now also calls
`flow.verified_inputs(record)` (the same fail-closed call `stage18`
makes) and, per claim, exports a `citations` array — a port of
`cite()`'s selection logic that emits *only* what `cite()` itself already
puts on the public page: the public source URL (still restricted to
`www.sec.gov`/`sec.gov`/`ir.aeromexico.com`, both in code and in
`contracts/web/analysis.schema.json`'s `citation.href` pattern), the
visible tooltip text, and the exact substring of the already-rendered
claim text to wrap — no excerpt/source/calculation object or lineage ever
leaves the file. `web/src/views/executive/narrative.ts::applyCitations`
ports `cite()`'s DOM-splicing step (same markup, classes, attributes,
numbering) against the rendered text. `tests/test_web_page_parity.py`
compares the full `innerText` (superscripts included) on both sides, so
parity is 100%, citations included.

## Entradas / salidas

- **Entradas:**
  - Exported by Python to `web/public/data/v1/…` (local, gitignored — see
    `.gitignore`); Vite copies everything under `web/public/` to the root
    of the served site / `dist/`, so at runtime these are fetched at
    `data/v1/…`, not `public/data/v1/…` (Vite convention — see
    `src/views/{flights,executive}/state.ts`'s `dataRoot`).
  - `data/v1/flights/quarters.json` (metadata, quarters, monthly
    passengers, world geometry, `available_periods`), fetched first; then
    `data/v1/flights/{domestic,international}/<period_id>.json` on
    demand — see `src/web_export/flights.py`.
  - `data/v1/executive.json` (metadata, records, views — every
    quarter, ~80 KB), fetched once — see `src/web_export/executive.py`.
  - `data/v1/analysis/<period_id>.json`, fetched lazily per period
    as the reading tab's period changes; a 404 means no approved analysis
    for that period — see `src/web_export/analysis.py`.
- **Salidas:** none; this is a read-only page.

## Ejecutar localmente

```
uv run python -m src.web_export --out web/public/data/v1
cd web && npm ci && npm run dev
```

Then open the URL `npm run dev` prints (`http://127.0.0.1:5173/` by
default). Add `--allow-missing-analysis` to the first command in a
checkout with no local `analysis_runs/` ledger (a clean public clone);
the reading tab then shows the "pending approval" fallback for every
quarter instead of failing the export.

To check the actual production build instead of the dev server:

```
cd web && npm run build && npm run preview
```

`web/serve.py` (a thin `http.server` wrapper) still exists for the
Playwright tests below, which serve the built `web/dist/` directly rather
than going through `npm run preview`.

## Comandos de web/

| Comando | Qué hace |
|---|---|
| `npm ci` | Instala `node_modules` desde `package-lock.json` (versiones fijas). |
| `npm run dev` | Servidor de desarrollo de Vite con recarga en caliente. |
| `npm run build` | Compila a `dist/` — determinista: dos builds seguidos producen los mismos hashes de archivo (verificado a mano; ver "Tamaño del bundle"). |
| `npm run preview` | Sirve `dist/` (el build) localmente. |
| `npm run check` | `tsc --noEmit` — chequeo de tipos estricto. |
| `npm run test` | `vitest run` — pruebas unitarias de funciones puras y la prueba de tipos generados al día. |
| `npm run gen:types` | Regenera `src/types/generated/*.ts` desde `contracts/web/*.schema.json`. |

## Comando de prueba focalizada

```
cd web && npm run check && npm run test && npm run build
uv run pytest -m browser -q tests/test_web_flights_smoke.py tests/test_web_page_smoke.py
uv run pytest --require-local-data -m "browser and local_data" -q tests/test_web_flights_parity.py tests/test_web_page_parity.py
```

- `test_web_flights_smoke.py` / `test_web_page_smoke.py` are `browser`
  only — since P5 they build `web/` with Vite once per pytest session
  (`web_dist_dir` in `tests/conftest.py`, skipped with a clear reason if
  `npm`/Node are missing) and serve the **built** `web/dist/` with the
  synthetic fixtures at `tests/fixtures/web/`, then check each tab renders
  with no console errors — so they are the ones enabled in CI's `web` job
  (see `.github/workflows/ci.yml` and `REPO_MAP.md`).
- `test_web_flights_parity.py` / `test_web_page_parity.py` are also
  `local_data` (they need the real warehouse-backed payloads and, for the
  reading tab, whatever this checkout's local `analysis_runs/` ledger
  currently has approved) to compare against; they also serve the built
  `web/dist/` and open it beside the published
  `static/aeromexico_tracker.html` across the full quarter matrix,
  comparing the visible numbers/text/chart data. Parity against the built
  site stayed 100% (same documented citation exception, see above) after
  the P5 conversion.

## Tamaño del bundle

Medido con `npm run build` (commit actual) más un export real desde el
warehouse local (`uv run python -m src.web_export --out web/public/data/v1
--allow-missing-analysis`), trimestre por defecto `2026Q2`, cargando la
página con Playwright y sumando el tamaño real de cada respuesta HTTP (ver
la metodología en `tests/test_web_page_smoke.py`/`test_web_flights_parity.py`;
las cifras de esta sección se tomaron con un script de un solo uso, no
parte de la suite).

**Carga inicial (pestaña de lectura, Vuelos sin abrir)** — desde P6a,
`main.ts` ya no importa ni monta `views/flights` al cargar la página (ver
"Estado de trimestre compartido y carga diferida de Vuelos" arriba), así
que esta es toda la transferencia hasta que alguien abre esa pestaña:

| Archivo | Sin comprimir | gzip |
|---|---|---|
| `dist/index.html` | 14.4 KB | 3.2 KB |
| `dist/assets/index-*.css` | 99.3 KB | 15.4 KB |
| `dist/assets/index-*.js` (tabs, executive, economy, Plotly core+bar+scatter — ya no incluye nada de `views/flights`) | 1,304.2 KB | 455.1 KB |
| `data/v1/executive.json` | 68.2 KB | 8.4 KB |
| `data/v1/analysis/2026Q2.json` (incluye las citas de P6a) | 26.6 KB | 6.5 KB |
| **Total de la carga inicial** | **1,512.6 KB (≈1.51 MB)** | **488.6 KB (≈0.49 MB)** |

**≈1.51 MB sin comprimir**, por debajo del objetivo de ≤ 2 MB de la Fase
4 — y ya sin el ≈24% que la versión P5 (con Vuelos montado siempre) tenía
por encima de ese objetivo (≈2.49 MB). `dist/assets/bootstrap-*.js`
(35.8 KB / 11.8 KB gzip, el chunk de Vuelos) tampoco se descarga hasta
que se abre esa pestaña.

**Al abrir la pestaña Vuelos por primera vez** (el resto de la
transferencia, cargado bajo demanda, con `state/period.ts` ya
sincronizado en el trimestre que estuviera seleccionado):

| Archivo | Sin comprimir | gzip |
|---|---|---|
| `dist/assets/bootstrap-*.js` (chunk de Vuelos, `import()` dinámico) | 35.8 KB | 11.8 KB |
| `data/v1/flights/quarters.json` (incluye la geometría mundial TopoJSON) | 634.0 KB | 212.9 KB |
| `data/v1/flights/domestic/2026M0{4,5,6}.json` (los 3 meses del trimestre por defecto) | 310.4 KB | 31.7 KB |
| **Subtotal al abrir Vuelos** | **980.1 KB (≈0.96 MB)** | **256.4 KB (≈0.25 MB)** |

Quien nunca abre Vuelos nunca paga esos ≈0.96 MB; quien la abre acaba
transfiriendo ≈2.49 MB en total — la misma cifra que P5 ya cargaba
siempre, ahora repartida en el tiempo en vez de al inicio.

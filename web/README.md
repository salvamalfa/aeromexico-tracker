# `web/`

Framework-free front-end for the whole published page — shared header,
period stepper, and the reader-tabs shell around three views (Lectura
ejecutiva, Economía unitaria, Vuelos) — loading the v1 payload split by
`src/web_export/` via `fetch`. See
`docs/arquitectura/auditoria-arquitectura-20260926.md` §4.2–4.3 and Fase 3,
and `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` for Vuelos' history.

## Responsabilidad

- One implementation of each view — the same ones the currently published
  `static/aeromexico_tracker.html` shows in its integrated mode — as real
  `.html`/`.js`/`.css` files instead of Python f-strings, so a human or an
  agent can edit them directly. `src/dashboard/flights_html.py`,
  `src/dashboard/executive_summary_html.py`, `src/analysis_agent/
  reader_ui.py` and their JS assets still generate that published page
  unchanged; this package does not touch them or `static/`.
- `index.html` is the whole page: the shared `<header>`/period stepper,
  the `.reader-tabs` shell (`#tab-reading`/`#tab-economy`/`#tab-flights`
  and their `role=tabpanel` sections), and each view's markup, copied from
  the *published* integrated page's DOM (inspect
  `static/aeromexico_tracker.html`, not the Python f-strings).
- ES modules under `src/views/<view>/*.js` (≤ 400 lines each, see
  `tests/test_repo_budgets.py`):
  - `shell/tabs.js`: the tab controller (click + arrow/Home/End keys,
    dispatches `reader-tab-visible` after resizing any Plotly graph the
    now-visible panel holds), ported from the inline `<script>`
    `src/analysis_agent/reader_ui.py::refine` appends.
  - `executive/{state,narrative,bootstrap}.js`: fetch
    `public/data/v1/executive.json` (records + views, shared by the
    reading *and* economy tabs, exactly like the published page's one
    `executive_summary.js` drives both) and, per period,
    `public/data/v1/analysis/<period_id>.json` — the export of
    `src/web_export/analysis.py` — to render the approved-analysis summary
    and the full-analysis dialog (`#analysis-full`, re-filled per period
    rather than one `<dialog>` per period like the published page, since
    this view fetches lazily). A period with no exported file (no
    approved analysis, or a dev build run with `--allow-missing-analysis`)
    shows the same "Análisis pendiente de aprobación" placeholder text.
  - `economy/{kpis,charts,table}.js`: the 4 KPI cards (RASK, CASK, ASK,
    Margen unitario — `load_factor_reported`/`passengers` are in the
    payload but never rendered here either, matching what
    `reader_ui.py::refine` drops from the published page), the three
    Plotly charts (unit economics, volume vs. RASK, load factor vs. RASK)
    and the by-quarter disclosure table, ported from
    `src/dashboard/assets/executive_summary.js`.
  - `flights/*.js` (unchanged from P4a): `state.js` (mutable state + lazy
    per-period fetch/cache), `dom.js` (formatting), `domestic.js`/
    `regions.js` (mode switches), `coverage.js` (route coverage dots/
    icons), `volume.js` (network volume line), `table.js` (route table +
    airport tooltip), `search.js` (airport search box), `map.js` (the
    Plotly flow map), `network.js` (mode/period orchestration), `mix.js`
    (passenger mix chart), `quarter.js` (global quarter selection),
    `bootstrap.js` (mounts the view and wires `#period-prev`/
    `#period-next` — see "Mount order" below).
  - `main.js`: mounts the tab shell, then `views/executive`, then
    `views/flights`, in that order (see "Mount order" below).
- CSS is split per view: `styles/base.css` (design tokens, page-wide
  resets, and everything shared by all three tabs — the `.page-shell`/
  `.hero`/period-stepper/`.reader-tabs` the published page's shared header
  and tab shell use), `views/executive/executive.css` (narrative card,
  analysis summary/dialog), `views/economy/economy.css` (KPI grid, chart
  cards, disclosure table) and `views/flights/flights.css` (unchanged from
  P4a, scoped under `.flights-view`).
- Plotly is vendored whole at `vendor/plotly-3.7.0.min.js` (MIT, matches
  the version the published page embeds via `plotly.offline.get_plotlyjs()`
  — see `src/analysis_agent/reader_ui.py`). The published page never uses
  ECharts or any other charting library. P5 replaces this with a partial
  Plotly bundle (`plotly.js/lib/core` + the traces these views use); see
  `docs/arquitectura/auditoria-arquitectura-20260926.md` Fase 4.

### Mount order matters for parity

The published page loads `executive_summary.js` before
`src/dashboard/assets/flights.js`; both attach their own, independent
click listener to the *same* `#period-prev`/`#period-next` buttons (there
is only one stepper in the DOM), so on every click both listeners fire,
in attachment order. `web/src/main.js` mounts `views/executive` before
`views/flights` for the same reason, so the two stay in the same relative
order the published page has. In the current, real payload both
quarter lists have the same 22 quarters in the same order, so both stay
in lockstep either way — but the *order* the listeners attach in is part
of what parity tests check, not just the end state.

### Known, accepted parity gap: citations

The published reading tab adds a superscript citation link
(`<sup><a class="source-note">`) next to some numbers in the analysis text
— see `src/analysis_agent/reader_ui.py::cite`. Building that link needs
the private evidence/calculation data from `verified_inputs()`
(excerpts, source URLs, calculation lineage), which
`src/web_export/analysis.py` never reads or exports — only
`lifecycle.consumer_payload(record)`'s already-rendered claim text. This
view shows the same text without that citation link.
`tests/test_web_page_parity.py` strips `<sup>` from both sides before
comparing prose, so it still proves the visible words match exactly.

## Entradas / salidas

- **Entradas:**
  - `public/data/v1/flights/quarters.json` (metadata, quarters, monthly
    passengers, world geometry, `available_periods`), fetched first; then
    `public/data/v1/flights/{domestic,international}/<period_id>.json` on
    demand — see `src/web_export/flights.py`.
  - `public/data/v1/executive.json` (metadata, records, views — every
    quarter, ~80 KB), fetched once — see `src/web_export/executive.py`.
  - `public/data/v1/analysis/<period_id>.json`, fetched lazily per period
    as the reading tab's period changes; a 404 means no approved analysis
    for that period — see `src/web_export/analysis.py`.
  - `public/data/` is local, not versioned (see `.gitignore`).
- **Salidas:** none; this is a read-only page.

## Ejecutar localmente

```
uv run python -m src.web_export --out web/public/data/v1
uv run python web/serve.py            # or: python -m http.server -d web
```

Then open `http://127.0.0.1:8000/`. Add `--allow-missing-analysis` to the
first command in a checkout with no local `analysis_runs/` ledger (a clean
public clone); the reading tab then shows the "pending approval" fallback
for every quarter instead of failing the export.

## Comando de prueba focalizada

```
uv run pytest -m browser -q tests/test_web_flights_smoke.py tests/test_web_page_smoke.py
uv run pytest --require-local-data -m "browser and local_data" -q tests/test_web_flights_parity.py tests/test_web_page_parity.py
```

- `test_web_flights_smoke.py` / `test_web_page_smoke.py` are `browser`
  only — they serve `web/` with the synthetic fixtures at
  `tests/fixtures/web/` and check each tab renders with no console
  errors, so they are the ones that could run in CI once `browser` is
  enabled there (currently excluded; see `REPO_MAP.md`).
- `test_web_flights_parity.py` / `test_web_page_parity.py` are also
  `local_data` (they need the real warehouse-backed payloads and, for the
  reading tab, whatever this checkout's local `analysis_runs/` ledger
  currently has approved) to compare against; they open the published
  `static/aeromexico_tracker.html` and `web/` side by side across the full
  quarter matrix and compare the visible numbers/text/chart data.

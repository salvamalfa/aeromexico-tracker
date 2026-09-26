# `web/`

Standalone, framework-free front-end for the **Vuelos** view, loading the
v1 payload split by `src/web_export/` via `fetch`. See
`docs/arquitectura/auditoria-arquitectura-20260926.md` §4.2–4.3 and Fase 3,
and `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` for the view's
history.

## Responsabilidad

- One implementation of the Vuelos panel — the same one the currently
  published `static/aeromexico_tracker.html` shows in its integrated mode —
  as real `.html`/`.js`/`.css` files instead of Python f-strings, so a
  human or an agent can edit them directly. `src/dashboard/flights_html.py`
  and `src/dashboard/assets/flights.js` still generate that published page
  unchanged; this package (P4a) does not touch them or `static/`.
- ES modules under `src/views/flights/*.js` (≤ 400 lines each, see
  `tests/test_repo_budgets.py`), split by responsibility: `state.js`
  (mutable state + lazy per-period fetch/cache), `dom.js` (formatting),
  `domestic.js`/`regions.js` (mode switches), `coverage.js` (route
  coverage dots/icons), `volume.js` (network volume line), `table.js`
  (route table + airport tooltip), `search.js` (airport search box),
  `map.js` (the Plotly flow map), `network.js` (mode/period
  orchestration), `mix.js` (passenger mix chart), `quarter.js` (global
  quarter selection).
- `index.html` copies the flights section's markup from the *published*
  integrated page (inspect `static/aeromexico_tracker.html`, not the
  Python f-strings), plus the shared period stepper the integrated page's
  executive header owns (P4b brings that view; until then this page keeps
  its own copy so Vuelos alone is fully interactive).
- CSS lives in `src/styles/base.css` (design tokens + page-wide resets,
  shared with whatever P4b adds) and `src/views/flights/flights.css`
  (everything else, scoped under a `.flights-view` root class via native
  CSS nesting — no Python CSS parser, unlike the retired
  `integrated_flights_css()`).
- Plotly is vendored whole at `vendor/plotly-3.7.0.min.js` (MIT, matches
  the version the published page embeds via `plotly.offline.get_plotlyjs()`
  — see `src/analysis_agent/reader_ui.py`). P5 replaces it with a partial
  bundle (`plotly.js/lib/core` + the four traces this view uses); see
  `docs/arquitectura/auditoria-arquitectura-20260926.md` Fase 4.

## Entradas / salidas

- **Entradas:** `public/data/v1/flights/quarters.json` (metadata, quarters,
  monthly passengers, world geometry, and the `available_periods`
  manifest — see `src/web_export/flights.py`), fetched first; then
  `public/data/v1/flights/domestic/<period_id>.json` and
  `public/data/v1/flights/international/<period_id>.json` on demand, one
  quarter/region/month selection at a time, cached in memory afterwards.
  `public/data/` is local, not versioned (see `.gitignore`).
- **Salidas:** none; this is a read-only view.

## Ejecutar localmente

```
uv run python -m src.web_export --out web/public/data/v1
uv run python web/serve.py            # or: python -m http.server -d web
```

Then open `http://127.0.0.1:8000/`.

## Comando de prueba focalizada

```
uv run pytest -m browser -q tests/test_web_flights_parity.py tests/test_web_flights_smoke.py
```

`test_web_flights_parity.py` is also `local_data` (it needs the real
warehouse-backed payload, via `flight_payload`, to compare against); it
opens both the published `static/aeromexico_tracker.html` and this view
side by side across a matrix of quarters/modes/regions/airports and
compares the visible numbers. `test_web_flights_smoke.py` is `browser`
only — it serves `web/` with the synthetic fixture at
`tests/fixtures/web/` and checks the page renders with no console errors,
so it is the one that could run in CI once `browser` is enabled there
(currently excluded; see `REPO_MAP.md`).

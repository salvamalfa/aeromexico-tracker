# `src/dashboard`

Payloads que `src/web_export`/`src/publish` consumen: la lectura ejecutiva y
Vuelos. The Streamlit multipage app and every module that rendered its own
HTML (`app.py`, `pages/`, `components/`, `theme.py`, `structure_*.py`,
`validate_stage10.py`, `validate_stage11.py`, `build_stage11.py`,
`executive_summary_html.py`, and the HTML-rendering half of
`flights_html.py`/`build_flights.py`) were retired in P7 (see
`docs/arquitectura/migracion-estado.md`); `web/` is now the only rendered
view.

## Responsabilidad

- **Lectura ejecutiva / economía unitaria:** `executive_summary.py` builds
  the payload `src/web_export/executive.py` exports and `src/publish/gate.py`
  consumes.
- **Vuelos:** `flights.py` (payload: red doméstica/internacional, capacidad,
  ocupación), `flights_html.py::integration_flight_payload` (the column
  whitelist that reaches the exported JSON — a column not added there is
  silently dropped), `domestic_routes.py`, `international_routes.py` (tablas
  de ruta por red), `build_flights.py` (rebuilds the payload and its
  candidate flight evidence after a source or Vuelos change).
- **Datos y calidad, sin UI:** `data.py` (consultas al warehouse en memoria,
  DuckDB sobre Parquet — sin Streamlit, ver `check_manual_freshness.py`
  usado por `.github/workflows/refresh.yml`), `validate_stage8.py` (los
  controles de datos del DAG en `src/pipeline/registry.py`: contratos,
  interpretaciones de métricas, anclas trimestrales, incertidumbre del
  forecast, salud de datos, frescura AFAC — sin los controles Streamlit
  `AppTest`/tema/componentes que existían antes de P7), `navigation.py`
  (`READER_TAB_SPECS`, el orden de las tres pestañas que `web/` reproduce),
  `prepare.py` (paso `dashboard.prepare` del pipeline).

Editar el generador, nunca un HTML producido. Ver `REPO_MAP.md` para el flujo
completo (payload → `src/web_export` → `src/publish/gate.py` → `site/`) y las
recetas de columna/UI.

## Entradas / salidas

- **Entradas:** `data/gold/*.parquet`, `data/warehouse.duckdb` (local).
- **Salidas:** payloads Python consumidos por `src/web_export`.

## Puntos de entrada

- `python -m src.dashboard.build_flights` — reconstruye Vuelos y su evidencia
  candidata.
- `just dashboard-validate` — corre `validate_stage8`.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py tests/test_stage11_executive_prototype.py
```

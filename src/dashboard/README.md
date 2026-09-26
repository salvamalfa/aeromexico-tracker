# `src/dashboard`

Payloads que `src/web_export`/`src/publish` consumen: la lectura ejecutiva y
Vuelos. `web/` (Vite + TypeScript) is the only rendered view; the modules
here build data payloads, never HTML.

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
  `AppTest`/tema/componentes que existían antes de P7), `prepare.py` (paso
  `dashboard.prepare` del pipeline).

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

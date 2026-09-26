# `src/dashboard`

Payloads y generadores del dashboard: la lectura ejecutiva, Vuelos, y la app
Streamlit heredada (que se retira; ver `docs/arquitectura/migracion-estado.md`,
paquete P7).

## Responsabilidad

- **Lectura ejecutiva / economía unitaria:** `executive_summary.py` (payload)
  + `executive_summary_html.py` (render); `build_stage11.py` genera el
  prototipo aislado (no reproduce el integrado, ver abajo).
- **Vuelos:** `flights.py` (payload: red doméstica/internacional, capacidad,
  ocupación), `flights_html.py` (maquetado y `integration_flight_payload`, la
  lista blanca de columnas que entran al HTML), `domestic_routes.py`,
  `international_routes.py` (tablas de ruta por red), `build_flights.py`
  (reconstruye el payload tras cambiar fuentes).
- **Estructura de datos:** `structure_metadata.py`, `structure_presentation.py`,
  `structure_html.py`, con sus validadores `validate_stage8.py`,
  `validate_stage10.py`, `validate_stage11.py`.
- **App Streamlit heredada** (`app.py`, `navigation.py`, `pages/`,
  `components/`, `data.py`, `prepare.py`, `theme.py`): sirve el HTML publicado
  vía `st.iframe`; no genera el HTML integrado.

El HTML integrado que se publica **no** sale de `build_stage11.py` solo: lo
ensambla `src/analysis_agent/stage18.py::consumer_html`. Ver `REPO_MAP.md`
para el flujo completo y las recetas de columna/UI.

## Entradas / salidas

- **Entradas:** `data/gold/*.parquet`, `data/warehouse.duckdb` (local).
- **Salidas:** payloads Python consumidos por `stage18.py`; prototipos HTML en
  `prototypes/` para revisión.

## Puntos de entrada

- `python -m src.dashboard.build_flights` — reconstruye Vuelos.
- `just dashboard` — Streamlit local (heredado).
- `just dashboard-validate` — controles de Etapa 8/10.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py tests/test_stage11_executive_prototype.py
```

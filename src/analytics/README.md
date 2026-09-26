# `src/analytics`

Estudios y modelos precomputados sobre Gold: forecast, anomalías, clustering,
NLP y la estimación de pasajeros por ruta y aerolínea.

## Responsabilidad

- Forecast SARIMA/naive estacional (`forecast.py`), anomalías (`anomalies.py`),
  clustering (`clustering.py`), reportes NLP (`nlp_reports.py`), EDA
  (`eda.py`), generación de notebooks (`build_notebook.py`).
- Estimación de pasajeros ruta×aerolínea por ajuste proporcional iterativo
  (`route_carrier.py`, `route_carrier_backtest.py`,
  `international_route_carrier.py`) — método documentado en
  `docs/estimacion-pasajeros-ruta-aerolinea.md`.
- Capacidad y consolidación internacional (`international_capacity.py`,
  `international_gold.py`, `international_review.py`).
- Todo output de un modelo se declara como estimación y conserva versión,
  insumos, diagnósticos e incertidumbre (ver `AGENTS.md`).

## Entradas / salidas

- **Entradas:** `data/gold/*.parquet`, `data/warehouse.duckdb` (local).
- **Salidas:** `src/dashboard/` payloads los consumen directamente; algunos
  estudios escriben a `data/analytics/` (local, no versionado).

## Puntos de entrada

- `python -m src.analytics` (`__main__.py` → `main()`).
- Módulos individuales por estudio, p. ej.
  `uv run python -m src.analytics.route_carrier`.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_route_carrier_ipf.py tests/test_international_route_carrier.py
```

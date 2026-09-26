# `src/transform`

Construye las tablas Gold públicas y versionadas a partir de Silver,
resolviendo dimensiones compartidas, historia tipo 2 (SCD2) y contratos.

## Responsabilidad

- Tablas maestras y de hechos (`stage6*.py`: `stage6_dimensions.py`,
  `stage6_facts.py`, `stage6_contracts.py`, `stage6_warehouse.py`).
- Linaje y contratos de Silver (`stage9.py`, `stage9_lineage.py`,
  `silver_contracts.py`).
- Reglas específicas de red doméstica/internacional (`domestic_slots.py`,
  `international_routes.py`, `afac_exclusive_domestic.py`,
  `aicm_international_slots.py`, `aifa_shared_presence.py`,
  `oma_documented_routes.py`).
- Generación del diccionario de datos (`generate_data_dictionary.py`, alimenta
  `docs/diccionario-datos.md`).

## Entradas / salidas

- **Entradas:** `data/silver/` (local).
- **Salidas:** `data/gold/*.parquet` (versionado en git, 43 tablas actuales;
  ver `docs/diccionario-datos.md`) y `data/warehouse.duckdb` (local,
  regenerable).

## Puntos de entrada

- `python -m src.transform` (`__main__.py` → `run()`), o `just transform`.
- `just rebuild` reconstruye todo el pipeline offline desde bronze.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_stage6.py tests/test_international_routes.py tests/test_aicm_international_slots.py -m "not local_data"
```

# `src/common`

Utilidades compartidas por todo el pipeline: almacenamiento inmutable, red,
logging y el ledger de calidad de datos.

## Responsabilidad

- `storage.py`: almacenamiento inmutable de bronze con hashes SHA-256,
  metadata y linaje de restatements (`_manifest.jsonl`, `_restatements.jsonl`).
- `quality.py`: ledger de incidencias de calidad de datos, de solo apéndice.
- `http.py`: cliente HTTP compartido (reintentos, user-agent, límites).
- `logging.py`: configuración de logging común al pipeline.

## Entradas / salidas

- **Entradas:** ninguna propia; recibe llamadas de `ingest/`, `parse/`,
  `transform/` y `pipeline/`.
- **Salidas:** escribe bajo `data/bronze/` (manifiesto/restatements) y
  `data/quality/` (local), según el módulo que lo invoque.

## Puntos de entrada

Biblioteca, sin CLI propio. Se importa como `from src.common import storage`,
`from src.common import quality`, etc.

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_storage.py tests/test_quality.py tests/test_http.py tests/test_logging.py
```

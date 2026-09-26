# `src/ingest`

Descarga fuentes públicas (y, cuando aplica, pagadas bajo cuota) tal como las
entrega el proveedor, con hash y metadata, sin transformarlas.

## Responsabilidad

- Ejecutar las ingestas registradas: SEC EDGAR, BMV XBRL, AFAC, BTS T-100,
  AeroDataBox, macro (Banxico/EIA), mercado, noticias/NLP, pares, aeropuertos,
  regulatorio (`aerodatabox/`, `afac/`, `airports/`, `bmv/`, `bts/`, `macro/`,
  `market/`, `news/`, `nlp/`, `peers/`, `regulatory/`, `sec/`).
- Registrar cada descarga en el manifiesto de bronze con su hash SHA-256 y
  detectar restatements (contenido que cambió bajo la misma URL).

## Entradas / salidas

- **Entradas:** red (fuentes públicas o con API key en el entorno) o
  respuestas ya guardadas para reanudación.
- **Salidas:** `data/bronze/` (local, no versionado salvo `_manifest.jsonl` y
  `_restatements.jsonl`, que sí se versionan).

## Puntos de entrada

- `python -m src.ingest` (`__main__.py` → `run()`) ejecuta las ingestas
  registradas en `src/pipeline/`.
- Los módulos por proveedor (p. ej. `sec/discover.py`,
  `aerodatabox/international.py`) también se invocan individualmente para
  depuración; ver sus propios `if __name__ == "__main__"`.
- Comandos con red, cuota o costo requieren `--dry-run` antes de ejecutarse en
  serio (ver `AGENTS.md`).

## Comando de prueba focalizada

```bash
uv run pytest -q tests/test_sec_discover.py tests/test_afac_monthly_stats.py tests/test_aerodatabox_international.py
```

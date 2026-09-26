# `src/web_export`

Exportadores que dividen los payloads v1 (`contracts/web/`) en archivos por
periodo, para que el futuro front-end (P4/P5) los cargue con `fetch` en vez
de recibirlos embebidos en el HTML. Ver
`docs/arquitectura/auditoria-arquitectura-20260926.md` Fase 2.

## Responsabilidad

- No genera datos nuevos: llama a `src.dashboard.flights.build_flight_payload()`
  y `src.dashboard.executive_summary.build_executive_payload()` (los mismos
  generadores que ya usa `stage18`), y a
  `src.dashboard.flights_html.integration_flight_payload()` para quedarse con
  exactamente lo que hoy se embebe en el HTML publicado.
- Antes de escribir cada archivo: lo valida contra su esquema en
  `contracts/web/*.schema.json` y contra `contracts/web/privacy.yaml`
  (`src/web_export/privacy.py`).
- Antes de exportar una vista, exige sus insumos Gold declarados como
  requeridos en `config/web_inputs.yaml` (`src/web_export/inputs.py`); si
  falta uno, falla con un mensaje que nombra el archivo exacto y cómo
  restaurarlo desde el repo privado. Nunca omite una sección en silencio.
- Escribe JSON determinista (`sort_keys=True`, separadores compactos, sin
  `NaN`): dos ejecuciones sobre el mismo warehouse producen bytes idénticos.

**No publica nada.** No toca `stage18`, ni las aprobaciones del Analysis
Agent, ni `static/aeromexico_tracker.html`. Este paquete (P3) solo prueba que
la división es equivalente al payload que ya se publica; el HTML publicado
sigue viniendo de `stage18.consumer_html` sin cambios.

## Entradas / salidas

- **Entradas:** `data/warehouse.duckdb` (local) vía los generadores de
  `src/dashboard/`; `contracts/web/*.schema.json`, `contracts/web/privacy.yaml`,
  `config/web_inputs.yaml`.
- **Salidas:** `<out>/flights/quarters.json`,
  `<out>/flights/domestic/<period_id>.json`,
  `<out>/flights/international/<period_id>.json`, `<out>/executive.json`.
  `<out>` es local (no versionado; ver `.gitignore` para `web/public/data/`).

## Punto de entrada

```
uv run python -m src.web_export --out web/public/data/v1
```

Imprime cada archivo escrito con su tamaño y falla (código de salida 1) con
un mensaje legible si falta un insumo requerido.

## Comando de prueba focalizada

```
uv run pytest -q tests/test_web_export.py
```

Incluye una prueba de equivalencia (`local_data`): recombinar los archivos
divididos reproduce, campo a campo, el payload que hoy se embebe en el HTML
integrado.

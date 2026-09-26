# `src/web_export`

Exportadores que dividen los payloads v1 (`contracts/web/`) en archivos por
periodo, para que el futuro front-end (P4/P5) los cargue con `fetch` en vez
de recibirlos embebidos en el HTML. Ver
`docs/arquitectura/auditoria-arquitectura-20260926.md` Fase 2.

## Responsabilidad

- No genera datos nuevos: llama a `src.dashboard.flights.build_flight_payload()`
  y `src.dashboard.executive_summary.build_executive_payload()`, y a
  `src.dashboard.flights_html.integration_flight_payload()` para quedarse con
  exactamente lo que `web/` consume.
- Antes de escribir cada archivo: lo valida contra su esquema en
  `contracts/web/*.schema.json` y contra `contracts/web/privacy.yaml`
  (`src/web_export/privacy.py`).
- Antes de exportar una vista, exige sus insumos Gold declarados como
  requeridos en `config/web_inputs.yaml` (`src/web_export/inputs.py`); si
  falta uno, falla con un mensaje que nombra el archivo exacto y cómo
  restaurarlo desde el repo privado. Nunca omite una sección en silencio.
- Escribe JSON determinista (`sort_keys=True`, separadores compactos, sin
  `NaN`): dos ejecuciones sobre el mismo warehouse producen bytes idénticos.
- `analysis.py` es distinto de los otros dos: no llama a un generador de
  `src/dashboard/`, sino que descubre qué periodos el ledger local tiene
  actualmente aprobados o publicados (`discover_approved_manifest`, P7 —
  antes leía el `#analysis-manifest` de la página Streamlit publicada,
  retirada; ver `docs/arquitectura/migracion-estado.md`), carga el registro
  correspondiente en `analysis_runs/drafts/` y llama a
  `src.analysis_agent.lifecycle.consumer_payload(record)` — el mismo paso
  de entrega fail-closed que usaba el retirado `stage18`, en modo solo
  lectura. También llama a `flow.verified_inputs(record)` (mismo llamado
  fail-closed) para construir, por afirmación, el `citations` que exporta —
  un port de lo que hacía `src.analysis_agent.reader_ui.py::cite()` (también
  retirado), que solo emite lo que `cite()` ya ponía en la página pública
  (URL de la fuente, texto del tooltip, subcadena a envolver); nunca un
  objeto de evidencia/cálculo ni linaje. Nunca escribe en el ledger ni
  aprueba/revoca nada. Si el registro o el ledger no están (clon público
  sin `analysis_runs/`), el manifiesto descubierto queda vacío o, con
  `--allow-missing-analysis` (solo para desarrollo), salta ese periodo en
  vez de fallar todo el export.

**No publica nada.** No toca las aprobaciones del Analysis Agent. `web/` es
la única implementación de cada vista desde P7; `src/publish/gate.py` es
quien compila `web/` y ensambla `site/` a partir de lo que este paquete
exporta.

## Entradas / salidas

- **Entradas:** `data/warehouse.duckdb` (local) vía los generadores de
  `src/dashboard/`; `contracts/web/*.schema.json`, `contracts/web/privacy.yaml`,
  `config/web_inputs.yaml`; para `analysis.py`, además `analysis_runs/`
  (local, no versionado).
- **Salidas:** `<out>/flights/quarters.json`,
  `<out>/flights/domestic/<period_id>.json`,
  `<out>/flights/international/<period_id>.json`, `<out>/executive.json`,
  `<out>/analysis/<period_id>.json`.
  `<out>` es local (no versionado; ver `.gitignore` para `web/public/data/`).

## Punto de entrada

```
uv run python -m src.web_export --out web/public/data/v1 [--allow-missing-analysis]
```

Imprime cada archivo escrito con su tamaño y falla (código de salida 1) con
un mensaje legible si falta un insumo requerido (Gold o, para `analysis.py`,
el expediente/ledger local — salvo `--allow-missing-analysis`).

## Comando de prueba focalizada

```
uv run pytest -q tests/test_web_export.py
```

Incluye una prueba de equivalencia (`local_data`): recombinar los archivos
divididos reproduce, campo a campo, el payload que hoy se embebe en el HTML
integrado.

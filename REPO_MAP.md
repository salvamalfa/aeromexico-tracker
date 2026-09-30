# Mapa del repositorio

Qué vive dónde, comandos clave y recetas paso a paso para los cambios más
comunes. Ver también `CLAUDE.md`, `AGENTS.md`, `CHANGELOG.md` y `ROADMAP.md`.

## Qué vive dónde

| Área | Módulos | Rol |
|---|---|---|
| Ingesta | `src/ingest/` | Descarga fuentes públicas (SEC, BMV, AFAC, T-100, AeroDataBox…) a `data/bronze/` (local, con hash). |
| Parseo | `src/parse/` | Normaliza bronze a `data/silver/` (local), fiel a cada fuente. |
| Transformación | `src/transform/` | Construye `data/gold/` (43 Parquet versionados, extractos públicos) desde silver. |
| Analítica | `src/analytics/` | Estudios y modelos precomputados sobre gold (forecast, estimación ruta×aerolínea, etc.). |
| Dashboard | `src/dashboard/` | Payloads que `src/web_export`/`src/publish` consumen: lectura ejecutiva (`executive_summary.py`), Vuelos (`flights.py`, `flights_html.py::integration_flight_payload` — la lista blanca de columnas, `domestic_routes.py`, `international_routes.py`), más `data.py`/`check_manual_freshness.py`/`validate_stage8.py` (consultas al warehouse y controles de calidad de datos, sin UI). `web/` es la única vista publicada. |
| Analysis Agent | `src/analysis_agent/` | Evidencia, cálculo, revisión y **publicación controlada** del análisis narrativo por trimestre (etapas 12–17). |
| Contratos web | `contracts/web/` | Esquemas JSON (draft 2020-12) del payload **v1** tal cual lo consume `web/` (Vuelos, ejecutivo y análisis) + `privacy.yaml` (frontera pública/privada). Fuente de verdad; no aspiracional. |
| Exportadores web | `src/web_export/` | Divide esos mismos payloads en JSON por periodo bajo `web/public/data/v1/` (local, no versionado), validados contra `contracts/web/` y `config/web_inputs.yaml` antes de escribir. `flights/quarters.json` incluye además `available_periods`: el manifiesto de qué archivos por periodo existen, para que `web/` sepa qué pedir con `fetch()` sin listar el directorio. `analysis.py` exporta, para cada periodo que el ledger local (`analysis_runs/`) tiene actualmente aprobado o publicado (`discover_approved_manifest`), exactamente lo que `analysis_agent.lifecycle.consumer_payload(record)` autoriza — lectura del flujo de aprobación existente, nunca escritura; falla si falta el expediente local salvo `--allow-missing-analysis` (dev). |
| Gate de publicación (`site/`) | `src/publish/` | El único objeto firmado y publicado: dado uno o más registros de `analysis_runs/drafts/` ya aprobados, re-verifica cada uno con las funciones de `lifecycle.py`, exporta el payload v1 (Vuelos/ejecutivo completos, análisis solo de los periodos dados), compila `web/` con Vite y ensambla+firma `site/` (`publication_manifest.json`: commit, hash de cada contrato, SHA-256/tamaño de cada archivo, entradas del `analysis-manifest`). `src/publish/verify.py` revisa ese manifiesto sin datos privados (lo ejecuta `.github/workflows/pages.yml` antes de desplegar). Recibo intent/published en `analysis_runs/publications/` (local). Ver `src/publish/README.md` y §4.2 punto 5/Fase 5 de la auditoría. |
| Front-end en archivos reales | `web/` | La página completa (Vite + TypeScript), **única** implementación publicada de las tres vistas (Lectura ejecutiva, Economía unitaria, Vuelos): HTML/CSS/TS reales (ES modules, `web/src/views/{flights,executive,economy,shell}/*.ts`, ≤ 400 líneas cada uno; tipos generados en `web/src/types/generated/` desde `contracts/web/*.schema.json` vía `npm run gen:types`) que consume `web/public/data/v1/` con `fetch()`. Plotly se importa parcial (`plotly.js/lib/core` + `bar`/`scatter`/`scattergeo`/`choropleth`, ver `web/src/lib/plotly.ts`). Ver `web/README.md`. |
| Pruebas | `tests/` | `uv run pytest`; marcadores `local_data` (necesita `data/bronze|silver`/warehouse local) y `browser` (Playwright) se excluyen en CI. |

**Gold tables:** 43 Parquet en `data/gold/` versionados en git (ver
`docs/diccionario-datos.md`). Cuatro estimaciones adicionales
(`fact_route_carrier_*_estimate.parquet`, `fact_aeromexico_*_capacity_estimate.parquet`)
son locales y regenerables, no versionadas.

**Dashboard/Vuelos:** `web/` es la única vista publicada (ver arriba). Sus
datos vienen de `src/dashboard/executive_summary.py::build_executive_payload()`
y `src/dashboard/flights.py::build_flight_payload()` +
`src/dashboard/flights_html.py::integration_flight_payload()` (lista blanca de
columnas: una columna nueva que no esté ahí se descarta en silencio), exportados
por `src/web_export/` y ensamblados por `src/publish/gate.py`. Editar el
generador (los módulos de `src/dashboard/` o `web/src/views/`), nunca un HTML
generado.

**Gate de publicación (`src/publish`):** dado uno o más registros ya
aprobados, `gate.py` re-verifica cada uno contra el ledger de aprobación
(`src/analysis_agent/lifecycle.py`, `analysis_runs/` local) antes de exportar,
compilar `web/` y ensamblar+firmar `site/` (manifiesto SHA-256, recibo
`.published.json`). La autorización permanente de `AGENTS.md` permite ejecutar
el gate para publicar cambios rutinarios solicitados sobre datos ya aprobados.
Nunca cambies un registro de aprobación sin autorización específica del dueño.

**Publicación en GitHub Pages (`site/`):** `site/` es el sitio ya
ensamblado y firmado que `.github/workflows/pages.yml` despliega tal cual —
en `master`, sin secretos ni reconstrucción de datos — a
<https://salvamalfa.github.io/aeromexico-tracker/>. Si el cambio solicitado
afecta al dashboard público, regenera `site/`, inclúyelo en el PR y sigue el
deploy de Pages conforme a `AGENTS.md`, sin pedir permiso adicional para una
publicación rutinaria:

```
uv run python -m src.publish --record analysis_runs/drafts/<periodo>/<version>.json --out site/
uv run python -m src.publish.verify site/
```

**Vista previa en `/v2/`.** `.github/pages-preview.json` puede fijar el commit
de una rama sin fusionar cuyo `site/` ya firmado se sirve en
`…/aeromexico-tracker/<path>/`, junto al sitio de `master`, que sigue en la raíz.
`pages.yml` verifica ese `site/` con el verificador y los contratos de su propio
commit, y si falla no despliega nada. Para actualizarla o retirarla, hace falta
un PR a `master` que cambie el commit fijado o borre el archivo. Ver
`docs/etapas/pages-preview-v2-20260930.md`.

**Repo de datos privado:** insumos regenerables y privados
(`data/bronze`, `data/silver`, warehouse, `analysis_runs/`) tienen respaldo en
[`salvamalfa/aeromexico-tracker-data`](https://github.com/salvamalfa/aeromexico-tracker-data)
(privado, Git LFS). Acceso al código público no implica acceso a esos datos ni
autorización para publicarlos. Ver "Datos y documentación" en `README.md`.

## Comandos clave

| Comando | Qué hace |
|---|---|
| `uv run pytest -m "not local_data and not browser" -q` | Suite pública/CI (sin datos locales ni navegador). Conteo actual: ver salida del comando, no lo copies aquí. |
| `just test` / `uv run pytest` | Suite completa local (necesita `data/bronze`/`silver`/warehouse). |
| `just rebuild` | Reconstrucción completa offline desde bronze. |
| `python -m src.dashboard.build_flights` | Reconstruye el payload de Vuelos y su evidencia candidata tras cambiar fuentes o Vuelos. |
| `uv run python -m src.web_export --out web/public/data/v1` | Exporta los payloads v1 divididos por periodo bajo `web/public/data/v1/` (local, gitignored, no publica nada; falla con mensaje claro si falta un insumo Gold o el expediente de análisis, salvo `--allow-missing-analysis`). Vite (`npm run dev`/`build`) copia el contenido de `web/public/` a la raíz del sitio servido/`dist/` (convención de Vite: `web/public/data/v1/x.json` queda accesible en `data/v1/x.json`, no en `public/data/v1/x.json`; ver `web/src/views/{flights,executive}/state.ts`). |
| `cd web && npm ci` | Instala node_modules desde `web/package-lock.json` (versiones fijas; Node 22 + npm 10). |
| `cd web && npm run dev` | Sirve `web/` con el servidor de desarrollo de Vite (recarga en caliente) en `http://127.0.0.1:5173/`; necesita los datos exportados arriba primero. |
| `cd web && npm run build` | Compila el sitio a `web/dist/` (determinista: dos builds seguidos producen los mismos hashes de archivo). |
| `cd web && npm run preview` | Sirve `web/dist/` (el build) para revisión antes de publicar. |
| `cd web && npm run check` | `tsc --noEmit`: chequeo de tipos estricto sin emitir archivos. |
| `cd web && npm run test` | `vitest run`: pruebas unitarias de funciones puras (formato, agregación, clasificación de región…) y la prueba de tipos generados al día. |
| `cd web && npm run gen:types` | Regenera `web/src/types/generated/*.ts` desde `contracts/web/*.schema.json`; ejecútalo tras editar un esquema. |
| `uv run python -m src.publish --record … --out site/` | Publica `site/` (verifica el registro ya aprobado, exporta v1, compila `web/`, ensambla y firma). Autorizado para cambios rutinarios solicitados según `AGENTS.md`. |
| `uv run python -m src.publish.verify site/` | Revisa `site/` contra su manifiesto, los esquemas y `privacy.yaml` — sin datos privados; lo mismo que corre `.github/workflows/pages.yml` antes de desplegar. |

## Recetas

### a) Mover o agregar un elemento de UI en Vuelos

Nada de esto genera HTML: `src/dashboard/` y `src/web_export/` son
constructores de payloads JSON; el único maquetado/interacción vive en
`web/src/views/`.

1. Lee `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` (traspaso canónico de Vuelos).
2. Edita el payload en `src/dashboard/flights.py` (datos) y/o la lista blanca en
   `src/dashboard/flights_html.py::integration_flight_payload` (qué campos
   llegan al JSON exportado vía `src/web_export/flights.py`).
3. Si el campo es nuevo, agrégalo al contrato en `contracts/web/flights.schema.json`.
4. Edita el maquetado/interacción en `web/src/views/flights/*.ts` (la única
   implementación de la vista).
5. Regenera: `python -m src.dashboard.build_flights`, luego
   `uv run python -m src.web_export --out web/public/data/v1`.
6. Corre `uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py`
   y, en `web/`, `npm run check && npm run test`.
7. Si el cambio debe verse en Pages y usa datos ya aprobados, ejecuta
   `python -m src.publish`, verifica `site/`, incluye el artefacto en el PR y
   sigue el deploy y la comprobación pública (ver `AGENTS.md`).

### b) Agregar una columna a la tabla de rutas

Igual que en (a): `src/dashboard/*_routes.py` y `flights_html.py` construyen
un payload JSON, no HTML/CSS; el maquetado vive solo en `web/src/views/flights/table.ts`.

1. Añade la columna en `src/dashboard/domestic_routes.py` y/o
   `src/dashboard/international_routes.py` (donde se construyen las filas).
2. Agrégala a la lista blanca en
   `src/dashboard/flights_html.py::integration_flight_payload` — si se omite
   este paso, la columna se descarta en silencio sin error.
3. Añade la columna al contrato público en `contracts/web/flights.schema.json`
   (si no está ahí, `uv run python -m src.web_export` la rechaza en la
   validación de esquema) y a `docs/diccionario-datos.md`.
4. Agrega la columna a la tabla renderizada en `web/src/views/flights/table.ts`
   (o al módulo de `web/src/views/flights/` que corresponda a esa columna).
5. Regenera: `python -m src.dashboard.build_flights`, luego
   `uv run python -m src.web_export --out web/public/data/v1`.
6. Corre `uv run pytest -q tests/test_international_routes.py tests/test_aicm_international_slots.py`
   y, en `web/`, `npm run check && npm run test`.

### c) Agregar un nuevo mes de datos

Sigue `docs/etapas/aerodatabox-agosto-captura-20260925.md` paso a paso
(flujo privado AeroDataBox → repo de datos → `data/gold/` → warehouse →
Vuelos → publicación). Ese documento es la referencia operativa; no la
dupliques aquí.

### d) Retomar trabajo pendiente

El trabajo abierto vive en `ROADMAP.md` ("Ahora"/"Siguiente"). Un paquete de
varios pasos delegado por la sesión coordinadora lo ejecuta el subagente
`implementador` (`.claude/agents/implementador.md`), en su propia rama,
commiteando y subiendo tras cada tarea. La historia de proyectos cerrados vive
en `docs/archivo/` y no se retoma.

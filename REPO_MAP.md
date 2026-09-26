# Mapa del repositorio

Qué vive dónde, comandos clave y recetas paso a paso para los cambios más
comunes. Ver también `CLAUDE.md`, `AGENTS.md` y, para la migración en curso,
`docs/arquitectura/migracion-estado.md`.

## Qué vive dónde

| Área | Módulos | Rol |
|---|---|---|
| Ingesta | `src/ingest/` | Descarga fuentes públicas (SEC, BMV, AFAC, T-100, AeroDataBox…) a `data/bronze/` (local, con hash). |
| Parseo | `src/parse/` | Normaliza bronze a `data/silver/` (local), fiel a cada fuente. |
| Transformación | `src/transform/` | Construye `data/gold/` (43 Parquet versionados, extractos públicos) desde silver. |
| Analítica | `src/analytics/` | Estudios y modelos precomputados sobre gold (forecast, estimación ruta×aerolínea, etc.). |
| Dashboard | `src/dashboard/` | Payloads que `src/web_export`/`src/publish` consumen: lectura ejecutiva (`executive_summary.py`), Vuelos (`flights.py`, `flights_html.py::integration_flight_payload` — la lista blanca de columnas, `domestic_routes.py`, `international_routes.py`), más `data.py`/`check_manual_freshness.py`/`validate_stage8.py` (consultas al warehouse y controles de calidad de datos, sin UI). La app Streamlit heredada y todo generador de HTML propio se retiraron en P7 (ver `docs/arquitectura/migracion-estado.md`); `web/` es la única vista. |
| Analysis Agent | `src/analysis_agent/` | Evidencia, cálculo, revisión y **publicación controlada** del análisis narrativo por trimestre (etapas 12–17; el consumidor HTML de la etapa 18, `stage18.py`/`reader_ui.py`, se retiró en P7 junto con la ruta que consumía). |
| Contratos web | `contracts/web/` | Esquemas JSON (draft 2020-12) del payload **v1** tal cual lo consume `web/` (Vuelos, ejecutivo y análisis) + `privacy.yaml` (frontera pública/privada). Fuente de verdad; no aspiracional. |
| Exportadores web | `src/web_export/` | Divide esos mismos payloads en JSON por periodo bajo `web/public/data/v1/` (local, no versionado), validados contra `contracts/web/` y `config/web_inputs.yaml` antes de escribir. `flights/quarters.json` incluye además `available_periods` (P4a): el manifiesto de qué archivos por periodo existen, para que `web/` sepa qué pedir con `fetch()` sin listar el directorio. `analysis.py` exporta, para cada periodo que el ledger local (`analysis_runs/`) tiene actualmente aprobado o publicado (`discover_approved_manifest`, P7 — antes leía el `#analysis-manifest` del HTML publicado, retirado), exactamente lo que `analysis_agent.lifecycle.consumer_payload(record)` autoriza — lectura del flujo de aprobación existente, nunca escritura; falla si falta el expediente local salvo `--allow-missing-analysis` (dev). |
| Gate de publicación (`site/`) | `src/publish/` | El único objeto firmado y publicado: dado uno o más registros de `analysis_runs/drafts/` ya aprobados, re-verifica cada uno con las funciones de `lifecycle.py`, exporta el payload v1 (Vuelos/ejecutivo completos, análisis solo de los periodos dados), compila `web/` con Vite y ensambla+firma `site/` (`publication_manifest.json`: commit, hash de cada contrato, SHA-256/tamaño de cada archivo, entradas del `analysis-manifest`). `src/publish/verify.py` revisa ese manifiesto sin datos privados (lo ejecuta `.github/workflows/pages.yml` antes de desplegar). Recibo intent/published en `analysis_runs/publications/` (local). Ver `src/publish/README.md` y §4.2 punto 5/Fase 5 de la auditoría. |
| Front-end en archivos reales | `web/` | La página completa (Vite + TypeScript desde P5), y desde P7 la **única** implementación publicada de las tres vistas (Lectura ejecutiva, Economía unitaria, Vuelos): HTML/CSS/TS reales (ES modules, `web/src/views/{flights,executive,economy,shell}/*.ts`, ≤ 400 líneas cada uno; tipos generados en `web/src/types/generated/` desde `contracts/web/*.schema.json` vía `npm run gen:types`) que consume `web/public/data/v1/` con `fetch()`. Plotly se importa parcial (`plotly.js/lib/core` + `bar`/`scatter`/`scattergeo`/`choropleth`, ver `web/src/lib/plotly.ts`). Ver `web/README.md`. |
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
`.published.json`). Nunca lo ejecutes de verdad ni cambies un registro de
aprobación salvo instrucción explícita del dueño.

**Publicación en GitHub Pages (`site/`, P6b):** `site/` es el sitio ya
ensamblado y firmado que `.github/workflows/pages.yml` despliega tal cual —
en `master`, sin secretos ni reconstrucción de datos — a
<https://salvamalfa.github.io/aeromexico-tracker/>. Publicar una nueva
versión de `site/` requiere **instrucción explícita del dueño**; no lo
ejecutes por iniciativa propia:

```
uv run python -m src.publish --record analysis_runs/drafts/<periodo>/<version>.json --out site/
uv run python -m src.publish.verify site/
```

**Streamlit y la ruta HTML heredada (retirados en P7):** hasta el commit
`e645d3e` de `master`, el dashboard también se servía como un único archivo
HTML (`src/analysis_agent/stage18.py::consumer_html` + `reader_ui.py`,
`src/dashboard/flights_html.py`/`executive_summary_html.py`, la app
Streamlit multipágina en `src/dashboard/{app,pages,components,theme,
structure_*,validate_stage10,validate_stage11,build_stage11}.py` y su copia
servida `static/aeromexico_tracker.html`). P7 (`docs/arquitectura/
migracion-estado.md`, `docs/etapas/migracion-p7-retiro-streamlit-20260926.md`)
retiró todo eso: `web/` es la única implementación de cada vista y `site/`
la única ruta de publicación. `e645d3e` queda como punto de archivo; el
dueño todavía debe borrar manualmente la app en share.streamlit.io.

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
| `uv run python -m src.publish --record … --out site/` | Publica `site/` (verifica el registro, exporta v1, compila `web/`, ensambla y firma). **Requiere instrucción explícita del dueño**; no lo ejecutes por iniciativa propia. |
| `uv run python -m src.publish.verify site/` | Revisa `site/` contra su manifiesto, los esquemas y `privacy.yaml` — sin datos privados; lo mismo que corre `.github/workflows/pages.yml` antes de desplegar. |

## Recetas

### a) Mover o agregar un elemento de UI en Vuelos

1. Lee `docs/etapas/vuelos-pasajeros-traspaso-20260913.md` (traspaso canónico de Vuelos).
2. Edita el payload en `src/dashboard/flights.py` (datos) y/o la lista blanca en
   `src/dashboard/flights_html.py::integration_flight_payload` (qué campos
   llegan al JSON exportado).
3. Edita el maquetado/interacción en `web/src/views/flights/*.ts` (la única
   vista publicada desde P7).
4. Regenera: `python -m src.dashboard.build_flights`, luego
   `uv run python -m src.web_export --out web/public/data/v1`.
5. Corre `uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py`
   y, en `web/`, `npm run check && npm run test`.
6. Si el cambio debe publicarse, pide instrucción explícita del dueño para
   `python -m src.publish` (ver arriba).

### b) Agregar una columna a la tabla de rutas

1. Añade la columna en `src/dashboard/domestic_routes.py` y/o
   `src/dashboard/international_routes.py` (donde se construyen las filas).
2. Agrégala a la lista blanca en
   `src/dashboard/flights_html.py::integration_flight_payload` — si se omite
   este paso, la columna se descarta en silencio sin error.
3. Actualiza el maquetado/estilos en `flights_html.py` (HTML) y las reglas de
   `src/dashboard/flights.py` si hay CSS embebido en el mismo módulo.
4. Regenera: `python -m src.dashboard.build_flights`.
5. Corre `uv run pytest -q tests/test_international_routes.py tests/test_aicm_international_slots.py`.
6. Actualiza `docs/diccionario-datos.md` si la columna es nueva en el
   contrato de datos.

### c) Agregar un nuevo mes de datos

Sigue `docs/etapas/aerodatabox-agosto-captura-20260925.md` paso a paso
(flujo privado AeroDataBox → repo de datos → `data/gold/` → warehouse →
Vuelos → publicación). Ese documento es la referencia operativa; no la
dupliques aquí.

### d) Retomar la migración de arquitectura

1. Lee `docs/arquitectura/migracion-estado.md` — la tabla de paquetes indica
   el primer no fusionado.
2. Lee `docs/arquitectura/auditoria-arquitectura-20260926.md` §4–§5 para el
   alcance exacto de ese paquete.
3. Si tiene rama/PR abierto, continúa desde su último commit; si no, créala
   desde `master`.
4. Ejecuta el trabajo con el subagente `migrador` (`.claude/agents/migrador.md`).
5. Verifica los criterios de salida del paquete (pruebas, comandos listados
   en la fila de la tabla).
6. Actualiza `docs/arquitectura/migracion-estado.md` (tabla + bitácora) en el
   mismo commit final del paquete.

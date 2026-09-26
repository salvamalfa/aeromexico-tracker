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
| Dashboard | `src/dashboard/` | Payloads y generadores HTML: lectura ejecutiva (`executive_summary*.py`), Vuelos (`flights.py`, `flights_html.py`, `domestic_routes.py`, `international_routes.py`), la app Streamlit heredada (`app.py`, `pages/`, `components/`, `data.py`, `navigation.py`). |
| Analysis Agent | `src/analysis_agent/` | Evidencia, cálculo, revisión y **publicación controlada** del análisis narrativo por trimestre (etapas 12–18). |
| Contratos web | `contracts/web/` | Esquemas JSON (draft 2020-12) del payload **v1** tal cual se embebe hoy en el HTML publicado (Vuelos, ejecutivo y análisis) + `privacy.yaml` (frontera pública/privada). Fuente de verdad; no aspiracional. |
| Exportadores web | `src/web_export/` | Divide esos mismos payloads en JSON por periodo bajo `web/public/data/v1/` (local, no versionado), validados contra `contracts/web/` y `config/web_inputs.yaml` antes de escribir. No publica ni toca `stage18`; el HTML publicado sigue viniendo de ahí sin cambios (fase 2 de la migración). `flights/quarters.json` incluye además `available_periods` (P4a): el manifiesto de qué archivos por periodo existen, para que `web/` sepa qué pedir con `fetch()` sin listar el directorio. `analysis.py` (P4b) exporta, por periodo listado en el `#analysis-manifest` del HTML publicado, exactamente lo que `analysis_agent.lifecycle.consumer_payload(record)` autoriza — lectura del flujo de aprobación existente, nunca escritura; falla si falta el expediente local salvo `--allow-missing-analysis` (dev). |
| Gate de publicación (`site/`) | `src/publish/` | Reemplaza a `stage18` como el objeto firmado: dado uno o más registros de `analysis_runs/drafts/` ya aprobados, re-verifica cada uno con las mismas funciones de `lifecycle.py` que usa `stage18`, exporta el payload v1 (Vuelos/ejecutivo completos, análisis solo de los periodos dados), compila `web/` con Vite y ensambla+firma `site/` (`publication_manifest.json`: commit, hash de cada contrato, SHA-256/tamaño de cada archivo, entradas del `analysis-manifest`). `src/publish/verify.py` revisa ese manifiesto sin datos privados (lo ejecuta `.github/workflows/pages.yml` antes de desplegar). Recibo intent/published en `analysis_runs/publications/` (local). Ver `src/publish/README.md` y §4.2 punto 5/Fase 5 de la auditoría. |
| Front-end en archivos reales | `web/` | La página completa (Vite + TypeScript desde P5) como HTML/CSS/TS reales (ES modules, `web/src/views/{flights,executive,economy,shell}/*.ts`, ≤ 400 líneas cada uno; tipos generados en `web/src/types/generated/` desde `contracts/web/*.schema.json` vía `npm run gen:types`) que consume `web/public/data/v1/` con `fetch()`: cabecera + selector de trimestre compartidos, y las tres pestañas del HTML integrado publicado (Lectura ejecutiva, Economía unitaria, Vuelos — P4a trajo Vuelos, P4b las otras dos, P5 las convirtió a TypeScript y las empaquetó con Vite). Una sola implementación de cada vista, la misma que muestra el HTML integrado publicado. Plotly se importa parcial (`plotly.js/lib/core` + `bar`/`scatter`/`scattergeo`/`choropleth`, ver `web/src/lib/plotly.ts`) en vez del bundle completo vendorizado que usaba P4. El HTML/CSS/JS publicados (`static/`, `src/dashboard/assets/*.js`, `*_html.py`) no cambian; ver `web/README.md`. |
| Pruebas | `tests/` | `uv run pytest`; marcadores `local_data` (necesita `data/bronze|silver`/warehouse local) y `browser` (Playwright) se excluyen en CI. |

**Gold tables:** 43 Parquet en `data/gold/` versionados en git (ver
`docs/diccionario-datos.md`). Cuatro estimaciones adicionales
(`fact_route_carrier_*_estimate.parquet`, `fact_aeromexico_*_capacity_estimate.parquet`)
son locales y regenerables, no versionadas.

**Dashboard/Vuelos:** el HTML integrado que se publica NO es el output de
`build_stage11.py` solo. Lo produce
`src/analysis_agent/stage18.py::consumer_html`, que llama a
`src/dashboard/executive_summary.py` (payload), inserta el análisis narrativo
aprobado, y llama a `src/dashboard/flights.py::build_flight_payload()` +
`src/dashboard/flights_html.py::integration_flight_payload()` (lista blanca de
columnas: una columna nueva que no esté ahí se descarta en silencio) para
Vuelos, y a `src/analysis_agent/reader_ui.py::refine` para el maquetado final
(pestañas, KPIs, panel de Vuelos). Editar el generador, nunca el HTML
producido.

**Gate de publicación (stage18):** `stage18.publish()` valida cada registro de
análisis contra el ledger de aprobación (`src/analysis_agent/lifecycle.py`,
`analysis_runs/` local) antes de reemplazar el HTML de forma atómica
(hash SHA-256, recibo `.published.json`). Nunca ejecutes `stage18 publish` ni
cambies un registro de aprobación salvo instrucción explícita del dueño.

**Duplicado conocido (no tocar sin instrucción):** el HTML publicado vive en
`static/aeromexico_tracker.html` (copia byte a byte del canónico
`prototypes/etapa-11/resumen_ejecutivo.html`) porque `streamlit_app.py` lo
sirve con `st.iframe`. Streamlit se retira en P7; hasta entonces ambos
archivos deben coincidir.

**Segundo duplicado, temporal (P4→P5):** la lógica de las tres pestañas
vive por ahora tanto en `src/dashboard/assets/{flights,executive_summary}.js`
+ `src/analysis_agent/reader_ui.py` (lo que generan `flights_html.py`,
`executive_summary_html.py` y `stage18`/`reader_ui` para el HTML publicado)
como, línea por línea, en los módulos TypeScript de `web/src/views/{flights,
executive,economy,shell}/*.ts` (la página completa de `web/`, convertida de
`.js` a `.ts` en P5).
`tests/test_web_flights_parity.py` y `tests/test_web_page_parity.py`
prueban que ambas coinciden hoy — con una excepción documentada y aceptada:
la cita en superíndice que el HTML publicado agrega a algunas cifras (dato
de evidencia privado que `consumer_payload()` no exporta, ver
`src/web_export/analysis.py`) no existe en `web/`. Un cambio de
comportamiento debe aplicarse en los dos lugares hasta que P5/una fase
posterior retire los generadores Python en favor de `web/` como única
implementación (ver auditoría §4.2 punto 4).

**Publicación en GitHub Pages (`site/`, P6b):** `site/` es el sitio ya
ensamblado y firmado que `.github/workflows/pages.yml` despliega tal cual —
en `master`, sin secretos ni reconstrucción de datos — a
<https://salvamalfa.github.io/aeromexico-tracker/>. Publicar una nueva
versión de `site/` requiere **instrucción explícita del dueño** (igual que
`stage18 publish`); no lo ejecutes por iniciativa propia:

```
uv run python -m src.publish --record analysis_runs/drafts/<periodo>/<version>.json --out site/
uv run python -m src.publish.verify site/
```

Mientras tanto Streamlit sigue sirviendo `static/aeromexico_tracker.html`
sin cambios (se retira en P7, §7 de la auditoría); ambos muestran el mismo
contenido aprobado durante la convivencia.

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
| `python -m src.dashboard.build_flights` | Reconstruye el payload de Vuelos tras cambiar fuentes o Vuelos, antes de regenerar el integrado. |
| `python -m src.analysis_agent.stage18 --record … --output …` | Publica el HTML integrado. **Requiere instrucción explícita del dueño**; no lo ejecutes por iniciativa propia. |
| `just dashboard` | Streamlit local (heredado; se retira en P7). |
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
2. Edita el payload en `src/dashboard/flights.py` (datos) o el maquetado en
   `src/dashboard/flights_html.py` (HTML/CSS del panel).
3. Si el elemento toca la vista integrada (pestañas, KPIs), revisa también
   `src/analysis_agent/reader_ui.py::refine`.
4. Regenera: `python -m src.dashboard.build_flights`, luego el integrado vía
   `stage18.consumer_html` (no `build_stage11.py` solo).
5. Corre `uv run pytest -q tests/test_flights_prototype.py tests/test_international_routes.py`.
6. Si el cambio debe publicarse, pide instrucción explícita del dueño para
   `stage18 publish` (actualiza `static/` también, ver arriba).

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

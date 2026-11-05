# `web/`

Vite + TypeScript front-end for the whole published page — shared header,
period stepper, and four visible tabs (Lectura ejecutiva, Mercado,
Economía unitaria, Noticias) — loading the v1 payload split by
`src/web_export/` via `fetch`. See
`docs/etapas/vuelos-pasajeros-traspaso-20260913.md` for the Vuelos entry guide.
Built with Vite and strict TypeScript (`package.json`, `vite.config.ts`,
`tsconfig.json`).

## Responsabilidad

- The **only** implementation of each view: real `.html`/`.ts`/`.css` files a
  human or an agent can edit directly — the single source of truth, not a
  port kept in parity with anything else.
- `index.html` is the whole page: the shared `<header>`/period stepper, the
  `.reader-tabs` shell (`#tab-reading`/`#tab-economy`/`#tab-flights` and
  their `role=tabpanel` sections), and each view's markup. Its entry script
  is `<script type="module" src="src/main.ts">`; Vite compiles that graph,
  there is no separate build step invoked by hand.
- TypeScript ES modules under `src/views/<view>/*.ts` (≤ 400 lines each, see
  `tests/test_repo_budgets.py`), `strict: true` (`tsconfig.json`):
  - `shell/tabs.ts`: the tab controller (click + arrow/Home/End keys,
    dispatches `reader-tab-visible` after resizing any Plotly graph the
    now-visible panel holds).
  - `executive/{state,narrative,bootstrap}.ts`: fetch
    `data/v1/executive.json` (records + views, shared by the
    reading *and* economy tabs) and, per period,
    `data/v1/analysis/<period_id>.json` — the export of
    `src/web_export/analysis.py` — to render the approved-analysis summary
    and the full-analysis dialog (`#analysis-full`, re-filled per period
    because this view fetches lazily). A period with no exported file (no
    approved analysis, or a dev build run with `--allow-missing-analysis`)
    shows the same "Análisis pendiente de aprobación" placeholder text.
  - `economy/{kpis,charts,table}.ts`: the 4 KPI cards (RASK, CASK, ASK,
    Margen unitario — `load_factor_reported`/`passengers` are in the
    payload but not rendered), the three
    Plotly charts (unit economics, volume vs. RASK, load factor vs. RASK)
    and the by-quarter disclosure table.
  - `flights/*.ts`: `official-routes.ts` (official-map state, exact selection,
    search and cached loading), `official-map.ts` (controls and route detail),
    `official-map-chart.ts` (bounded Plotly traces and responsive canvas),
    `state.ts` (the retained financial/passenger payload), `mix.ts`
    (passenger mix), `quarter.ts` (global quarter), and `bootstrap.ts`
    (mounting). The previous `map.ts`/`network.ts` and their support modules
    remain for regression of the retained historical contract; bootstrap no
    longer mounts their estimated/programming selectors.
  - `main.ts`: mounts the tab shell, then `views/executive`, then
    `views/flights` (via a dynamic `import()`, see "Tamaño del bundle"
    below), in that order (see "Mount order" below).
  - `types/domain.ts`: hand-written types for the in-memory shapes the
    views work with (routes, airports, networks, quarter/executive
    records). `types/generated/*.ts` are generated from
    `contracts/web/*.schema.json` by `npm run gen:types` — never edit
    them by hand; `types/generated.test.ts` (vitest) fails if they are
    stale vs. the schemas.
  - `lib/plotly.ts`: the partial Plotly bundle these views import instead
    of a global `window.Plotly` — see "Plotly" below.
- CSS is split per view: `styles/base.css` (design tokens, page-wide
  resets, and everything shared by all three tabs — the `.page-shell`/
  `.hero`/period-stepper/`.reader-tabs` the published page's shared header
  and tab shell use), `views/executive/executive.css` (narrative card,
  analysis summary/dialog), `views/economy/economy.css` (KPI grid, chart
  cards, disclosure table) and `views/flights/flights.css` (scoped under `.flights-view`).

### Mapa oficial de Mercado

La interfaz preparada el 5 de noviembre de 2026 usa
[`official_route_network_v1`](../contracts/web/official-routes.schema.json)
desde `data/v1/official-routes.json`. La preview local usa un candidato real;
esto no acredita aprobación de datos ni publicación. El trimestre superior
es único y nunca se sustituye por otro disponible.

- Nacional: AFAC, todas las aerolíneas, ciudades. Internacional: el mismo
  universo AFAC, excluido EE. UU.; Canadá, Centroamérica (incluido Caribe),
  Sudamérica, Europa y Asia se filtran con metadatos de país y región.
- EE. UU.: BTS T-100, clases regulares F y G, incluidos vuelos de carga.
  El selector contiene sólo Grupo Aeroméxico (Aerovías y Connect), Volaris y
  Viva; la selección inicial son las tres. No representa todo el mercado BTS.
- Vuelos dimensiona y ordena las rutas. «Más vuelos» muestra doce; «Todas»
  conserva la red completa. Totales, búsqueda y lista incluyen rutas sin
  coordenadas y ceros explícitos de la fuente. El dibujo sólo representa
  valores positivos. Meses faltantes siguen N/D. El icono amarillo identifica
  cobertura parcial; los detalles conservan meses, sentidos y periodo anual
  comparable. Un resultado regional vacío conserva su filtro y muestra N/D.
  `comparison_months` conserva el soporte del año actual; las fechas de la
  base interanual se rotulan un año antes, sin modificar ese soporte ni cifras.
- `map_scope`, `map_region` y `map_carriers` guardan los filtros propios.
  `sel_map` antiguo inicializa sólo la selección BTS; `INDUSTRY` conserva el
  significado de las tres mexicanas. Los filtros financieros son independientes.
- «Pregunta» y las preguntas generales desde Mercado fijan dataset, trimestre,
  ámbito, grano y meses visibles. AFAC no hereda entidades. Sólo EE. UU.
  envía `map_carriers`. Las tarjetas financieras, participación y mezcla
  mantienen su contexto propio. El backend debe aceptar la misma versión
  exacta antes de consultar el nuevo conjunto.

Se conservan los contratos y las regresiones históricas. Los tipos oficiales
se generan desde el esquema; las nuevas fixtures y pruebas cubren selección,
cancelación de cargas, búsqueda fuera del top, faltantes geográficos y límites
de trazas. El navegador comprueba el build con fixtures sintéticas explícitas;
la revisión local adicional usa el candidato real, sin modificar `site/`, las
ocho lecturas ni las noticias. `tmp/official-map-ui/` contiene la revisión
regenerable y no se versiona ni publica.

Para un navegador ya instalado, los smoke admiten
`PLAYWRIGHT_CHROMIUM_EXECUTABLE`; si se define debe apuntar a un ejecutable
existente. En Node 25 local, usar `NODE_OPTIONS=--no-experimental-webstorage`
evita que el almacenamiento experimental nativo sustituya al de jsdom.

### Formato de las tarjetas KPI

Todas las tarjetas de indicadores, en cualquier pestaña actual o nueva, muestran
como máximo un decimal en sus valores y comparativos. Los valores medidos,
porcentajes, puntos porcentuales e importes en millones usan un decimal; los
conteos discretos pueden ser enteros. Usa `src/lib/kpi-format.ts` al renderizar
las tarjetas y sus etiquetas accesibles. Conserva unidades, signos y faltantes.
El redondeo parte del valor numérico completo, nunca de otro texto redondeado.
Los registros, cálculos, series y tablas de detalle conservan su precisión.
Las pruebas `src/lib/kpi-format.test.ts`, `src/views/economy/kpis.test.ts` y
`src/views/market/point-detail.test.ts` verifican el redondeo desde el valor completo,
las etiquetas accesibles, los faltantes y la precisión conservada en las tablas.

Los cuatro indicadores y las tres gráficas de Economía incluyen un icono con
definición breve y fuentes financieras clicables. Cambian con la aerolínea;
Industria enlaza los tres emisores y explica la ponderación por capacidad.
Los gráficos históricos enlazan archivos oficiales de resultados. El icono y
su panel se reutilizan al cambiar de periodo; la fuente queda fuera del título
adjunto a «Pregunta». La regresión de interacción vive en
`src/views/economy/sources.test.ts` y `src/views/market/source-info.test.ts`.

### Plotly

`src/lib/plotly.ts` imports
`plotly.js/lib/core` plus only the trace types these views actually use —
`bar`/`scatter` (economy charts, the passenger-mix chart) and
`scattergeo`/`choropleth` (the Vuelos flow map) — and `Plotly.register()`s
them, through `npm`'s `plotly.js` package (pinned in `package.json`) and
Vite's bundler instead of a `<script>` tag. Every view imports `Plotly`
from `src/lib/plotly.ts`, never from a global `window.Plotly`. The
published page never uses ECharts or any other charting library; this
uses Plotly 4.1.2 after the security update of 21 October 2026.
Deliberately excluded: MapLibre map traces, which this page does not use.
The production build includes MapLibre CSS through Plotly core, but no
MapLibre JavaScript modules. See the security section for scope and validation.

### Estado de trimestre compartido y carga diferida de Vuelos

The published page's own `#period-prev`/`#period-next` are shared by two
independent scripts: `executive_summary.js` attaches its own click
listener, then `src/dashboard/assets/flights.js` attaches a second,
independent one to the same buttons (there is only one stepper in the
DOM) — every click fires both, in attachment order, each keeping its own
`periodIndex`. An earlier version of `web/` ported that structure as-is:
`views/executive` and `views/flights` each kept their own `periodIndex` and
their own listeners on the same buttons, and `web/src/main.ts` mounted
`views/flights` right after `views/executive` on every page load so the
two stayed in lockstep — this only worked because both quarter lists
happen to hold the same 22 quarters in the same order, and it meant
`views/flights`' data (`quarters.json`, world geometry, network files)
always loaded even for a reader who never opens the Vuelos tab.

The top stepper is the only quarter selector across the dashboard. Reading,
financial cards, and charts follow `state/period.ts`. The reading page combines
Industry and the three issuers in one sheet (`executive/overview.ts`), checking
availability for that exact quarter against `publication_manifest.json`.
Legacy `readingPeriod` and `sel_reading` parameters do not select another
reading. Missing approved documents stay missing; no earlier quarter replaces
them. Map controls offer monthly details only within the global quarter, never
another quarter. Source coverage labels remain independent of the selection. The summary uses
selective bold emphasis; a disclosure below it, inside the same reading card, renders the complete
approved sections and citations, unchanged, for that same global quarter. It
clears and closes on a quarter change. This presentation does not replace any
canonical thesis or approval.

That version was replaced with one shared store, `web/src/state/period.ts`: it
owns the selected index and the *single* pair of click listeners on
`#period-prev`/`#period-next` (`wireStepper()`, wired once by
`views/executive/bootstrap.ts`, since the executive view always mounts
first). `views/executive/bootstrap.ts` and `views/flights/bootstrap.ts`
each `subscribe()` to it instead of keeping their own listeners; a
subscriber is notified in subscription order on every move, so the
executive view still renders before Vuelos on each click — the same
attachment-order guarantee the published page's two independent
listeners gave, now expressed as subscriber order instead. Each view
still keeps its own `periodIndex` field (`views/executive/state.ts`,
`views/flights/state.ts`) pointing into its *own* records/quarters array
— `views/{executive,flights}/bootstrap.ts` re-derive it by `period_id`
lookup every time the shared store moves, rather than assuming the two
arrays share one index space.

Because the store keeps the selected `period_id`, not just an index,
`views/flights/bootstrap.ts` (mounted lazily, see next) can join *after*
several quarter switches on the reading tab and immediately pick up
`currentPeriodId()` — this is the behaviour
`test_switching_quarters_before_opening_flights_survives_the_lazy_mount`
in the now-removed `tests/test_web_flights_parity.py` used to check against
the previously published page: switch quarters on the reading tab, *then*
open Vuelos for the first time, then switch again. The coverage of this
specific sequence is a residual gap until a multi-quarter synthetic fixture
replaces it.

**Carga inicial de Vuelos**: `web/src/main.ts` no longer mounts
`views/flights` unconditionally on load. It listens for the same
`reader-tab-visible` `CustomEvent` `views/shell/tabs.ts` already
dispatches on every tab switch (`views/flights/bootstrap.ts` itself used
it to resize Plotly graphs) and mounts Vuelos — `import()`, `loadQuarters()`
and all — the first time `panel-flights` becomes visible; a reader who
never opens that tab never fetches `quarters.json`, the world geometry or
any network file, and never even downloads the `bootstrap-*.js` chunk.
See "Tamaño del bundle" below for what this drops from the initial
transfer.

### Citations

The reading tab adds a superscript citation link (`<sup><a class="source-note">`)
next to some numbers in the analysis text. `src/web_export/analysis.py` calls
`flow.verified_inputs(record)` (fail-closed) and, per claim, exports a
`citations` array with *only* public fields: the source URL (restricted to
`www.sec.gov`/`sec.gov`/`ir.aeromexico.com`, both in code and in
`contracts/web/analysis.schema.json`'s `citation.href` pattern), the visible
tooltip text, and the exact substring of the rendered claim text to wrap — no
excerpt/source/calculation object or lineage leaves the file.
`web/src/views/executive/narrative.ts::applyCitations` splices them into the
rendered text. `tests/test_site_parity.py` checks the rendered
`#narrative-copy` against the ledger's `consumer_payload`/citation export,
superscripts included.

## Entradas / salidas

- **Entradas:**
  - Exported by Python to `web/public/data/v1/…` (local, gitignored — see
    `.gitignore`); Vite copies everything under `web/public/` to the root
    of the served site / `dist/`, so at runtime these are fetched at
    `data/v1/…`, not `public/data/v1/…` (Vite convention — see
    `src/views/{flights,executive}/state.ts`'s `dataRoot`).
  - `data/v1/flights/quarters.json` (metadata, quarters, monthly
    passengers, world geometry, `available_periods`), fetched first; then
    `data/v1/flights/{domestic,international}/<period_id>.json` on
    demand — see `src/web_export/flights.py`.
  - `data/v1/executive.json` (metadata, records, views — every
    quarter, ~80 KB), fetched once — see `src/web_export/executive.py`.
  - `data/v1/analysis/<period_id>.json`, fetched lazily per period
    as the reading tab's period changes; a 404 means no approved analysis
    for that period — see `src/web_export/analysis.py`.
- **Salidas:** none; this is a read-only page.

## Publicación

Esta página, ya compilada con Vite, es exactamente lo que
`.github/workflows/pages.yml` despliega en
<https://salvamalfa.github.io/aeromexico-tracker/> — `web/dist/` más
`data/v1/` (Vite copia `web/public/` a la raíz de `dist/`), ensamblado y
firmado como `site/` por `src/publish/gate.py`. Ver `src/publish/README.md`,
`REPO_MAP.md` ("Publicación en GitHub Pages") y `AGENTS.md`: una petición
de cambio rutinario del dueño autoriza al agente a publicar y verificar el
resultado, usando un expediente ya aprobado. Confirma en Git los cambios de
`web/` antes de ejecutar el gate; este rechaza entradas de compilación sin
commit. `web/` en sí no cambia para publicar: el gate solo compila lo que ya
está aquí.

## Ejecutar localmente

```
uv run python -m src.web_export --out web/public/data/v1
cd web && npm ci && npm run dev
```

Then open the URL `npm run dev` prints (`http://127.0.0.1:5173/` by
default). Add `--allow-missing-analysis` to the first command in a
checkout with no local `analysis_runs/` ledger (a clean public clone);
the reading tab then shows the "pending approval" fallback for every
quarter instead of failing the export.

To check the actual production build instead of the dev server:

```
cd web && npm run build && npm run preview
```

`web/serve.py` (a thin `http.server` wrapper) still exists for the
Playwright tests below, which serve the built `web/dist/` directly rather
than going through `npm run preview`.

## Comandos de web/

| Comando | Qué hace |
|---|---|
| `npm ci` | Instala `node_modules` desde `package-lock.json` (versiones fijas). |
| `npm run dev` | Servidor de desarrollo de Vite con recarga en caliente. |
| `npm run build` | Compila a `dist/` — determinista: dos builds seguidos producen los mismos hashes de archivo (verificado a mano; ver "Tamaño del bundle"). |
| `npm run preview` | Sirve `dist/` (el build) localmente. |
| `npm run check` | `tsc --noEmit` — chequeo de tipos estricto. |
| `npm run test` | `vitest run` — pruebas unitarias de funciones puras y la prueba de tipos generados al día. |
| `npm run gen:types` | Regenera `src/types/generated/*.ts` desde `contracts/web/*.schema.json`. |

## Comando de prueba focalizada

```
cd web && npm run check && npm run test && npm run build
uv run pytest -m browser -q tests/test_web_flights_smoke.py tests/test_web_page_smoke.py
uv run pytest --require-local-data -m "browser and local_data" -q tests/test_site_parity.py
```

- `test_web_flights_smoke.py` / `test_web_page_smoke.py` are `browser`
  only — they build `web/` with Vite once per pytest session
  (`web_dist_dir` in `tests/conftest.py`, skipped with a clear reason if
  `npm`/Node are missing) and serve the **built** `web/dist/` with the
  synthetic fixtures at `tests/fixtures/web/`, then check each tab renders
  with no console errors — so they are the ones enabled in CI's `web` job
  (see `.github/workflows/ci.yml` and `REPO_MAP.md`).
- `test_site_parity.py` (also `local_data`) checks the already-assembled
  `site/` against its own sources of truth instead of a second render — see
  its module docstring.
  A local-data-only sub-test also snapshot-compares `site/`'s committed
  `data/v1/` against a fresh `src.web_export` run.

## Tamaño del bundle

Medido con `npm run build` (commit actual) más un export real desde el
warehouse local (`uv run python -m src.web_export --out web/public/data/v1
--allow-missing-analysis`), trimestre por defecto `2026Q2`, cargando la
página con Playwright y sumando el tamaño real de cada respuesta HTTP (ver
la metodología en `tests/test_web_page_smoke.py`/`test_web_flights_parity.py`;
las cifras de esta sección se tomaron con un script de un solo uso, no
parte de la suite).

**Carga inicial (pestaña de lectura, Vuelos sin abrir)** — `main.ts` no importa ni monta `views/flights` al cargar la página (ver
"Estado de trimestre compartido y carga diferida de Vuelos" arriba), así
que esta es toda la transferencia hasta que alguien abre esa pestaña:

| Archivo | Sin comprimir | gzip |
|---|---|---|
| `dist/index.html` | 14.4 KB | 3.2 KB |
| `dist/assets/index-*.css` | 99.3 KB | 15.4 KB |
| `dist/assets/index-*.js` (tabs, executive, economy, Plotly core+bar+scatter — ya no incluye nada de `views/flights`) | 1,304.2 KB | 455.1 KB |
| `data/v1/executive.json` | 68.2 KB | 8.4 KB |
| `data/v1/analysis/2026Q2.json` (incluye las citas) | 26.6 KB | 6.5 KB |
| **Total de la carga inicial** | **1,512.6 KB (≈1.51 MB)** | **488.6 KB (≈0.49 MB)** |

**≈1.51 MB sin comprimir**, por debajo del objetivo de ≤ 2 MB. `dist/assets/bootstrap-*.js`
(35.8 KB / 11.8 KB gzip, el chunk de Vuelos) tampoco se descarga hasta
que se abre esa pestaña.

**Al abrir la pestaña Vuelos por primera vez** (el resto de la
transferencia, cargado bajo demanda, con `state/period.ts` ya
sincronizado en el trimestre que estuviera seleccionado):

| Archivo | Sin comprimir | gzip |
|---|---|---|
| `dist/assets/bootstrap-*.js` (chunk de Vuelos, `import()` dinámico) | 35.8 KB | 11.8 KB |
| `data/v1/flights/quarters.json` (incluye la geometría mundial TopoJSON) | 634.0 KB | 212.9 KB |
| `data/v1/flights/domestic/2026M0{4,5,6}.json` (los 3 meses del trimestre por defecto) | 310.4 KB | 31.7 KB |
| **Subtotal al abrir Vuelos** | **980.1 KB (≈0.96 MB)** | **256.4 KB (≈0.25 MB)** |

Quien nunca abre Vuelos nunca paga esos ≈0.96 MB; quien la abre acaba
transfiriendo ≈2.49 MB en total, repartidos en el tiempo en vez de al inicio.

## Dependencias y avisos de seguridad

Actualización del 21 de octubre de 2026: el lockfile corrige las siete
entradas señaladas por `npm audit`. Las entradas propagadas por dependencias
no representan siete fallos distintos. No se usa `npm audit fix --force`.

| Dependencia | Antes | Ahora | Motivo |
|---|---|---|---|
| Vite | 7.3.6 | 7.3.7 | Corrige los avisos de `launch-editor`. |
| Vitest y sus paquetes internos | 3.2.7 | 4.1.12 | Corrige `@vitest/mocker` y elimina `tinypool` del árbol. |
| Plotly | 3.7.0 | 4.1.2 | Incluye MapLibre 6.11.2, fuera del rango vulnerable. |
| source-map-js | 1.2.1 | 1.2.2 | Corrige el aviso de consumo de recursos al interpretar mapas. |

Se mantiene Node 22. Vitest 4 requiere restaurar explícitamente los spies del
navegador entre pruebas; el cierre de `review/bootstrap.test.ts` lo hace sin
relajar sus comprobaciones. Se conservan las cuatro trazas de Plotly que usa
la interfaz. Las versiones y hashes exactos están en `package-lock.json`.

Plotly 4 cambia las marcas de los ejes superpuestos a una cuadrícula sincronizada.
Se fija `tickmode: "auto"` en los tres ejes secundarios de Economía para
conservar la escala visual anterior. La prueba de navegador observa posiciones
reales de las marcas y rangos distintos: pasa con el build anterior de Plotly 3,
falla con Plotly 4 sin el ajuste y pasa al conservar las marcas independientes.
No se basa solo en inspeccionar la configuración enviada a Plotly.

La consulta `npm audit --package-lock-only --json` devuelve cero avisos para
las 392 entradas del lockfile actualizado. Es una consulta al corte, no una
garantía de ausencia de vulnerabilidades futuras. La revisión de los módulos
que Rollup incorpora al build local encontró solo CSS de MapLibre; no incluyó
su JavaScript ni módulos de Mapbox, Vitest, Tinypool o source-map-js.
La ausencia de un nombre en texto minificado no se usa como prueba de alcance.

Fuentes oficiales: [aviso de MapLibre](https://github.com/advisories/GHSA-jrc7-96c5-q579),
[aviso de Vitest](https://github.com/advisories/GHSA-82fw-gwwq-j7x9),
[aviso de Tinypool](https://github.com/advisories/GHSA-85c8-ppgw-ccpr),
[aviso de source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q),
[aviso de Vite](https://github.com/advisories/GHSA-587h-7wmj-h5pm)
[migración de Vitest 4](https://v4.vitest.dev/guide/migration.html)
y [migración de ejes en Plotly 4](https://plotly.com/javascript/guides/migrating-to-v4/#overlaying-axis-tickmode).

Comprobación acotada de la publicación vigente: el chunk
`assets/plotly-DRbKALdc.js` tiene 1.286.176 bytes y coincide por SHA-256 entre
el manifiesto Git, la respuesta HTTP y un build con los módulos Plotly 3.7.0
ya existentes, sin reinstalarlos. Su grafo incorpora CSS de MapLibre y excluye
su JavaScript. No es una reproducción completa del sitio: solo cuatro de las
catorce salidas de ese build coinciden con el manifiesto vigente. Esta prueba
se limita al chunk Plotly servido y no declara actualizado todo el frontend.

El build de esta rama y la publicación servida son estados distintos.
La actualización de `site/` requiere el gate y la verificación de Pages;
no copiar compilados a mano ni afirmar que el sitio usa el lockfile nuevo
solo porque pasen las pruebas locales.

### Mercado integrado · revisión local

Mercado reúne las vistas anteriores de Mercado y Vuelos. Conserva exactamente
las cuatro tarjetas financieras: pasajeros, ASM, RPM y ocupación, con sus
comparativos. El orden es mapa de rutas, participación AFAC y mezcla nacional /
internacional. Los identificadores internos de Vuelos se conservan para no
romper la carga diferida ni los contratos del chat; los enlaces anteriores a
Mercado o Vuelos abren la misma pestaña visible Mercado.

Se retiraron las tres tarjetas AFAC y, por la instrucción posterior del dueño,
el desplegable de datos por aerolínea. Su detalle mensual ahora se consulta al
señalar o tocar la gráfica, o con el foco y las flechas del teclado. Muestra una
fecha, tres aerolíneas, participación, pasajeros en millones y variación frente
al mismo mes del año anterior. La base de comparación se nombra una sola vez;
faltantes y bases cero quedan N/D. Los cambios positivos son azules y los
negativos rojos. La fuente independiente muestra «Fuente: AFAC.» con AFAC como
enlace; no atribuye a AFAC los KPI financieros superiores.

La gráfica conserva toda la historia y ejes fijos hasta el último mes real,
aunque cambie el trimestre global. Sólo se mueve la franja de selección.
Total y Nacional parten de 15 %; Internacional baja a 8 % para incluir el mínimo
histórico de Viva (8.87 %). El detalle responde al mes del punto, mientras
«Pregunta» conserva el trimestre global y el segmento seleccionados.

El detalle enriquecido compartido con la mezcla se monta fuera de las tarjetas
y usa la capa superior nativa del navegador, encima del chat. Sus límites usan
el área útil de pantalla, incluida la barra de desplazamiento. Escape cierra el
detalle antes que el chat; cambiar de pestaña o tamaño lo cierra. Las ayudas de
fuente también se cierran al cambiar de tamaño para evitar posiciones antiguas.

### Noticias · candidato del PR #136

El archivo mensual mantiene tarjetas con resúmenes originales, tres fechas y
fuentes trazables. Los filtros incluyen disponibilidad en el chat; la cobertura
parcial se consulta con el botón de información del título. Los controles de
aprobación pertenecen al expediente, fuera de la pestaña. La navegación desde
el chat valida corpus y cita. Decisiones de revisión:
`docs/etapas/noticias-ajustes-ui-20261018.md`.

### Corte financiero Aeroméxico 3T26

La actualización financiera conserva el trimestre inicial común de las demás
aerolíneas. Aeroméxico dispone además de 3T26 en las tarjetas existentes y las
tres gráficas de economía unitaria; Industria y competidores conservan sus
series y muestran `No disponible` cuando falta ese trimestre. Las bases de
comparación del reporte se consultan en el desplegable junto a las tarjetas.
La lectura conserva su selector independiente y su contenido aprobado.

El store de periodos financieros sigue siendo el dueño de la cabecera. Si un
trimestre financiero no existe en Vuelos, el panel retiene su corte real y lo
identifica explícitamente; no sobrescribe la cabecera ni cambia los archivos del
mapa. La suscripción de Vuelos actualiza esa advertencia también cuando ya estaba
abierto en un trimestre anterior.

### Revisión local de noviembre de 2026

El modo desarrollo carga `web/.env.development`, con el botón de chat activo y
la misma URL pública del servicio publicado. No contiene credenciales; conserva
la autenticación y las restricciones de origen del servidor. Mostrar el panel
no garantiza disponibilidad del servicio: health respondió 502 el 1 de noviembre.

`?period=2026Q3&review=1` muestra la propuesta editorial local de los cuatro
análisis desde `tmp/editorial-rerun/2026Q3.json`. El middleware existe sólo en
Vite desarrollo; no exporta borradores al directorio público ni los aprueba.
Los enlaces históricos sin esa propuesta usan el catálogo publicado.

«Pregunta» permanece en la esquina superior derecha de cada componente. El hover
sobre la tarjeta destaca sólo el botón. Al pulsarlo se adjunta una instantánea
de contexto en el compositor; la pregunta se envía únicamente con Enviar.
Sin adjunto se usa la vista actual al enviar. Los nombres de selectores siguen
accesibles aunque no se dibujen títulos encima. El estado editorial continúa
controlado por el lifecycle, con independencia de las leyendas de interfaz.


En Vuelos, el mapa usa únicamente el trimestre global. Nacional/Internacional y
los filtros de rutas están dentro de la barra de la tarjeta. La cobertura se
presenta como mini indicador junto al volumen, con porcentaje sólo si existen
representación y denominador AFAC comparables; la ayuda conserva los meses
observados, rutas representadas/mostradas y límites de la fuente. La descripción
accesible de la mezcla conserva cobertura sin un párrafo visible. Pregunta se
adjunta por gráfica (mapa o mezcla), sin un botón en el contenedor de toda la vista.


Todos los indicadores financieros de Vuelos y los mini indicadores del mapa
usan la misma ayuda que Mercado: icono único junto al nombre y panel con fuente
enlazada y una definición breve. Admite hover, foco y clic táctil; permite entrar
en el enlace sin cerrar el panel. Las frecuencias estimadas enlazan AeroDataBox;
AFAC se identifica como denominador de cobertura o atribución, según corresponda.


La pestaña Mercado integra los cuatro KPI financieros, el mapa, participación
AFAC y mezcla por segmento. La mezcla usa el AFAC vigente también para Grupo
Aeroméxico (incluye Connect); el reporte corporativo sigue como alternativa.
Su detalle muestra un periodo, la base del año anterior una vez, y pasajeros y
variación anual por segmento. Si faltan base o meses comparables, conserva N/D.
Norteamérica muestra sólo observados cuando existen; el filtro se aplica antes
de totales y listados. Otras regiones mantienen sus tipos reales. El porcentaje
AFAC no se reutiliza para una región o vista de evidencia distinta.

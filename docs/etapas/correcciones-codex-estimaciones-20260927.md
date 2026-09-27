# Correcciones Codex sobre estimaciones y Gold de rutas · 27 sep 2026

## Alcance

Tres hallazgos de Codex sobre
[salvamalfa/aeromexico-tracker#69](https://github.com/salvamalfa/aeromexico-tracker/pull/69),
que a su vez cerraba cinco hallazgos previos (PRs #10, #19, #20). Este reporte
cubre el conjunto completo de cambios en la rama, no solo el incremento de
esta sesión.

## Qué cambió y por qué

**1. Capacidad "Boeing 737" genérica: 175.7 → 175.1 pasajeros.**
`data/reference/aeromexico_aircraft_seat_capacity.csv` declaraba pesos y
capacidades ((34×173 + 47×170 + 30×185.5) / 111) cuyo punto medio real es
175.1, no el 175.7 publicado. Solo `src/analytics/international_capacity.py`
lee este archivo, y ese módulo requiere los Parquet privados del barrido
AeroDataBox para correr.

**2. Bandas de ocupación fuera de [0, 100%] (nacional e internacional).**
`load_factor_low/high` podía caer fuera de rango (ej. 103.41% en MEX↔MXL)
aunque el punto fuera plausible, porque solo el punto se validaba contra
[0, 1]. `src/dashboard/domestic_routes.py` e
`src/dashboard/international_routes.py::_route_capacity_metrics` ahora
validan cada extremo por separado y lo retienen como `None` (nunca lo
recortan a 0/1) cuando es implausible.

**3. Rango de sensibilidad del IPF retenido cuando alguna celda fue
reparada.** `passengers_low/high` de una celda reparada temporalmente
proviene de un escenario de sensibilidad que Gold no conserva por celda
(la identidad del escenario se pierde). Sumar extremos de celdas con
escenarios distintos por dirección/mes/ruta/red producía un rango que el
estimador nunca calculó. `src/dashboard/domestic_routes.py` ahora suma los
extremos solo cuando ningún componente del grupo requirió reparación
(donde low == high == punto, así que la suma es exacta); si algún
componente fue reparado, el grupo entero queda sin rango (`None`), nunca
con un rango parcial o fabricado.

**4. Mezcla trimestral de pasajeros/ASM/RPM con `NaN` silencioso.**
`src/dashboard/flights.py::_load_mix` sumaba los tres meses con
`Series.sum()`, que ignora nulos (y da 0.0 si los tres son nulos) mientras
marcaba el trimestre como completo. Ahora exige que los tres meses sean no
nulos y finitos antes de sumar; si falta uno, el trimestre completo se
omite (mismo criterio que la cobertura incompleta existente) en vez de
publicar un total parcial.

**5. `build_warehouse` omitía en silencio Gold de extensión de rutas
ausente.** `just rebuild` copia Bronze (incluidas las seis investigaciones
manuales de extensión de rutas) pero excluye `data/gold`, y esos seis
generadores no están en `src.pipeline.registry.PIPELINE_STEPS`. Antes, si
el bronce estaba presente pero el Gold no, el warehouse se reconstruía sin
esa tabla, sin avisar. `src/transform/stage6_warehouse.py` ahora levanta
`RouteExtensionMissingError` en ese caso; las cuatro tablas que
genuinamente dependen de insumos privados/pagados (`fact_route_carrier_*`,
`fact_aeromexico_*_capacity_estimate`) siguen con omisión silenciosa
legítima (`None` como fuente).

**5b. Guarda de fuente equivocada para AIFA (esta sesión).**
`fact_aifa_shared_route_presence` y su bridge usaban
`_EXCLUSIVE_MARKET_SOURCES`, que incluye el documento de traspaso de Colima
— insumo de `afac_exclusive_domestic.py`, no de
`src/transform/aifa_shared_presence.py`, que solo lee el libro AFAC y el
directorio de aerolíneas de AIFA (`_verified(AFAC)` / `_verified(ROSTER)`).
Con la guarda compartida, un snapshot con el libro AFAC y el directorio
pero sin el documento de Colima no fallaba en cierre cuando el Gold de AIFA
faltaba. Se creó `_AIFA_SHARED_PRESENCE_SOURCES` (solo esos dos archivos) y
se revisaron las demás filas de `ROUTE_EXTENSION_BRONZE_SOURCES` contra el
generador que cada una nombra; el resto ya listaba exactamente sus propios
insumos.

**6. Cliente web fabricaba bandas de sensibilidad ausentes (esta sesión).**
Con (3) publicando `passengers_low/high` (y `load_factor_low/high`) como
`null` cuando el rango no está disponible, `web/src/views/flights/`
sustituía el extremo faltante por el punto central
(`domestic.ts`, `table.ts`) o por cero (`volume.ts`), fabricando un rango
de ancho cero o basado en cero. Se agregó `sensitivityRange(low, high)` en
`dom.ts` (retiene ambos extremos solo si ambos son finitos) y se usó en
`domestic.ts::aggregateDomesticMonths` (propaga `null` si cualquier mes
sumado carece de un extremo), `table.ts::metricCell` /
`estimateDirectionLine` (omiten la banda y muestran "rango de sensibilidad
no disponible" en el título) y `volume.ts::renderNetworkVolume` (suma
extremos solo entre rutas que sí contribuyen al total de pasajeros y da
`null`, no 0, en cuanto una de ellas carece de un extremo).

**7. `RouteExtensionMissingError` rompía `just rebuild` porque nadie
regeneraba el Gold antes de que la guarda lo exigiera (esta sesión, hallazgo
P1 de Codex sobre #69).** El punto 5 dejó la guarda en cierre correcto, pero
`src/rebuild.py` reconstruye desde un checkout limpio sin `data/gold`;
`transform.stage6` construye el warehouse antes de que cualquier generador de
extensión de rutas pudiera correr; y esos seis generadores seguían sin estar
en `src.pipeline.registry.PIPELINE_STEPS` (necesitan el warehouse de
`transform.stage6`, en particular `dim_airport`, para poder producir su
propio Gold). Resultado: cualquier `just rebuild` con un snapshot Bronze
normal (que incluye las seis investigaciones manuales, copiadas como Bronze
ordinario) abortaba en `dashboard.materialize_stage9`.

Se investigó cada generador (`src/transform/domestic_slots.py`,
`aicm_international_slots.py`, `oma_documented_routes.py`,
`international_routes.py`, `aifa_shared_presence.py`,
`afac_exclusive_domestic.py`): los seis leen únicamente su(s) documento(s)
Bronze de investigación y `dim_airport` desde el warehouse ya construido por
`transform.stage6`; ninguno depende de insumos pagados o privados
irreproducibles, y cada uno escribe su Gold y lo carga de vuelta al mismo
warehouse él mismo (`CREATE OR REPLACE TABLE ... FROM read_parquet`).

Se eligió la opción preferida (registrar los generadores en el DAG, no copiar
Gold comprometido como atajo): se agregaron seis pasos `transform.*`
opcionales en `PIPELINE_STEPS`, cada uno con `depends_on=("transform.stage6",)`
y con requisito de entrada exactamente los mismos archivos Bronze que ya
declaraba `ROUTE_EXTENSION_BRONZE_SOURCES` (duplicados como literales en
`src/pipeline/registry.py` porque importar `src.transform.stage6_warehouse`
desde el registro sería una importación circular — `src.transform.__init__`
importa `src.pipeline`, que carga el registro primero). Al ser opcionales, un
snapshot sin esa investigación Bronze los omite (`NOT_AVAILABLE`) sin fallar
el rebuild, y la guarda tampoco se dispara porque el mismo Bronze está
ausente. `src/transform/stage6_warehouse.py` ganó
`ROUTE_EXTENSION_GENERATOR_STEPS` (tabla → step_id) para que las pruebas
puedan verificar que cada paso registrado produce exactamente la tabla que la
guarda exige, sin duplicar de memoria esa relación.

`tests/test_pipeline_route_extension_steps.py` (nuevo) cubre: los seis pasos
existen, son opcionales y dependen de `transform.stage6`; se ejecutan después
de `transform.stage6` y antes de `dashboard.materialize_stage9` (donde
`build_warehouse` vuelve a exigir la guarda); sus patrones Bronze
coinciden exactamente con `ROUTE_EXTENSION_BRONZE_SOURCES`; sus salidas
declaradas coinciden con `ROUTE_EXTENSION_GENERATOR_STEPS`; y la guarda sigue
fallando en cierre si el Gold de un generador registrado falta en el momento
de cargar el warehouse.

## Cómo se validó

- `uv run pytest -q -m "not local_data and not browser"` → 523 passed, 5
  skipped (los 5 omitidos son artefactos locales de Stage 4 intencionalmente
  no versionados).
- `uv run pytest -q tests/test_stage6_warehouse_route_extensions.py
  tests/test_pipeline_route_extension_steps.py tests/test_pipeline_orchestration.py`
  → 27 passed (nuevo: `test_pipeline_route_extension_steps.py`, 6 pruebas que
  verifican registro, orden en el DAG, correspondencia de insumos/salidas con
  la guarda, y que la guarda sigue fallando en cierre).
- `cd web && npm run check && npm test && npm run build` → tsc sin errores;
  59 tests Vitest (nuevos: `sensitivityRange` en `dom.test.ts`, dos casos de
  agregación nula en `domestic.test.ts`, `volume.test.ts` nuevo con los dos
  casos de rango agregado); build de producción sin errores (el aviso de
  tamaño de chunk es preexistente y no relacionado).
- `uv run ruff format --check src/dashboard/international_routes.py
  src/analysis_agent/lifecycle.py` → ya formateados.
- `uv run python -m src.publish.verify site/` → válido (sin cambios a
  `site/` en esta rama).
- `git diff --check` → limpio.
- Prueba de presupuesto de líneas del repositorio (`tests/test_repo_budgets.py`)
  → pasa sin ajustar límites en los archivos tocados por esta sesión.

## Límites que permanecen

- El rango de sensibilidad de una ruta/mes con alguna celda reparada por IPF
  sigue sin poder reconstruirse retroactivamente: Gold no conserva la
  identidad del escenario por celda. Mientras eso no cambie, esas
  celdas/agregados se publican y se muestran sin banda, nunca con una
  aproximada.
- `fact_aeromexico_international_capacity_estimate` (y la derivación
  doméstica equivalente) no son Gold pública comprometida; requieren que el
  dueño las regenere desde los insumos privados de AeroDataBox para que la
  corrección de 175.1 se refleje en cifras publicadas.
- `site/` no se tocó ni se republicó en esta rama; los cambios de esta rama
  no llegan al dashboard público hasta que el dueño ejecute la
  regeneración y publicación explícitas.

## Cifras publicadas que cambiarán al regenerar

- Cualquier cifra de capacidad/ocupación internacional derivada del punto
  medio "Boeing 737" (175.7 → 175.1), tras regenerar
  `fact_aeromexico_international_capacity_estimate` con AeroDataBox.
- Bandas de ocupación (`load_factor_low/high`) de rutas nacionales e
  internacionales que antes mostraban un valor fuera de [0, 100%]: ahora
  aparecerán como no disponibles (`None`) en vez de ese valor implausible.
- Bandas de sensibilidad de pasajeros (`passengers_low/high`) de cualquier
  ruta/dirección/mes/agregado de red con alguna celda reparada por IPF:
  antes mostraban un rango sumado entre escenarios distintos; ahora no
  muestran rango.
- Totales trimestrales de la mezcla SEC (pasajeros/ASM/RPM) para cualquier
  trimestre con algún mes nulo: antes podían publicarse como 0 o parciales;
  ahora el trimestre completo se omite.
- La tabla `fact_aifa_shared_route_presence` (y su bridge) en el warehouse
  reconstruido: antes podía faltar en silencio con el libro AFAC y el
  directorio de AIFA presentes pero sin el documento de Colima; ahora ese
  caso hace fallar `build_warehouse` en vez de omitirla.
- En el dashboard web, cualquier fila o agregado de Vuelos con rango de
  sensibilidad ausente: antes mostraba un rango de ancho cero (sustituyendo
  el extremo por el punto) o un rango basado en cero; ahora muestra el punto
  solo, o "rango de sensibilidad no disponible".

## Commits de esta sesión

- `d785c16` — bandas de sensibilidad ausentes preservadas en el cliente web.
- `1d4bc6e` — guarda de fuente propia para la presencia compartida en AIFA.
- `51a7437` — registro de los seis generadores de extensión de rutas en
  `PIPELINE_STEPS` para que `just rebuild` no falle contra su propia guarda.

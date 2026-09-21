# Auditoría Grupo Aeroméxico · Vuelos nacional · 21 sep 2026

## Alcance

Auditoría solicitada de la pestaña Vuelos, sección nacional (marzo–julio 2026),
para confirmar que Aerovías de México y Aeroméxico Connect se presentan y
calculan conjuntamente como **Grupo Aeroméxico** en pasajeros, vuelos, asientos
y ocupación, sin que la ausencia de una filial en una fuente invalide la
capacidad de la otra, y sin doble conteo cuando ambas están presentes. Incluye
revisión específica de la implementación del PR
[salvamalfa/aeromexico-tracker#21](https://github.com/salvamalfa/aeromexico-tracker/pull/21).

## Limitación de datos en este entorno

Este checkout de nube no tiene `data/warehouse.duckdb` ni los Parquet
`fact_route_carrier_domestic_estimate.parquet` /
`fact_aeromexico_domestic_capacity_estimate.parquet` (ambos ignorados a
propósito para el repositorio público; ver `.gitignore` líneas 22–23 y
`AGENTS.md`). El respaldo privado
`../Aeromexico Tracker Data/derived/aerodatabox/...` tampoco estaba disponible
en esta sesión. Por lo tanto **no fue posible ejecutar la auditoría
programática de los 276 mercado-mes reales ni de los 13 casos con capacidad
incompleta contra datos de producción**: `tests/test_domestic_slots.py` y
`tests/test_flights_prototype.py` fallan aquí exactamente igual con y sin los
cambios de esta auditoría (`FileNotFoundError` / `IOException` al abrir
`data/silver/*.parquet` y `data/warehouse.duckdb`), lo que confirma que la
causa es la ausencia local de datos, no una regresión introducida. La
comparación de conteos exactos por mes, la tabla de los 13 `N/D` y la
verificación visual de Streamlit/GDL–MEX quedan pendientes de una sesión con
acceso al warehouse local o al repositorio privado de datos.

Lo que sí se pudo hacer de forma completa y reproducible es la **auditoría de
código** de la lógica de agregación, presentación y las reglas de negocio que
determinan esos números, más una batería de pruebas sintéticas que no
dependen del warehouse.

## Revisión del PR #21

El PR #21 (`027ee36`, ya fusionado en `master`) corrigió exactamente el
defecto que este encargo buscaba confirmar: antes de esa merge, la capacidad
por dirección/mes se evaluaba fila por fila (`row_capacity_metrics`), así que
un mercado con datos de capacidad de una sola filial en AeroDataBox producía
directamente asientos/vuelos/ocupación `N/D` a nivel de detalle, aunque la
otra filial sí tuviera evidencia. El PR introdujo `capacity_by_direction`
(`groupby(period_id, market_key, origin, destination).agg(...)`), que suma la
capacidad de **cualesquiera** filiales presentes en
`fact_aeromexico_domestic_capacity_estimate` antes de decidir si la celda está
completa, y cambió la etiqueta de carrier a `"Grupo Aeroméxico"` en el detalle
mensual. Se verificó con datos sintéticos (ver abajo) que este comportamiento
es correcto: un mercado con capacidad de una sola filial en una dirección ya
no cae a `N/D` si la otra dirección o la misma dirección para la otra filial
sí tiene evidencia.

## Hallazgo y corrección aplicada

`src/dashboard/domestic_routes.py::estimated_network` conservaba, tras el
PR #21, un `frame.merge(capacity[capacity_columns], ..., validate="one_to_one")`
por fila carrier/dirección/mes que ya no lo consume ningún camino de salida:
desde el PR #21, `capacity_metrics` siempre recalcula `capacity_part` a nivel
de dirección (`route_scope` era `True` en las tres llamadas). Ese merge muerto
no cambiaba ningún número mostrado, pero sí era una fuente innecesaria de
fallo: un `MergeError` de `validate="one_to_one"` ahí (p. ej. por una fila de
capacidad duplicada real en los datos) tumbaría la construcción de *todo* el
payload de Vuelos en lugar de degradar solo la celda afectada a `N/D`.

Se eliminó el merge muerto y el parámetro `route_scope` (ya constante) de
`capacity_metrics`, dejando la única ruta de cálculo —la agregación por
dirección que ya usaban las tres llamadas— sin cambiar ningún resultado. Se
verificó con las mismas pruebas sintéticas que la salida es idéntica antes y
después del cambio.

No se encontró en el código ningún lugar de la pestaña Vuelos (`flights.py`,
`flights_html.py`, `assets/flights.js`, ni el HTML integrado
`prototypes/etapa-11/resumen_ejecutivo.html` / su copia pública
`static/aeromexico_tracker.html`) que siga mostrando "Aerovías de México" o
"Aeroméxico Connect" por separado en el detalle nacional: `carrier_label` se
fija a `"Grupo Aeroméxico"` en la construcción del payload
(`domestic_routes.py`), y el detalle expandido (`monthly` en
`flights_html.py`/`flights.js`) separa únicamente por dirección
(origen→destino), nunca por filial, tal como exige el encargo. La separación
por razón social permanece documentada solo internamente: en el `SOURCE` de
`fact_route_carrier_domestic_estimate` (`carrier_key` = `AEROMEXICO` /
`AEROMEXICO_CONNECT`) y en `ESTIMATED_CARRIERS`, que ya no llega a la interfaz.

## Reglas verificadas por lógica y por prueba sintética

No se pudo ejecutar la agregación contra los datos reales, pero se replicó su
comportamiento con un mini-warehouse DuckDB en memoria (`tests/test_domestic_slots.py`,
tres pruebas nuevas) que ejercita exactamente las reglas del encargo:

1. **Pasajeros**: `passengers_estimated_low/high` se preservan y se suman por
   filial (`test_group_capacity_survives_a_single_carrier_without_invalidating_the_route`).
2. **Vuelos y asientos**: una dirección con capacidad observada solo para
   Aerovías de México (Connect ausente de AeroDataBox en esa dirección) sigue
   reportando asientos/vuelos de Grupo Aeroméxico en vez de `N/D`
   (`test_group_capacity_survives_a_single_carrier_without_invalidating_the_route`).
   Cuando ambas filiales están presentes, la suma es exactamente la suma de
   ambas, sin duplicar
   (`test_group_capacity_sums_both_carriers_exactly_once`).
3. **Ocupación**: un punto estimado con pasajeros > asientos produce
   `load_factor = None` con `load_factor_status = "inconsistent_inputs"`, pero
   conserva vuelos y asientos sin alterarlos
   (`test_load_factor_above_100_percent_is_nd_but_keeps_flights_and_seats`).
4. **No redistribución sin evidencia**: la suma por dirección solo usa filas
   que existen en `fact_aeromexico_domestic_capacity_estimate`; una filial sin
   fila en esa tabla aporta cero, nunca una capacidad inventada o prorrateada.

## Lo que queda pendiente

- Conteo exacto por mes de mercados con pasajeros/vuelos/asientos/ocupación
  completos, y la tabla de los 13 casos `N/D` con su motivo específico
  (observación insuficiente, sentido faltante, cobertura de modelo, error de
  unión, soporte temporal u otra regla): requiere el warehouse local o el
  Parquet privado `fact_aeromexico_domestic_capacity_estimate.parquet`, no
  disponibles en esta sesión. La lógica de agregación que determina esos 13
  casos no cambió en esta auditoría (solo se removió código muerto), así que
  el conteo publicado en
  `docs/etapas/vuelos-capacidad-ocupacion-estimada-20260920.md` (276
  mercado-mes, 263 con vuelos y asientos completos, 60 con ocupación
  inconsistente) sigue siendo la referencia vigente hasta que se pueda
  reejecutar con datos reales.
- Verificación visual de GDL–MEX y de un mercado con una sola filial interna
  en la publicación de Streamlit: no fue posible en este entorno sin la
  aplicación desplegada ni el warehouse.
- No se hicieron llamadas nuevas a AeroDataBox ni se consumieron unidades de
  RapidAPI.

## Invariantes de gobierno confirmadas sin cambio

- `historically_eligible_at_2026_07_13 = false` y `agent_eligible = false` se
  siguen fijando explícitamente en `domestic_routes.py`.
- `flight_evidence_v1` no se activa ni se referencia.
- La distinción entre vuelos programados y realizados permanece: el `mode`
  sigue siendo `estimated_domestic`/`scheduled_domestic` y los textos de la UI
  siguen usando "estimados"/"programados", nunca "realizados".
- No se tocaron las reglas de retención de AeroDataBox ni `analysis_runs/`.

## Pruebas ejecutadas

- `uv run python -m pytest tests/test_domestic_slots.py -k "group_capacity or load_factor_above"`:
  3 pasan (nuevas).
- `uv run python -m pytest -q` (suite completa, con el extra `analytics`
  instalado): 380 pasan, 42 fallan, 6 se omiten, 17 dan error — idéntico antes
  y después del cambio de código (comparado con `git stash`), y las fallas
  restantes son todas por archivos locales ausentes
  (`data/silver/*.parquet`, `data/warehouse.duckdb`), no por esta auditoría.
- `git diff --check`: sin advertencias.

## Archivos modificados

- `src/dashboard/domestic_routes.py`: elimina el merge de capacidad por fila
  ya no consumido; el resultado numérico no cambia (verificado con pruebas
  sintéticas equivalentes antes/después).
- `tests/test_domestic_slots.py`: tres pruebas de regresión sintéticas que no
  dependen del warehouse local.
- `docs/etapas/vuelos-grupo-aeromexico-auditoria-20260921.md`: este reporte.

No se regeneró ningún HTML porque el cambio de código no altera ningún valor
de salida (confirmado con las pruebas sintéticas antes/después) y esta sesión
no tiene el warehouse local para regenerarlos desde el generador real.

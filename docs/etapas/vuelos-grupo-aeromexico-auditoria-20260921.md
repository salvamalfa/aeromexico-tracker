# Auditoría Grupo Aeroméxico · Vuelos nacional · 21 sep 2026

## Alcance

Auditoría de la pestaña Vuelos, sección nacional (marzo–julio 2026), para
confirmar que Aerovías de México y Aeroméxico Connect se presentan y calculan
conjuntamente como **Grupo Aeroméxico** en pasajeros, vuelos, asientos y
ocupación, sin que la ausencia de una filial en una fuente invalide la
capacidad de la otra, y sin doble conteo cuando ambas están presentes. Incluye
revisión específica de la implementación del PR
[salvamalfa/aeromexico-tracker#21](https://github.com/salvamalfa/aeromexico-tracker/pull/21)
y de los 13 mercado-mes con capacidad incompleta reportados en
`docs/etapas/vuelos-capacidad-ocupacion-estimada-20260920.md`.

## Acceso a datos usado

Esta sesión clonó el respaldo privado `salvamalfa/aeromexico-tracker-data`
(autorizado explícitamente por el usuario) para poder auditar contra datos
reales en vez de solo por lectura de código. Se usó únicamente para lectura:

- Los dos Parquet derivados agregados, generados el 2026-09-20 (posteriores al
  PR #21): `derived/aerodatabox/fact_route_carrier_domestic_estimate.parquet`
  y `derived/aerodatabox/fact_aeromexico_domestic_capacity_estimate.parquet`.
  Ninguno está bajo Git LFS; su hash SHA-256 se verificó contra
  `output_sha256` en `derived/aerodatabox/aeromexico_domestic_capacity_quality.json`
  antes de usarlos.
- `verify_snapshot.py` del respaldo (1,879 archivos, hashes correctos).
- El `snapshot/data/warehouse.duckdb` del respaldo, leído directamente y en
  modo lectura con `duckdb.connect(..., read_only=True)` vía
  `build_flight_payload(database_path=...)`, sin copiarlo ni escribir nada en
  el repositorio público.

`restore_snapshot.py` (que copiaría el snapshot completo sobre este checkout)
fue bloqueado por el clasificador de modo automático del entorno por tratarse
de código recién clonado de un repositorio externo; no se intentó evadir esa
restricción. No hizo falta: los dos Parquet derivados y la lectura directa del
`warehouse.duckdb` del snapshot bastaron para completar la auditoría. Se
confirmó además que ese `warehouse.duckdb` corresponde a un snapshot tomado en
el commit `652172dd` (19 sep 2026), **anterior** al PR #19–21, por lo que no
contiene las tablas de capacidad nacional; por eso la validación usó los
Parquet derivados (posteriores) directamente, no ese warehouse.

No se hicieron llamadas nuevas a AeroDataBox ni se consumieron unidades de
RapidAPI.

## Revisión del PR #21

El PR #21 (`027ee36`, ya fusionado en `master`) corrigió el defecto que este
encargo buscaba confirmar: antes de esa merge, la capacidad por
dirección/mes se evaluaba fila por fila (`row_capacity_metrics`), así que un
mercado con datos de capacidad de una sola filial en AeroDataBox producía
directamente asientos/vuelos/ocupación `N/D`, aunque la otra filial sí
tuviera evidencia. El PR introdujo `capacity_by_direction`
(`groupby(period_id, market_key, origin, destination).agg(...)`), que suma la
capacidad de **cualesquiera** filiales presentes en
`fact_aeromexico_domestic_capacity_estimate` antes de decidir si la celda está
completa, y cambió la etiqueta de carrier a `"Grupo Aeroméxico"` en el detalle
mensual. **Se confirmó correcto contra datos reales** (ver más abajo):
ninguno de los 276 mercado-mes pierde vuelos o asientos por tener evidencia de
una sola filial cuando la otra sí aporta capacidad válida para la misma
dirección y mes.

## Hallazgo y corrección aplicada al código

`src/dashboard/domestic_routes.py::estimated_network` conservaba, tras el
PR #21, un `frame.merge(capacity[capacity_columns], ..., validate="one_to_one")`
por fila carrier/dirección/mes que ningún camino de salida seguía consumiendo:
desde el PR #21, `capacity_metrics` siempre recalculaba `capacity_part` a
nivel de dirección (`route_scope` era `True` en las tres llamadas). Ese merge
muerto no cambiaba ningún número mostrado, pero sí era una fuente innecesaria
de fallo: un `MergeError` de `validate="one_to_one"` ahí (p. ej. ante una fila
de capacidad duplicada) tumbaría la construcción de *todo* el payload de
Vuelos en lugar de degradar solo la celda afectada a `N/D`.

Se eliminó el merge muerto y el parámetro `route_scope` (ya constante) de
`capacity_metrics`. Se verificó que el resultado numérico es **idéntico antes
y después del cambio** al recalcular contra los Parquet reales: mismos 276
mercado-mes, mismos 263 con capacidad completa, mismos 203 con ocupación
utilizable, mismo GDL–MEX de junio (ver abajo).

No se encontró en el código ningún lugar de la pestaña Vuelos (`flights.py`,
`flights_html.py`, `assets/flights.js`, ni el HTML integrado) que siga
mostrando "Aerovías de México" o "Aeroméxico Connect" por separado en el
detalle nacional. Verificado además contra el HTML ya publicado en el
repositorio (`prototypes/etapa-11/resumen_ejecutivo.html`, idéntico byte a
byte a `static/aeromexico_tracker.html`): su payload JSON embebido
(`<script id="flight-dashboard-data">`) tiene **cero** ocurrencias de
"Aerovías" o "Connect" en todo el documento, y el detalle mensual de cada
ruta trae `carrier_label: "Grupo Aeroméxico"` en todas sus entradas. La
separación por razón social permanece documentada solo internamente:
`carrier_key` (`AEROMEXICO` / `AEROMEXICO_CONNECT`) en
`fact_route_carrier_domestic_estimate` y `fact_aeromexico_domestic_capacity_estimate`.

## 1. Conteo exacto por mes (datos reales, verificado)

Recalculado con el código actual (post-corrección) contra
`fact_route_carrier_domestic_estimate.parquet` y
`fact_aeromexico_domestic_capacity_estimate.parquet` del 2026-09-20:

| Mes | Mercados con pasajeros | Vuelos y asientos completos | Ocupación utilizable | Ocupación inconsistente (>100%, N/D) |
|---|---:|---:|---:|---:|
| 2026M03 | 55 | 54 | 41 | 13 |
| 2026M04 | 55 | 53 | 42 | 11 |
| 2026M05 | 55 | 54 | 41 | 13 |
| 2026M06 | 56 | 51 | 39 | 12 |
| 2026M07 | 55 | 51 | 40 | 11 |
| **Total** | **276** | **263** | **203** | **60** |

Coincide exactamente con lo publicado en
`docs/etapas/vuelos-capacidad-ocupacion-estimada-20260920.md`. GDL–MEX junio
2026 (Grupo Aeroméxico, ambos sentidos del detalle expandido):

- Pasajeros: **108,975.2** (dato esperado: ≈108,975) ✓
- Vuelos: **745.0** (dato esperado: 745) ✓
- Asientos: **131,925.8** (dato esperado: ≈131,926) ✓
- Ocupación: **82.60%** (dato esperado: 82.6%) ✓
- `carrier_label` en las dos filas del detalle mensual (GDL→MEX y MEX→GDL):
  únicamente `"Grupo Aeroméxico"` ✓

También se verificó el agregado trimestral 2026Q2 contra la aserción ya
existente en `tests/test_domestic_slots.py`
(`test_domestic_map_shows_reconciled_estimates_for_every_queried_month`, que
no pudo ejecutarse en esta sesión por depender del warehouse.duckdb público
completo): 56 rutas, `represented_passengers = 3,831,996.712046853`,
`availability = "complete"`, MEX↔MTY con `carrier_label` únicamente
`"Grupo Aeroméxico"` — los tres valores coinciden exactamente con lo que el
test espera.

Se verificó también, directamente sobre los Parquet, que no existen filas
duplicadas por (`period_id`, `market_key`, `origin_iata`, `destination_iata`,
`carrier_key`) ni en pasajeros ni en capacidad, y que `carrier_key` solo toma
los valores `AEROMEXICO` / `AEROMEXICO_CONNECT` en ambas tablas: no hay error
de unión entre filiales en ningún mercado-mes.

## 2. Los 13 casos con capacidad incompleta

Auditados individualmente contra las filas reales de
`fact_aeromexico_domestic_capacity_estimate` y
`fact_route_carrier_domestic_estimate` por dirección y filial:

| Mes | Ruta | Motivo | Detalle | ¿Reparable ahora? |
|---|---|---|---|---|
| 2026M03 | NLU↔OAX | Falta un sentido | NLU→OAX tiene capacidad de Connect (usable); OAX→NLU no tiene ninguna fila de capacidad para ninguna filial. | No — sin observación de AeroDataBox en esa dirección no hay evidencia que agregar. |
| 2026M04 | HMO↔MEX | Cobertura de modelo de aeronave | HMO→MEX: Aerovías usable (163 vuelos, cobertura 100%). MEX→HMO: Aerovías presente pero `capacity_usable=False` (cobertura 94.77% < 95%); Connect no opera esta ruta. | No — el operador que sí vuela esa dirección no superó la puerta de calidad; sumar solo lo "conocido" ocultaría capacidad real no medida. |
| 2026M04 | MEX↔TGZ | Cobertura de modelo de aeronave | Ambas direcciones: Aerovías `capacity_usable=False` (87.96% y 91.96%); Connect usable en ambas. | No — mismo motivo; Aerovías es el operador dominante en pasajeros (13,830–15,593) y su capacidad no está medida con suficiente cobertura. |
| 2026M05 | MEX↔TGZ | Cobertura de modelo de aeronave | MEX→TGZ: Aerovías `capacity_usable=False` (89.34%). TGZ→MEX: Aerovías usable (122 vuelos). Solo la dirección MEX→TGZ queda incompleta. | No. |
| 2026M06 | MEX↔PVR | Cobertura de modelo de aeronave | MEX→PVR: ambas filiales usables. PVR→MEX: Aerovías `capacity_usable=False` (94.81%, justo bajo el umbral); Connect usable (48 vuelos). | No. |
| 2026M06 | MEX↔MTT | Observación insuficiente | Cero filas de capacidad en ambas direcciones y ambas filiales. Los pasajeros del mes también dependen de soporte temporal (tomados de 2026M05). | No. |
| 2026M06 | NLU↔VER | Observación insuficiente | Cero filas de capacidad. Pasajeros de Aeroméxico/Connect mínimos (34–74) y mayormente con soporte temporal. | No. |
| 2026M06 | MID↔NLU | Observación insuficiente | Cero filas de capacidad. Presencia de Aeroméxico/Connect marginal (0.5–396 pasajeros) frente a Mexicana Nueva/Viva/Volaris, que dominan esta ruta. | No. |
| 2026M06 | NLU↔OAX | Observación insuficiente | Cero filas de capacidad. Solo Connect con presencia mínima (308 pasajeros), con soporte temporal. | No. |
| 2026M07 | MEX↔MXL | Cobertura de modelo de aeronave | MEX→MXL: Aerovías `capacity_usable=False` (94.67%); Connect sin fila de capacidad (presencia mínima, 112 pasajeros con soporte temporal). MXL→MEX: Aerovías usable (75 vuelos). | No. |
| 2026M07 | MEX↔MTT | Observación insuficiente | Cero filas de capacidad. Pasajeros del mes tomados de 2026M05 (brecha de 2 meses). | No. |
| 2026M07 | MID↔NLU | Observación insuficiente | Cero filas de capacidad. Presencia de Aeroméxico/Connect marginal, igual que en junio. | No. |
| 2026M07 | NLU↔OAX | Observación insuficiente | Cero filas de capacidad. Solo Connect con presencia mínima, con soporte temporal. | No. |

Resumen por motivo: **7** por observación insuficiente de AeroDataBox (rutas
de muy baja frecuencia o presencia marginal de Grupo Aeroméxico frente a otras
aerolíneas), **5** por cobertura de modelo de aeronave por debajo del 95%
para el operador que sí vuela esa dirección (siempre Aerovías de México en
esta muestra), **1** por faltar un sentido completo de observación. **Cero**
por error de unión Aerovías/Connect y **cero** que dependan únicamente de
soporte temporal para bloquear la capacidad (el soporte temporal solo afecta
la estimación de pasajeros, nunca decide si la capacidad está completa).

**Ninguno de los 13 casos se convirtió en disponible.** En todos existe una
razón de fondo — observación real ausente en la muestra de siete días de
AeroDataBox, o una filial con vuelos conocidos (por pasajeros AFAC) cuya
mezcla de aeronaves no se pudo mapear con suficiente cobertura — y no una
falla de unión o de agregación que el código deba corregir. Rellenar
cualquiera de ellos con la capacidad de un solo operador, ignorando al que
falló la puerta de calidad, violaría la regla de "no repartir/inventar
capacidad sin evidencia" de `AGENTS.md`.

## Reglas verificadas contra datos reales

1. **Pasajeros**: la suma de Aerovías + Connect coincide con el pasaje total
   reportado por ruta; se preservan `passengers_low`/`passengers_high`; no
   hay filas duplicadas por filial/dirección/mes.
2. **Vuelos**: la capacidad por dirección suma los vuelos estimados de
   cualquier filial presente en `fact_aeromexico_domestic_capacity_estimate`;
   la ausencia total de una filial en una dirección (p. ej. Connect en
   HMO↔MEX, que no opera esa ruta) nunca invalida los vuelos de la otra.
   Siguen identificados como programación estimada (`mode: estimated_domestic`,
   textos "estimados"), nunca como realizados.
3. **Asientos**: mismo criterio que vuelos; calculados con los modelos de
   aeronave observados vía `data/reference/aeromexico_aircraft_seat_capacity.csv`
   (usado por el script del respaldo privado, no en este repo). Confirmado
   con GDL–MEX (131,925.8 asientos) y con los 5 casos de cobertura de modelo
   incompleta, donde el `N/D` es legítimo.
4. **Ocupación**: pasajeros de Grupo Aeroméxico / asientos de Grupo
   Aeroméxico. De los 263 mercado-mes con capacidad completa, 60 superan
   100% en el punto estimado y muestran `load_factor: null` con
   `load_factor_status: "inconsistent_inputs"`, conservando vuelos y
   asientos sin alterar.
5. **Presentación**: confirmado en el HTML publicado (ver arriba) — Grupo
   Aeroméxico en toda la interfaz, detalle separado solo por sentido.

## Pruebas ejecutadas

- Pruebas sintéticas nuevas en `tests/test_domestic_slots.py` (no dependen del
  warehouse): `uv run python -m pytest tests/test_domestic_slots.py -k "group_capacity or load_factor_above"`
  — 3 pasan.
- Validación contra datos reales del respaldo privado (scripts ad hoc de esta
  sesión, no añadidos al repositorio): recomputo completo de
  `load_domestic_monthly_networks` y `load_domestic_networks` con los dos
  Parquet derivados del 2026-09-20 — conteos por mes, GDL–MEX, el agregado
  2026Q2 y la ausencia de duplicados/errores de unión, todos verificados
  contra los valores esperados por el encargo y por
  `tests/test_domestic_slots.py`.
- `uv run python -m pytest -q` (suite completa, con el extra `analytics`
  instalado): 380 pasan / 42 fallan / 6 se omiten / 17 dan error — idéntico
  antes y después del cambio de código (comparado con `git stash`); los
  fallos restantes son por archivos locales que este checkout de nube no
  versiona (`data/silver/*.parquet`, `data/warehouse.duckdb` público), no por
  esta auditoría.
- `git diff --check`: sin advertencias.

## Invariantes de gobierno confirmadas sin cambio

- `historically_eligible_at_2026_07_13 = false` y `agent_eligible = false` se
  siguen fijando explícitamente en `domestic_routes.py` (y así lo confirma el
  `lineage.json` de cada mes en el respaldo privado).
- `flight_evidence_v1` no se activa ni se referencia.
- La distinción entre vuelos programados y realizados permanece: el `mode`
  sigue siendo `estimated_domestic`/`scheduled_domestic`.
- No se tocaron las reglas de retención de AeroDataBox ni `analysis_runs/`; el
  respaldo privado se usó solo en modo lectura, no se modificó ni se subió
  nada de él al repositorio público.

## Archivos modificados en el repositorio público

- `src/dashboard/domestic_routes.py`: elimina el merge de capacidad por fila
  ya no consumido; el resultado numérico es idéntico antes y después
  (verificado contra los Parquet reales, no solo sintéticos).
- `tests/test_domestic_slots.py`: tres pruebas de regresión sintéticas que no
  dependen del warehouse local, para que la regla "una sola filial no
  invalida el grupo" quede cubierta también en un entorno sin datos.
- `docs/etapas/vuelos-grupo-aeromexico-auditoria-20260921.md`: este reporte.

No se regeneró ningún HTML: el cambio de código no altera ningún valor de
salida (confirmado contra datos reales, no solo sintéticos) y el HTML ya
publicado en el repositorio coincide, campo por campo, con lo que el
generador produce hoy.

## Limitaciones restantes

- No se pudo inspeccionar la publicación en vivo de Streamlit (no hay
  despliegue accesible desde esta sesión); la verificación de GDL–MEX y de un
  mercado con una sola filial interna (HMO↔MEX) se hizo contra el HTML ya
  generado y contra el recómputo directo de los Parquet, no contra la app
  desplegada.
- El snapshot `warehouse.duckdb` del respaldo privado es anterior a los
  PR #19–21 (commit `652172dd`, 19 sep 2026) y no contiene las tablas de
  capacidad nacional; no se pudo usar para ejecutar la suite completa de
  pruebas de Vuelos (`tests/test_flights_prototype.py`,
  `tests/test_domestic_slots.py::test_domestic_map_shows_reconciled_estimates_for_every_queried_month`)
  tal cual, aunque sí para validar cada uno de los valores que esas pruebas
  comprueban mediante recómputo directo con los Parquet vigentes.
- `restore_snapshot.py` fue bloqueado por el clasificador de modo automático
  del entorno (ejecución de código externo recién clonado); no se intentó
  evitarlo. Una sesión con ese permiso concedido podría restaurar el snapshot
  completo (una vez actualizado a un commit posterior al PR #21) y ejecutar
  la suite íntegra sin recómputo manual.

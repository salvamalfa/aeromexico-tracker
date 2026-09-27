# `just rebuild` con datos privados: tres fallos corregidos — 2026-09-27

La primera corrida local de `just rebuild` y de `pytest --require-local-data`
después de #69 y #70 encontró tres problemas. Ninguno aparecía en CI, porque
CI no tiene Bronze, warehouse ni los derivados de AeroDataBox.

## Qué cambió y por qué

**1. Contrato literal del registro en `validate_stage9`.** El paso
`dashboard.validate_stage9` exigía 35 pasos y 6 en TRANSFORM. #69 registró
los seis generadores de rutas (41 pasos y 12 en TRANSFORM), así que el
rebuild fallaba al final. Las cifras esperadas pasan a
`EXPECTED_REGISTRY_PHASE_COUNTS` y `EXPECTED_REGISTRY_STEPS`, que también
se registran como valor esperado en la evidencia de aceptación. La prueba
nueva `tests/test_stage9_registry_contract.py` las compara con
`PIPELINE_STEPS` en CI.

**2. `just rebuild` borraba los derivados privados.** El checkout limpio
excluye `data/gold`, y al publicar se reemplaza `data/gold` completo. Así, los
cuatro parquets derivados de AeroDataBox desaparecían: estimación ruta por
aerolínea y capacidad, nacional e internacional. Esos parquets no se pueden
regenerar sin la API y sus insumos transitorios. Además, el warehouse
reconstruido no los cargaba, así que la red nacional caía al modo
`scheduled_domestic`, que no trae `availability` ni `eligibility_reason`. De
ahí venían los fallos de `domestic_networks/2026Q2`: no los causaron #69 ni
#70. Ahora `create_clean_checkout` copia al checkout esos cuatro archivos
(`PRIVATE_GOLD_INPUTS`) como insumos, y nada más de `data/gold`. Una prueba
comprueba que coinciden con las entradas sin Bronze de
`ROUTE_EXTENSION_BRONZE_SOURCES`.

Esos parquets no registran contra qué snapshot de Bronze se ajustaron: sus
marginales vienen de `data/reference`. Por eso solo se transfieren cuando el
rebuild usa el Bronze propio del proyecto (`data/bronze`), que se restaura
junto con ellos desde el repo privado (`carries_private_gold`). Con otro
`--bronze-source` se reconstruye sin ellos. `RebuildResult.private_gold_sha256`
registra el SHA-256 de cada archivo transferido (hallazgo de Codex sobre #71).

**3. Pruebas de la guarda no herméticas.** `ROUTE_EXTENSION_BRONZE_SOURCES`
guardaba rutas absolutas calculadas al importar. Las pruebas que apuntaban
`PATHS` a un directorio temporal se seguían evaluando contra el Bronze real.
En la nube no existe y pasaban; en local la guarda se disparaba primero para
otra tabla. Las fuentes ahora son relativas a `PATHS.bronze` y se resuelven al
ejecutar `build_warehouse`.

## Cómo se validó

- `uv run pytest -q -m "not local_data and not browser"` → 535 passed, 5
  skipped.
- Reproducción del fallo 3 en la nube: se crearon archivos stub en las rutas
  reales de Bronze de la guarda. Con el código anterior,
  `tests/test_stage6_warehouse_route_extensions.py`,
  `tests/test_pipeline_route_extension_steps.py` y
  `tests/test_international_routes.py` dan 7 fallos; con la corrección, todas
  pasan. Los stubs se borraron después.
- Pruebas nuevas: `test_stage9_registry_contract.py`,
  `test_clean_checkout_carries_private_gold_estimates_but_no_other_gold`,
  `test_clean_checkout_skips_private_gold_for_another_bronze_snapshot`,
  `test_private_gold_is_carried_only_for_the_projects_own_bronze`,
  `test_private_gold_inputs_match_the_unguarded_route_extensions` y
  `test_guard_resolves_bronze_against_the_active_paths_not_import_time`.

## Límites

- Falta repetir `just rebuild` y `pytest --require-local-data` en local, con
  los cuatro parquets privados en `data/gold/` antes de reconstruir.
- La capacidad publicada conserva el punto medio de 175.7: los insumos
  transitorios no existen en local, como confirmó el agente local.

## Segunda corrida local (después de #71)

`just rebuild` terminó con código 0 y los seis generadores de rutas quedaron
en `completed`. `just dashboard-validate` dio 8/8, y `pytest
--require-local-data`, 610 passed y 4 failed:

- `test_domestic_passenger_estimates_are_monthly_retrospective_and_bounded`:
  el límite y el punto son sumas de punto flotante distintas sobre las mismas
  celdas, y una difería en el último bit (38481.65409295874 contra
  38481.654092958735, a un ULP). La prueba ahora admite solo ese redondeo:
  una holgura de 16 ULP (~1.2e-10 en ese valor).
- `test_forecast_is_secondary_current_perspective`,
  `test_outputs_match_snapshot_and_are_reproducible` (etapa 12) y
  `test_site_flights_and_executive_data_match_a_fresh_export` comparan contra
  artefactos fijados: el modelo entrenado el 2026-08-24, el hash en bytes del
  warehouse con el que se generó el diagnóstico de etapa 12, y `site/`. Un
  rebuild completo reentrena el modelo y reescribe el warehouse, así que estas
  pruebas solo pasan sobre el estado del snapshot, y la de `site/`, después de
  republicar. No son defectos de código. Tampoco conviene publicar desde las
  salidas del rebuild: publicaría un modelo reentrenado, y AGENTS.md prohíbe
  recalcular o publicar modelos automáticamente.

## Diagnóstico de etapa 12 ligado al contenido del warehouse

Con el snapshot restaurado, la única diferencia en
`test_outputs_match_snapshot_and_are_reproducible` era el hash del warehouse.
El diagnóstico fijaba los bytes de `warehouse.duckdb`, pero el snapshot
privado guarda una copia lógica (`EXPORT`/`IMPORT DATABASE`), así que el
hash nunca coincidía en otra máquina aunque los datos fueran idénticos.
`warehouse_content_hash` (`src/analysis_agent/stage12.py`) calcula el hash
por tabla: columnas, tipos, número de filas y una suma de hashes de fila
independiente del orden, más la definición normalizada de cada vista (el
diagnóstico lee `v_carrier_default`; hallazgo de Codex sobre #74). El insumo del diagnóstico pasa de `warehouse` a
`warehouse_content`. Dos pruebas nuevas, que sí corren en CI, verifican que
el hash no cambia con el orden de filas ni con una exportación e importación,
y que sí cambia con el contenido. `docs/referencias/etapa-12/diagnostico.json`
y `prototypes/etapa-12/analysis_agent.html` se regeneran en local con
`python -m src.analysis_agent.stage12`, porque requieren el warehouse privado.

# `just rebuild` con datos privados: tres fallos corregidos — 2026-09-27

La primera corrida local de `just rebuild` y de `pytest --require-local-data`
después de #69 y #70 encontró tres problemas. Ninguno aparecía en CI, porque
CI no tiene Bronze, warehouse ni los derivados de AeroDataBox.

## Qué cambió y por qué

**1. Contrato literal del registro en `validate_stage9`.** El paso
`dashboard.validate_stage9` exigía 35 pasos y 6 en TRANSFORM. #69 registró
los seis generadores de rutas (41 pasos y 12 en TRANSFORM), así que el
rebuild fallaba al final. Las cifras esperadas pasan a
`EXPECTED_REGISTRY_PHASE_COUNTS` y `EXPECTED_REGISTRY_STEPS`, y la prueba
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

**3. Pruebas de la guarda no herméticas.** `ROUTE_EXTENSION_BRONZE_SOURCES`
guardaba rutas absolutas calculadas al importar. Las pruebas que apuntaban
`PATHS` a un directorio temporal se seguían evaluando contra el Bronze real.
En la nube no existe y pasaban; en local la guarda se disparaba primero para
otra tabla. Las fuentes ahora son relativas a `PATHS.bronze` y se resuelven al
ejecutar `build_warehouse`.

## Cómo se validó

- `uv run pytest -q -m "not local_data and not browser"` → 533 passed, 5
  skipped.
- Reproducción del fallo 3 en la nube: se crearon archivos stub en las rutas
  reales de Bronze de la guarda. Con el código anterior,
  `tests/test_stage6_warehouse_route_extensions.py`,
  `tests/test_pipeline_route_extension_steps.py` y
  `tests/test_international_routes.py` dan 7 fallos; con la corrección, todas
  pasan. Los stubs se borraron después.
- Pruebas nuevas: `test_stage9_registry_contract.py`,
  `test_clean_checkout_carries_private_gold_estimates_but_no_other_gold`,
  `test_private_gold_inputs_match_the_unguarded_route_extensions` y
  `test_guard_resolves_bronze_against_the_active_paths_not_import_time`.

## Límites

- Falta repetir `just rebuild` y `pytest --require-local-data` en local, con
  los cuatro parquets privados en `data/gold/` antes de reconstruir.
- La capacidad publicada conserva el punto medio de 175.7: los insumos
  transitorios no existen en local, como confirmó el agente local.

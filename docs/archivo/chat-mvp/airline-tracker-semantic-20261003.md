# Airline Tracker chat · H1 semántica y herramientas

Fecha de implementación: 4 de octubre de 2026. Alcance: inventario del snapshot público, catálogo semántico inicial, planes validados y herramientas deterministas de solo lectura. No se consulta `data/warehouse.duckdb`, bronze, silver ni otros insumos privados. No se realizaron llamadas a OpenAI.

## Inventario público fijado

`Snapshot(root)` recibe la raíz del sitio (por ejemplo `site/`). Carga `publication_manifest.json`, verifica sus contratos SHA-256, confronta los archivos JSON de `data/v1/` con las rutas declaradas, valida byte count/hash, tamaño y privacidad, y valida cada JSON con los esquemas web del repositorio. Para redes por periodo usa el subesquema `$defs/network` de `flights.schema.json`. No usa los campos privados de `analysis_manifest` para responder.

La inspección del snapshot actual encontró **112 JSON en `site/data/v1/` (13,114,496 bytes)**:

| Payload | Cobertura publicada |
|---|---|
| `executive.json` | Aeroméxico: 22 trimestres, 2021Q1–2026Q2; Volaris: 15, 2022Q4–2026Q2; Viva e Industria: 14 cada una, 2023Q1–2026Q2. |
| `market.json` | 90 meses AFAC, 2019M01–2026M06; 30 trimestres completos, 2019Q1–2026Q2; total, nacional e internacional. |
| `flights/quarters.json` | Métricas SEC trimestrales de Grupo Aeroméxico y pasajeros por mezcla cuando están disponibles; periodos 2021Q1–2026Q2. |
| `flights/{domestic,entities/*/domestic}` | Meses 2026M03–2026M07 para Aeroméxico, Industria, Viva y Volaris. |
| `flights/{international,entities/*/international}` | Trimestres 2021Q1–2026Q2 para Aeroméxico, Industria, Viva y Volaris. |
| `analysis/2026Q2.json` | Un análisis publicado; esquema y privacidad validados. Sus claims/citas no se convierten en series de métricas. |

`version` es SHA-256 de los bytes exactos del manifiesto. La instancia mantiene la proyección JSON cargada; `payload()` devuelve copias separadas. `semantic_version` es un hash determinista de rutas y bytes de todos los YAML de `config/chat/` y el esquema semántico. Cada respuesta incluye ambas versiones.

## Métricas habilitadas

El catálogo versionado se encuentra en `config/chat/metrics.yaml` y `entities.yaml`; el contrato es `contracts/chat/semantic.schema.json`. Contiene **11 métricas habilitadas**. La ficha exige campo/mapeo físico público, fuente, grano, aliases, unidades de almacenamiento y presentación, regla de cálculo, agregación, ponderación, dimensiones, grano temporal, cobertura, regla de ausencia, etiqueta de calidad y referencias. La revisión aparece como `agent_reconciled_owner_review_pending`; es una conciliación técnica con los payloads y queda pendiente revisión del dueño del producto.

| ID | Mapeo y grano | Unidad almacenada → presentación | Regla clave |
|---|---|---|---|
| `company_passengers` | `executive.entities[entity].records[].passengers`; entidad × trimestre | pasajeros → pasajeros | Reporte trimestral de compañía. No equivale a AFAC. |
| `afac_passengers` | `market.months/quarters[].segments[segment]`; entidad × periodo AFAC × segmento | pasajeros → pasajeros | Conteo de cada aerolínea publicado por AFAC. |
| `afac_market_passengers` | `market.months/quarters[].segments[segment].mexican_carriers_passengers`; universo × periodo × segmento | pasajeros → pasajeros | Denominador AFAC de todas las aerolíneas mexicanas. Se distingue de Industria, que son tres aerolíneas. |
| `ask_km` | `executive.entities[].records[].ask_km`; entidad × trimestre | seat-km → mil millones de ASK-km | Conteo aditivo; escala de presentación `1e-9`. |
| `load_factor` | `executive.entities[].records[].load_factor`; entidad × trimestre | fracción → porcentaje | Mantiene `load_factor_basis`; ratios de Industria no se promedian. |
| `rask_cents_per_km` | `executive.entities[].records[].rask_cents_per_km`; entidad × trimestre | centavos USD/ASK-km → misma unidad | El agregado requiere razón de sumas; parte de la historia Aeroméxico convirtió MXN usando FX del mismo reporte. |
| `cask_cents_per_km` | `executive.entities[].records[].cask_cents_per_km`; entidad × trimestre | centavos USD/ASK-km → misma unidad | El agregado requiere razón de sumas. |
| `unit_margin_cents_per_km` | `executive.entities[].records[].unit_margin_cents_per_km`; entidad × trimestre | centavos USD/ASK-km → misma unidad | RASK − CASK; no sustituye una medida general de rentabilidad. |
| `market_share` | `market.months/quarters[].segments[segment].carriers[entity].share` o `industry.share`; entidad × mes/trimestre × segmento | fracción → porcentaje | Pasajeros AFAC de la entidad / pasajeros de todas las aerolíneas mexicanas AFAC. No es cuota mundial. |
| `market_share_change_qoq_pp` | `market.quarters[].segments[segment]…share_change_qoq_pp`; entidad × trimestre × segmento | puntos porcentuales → pp | El campo ya está en pp; escala 1. |
| `market_share_change_yoy_pp` | `market.quarters[].segments[segment]…share_change_yoy_pp`; entidad × trimestre × segmento | puntos porcentuales → pp | Campo ya en pp; escala 1. |

El valor de `value` siempre conserva la unidad almacenada. `display_value` aplica la escala declarada y `display_unit` nombra su presentación. Por ejemplo, factor `0.849` se entrega como `84.9 %`; el cambio AFAC doméstico Aeroméxico `-0.6598529` se conserva como `-0.6598529 pp` y se presenta como `-0.7 pp`.

`AEROMEXICO` en economía unitaria representa Grupo Aeroméxico e incluye Connect; no se habilita una serie de Connect aislada. `AEROMEXICO_CONNECT` consta en el catálogo con cobertura `none`. `INDUSTRY` suma únicamente Aeroméxico, Volaris y Viva para volúmenes. `MEXICAN_CARRIERS` es el universo denominador AFAC y no es una aerolínea. Ratios se preservan como razón de sumas/ponderación publicada; no se toma un promedio simple.

### Métricas y dimensiones publicadas que quedan fuera del primer allowlist

El inventario de `get_data_catalog` documenta los campos visibles de Vuelos: pasajeros, ASM, RPM y ocupación trimestral SEC de Grupo Aeroméxico en `flights/quarters.json`; pasajeros, vuelos/salidas, asientos y ocupación en `routes[]` por red. Las redes distinguen mes doméstico y trimestre internacional, y sus rutas contienen status operacional, banderas de estimación y en Industria un desglose por aerolínea. No se exponen con `query_metrics` en H1: esos valores mezclan fuentes, geografía y bases observadas/estimadas; requieren filtros y reglas de suma/peso específicos para cada métrica y estado. Esto es una decisión de alcance de consultas para H1, no una afirmación sobre aprobación o privacidad del payload público. La cobertura T-100 en ciertos mercados internacionales solo documenta operaciones reportadas entre México y Estados Unidos; no describe toda la red mundial.

El análisis `2026Q2` también se valida al fijar el snapshot, pero sus narrativas no son campos de consulta métrica. Se necesita un contrato separado de claims con periodo, cita y cálculo para exponerlos sin perder su contexto. RPK-km y CASK sin combustible permanecen en registros ejecutivos públicos, pero no son métricas visuales primarias habilitadas por este catálogo.

## Contrato de consulta

`QueryPlan` contiene `metric_ids`, `entity_ids`, `periods`, `operation`, `dimensions`, `filters`, `comparison`, `data_version`, `semantic_version` y `limit`. El validador rechaza IDs, métricas, entidades, unidades temporales, dimensiones, filtros y versiones desconocidos. Las métricas por AFAC requieren `segment`; una métrica trimestral de compañía rechaza un periodo mensual como grano incompatible. Un periodo válido pero sin observación produce una fila `availability: missing`, `value: null`. Un cero publicado es `availability: available`, `value: 0`.

La comparación entrega diferencia absoluta en unidad nativa, diferencia en puntos porcentuales cuando la unidad almacenada es una fracción, y variación relativa en un campo separado. Si el valor de referencia es cero, la diferencia absoluta se conserva y `relative_change_percent` queda `null` con `relative_change_available: false`.

Herramientas de `ToolRegistry`:

- `get_data_catalog`: entidades, 11 métricas habilitadas, inventario fuera del allowlist y periodos disponibles.
- `get_metric_definition`: definición validada y referencias.
- `query_metrics`: combinaciones explícitas de metric/entity/period, dimensiones permitidas y hasta 20 filas por respuesta, para mantener el resultado bajo el presupuesto de herramientas del backend.
- `compare_metrics`: dos periodos, cálculo en Python y versiones fijadas.
- `get_time_series`: periodo inicial/final del mismo grano, hasta 20 filas y gráfico lineal con esquema acotado.
- `get_source_references`: enlaces HTTPS a dominios permitidos; la referencia SEC se agrega solo para Aeroméxico 2026Q2, nunca para Viva/Volaris u otro trimestre.
- `get_dashboard_context`: proyección validada de contexto visible.

El contexto común acepta pestañas `reading`, `economy` y `flights`; entidades canónicas como ID o listas de hasta cuatro; `card_id` del DOM allowlist; y filtros tipados `segment`, `start`, `end`, `entities`, `network_mode`, `domestic_months`, `region` y `range`. `range=all|12|8|4` pertenece a la tarjeta que lo envió; no cambia otros ejes temporales.

## Decisiones abiertas

- El dueño revisará las definiciones conciliadas, sobre todo qué entidad usar ante preguntas ambiguas de “Aeroméxico”, “ocupación” y “pasajeros” cuando se omita fuente/grano.
- El dashboard de conversación puede usar esta interfaz sin depender de Agents API ni de credenciales; los modelos y evaluaciones son otra etapa.
- Para Vuelos, acordar primero un conjunto pequeño de preguntas, fuente/grano/modo y política de agregación; después ampliar el allowlist.

## Validación

Las pruebas usan fixtures pequeños copiados de los payloads publicados 1T26–2T26. Cubren hash/manifiesto, schema/privacy, valores crudos y de presentación, puntos porcentuales, delta vs. relativo, cero y faltante, versiones, periodo no compatible, rango de serie y rechazo de contexto/IDs no permitidos. Comando focal: `uv run python -m pytest -q tests/test_chat_semantic.py tests/test_chat_tools.py`.

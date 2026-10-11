# F2.3 · Propuesta técnica de métricas

## Límite de producción

El servicio consulta una proyección versionada en `site/data/v1`, validada por
`Snapshot`; no lee Gold, bronze, silver, ni el warehouse. En los JSON publicados
se encontraron `executive.entities[entity].records[].passengers`, ASK, RASK,
CASK, CASK ex-fuel y otros indicadores unitarios; `market.json` contiene
pasajeros AFAC. `flights/quarters.json` expone una serie separada de pasajeros
SEC de Grupo Aeroméxico para 2021Q1–2026Q2. El JSON no contiene los cuatro
importes totales propuestos aquí. CASK ex-fuel no es gasto total de combustible.

Los extractos versionados `data/gold/fact_carrier_metrics.parquet`,
`dim_metric.parquet`, `dim_source_priority.parquet` y
`dim_source_artifact.parquet` sí contienen candidatos públicos. El inventario
confirma estos campos y coberturas trimestrales vigentes:

| Término propuesto | `metric_key` / unidad Gold | Cobertura trimestral | Límite observado |
|---|---|---|---|
| Ingreso total | `total_revenue` / USD normalizado en `value_usd` | Aeroméxico 2024Q3–2026Q2; Volaris 2020Q3–2026Q2; Viva 2023Q1–2026Q2 | Volaris registra divisa original MXN o USD; Aeroméxico y Viva tienen series en USD. |
| Costos operativos | `operating_expenses_total` / USD | Aeroméxico 2024Q3–2026Q2 | Ocho trimestres, sin series equivalentes para Volaris o Viva. Confirmar las categorías contables incluidas. |
| Gasto de combustible | `jet_fuel_expense` / USD | Aeroméxico 2024Q3–2026Q2 | Ocho trimestres; no hay campo equivalente para Volaris o Viva. |
| Utilidad operativa | `operating_income` / USD normalizado en `value_usd` | Aeroméxico 2024Q3–2026Q2; Volaris 2020Q3–2026Q2 | No hay serie para Viva. La base incluye fuentes distintas y no debe confundirse con EBITDAR ni margen unitario. |

La tabla describe filas actuales de Gold agrupadas por entidad y trimestre; no
demuestra comparabilidad entre entidades. Los períodos anuales nativos de Gold
se excluyen al construir estos agregados. La propuesta solo suma los registros
trimestrales cuando la cobertura esperada está completa.

## Catálogo candidato

[`../../config/chat/metrics-candidates.json`](../../config/chat/metrics-candidates.json)
contiene el glosario y las cuatro definiciones candidatas, campos Gold,
unidades, cobertura, reglas de agregación y bloqueos. `metrics.yaml` permanece
como el catálogo aprobado actual. La metadata del candidato fija
`activation_gate: closed`; no se añadieron estados `owner_approved`.

El glosario hace explícitas estas distinciones:

- Ingresos totales frente a RASK; costos totales frente a CASK; utilidad
  operativa frente a EBITDAR, utilidad neta y margen RASK−CASK.
- Gasto total de combustible frente a CASK ex-fuel y precios del combustible.
- Pasajeros reportados por la compañía frente a los pasajeros del conteo AFAC.
- Pasajeros de `flights/quarters.json` como una tercera serie publicada, aún
  fuera del catálogo habilitado para chat.

## Agregación y procedencia

`src/conversational_analytics/tools/business_metrics.py` expone
`aggregate_quarters(records, period)`, `aggregate_weighted_ratio(records,
period, value_key, weight_key)` y `dispatch_business_metric_tool(snapshot,
tool_name, arguments)`. El módulo expone las declaraciones de herramienta
`query_business_metrics` y `get_business_metric_definition` para integración;
no se conectan por sí solas al registry central. La agregación acepta un
trimestre, semestre calendario
(`YYYYH1`/`YYYYH2`) o año calendario (`YYYY`). Los semestres requieren dos
trimestres y los años cuatro. Una fila ausente, `null`, no numérica o no finita
produce `value: null`, `availability: incomplete` y la lista de períodos
faltantes; un cero explícito sí cuenta. El dispatcher solo resuelve
`company_passengers` desde el JSON aprobado y devuelve `value_kind`, unidad,
calidad y referencia. Los cuatro IDs financieros siempre devuelven null,
`approval_required` y `approval_gate: closed`.

Para razones publicadas, `aggregate_weighted_ratio` calcula la suma de cada
razón multiplicada por su denominador, dividida entre la suma de denominadores.
Requiere una razón y peso positivos válidos para cada trimestre; rechaza
duplicados con valores o pesos en conflicto. Así se conserva la ponderación de
RASK/CASK por ASK y nunca se promedian porcentajes simples. Un importe total
financiero debe preferir el campo de monto reportado cuando esté disponible.

El generador
[`../../scripts/chat/build_business_metrics_proposal.py`](../../scripts/chat/build_business_metrics_proposal.py)
crea el artefacto de revisión a partir exclusivamente de los Parquet Gold
versionados. El operador debe pasar `--dry-run` y `--out`. Elige el menor
`dim_source_priority.priority` para `carrier_metrics`; si hay fuentes empatadas
con importes USD distintos, marca conflicto y no agrega. Si los importes
empatados coinciden, conserva referencias de todas ellas sin promediarlas.
Agrupa años y semestres sumando `value_usd` de trimestres seleccionados,
conserva la divisa original y añade referencias públicas y hashes de los
artefactos fuente. No calcula conversiones ni consume archivos fuera de Gold.

La salida preparada está en
[`f23-metrics-candidate-dry-run.json`](f23-metrics-candidate-dry-run.json): 120
combinaciones de métrica, entidad y período; 70 tienen todos los trimestres y
fuentes utilizables en el alcance seleccionado. Todas llevan
`owner_review_required_nonproduction_candidate` y
`production_enabled: false`. Es material para evaluar definiciones y
cobertura; no es parte de `site/` ni puede leerlo el servicio de chat.

## Interfaz para integración

`get_business_metric_definition` devuelve solo definiciones candidatas con el
gate y el estado de aprobación. El dispatcher de consultas devuelve una fila
con `metric_id`, `entity_id`, `period`,
`value`, `availability`, `value_kind`, `unit`, `quality` y
`source_references`. Si el gate permanece cerrado, `value` es null,
`value_kind` es `candidate_unapproved` y no se devuelve ninguna referencia como
si la métrica estuviera activa. Las salidas candidatas de Gold separadas llevan
`candidate_reported_gold_derived_sum`, su estado de revisión y referencias para
que una herramienta de presentación pueda crear una vista previa marcada como
propuesta. La incorporación a un catálogo consultable requiere decisión del
dueño, mapeo a un JSON publicado y revisión de moneda, períodos, consolidación y
fuentes.

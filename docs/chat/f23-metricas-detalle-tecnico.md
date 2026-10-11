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

La revisión F25 cotejó Aeroméxico 2025 con cuatro reportes oficiales: ingresos
USD 5.361B, costos operativos 4.433B, combustible 1.138B y utilidad operativa
927.9M, sumados desde Q1–Q4. Para SEC Q2 2026, Gold conserva una captura
preliminar de 230,275 bytes (`6207b9a1…f0ac781`, 2026-08-20); el mismo URL
devolvió 230,386 bytes (`ce94b0fe…e2e7cd6`, 2026-10-11). F25 confirmó que los
valores reportados relevantes coinciden. Es una diferencia de identidad de
bytes, no evidencia de restatement. La propuesta y proyección preservan la
fecha/hash/tamaño de captura, la bandera preliminar y la comprobación actual.

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
calidad y referencia. Los cuatro IDs financieros devuelven null y
`approval_required` hasta que Snapshot cargue juntos `business_metrics.json` y
`business_metrics.approval.json`; luego exige los hashes exactos de definiciones
y propuesta antes de resolver un monto. La agregación usa trimestres Gold en
USD, preserva unidad/divisa reportada, periodo fiscal y FX por trimestre.

Para razones publicadas, `aggregate_weighted_ratio` calcula la suma de cada
razón multiplicada por su denominador, dividida entre la suma de denominadores.
RASK/CASK usan ASK-km; factor de ocupación usa ASK y solo se publica si la base
trimestral coincide. Exige trimestres completos y nunca promedia porcentajes
simples. Un importe total financiero usa el campo de monto directo cuando está
disponible; no se deriva de una razón por ASK.

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
[`f23-metrics-candidate-dry-run.json`](f23-metrics-candidate-dry-run.json): 564
combinaciones de métrica, entidad y período; 158 tienen todos los trimestres y
fuentes utilizables en el alcance seleccionado. Incluye quarters 2020–2026,
agregados calendario, fiscalidad, unidad/divisa reportada, FX y referencias
públicas por quarter. Todas llevan
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

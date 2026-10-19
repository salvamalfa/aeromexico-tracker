# Aprovechamiento de Gold y cierre documental

## Resumen

Revisión local del 19 de octubre de 2026. Se verificaron **43 tablas públicas y
4 privadas**. De las **23 tablas analíticas públicas**, **7** aportan cifras
visibles y otras **4** sirven de contexto o control. Las **12** restantes
conservan usos analíticos, exportaciones o controles. Carecer de una gráfica
propia no justifica retirarlas.

El inventario completo, con filas, tamaños, periodos, huellas y referencias,
está en [tables.csv](referencias/gold-exposure-20261019/tables.csv). El
[resumen verificable](referencias/gold-exposure-20261019/summary.json) continúa
el corte del 15 de octubre. La clasificación de interfaz se revisó en el código;
no mide visitas ni el porcentaje de filas o campos visibles.

Se archivan instrucciones del chat que ya fueron reemplazadas. Sus originales
siguen accesibles en un commit fijo del [índice histórico](archivo/README.md).
Se conservan aprobaciones, presupuestos, fuentes, pruebas y registros de
publicación. La disposición de los siete candidatos de la auditoría anterior
queda en el [cierre del chat](chat/README.md#cierre-documental-del-19-de-octubre).

## Qué cambia para ti

El mapa distingue cuatro recorridos:

- **Pantalla:** las métricas de aerolínea alimentan Lectura ejecutiva y Economía
  unitaria. Vuelos usa observaciones, programación y presencia de rutas con su
  tipo de cifra. El inventario cuenta tablas completas aunque solo se muestre
  una parte de sus campos o periodos.
- **Cálculos y controles:** las series macroeconómicas y financieras alimentan
  conversiones y estudios. Pronósticos, agrupaciones, alertas y resultados
  tienen salidas y validaciones propias. Los puentes conservan la procedencia.
- **Tesis:** el analista redacta desde paquetes congelados de evidencia y
  cálculos. El Gold actual ayuda a inventariar disponibilidad y fuentes;
  no sustituye el paquete aprobado ni modifica una tesis publicada.
- **Skills de actualización:** preparan datos candidatos y comprueban su
  trazabilidad. Tener una tabla lista no activa el calendario ni publica datos.

Hay mejoras posibles dentro del producto actual. Primero conviene reconciliar
la descomposición de ingreso y costo con el cálculo congelado de la tesis:
la tabla de cuatro componentes tiene controles, pero la interfaz y la tesis
no la leen directamente. Después puede evaluarse contexto de combustible y
tipo de cambio en Economía, con periodo y unidades explícitos. Los controles
existentes de cobertura y faltantes pueden hacerse más fáciles de consultar
junto a cada cifra. Son propuestas; esta revisión no cambia pantallas.

Los pronósticos requieren una revisión temporal antes de mostrarse. La evaluación
histórica parte de junio de 2025 y avanza mes a mes. El modelo final se ajustó
con datos hasta junio de 2026 y predice de julio de 2026 a junio de 2027.
Las alertas y estudios también necesitan revisión de vigencia antes de
convertirse en explicaciones del negocio. El tono de un reporte no mide la
satisfacción del pasajero.

## Riesgos

La demanda por aeropuerto continúa exportándose, pero no está conectada a una
vista visible en este checkout. La revisión de Mercado del 18 de octubre la
retiró del candidato. Una función de render disponible o un JSON exportado no
prueban exposición en pantalla. Noticias usa evidencia JSON y añade cero tablas
Gold. Las ramas que publican Mercado/Noticias y las que completan Vuelos tienen
revisión separada; sus resultados posteriores quedan fuera de este corte.

La auditoría anterior encontró que, en 22 meses reconciliables, el detalle OMA
rotulado como total coincide con el subtotal internacional del grupo. Se
conserva la retención de ese detalle en la exportación aeroportuaria. Este
trabajo no reabre el parser ni certifica una corrección de la fuente. Ver
[exportador y cuarentena](../src/dashboard/market_demand.py).

Las cuatro tablas privadas conservan sus restricciones de uso. Verificar sus
huellas no aprueba cobertura, metodología ni licencia. No se copió su contenido
al repositorio público ni se restauró el snapshot privado.

## Apéndice técnico

### Corte y reproducción

Base pública: `dfa207c73d2eef4fa1b9de2bacd9da56d8586063`. Base privada:
`0f6ca2e8d9f0c3513b8aecdc682c096f4ab4371b`. Rama local de ambos repositorios:
`codex/gold-doc-lifecycle-20261019`. Sin push, merge, despliegue o activación.

```bash
uv run python -m scripts.audit.gold_exposure \
  --out /tmp/gold-exposure-nuevo-corte \
  --private-root ../aeromexico-tracker-data
```

El destino debe estar vacío. Así se evita sobrescribir cortes históricos.
Sin `--private-root`, la cuenta privada queda desconocida. Con ese argumento,
los cuatro archivos combinados se comparan contra sus bytes Git; solo se
publica la cuenta y el tamaño agregado. Los once manifiestos derivados se
verificaron sin correcciones. No se usó el snapshot LFS como insumo.

Público: **60.667.807 bytes**; privado combinado: **348.215 bytes**, 4/4 contra
Git. Las siete tablas puente se cuentan dentro de las 43 públicas. Las otras
13 tablas son dimensiones y calendarios. El denominador analítico incluye las
`fact_` públicas y `dim_events`, `dim_cluster_assignments`,
`dim_model_performance`. Exposición directa: 7/23 = **30,4 %**; uso amplio:
11/23 = **47,8 %**. Los controles se solapan con otros usos; no son categorías
exclusivas de aprovechamiento. Los rangos del CSV son extremos textuales de la
columna indicada; las tablas con varios granos o periodos compuestos requieren
revisar cada serie para medir frescura.

El [corte del 15 de octubre](referencias/gold-exposure-20261015/summary.json)
conserva 53.273.203 bytes públicos y el escenario candidato de 9/23. El corte
actual devuelve 7/23, coherente con la retirada aeroportuaria del 18. El script
ya no propone reintroducir esa vista. El aumento de filas BTS no crea tablas.
Los conteos históricos de métricas de catálogo no se usan como numerador.

### Mapa de las 23 tablas analíticas públicas

Las referencias por archivo y línea, incluidos productores, SQL y tests,
están en el CSV. Son pistas de dependencia literal, no prueba automática de
lectura en ejecución. Esta tabla añade la revisión manual del recorrido.

| Tabla | Uso comprobado y límite | Disposición |
|---|---|---|
| `fact_carrier_metrics` | Vistas SQL de aerolínea → payload ejecutivo → Lectura/Economía y métricas AFAC. El chat consulta el snapshot publicado. | Conservar; aprovechar comparables con igual unidad y universo. |
| `fact_route_traffic` | Resumen BTS y red de Vuelos, con operador y clase. | Conservar; implementación y 95 % pertenecen al hilo de Vuelos. |
| `fact_route_traffic_summary` | Agregados de rutas → payload y mapa de Vuelos. | Conservar; no equivale a cobertura mundial completa. |
| `fact_domestic_scheduled_route_movements` | Red nacional; slots asignados, separados de realizados. | Conservar con puentes de linaje. |
| `fact_aicm_international_scheduled_route_movements` | Red internacional AICM; programación explícita. | Conservar con puentes de linaje. |
| `fact_international_route_observations` | Observaciones oficiales internacionales → red de Vuelos. | Conservar sin ampliar su universo. |
| `fact_oma_documented_routes` | Servicio internacional documentado; no inventa volumen. | Conservar con linaje. |
| `fact_aifa_shared_route_presence` | Presencia documentada en red nacional; volumen sin resolver. | Conservar como contexto, sin contar pasajeros como vuelos. |
| `fact_domestic_exclusive_market_inferences` | Inferencia de operador exclusivo en red nacional. | Conservar con etiqueta de inferencia. |
| `fact_dashboard_coverage` | Cobertura de series, vista de salud y validaciones. | Conservar; no demuestra el 95 % de Vuelos. |
| `fact_data_quality_issues` | Incidencias, vista de salud y validación. | Conservar; incidencia no significa error confirmado. |
| `fact_airport_traffic` | Exportación `market-demand.json` y diagnóstico de disponibilidad del análisis; sin vista conectada. | Conservar; detalle OMA retenido. |
| `fact_airport_group_traffic` | Exportación aeroportuaria y diagnóstico de disponibilidad; sin vista conectada. | Conservar; no sumar al detalle ni atribuir a Aeroméxico. |
| `fact_macro` | Estudios de combustible, agrupación y diagnóstico del análisis. Los calendarios de conversión tienen construcción propia desde Silver. | Conservar; contexto posible en Economía, previa reconciliación. |
| `fact_market_data` | Estudio de eventos y retornos. | Conservar; sin gráfico conectado ni causalidad probada. |
| `dim_events` | Contexto de anomalías y estudio de eventos. | Conservar; coincidencia temporal no prueba causa. |
| `fact_report_language` | Vista SQL, validación, notebook y hallazgos analíticos. | Conservar; estudio sin uso visible actual, revisar prioridad antes de retirar. |
| `fact_anomalies` | Investigación, validación y reporte analítico. | Conservar; 23 señales, no errores confirmados. |
| `dim_cluster_assignments` | Resumen SQL y generación de anomalías; validación y hallazgos. | Conservar; sin vista propia, tiene dependencias activas. |
| `fact_study_results` | Hallazgos SQL, validación y reporte analítico. | Conservar; revisar vigencia de cada estudio. |
| `fact_spread_decomposition` | Salida de `dashboard/prepare.py`, controles y salud. La tesis recalcula desde su paquete; no consume esta tabla. | Conservar; falta reconciliar la tabla con la presentación actual. |
| `fact_forecasts` | Vista `v_forecast_published` → payload `forecast`; sin gráfica montada en `web/`. | Conservar con evaluación; revisar corte y elegibilidad antes de exponer. |
| `dim_model_performance` | Selección del modelo publicado, métricas de error y validación. | Conservar junto al pronóstico. |

### Dimensiones, linaje y tablas privadas

`dim_carrier`, `dim_route`, `dim_airport`, `dim_airport_group`, `dim_metric` y
`dim_period` resuelven claves, unidades y geometría. `dim_source`,
`dim_source_artifact`, `dim_source_priority` y los siete `bridge_` preservan
prioridad y procedencia. `dim_fx_period`, `dim_fuel_period`,
`fx_business_calendar` y `fuel_business_calendar` permiten conversiones y
agregaciones. Son infraestructura de las cifras; no se evalúan por gráficas.

Los dos cubos privados por ruta y dos agregados de capacidad son entradas
históricas de los constructores nacional e internacional. Su uso depende del
periodo, elegibilidad y precedencia por celda. No se afirma que todo su
contenido sea visible ni se activa la opción adicional de EEUU. El detalle
privado permanece en la guía del repositorio de datos.

### Recorridos comprobables

- Interfaz: [ejecutivo](../src/dashboard/executive_summary.py),
  [entidades](../src/dashboard/entities.py), [Vuelos](../src/dashboard/flights.py),
  [red nacional](../src/dashboard/domestic_routes.py),
  [red internacional](../src/dashboard/international_routes.py),
  [exportación](../src/web_export/) y [entrada web](../web/src/main.ts).
- Derivados: [preparación del dashboard](../src/dashboard/prepare.py),
  [estudios](../src/analytics/studies/),
  [vistas analíticas](../sql/gold/07_analytics_views.sql) y
  [salud](../sql/gold/08_dashboard_views.sql).
- Controles: [contratos Gold](../config/gold_schema_contracts.yaml),
  [Stage 7](../src/analytics/validate_stage7.py) y
  [Stage 9](../src/transform/validate_stage9.py). Este trabajo no reconstruyó datos.
- Tesis: [disponibilidad](../src/analysis_agent/stage12.py),
  [evidencia](../src/analysis_agent/evidence.py),
  [cálculo cerrado](../src/analysis_agent/quantitative.py) y
  [skill del analista](../.agents/skills/aeromexico-tracker-analysis/SKILL.md).
  El vocabulario «Gold» de los fixtures del chat también significa respuestas
  esperadas; [su generador](../scripts/chat/build_business_gold.py) lee el
  snapshot fijado, no abre las tablas Parquet.

### Dependencias de las skills

Las ocho familias aplican el [contrato común](../.agents/skills/source-updates-common.md).
Corporativo y tráfico contribuyen a métricas de aerolínea; rutas a las tablas
de red y sus puentes; aeropuertos a tráfico aeroportuario/grupos; macro y
mercado a sus series y calendarios; contexto a dimensiones/eventos; internos
a derivados y linaje. Noticias produce evidencia JSON, sin sumar tablas Gold.
El [coordinador](../.agents/skills/airline-update-coordinator/SKILL.md) ordena
construcción y validación del candidato. El plan no certifica frescura ni
publicación. Estas son dependencias, no una certificación de que las ocho
familias estén completas. Su código y el catálogo quedan en el otro hilo.

### Cierre documental

Se continuó la [auditoría del 18](referencias/source-updates-20261018/lifecycle-audit.json).
Solo se actualizan sus enlaces de documentos retirados y se agrega el resultado
de seguimiento; se conservan sus conteos y observaciones históricas.
La política y el check de cierre ya existen en
[AGENTS.md](../AGENTS.md#cierre-documental-obligatorio-por-tarea) y
[CI](../.github/workflows/ci.yml). Se corrige la receta de cierre de
[REPO_MAP](../REPO_MAP.md) para exigir inventario, dependencias y disposición
por archivo, también en tareas locales y antes de un traslado. El retiro real
detectó un fallo previo del check: interpretaba las URLs dinámicas de pruebas
como direcciones IPv6 inválidas y abortaba. Se corrigió el escaneo para continuar
con las rutas literales. Los enlaces Markdown malformados siguen siendo errores
de validación. Dos regresiones comprueban ambos límites.

[Validación de esta entrega](referencias/gold-exposure-20261019/validation.json):
39 pruebas focalizadas aprobadas, lint y diff limpios. Escaneo de 111 Markdown
públicos sin destinos locales rotos; 23 enlaces a objetos Git comprobados.
La revisión independiente pasó 36 pruebas y cerró sin hallazgos pendientes
después de corregir las fechas del pronóstico y el fallo del control documental.
No se corrió la suite de pipeline ni navegador: no cambian datos, interfaz,
contratos o transformaciones. El snapshot privado no se restauró ni certificó.

## Pendientes

- Revisar y priorizar las mejoras de Economía y contexto dentro de las vistas
  actuales. Esta pasada entrega el mapa y el cierre documental; no implementa
  propuestas de producto.
- Reconciliar descomposición y vigencia de pronósticos/estudios antes de darles
  nueva exposición. Las tres tablas históricamente propuestas para posible
  archivo suman 74.703 bytes; sus dependencias impiden tratarlas como sobrantes.
- El hilo de fuentes completa las ocho familias antes de activar el calendario.
  El hilo de Vuelos resuelve el 95 % y su Gold. PR140/M11 y PR142/35 conservan
  sus límites y revisiones independientes.

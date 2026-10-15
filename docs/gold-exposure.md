# Exposición de Gold al 15 de octubre de 2026

Esta auditoría describe el dashboard real y los candidatos independientes de
Mercado y Noticias. No aprueba ni publica ninguno. La rama de Vuelos de otro
encargo queda fuera del cambio. Inventario reproducible:
`uv run python -m scripts.audit.gold_exposure`; resultados en
`docs/referencias/gold-exposure-20261015/{tables.csv,summary.json}`.

## Denominador y aproximación

Se verifican **43 Parquet públicos versionados**, **7 tablas puente de linaje**
y **4 Gold privados de Vuelos** restaurados en destinos ignorados. Los públicos
ocupan **53,273,203 bytes (~50.8 MiB)** comprimidos; el CSV da filas, bytes,
periodos y referencias de código de cada tabla. Ese tamaño corresponde a los
Parquet, no a su duplicación en el warehouse ni al coste total de respaldos LFS.

El denominador analítico público es **23 tablas**: todas las `fact_` más
`dim_events`, `dim_cluster_assignments` y `dim_model_performance`. Excluye las
siete tablas de linaje, dimensiones de claves/procedencia y calendarios. Los
cuatro cubos privados quedan fuera del denominador público y conservan su
tratamiento y elegibilidad anteriores.

La clasificación es estática y conservadora: **7/23 (~30%)** tienen cifras
identificables en componentes visibles (incluidos agregados/subconjuntos de la
red de Vuelos); otras **4/23** aportan presencia, cobertura o validación. Si se
cuenta también ese contexto, el alcance amplio es **11/23 (~48%)**. Eso no
significa que todas las filas/campos de esas tablas se vean ni que tengan una
gráfica exclusiva. La cobertura y los tipos de cifra filtran las rutas visibles.

Mercado agrega dos tablas de demanda: exposición directa candidata **9/23
(~39%)**, o **13/23 (~57%)** incluyendo contexto/validación. Su exposición es
parcial: solo aeropuertos mexicanos, cortes disponibles y detalle OMA retenido
por calidad. Noticias consume evidencia JSON; añade **cero tablas Gold** a esta
cuenta. Antes y después son escenarios revisables; producción permanece igual.

Las **99 definiciones**, **93 claves presentes** y **34 banderas seleccionadas**
del inventario métrico previo describen catálogo/configuración, no uso real de
la UI. No se utilizan como numerador. Las referencias de texto del CSV sirven
para encontrar dependencias; por sí solas no demuestran exposición.

## Información que no tiene una visualización propia

| Tabla | Qué contiene | Decisión propuesta y dependencias |
|---|---|---|
| `fact_airport_traffic` | 566 observaciones aeropuerto/mes | Visualizar parcialmente en Mercado; excluir Jamaica y retener detalle OMA. No atribuir totales a Aeroméxico. |
| `fact_airport_group_traffic` | 47 observaciones grupo/mes, total y segmentos en México | Mostrar grupos por separado; nunca sumarlos al detalle aeroportuario. |
| `fact_macro` | 1,494 observaciones de combustible, FX y macro | Conservar: alimenta calendarios, análisis y contrastes; estudiar una vista de costes/contexto. |
| `fact_market_data` | 11,897 observaciones de precios/volumen financieros | Conservar; posible vista de contexto financiero con unidades y activos explícitos. |
| `dim_events` | 22 eventos regulatorios/corporativos | Conservar como contexto de anomalías; una coincidencia temporal no prueba causalidad. |
| `fact_report_language` | 11 indicadores lingüísticos de reportes | Evaluar archivo futuro si se retira el estudio: aún tiene vistas SQL y validación. No confundir tono con satisfacción. |
| `fact_anomalies` | 23 alertas estadísticas | Conservar e investigar; no son errores confirmados. |
| `dim_cluster_assignments` | 407 agrupaciones de series | Evaluar archivo futuro de este estudio después de revisar las vistas SQL, pruebas y consumidores. |
| `fact_study_results` | 7 resultados de estudios | Evaluar archivo futuro de estudios inactivos con su procedencia y consumidores. |
| `fact_spread_decomposition` | 4 descomposiciones de cambio del margen unitario | Conservar: respalda cálculos y tesis; la identidad no demuestra una causa económica. |
| `fact_forecasts` | 24 valores pronosticados con bandas/horizontes | Conservar: se exporta un payload y tiene controles; la UI actual no dibuja su serie. |
| `dim_model_performance` | 5 evaluaciones de modelos/baselines | Conservar junto al forecast y sus validaciones. |

Las otras tablas de contexto son `fact_aifa_shared_route_presence`,
`fact_domestic_exclusive_market_inferences`, `fact_dashboard_coverage` y
`fact_data_quality_issues`. No se consideran basura porque carezcan de gráfica.
Las siete tablas puente conservan linaje; no son candidatas a borrado. Las
dimensiones y los calendarios permiten claves, conversiones y trazabilidad.

No hay datos de clientes, reservas o fidelización para construir esas vistas.
La flota tiene una serie corta de Aeroméxico; no permite inventar un comparativo
histórico homogéneo de las tres aerolíneas.

## Hallazgo de calidad de OMA

En **22 meses reconciliables**, la suma del campo `passengers_total` del detalle
OMA coincide exactamente con el subtotal internacional del grupo, y difiere de
su total. El candidato retiene todo el detalle de ese grupo hasta revisar el
parser y los originales. Conserva el total de grupo por separado, sin imputar
ni reescribir Gold. Riesgo alto para rankings aeroportuarios; evidencia fuerte
de una confusión de subtotal, origen exacto pendiente de corregir en otra etapa.

Archivar en el futuro exige revisar SQL `07_analytics_views.sql` y
`08_dashboard_views.sql`, contratos, warehouse, validaciones, notebooks y
consumidores; conservar manifiestos y evidencia, definir reproducción y recibir
la decisión del dueño. No se borró ni archivó ningún archivo en este trabajo.

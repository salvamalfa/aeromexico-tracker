# Etapa 6 — Tablas maestras (capa gold)

Fecha de cierre: 2026-08-23  
Estado: COMPLETA

## Qué se construyó

- Modelo dimensional completo con `dim_carrier`, `dim_period`, `dim_metric`,
  `dim_route`, `dim_airport` y `dim_events`.
- Cinco hechos de negocio: métricas de aerolínea, tráfico por ruta, tráfico por
  aeropuerto, mercado y macro; además, un hecho auditable de issues de calidad.
- Contrato YAML versionado para las 16 tablas gold, ejecutado con Pandera sobre cada
  tabla completa antes de publicarla.
- Normalización simultánea millas-kilómetros y métricas por milla-por kilómetro con el
  factor exacto `1.609344`.
- Conversión monetaria a USD con promedio para P&L y cierre para balance, conservando
  valor original, moneda, tasa y tipo de tasa.
- SCD2 para hechos BMV reexpresables, con vistas current y as-reported mediante
  `is_current`, `valid_from`, `valid_to` y `restatement_count`.
- Ejes `calendar_period_id` y `fiscal_period_id` en todas las tablas de hechos; las
  finanzas de Ryanair preservan su calendario fiscal.
- Métricas derivadas, crecimiento QoQ/YoY, TTM, conciliación reportado-derivado y
  preferencia explícita por la cifra reportada cuando la diferencia supera 1%.
- Fórmula SLA del prospecto implementada. Se publican 83 filas SLA con `NULL` porque
  ninguna fuente estructurada actual ofrece etapa promedio global comparable; no se
  sustituyó con la etapa del mercado México-EE.UU. de T-100.
- Serie AFAC mensual desestacionalizada por STL para Aeroméxico consolidado, claramente
  identificada como derivada.
- Doble vista de entidad: standalone y consolidada. La consolidada es la predeterminada.
- Warehouse DuckDB local con 13 vistas de consumo y diccionario de datos generado desde
  los contratos y `dim_metric`.
- Corrección del parser Volaris: los marcadores de nota `(1)`/`(2)` en tablas SEC ya no
  se interpretan como capacidades negativas. El crosswalk T-100 también quedó con orden
  total determinista.

## Tablas y cobertura

| Tabla gold | Filas | Cobertura o grano |
|---|---:|---|
| `dim_carrier` | 182 | entidades prioritarias, AFAC y T-100 |
| `dim_period` | 199 | 2015–2026; mes, trimestre y año |
| `dim_metric` | 99 | 34 métricas de dashboard ligadas al glosario |
| `dim_route` | 3,407 | ruta direccional México-EE.UU. |
| `dim_airport` | 9,071 | OurAirports + 18 códigos históricos/BTS-only |
| `fact_carrier_metrics` | 6,207 | formato largo, reportado y derivado |
| `fact_route_traffic` | 189,809 | aerolínea-ruta-mes-aeronave-clase |
| `fact_airport_traffic` | 613 | aeropuerto-mes-fuente |
| `fact_market_data` | 11,897 | emisor-sesión |
| `fact_macro` | 1,494 | indicador-periodo-agregación |
| `fact_data_quality_issues` | 23 | discrepancias reportado-derivado |

Cobertura de `fact_carrier_metrics` por fuente:

| Fuente | Filas | Aerolíneas | Métricas | Rango |
|---|---:|---:|---:|---|
| AFAC | 3,642 | 12 | 1 | 2015M01–2026M06 |
| Derivaciones gold | 1,383 | 5 | 44 | 2015M01–2026Q2 |
| SEC EDGAR | 641 | 3 | 42 | 2022Q4–2026Q2 |
| BMV XBRL | 293 | 2 | 7 | 2018–2026Q2 |
| Ryanair IR | 158 | 1 | 2 | 2021M08–2026Q2 |
| Viva IR | 90 | 1 | 7 | 2023Q1–2026Q2 |

## Vistas de consumo

- `v_aeromexico_quarterly`
- `v_peer_comparison`
- `v_market_share_mx`
- `v_route_performance`
- `v_unit_economics`
- `v_data_health`
- `v_restatements`
- `v_events_timeline`
- `v_carrier_standalone`
- `v_carrier_consolidated`
- `v_carrier_default`
- `v_carrier_metrics_wide`
- `v_seasonally_adjusted`

`v_carrier_default` parte de la vista consolidada y aplica precedencia de fuentes por
celda. SEC/IR y las derivaciones de negocio preceden a BMV en la vista corriente; BMV
permanece completo y versionado para conciliación y reexpresiones.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 90 tests |
| Definición de aceptación Etapa 6 | PASS | 25/25 controles |
| Contratos gold | PASS | 16/16 tablas completas |
| Claves de aerolínea | PASS | cero nulos en facts principales |
| Integridad referencial | PASS | carrier, periodo, métrica, ruta y aeropuerto |
| Load factor derivado | PASS | 39/39 bajo 0.5 pp; máximo 0.4696 pp |
| Trimestres vs anual | PASS | 18 conciliaciones; diferencia máxima 0.0128% |
| FX | PASS | promedio P&L, cierre balance, cero tasas faltantes |
| Métricas del dashboard | PASS | 34/34 con interpretación y enlace al glosario |
| Estacionalidad | PASS | 138 meses STL explícitamente marcados |
| Vistas | PASS | todas las vistas obligatorias creadas |
| Ancla Aeroméxico 1Q26 | PASS | consultada en `v_aeromexico_quarterly` |
| Rebuild offline | PASS | dos ejecuciones completas sin red |
| Idempotencia gold | PASS | 16/16 SHA-256 idénticos en baseline y dos rebuilds |

La consulta ancla de 1Q26 devuelve: ingresos `1,341.0 mdd`, EBITDAR ajustado
`335.8 mdd`, margen operativo `10.6%`, load factor reportado `84.4%`, ASM
`8,596 millones` y flota `166`.

## Entidades y excepciones documentadas

AFAC contiene 14,962 filas. El crosswalk prioritario asigna 2,784 (18.6%) a 11
aerolíneas mexicanas; 12,178 filas correspondientes a 269 nombres, principalmente
aerolíneas extranjeras y operadores chárter, permanecen sin `carrier_key` en silver y
están documentadas en `data/quality/stage6_entity_exceptions.parquet`.

Estas filas no se convierten a cero ni se eliminan del mercado: todas participan en el
agregado `MARKET_TOTAL_MX`, que es el denominador de `v_market_share_mx`. El porcentaje
de mapeo mide alcance del crosswalk de negocio, no pérdida de pasajeros.

T-100, SEC y mercado tienen cero claves de aerolínea nulas. Los 18 códigos de aeropuerto
históricos o privados que no existen en el snapshot de OurAirports se resolvieron con
los metadatos del propio T-100 y quedaron marcados `historical_or_bts_only_code`.

## Calidad y discrepancias conservadas

Se registraron 23 warnings `reported_derived_discrepancy`. Son diferencias reales de
definición entre métricas unitarias publicadas y reconstrucciones desde estados
financieros/capacidad. La vista de negocio usa la cifra reportada; la derivada y la
diferencia siguen consultables en gold.

La corrección del parser Volaris fue necesaria para cumplir la conciliación de load
factor. Las filas HTML contienen un marcador de nota entre etiqueta y valor; antes se
interpretaba `(2)` como `-2`. Después de corregir el parser, las 39 conciliaciones de
load factor cumplen el umbral sin ajustar cifras artificialmente.

## Conversiones y comparabilidad

- 45 observaciones BMV en MXN fueron convertidas a USD: 26 con tipo promedio y 19 con
  tipo de cierre.
- Las fuentes que ya reportan USD conservan tasa `1.0` y el tipo aplicable.
- Las finanzas de Ryanair permanecen fiscales; solo sus métricas operativas mensuales se
  reconstruyen a calendario.
- Las 83 observaciones SLA son nulas deliberadamente hasta obtener etapa promedio
  global publicada por aerolínea y periodo. T-100 cubre únicamente México-EE.UU. y no es
  un sustituto válido para la red total.

## Decisiones tomadas

- **Warehouse:** solo DuckDB local; no se crea espejo BigQuery.
- **Alcance predeterminado:** consolidado, sumando Aeroméxico Connect al grupo donde la
  fuente permite hacerlo.
- **Persistencia:** Parquet gold como evidencia reproducible y DuckDB como capa de
  consulta; el archivo `.duckdb` sigue fuera de Git.
- **Moneda base:** USD.
- **Precedencia:** la cifra reportada prevalece sobre la derivada si difieren más de 1%,
  sin borrar ninguna de las dos.
- **Stage length:** no estimar ni reutilizar una subred no comparable.

La decisión de infraestructura está formalizada en
`docs/decisiones/decision-007-warehouse-bigquery.md`.

## Supuestos hechos

- `USD/MXN` se interpreta como MXN por USD; por tanto, un valor MXN se divide entre la
  tasa para obtener USD.
- La ventana de Semana Santa usada en `dim_period` va de Domingo de Ramos a lunes de
  Pascua, nueve días, y se reparte entre Q1 y Q2.
- La serie STL consolida Aeroméxico y Aeroméxico Connect, usa periodo 12 y se publica
  como `passengers_afac_sa`; nunca sustituye la serie observada.
- Los agregados de mercado AFAC incluyen nombres no mapeados, porque el denominador debe
  representar todo el mercado observado.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 6.

## Riesgos para la siguiente etapa

- Las comparaciones unitarias entre aerolíneas seguirán sin SLA no nulo hasta que exista
  etapa promedio global comparable.
- Los 23 issues de definición requieren que la Etapa 7 distinga claramente reportado,
  derivado y preferido en cualquier narrativa.
- La baja cobertura nominal del crosswalk AFAC es deliberada; análisis de carriers
  extranjeros requeriría ampliar el catálogo antes de tratarlos individualmente.
- La desestacionalización debe mantenerse etiquetada y nunca mezclarse con valores
  observados en una misma serie sin indicación visual.

## Comandos para reproducir

```powershell
just rebuild
uv run python -m src.transform.validate_stage6
uv run python -m src.transform.generate_data_dictionary
uv run pytest -q
```

La Etapa 7 no se inició. Se requiere un `go` explícito.

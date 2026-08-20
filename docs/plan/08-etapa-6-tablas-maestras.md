# Etapa 6 — Tablas Maestras (Capa Gold)

**Objetivo:** convertir todas las tablas silver dispersas en un conjunto pequeño,
coherente y bien modelado de **tablas maestras** que sirvan como única fuente de verdad
para la analítica y el dashboard. Este es el corazón del proyecto desde el punto de vista
de ingeniería de datos.

**Criterio de éxito:** un analista que nunca vio el proyecto puede responder cualquier
pregunta de negocio con dos o tres joins, sin tocar ningún archivo bronze.

---

## 1. Modelo dimensional

### Dimensiones

#### `dim_carrier`
```
carrier_key            PK
carrier_name
carrier_name_short
iata_code, icao_code
country
business_model         -- 'network' | 'lcc' | 'ulcc' | 'regional' | 'group'
is_public
ticker, exchange, cik
reporting_standard     -- 'IFRS' | 'US-GAAP'
reporting_currency
unit_system            -- 'metric' | 'imperial'
fiscal_year_end_month
parent_carrier_key     -- Aeroméxico Connect -> Aeroméxico
is_peer, is_focus
```

#### `dim_period`
```
period_id              PK  -- '2026Q1'
period_type            -- 'month' | 'quarter' | 'year' | 'ttm'
period_start_date, period_end_date
year, quarter, month
days_in_period
is_covid_period        -- flag útil: 2020-03 a 2021-12
prior_period_id        -- para QoQ
prior_year_period_id   -- para YoY
```

#### `dim_metric` — **la tabla que convierte esto en un producto de negocio**
```
metric_key             PK
metric_name_es, metric_name_en
metric_category        -- 'capacity' | 'demand' | 'unit_revenue' | 'unit_cost' |
                       -- 'profitability' | 'operational' | 'financial' | 'market'
unit_normalized
formula                -- fórmula literal en texto
higher_is_better       -- boolean o NULL si depende del contexto
business_interpretation_up     -- "Un TRASM más alto significa que..."
business_interpretation_down
why_it_matters                 -- párrafo de negocio
typical_range_network          -- benchmark para network carriers
typical_range_ulcc             -- benchmark para ULCC
caveats                        -- "no comparable entre aerolíneas sin ajustar por stage length"
display_format                 -- '0.0%', '$0.00', '0,0'
display_order
```

**Esta tabla se llena desde `11-glosario-kpis.md`.** Es lo que hace que el dashboard
tenga narrativa de negocio sin hardcodear textos en el código de la UI. El usuario pidió
explícitamente que cada KPI tuviera explicación de negocio — **aquí es donde vive**.

#### `dim_airport`
Ya construida en la Etapa 4.

#### `dim_route`
```
route_key              PK  -- 'MEX-LAX'
origin_iata, dest_iata
origin_country, dest_country
distance_km, distance_miles
is_domestic_mx, is_transborder_us, is_international
market_key             -- ruta bidireccional: 'LAX-MEX' y 'MEX-LAX' -> 'MEX<>LAX'
```

#### `dim_events`
Ya construida en la Etapa 4.

### Tablas de hechos

#### `fact_carrier_metrics` — **la tabla maestra principal**
Formato largo (una fila por aerolínea-periodo-métrica-segmento):
```
carrier_key            FK
period_id              FK
metric_key             FK
segment                -- 'total' | 'domestic' | 'international' | 'transborder'
value                  -- normalizado
value_as_reported      -- antes de normalizar unidades/moneda
unit_as_reported
currency
is_derived             -- lo calculamos nosotros vs lo reportó la fuente
is_preliminary
is_estimated
derivation_formula     -- si is_derived, cómo se calculó
-- SCD2
valid_from, valid_to, is_current, restatement_count
-- linaje
source_system, source_file, source_hash, ingested_at
confidence             -- 0-1
```

**Por qué formato largo y no ancho:** las fuentes publican distintos subconjuntos de
métricas, en distintos periodos, con distintos segmentos. El formato ancho generaría
una tabla mayormente `NULL` y frágil ante nuevas métricas. El largo es extensible y
permite el linaje por celda. El dashboard pivota lo que necesita.

Se provee además una vista ancha de conveniencia:
```sql
CREATE VIEW v_carrier_metrics_wide AS
PIVOT fact_carrier_metrics ON metric_key USING first(value)
GROUP BY carrier_key, period_id, segment;
```

#### `fact_route_traffic` (desde BTS T-100)
```
carrier_key, route_key, period_id, aircraft_type, service_class,
departures_scheduled, departures_performed, seats, passengers,
freight_kg, mail_kg, asm, rpm, load_factor, distance_miles,
source_system, ingested_at
```

#### `fact_airport_traffic`
```
airport_iata, period_id, passengers_domestic, passengers_international,
passengers_total, cargo_tons, operations, operator_group, source_system
```

#### `fact_market_data`
```
carrier_key, date, close, adj_close, volume, currency,
return_1d, return_ytd, volatility_30d
```

#### `fact_macro`
```
period_id, indicator_key, value, unit, source_system
```
(FX, jet fuel, INPC, turismo, IGAE — todo lo exógeno en una sola tabla larga)

## 2. Normalizaciones obligatorias

### 2.1 Unidades: métrico ↔ imperial
```
1 milla estatuta = 1.609344 km
ASK_km = ASM_miles × 1.609344
RPK_km = RPM_miles × 1.609344
CASK_per_km = CASM_per_mile / 1.609344
RASK_per_km = RASM_per_mile / 1.609344
```
**Almacenar ambas.** El dashboard debe permitir alternar entre sistemas, porque un
analista mexicano piensa en km y la industria estadounidense en millas.

### 2.2 Moneda
- Moneda base del proyecto: **USD**
- Conversión de EUR (Ryanair, IAG) y MXN usando `dim_fx_period`
- **P&L → tipo de cambio promedio del periodo. Balance → tipo de cambio de cierre.**
- Guardar `value_usd` y `value_original_currency` con su `currency`
- Toda conversión registra `fx_rate_used` y `fx_rate_type` en la fila

### 2.3 Ajuste por stage length — **la normalización crítica**

Las métricas unitarias caen mecánicamente cuando la etapa promedio sube (los costos
fijos por vuelo se reparten entre más kilómetros). Comparar el CASM de Ryanair
(etapas cortas) contra el de Aeroméxico (con largo alcance) sin ajustar es un error
grave y común.

**Usar la fórmula que la propia Aeroméxico publica en su prospecto:**
```
SLA_RASK = RASK × (stage_length_carrier / 1834)^0.5
SLA_CASK = CASK × (stage_length_carrier / 1834)^0.5
```
donde 1,834 km es la etapa de referencia usada por la compañía y el exponente es 0.5.

**Reglas de implementación:**
- Calcular **siempre** la versión ajustada junto a la cruda
- Etiquetar claramente en el dashboard cuál es cuál
- Si no se conoce el stage length de una aerolínea en un periodo, la métrica ajustada
  es `NULL` (**no** se estima)
- Documentar la fórmula y su origen en `dim_metric.caveats`

### 2.4 Periodos fiscales → calendario
- `fiscal_period_id` y `calendar_period_id` en toda tabla de hechos
- Ryanair (FY marzo): métricas operativas reconstruidas a calendario desde datos
  mensuales; financieros **solo comparables en base fiscal** (declararlo)
- **Toda comparación por defecto del dashboard usa calendario**

### 2.5 Trimestre puro vs acumulado (YTD)
Algunas fuentes solo publican acumulado. Derivar:
```
Q2 = YTD_H1 − Q1
Q3 = YTD_9M − YTD_H1
Q4 = FY − YTD_9M
```
Marcar `is_derived = true` y guardar la fórmula en `derivation_formula`.
**Validar:** la suma de los cuatro trimestres derivados debe igualar el anual (±0.1%).

### 2.6 Consolidación de subsidiarias
**Decisión de negocio a consultar con el usuario** (ya planteada en la Etapa 3):
Aeroméxico + Aeroméxico Connect en AFAC vs el consolidado de los filings.

Implementar `dim_carrier.parent_carrier_key` y ofrecer **dos vistas**:
- `v_carrier_standalone` — cada entidad por separado
- `v_carrier_consolidated` — sumadas al nivel del grupo

Predeterminada: consolidada (para que cuadre con los financieros). Configurable.

## 3. Conciliación de entidades

El `carrier_crosswalk.csv` construido en las Etapas 3-5 es ahora un artefacto de primera
clase. Requisitos:

1. **Cobertura completa**: cero filas con `carrier_key = NULL` en las fuentes principales,
   o cada excepción documentada
2. **Vigencia temporal**: `valid_from`/`valid_to` para manejar rebrandings y quiebras
   (Interjet, Mexicana legacy vs nueva)
3. **Test de cobertura**: un test que falla si aparece un nombre de aerolínea nuevo
   sin mapear al reprocesar
4. **Reporte de cobertura** por fuente: `% de filas mapeadas`, publicado en el panel
   de salud de datos

Lo mismo para aeropuertos: cero códigos IATA sin resolver contra `dim_airport`.

## 4. Métricas derivadas a calcular en gold

Además de lo reportado, calcular y guardar (con `is_derived = true`):

| Métrica derivada | Fórmula |
|---|---|
| `load_factor_derived` | `rpk / ask` (para cruzar contra el reportado) |
| `rask` | `total_revenue / ask` |
| `prask` | `passenger_revenue / ask` |
| `cask` | `total_operating_expense / ask` |
| `cask_ex_fuel` | `(total_operating_expense − fuel_expense) / ask` |
| `unit_margin` / `pask` | `rask − cask` ← **la métrica que más importa** |
| `yield` | `passenger_revenue / rpk` |
| `break_even_load_factor` | `cask / yield` |
| `fuel_cost_share` | `fuel_expense / total_operating_expense` |
| `ancillary_share` | `ancillary_revenue / total_revenue` |
| `revenue_per_passenger` | `total_revenue / passengers` |
| `market_share_domestic_mx` | pax de la aerolínea / pax total del mercado (AFAC) |
| `asm_per_aircraft` | `asm / fleet_size` (proxy de utilización) |
| `yoy_growth_*` | `(v_t − v_{t−4}) / v_{t−4}` para trimestres |
| `qoq_growth_*` | `(v_t − v_{t−1}) / v_{t−1}` |
| `ttm_*` | suma móvil de 4 trimestres (suaviza estacionalidad) |

**Regla crítica:** cuando una métrica derivada difiere de la reportada por la compañía
en más de 1%, **prevalece la reportada** en el dashboard, pero la derivada se conserva
y la discrepancia se registra en `data_quality_issues`. La discrepancia misma es
información: revela diferencias de definición.

## 5. Estacionalidad

La demanda aérea mexicana es fuertemente estacional (Semana Santa, verano, diciembre).
**Semana Santa se mueve entre marzo y abril**, lo que distorsiona las comparaciones
Q1 vs Q2 de un año a otro.

Implementar en `dim_period`:
```
easter_date, easter_quarter, easter_days_in_q1, easter_days_in_q2
```
Y ofrecer en gold una serie desestacionalizada (STL o X-13) para las métricas principales,
claramente marcada como tal. **Nunca** presentar desestacionalizado sin decirlo.

## 6. Vistas de consumo

Crear en DuckDB, documentadas:

| Vista | Para qué |
|---|---|
| `v_aeromexico_quarterly` | Todas las métricas de Aeroméxico por trimestre, ancho |
| `v_peer_comparison` | Métricas normalizadas de todas las aerolíneas, lado a lado |
| `v_market_share_mx` | Participación mensual del mercado mexicano (desde AFAC) |
| `v_route_performance` | Rutas México-EE.UU. con ASM/RPM/LF (desde T-100) |
| `v_unit_economics` | RASK, CASK, spread, ajustados y crudos |
| `v_data_health` | Cobertura, huecos, issues, última actualización por fuente |
| `v_restatements` | Histórico de reexpresiones |
| `v_events_timeline` | Eventos para anotar las gráficas |

## 7. Diccionario de datos

Generar `docs/diccionario-datos.md` **automáticamente** desde los esquemas + `dim_metric`,
con un script `src/transform/generate_data_dictionary.py`. Debe incluir por cada tabla:
columnas, tipos, descripción, fuente, y por cada métrica: fórmula e interpretación
de negocio.

Que sea generado (y no escrito a mano) garantiza que no se desactualice.

## 8. ¿BigQuery?

**Decisión a tomar en esta etapa con el usuario.** Opciones:

- **A) Solo DuckDB local.** Más simple, suficiente para el volumen, cero costo, el
  dashboard lee el `.duckdb` o Parquet directo. **Recomendada.**
- **B) DuckDB + espejo en BigQuery.** El usuario ya domina BigQuery; le permite hacer
  análisis ad-hoc con las herramientas que usa a diario, y es un plus de portafolio.
  Costo: cero dentro del free tier (10 GB / 1 TB query mes). Esfuerzo: bajo
  (exportar Parquet gold → cargar a BQ).

Si se elige B, implementarlo como un paso opcional del pipeline, nunca como dependencia
del dashboard.

## 9. Validación de la Etapa 6

- Todas las tablas gold tienen contrato de esquema declarado y validado (`pandera`)
- Cero `carrier_key` nulos en fuentes principales (o excepciones documentadas)
- Invariantes de negocio pasan sobre **toda** la tabla gold, no solo sobre muestras
- Suma de trimestres derivados = anual reportado (±0.1%)
- Load factor derivado vs reportado: diferencia <0.5 pp en >95% de las filas
- La cifra ancla de 1Q26 de Aeroméxico se puede consultar desde `v_aeromexico_quarterly`
  y coincide con `00-contexto-y-principios.md` §3
- `dim_metric` tiene interpretación de negocio poblada para el 100% de las métricas
  que el dashboard va a mostrar
- El diccionario de datos se genera sin errores
- `just rebuild` reconstruye todo desde bronze **sin red** y produce resultados idénticos

---

## Entregables de la Etapa 6

1. `sql/gold/*.sql` con todas las transformaciones versionadas
2. `src/transform/` con la orquestación silver → gold
3. Todas las tablas `gold/*.parquet` + vistas en `warehouse.duckdb`
4. `dim_metric` completamente poblada desde el glosario
5. `docs/diccionario-datos.md` generado
6. Suite de validación completa en verde
7. Decisión documentada sobre BigQuery
8. `docs/etapas/etapa-6-reporte.md` con estadísticas de cobertura por fuente y métrica

**Detenerse y esperar "go".**

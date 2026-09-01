# Diccionario de datos

> Archivo generado automáticamente por `python -m src.transform.generate_data_dictionary`.
> Contrato: `stage9_v1.0.0`. No editar manualmente.

## Tablas gold

### `dim_carrier`

Etapa de materialización: `6`.

Grano declarado: `carrier_key`.

Clave primaria declarada: `carrier_key`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `carrier_key` | `string` | no | — | Clave estable de la entidad aérea. |
| `carrier_name` | `string` | no | — | Razón o nombre operacional. |
| `carrier_name_short` | `string` | no | — | Nombre corto para visualización. |
| `iata_code` | `string` | sí | — | Código IATA de dos caracteres. |
| `icao_code` | `string` | sí | — | Código ICAO. |
| `country` | `string` | sí | — | País base de la entidad. |
| `business_model` | `string` | no | — | Modelo de negocio normalizado. |
| `is_public` | `bool` | no | — | Indica si cotiza en bolsa. |
| `ticker` | `string` | sí | — | Ticker principal usado por el proyecto. |
| `exchange` | `string` | sí | — | Bolsa principal o combinación de bolsas. |
| `cik` | `string` | sí | — | CIK de SEC |
| `reporting_standard` | `string` | sí | — | IFRS o US-GAAP. |
| `reporting_currency` | `string` | sí | — | Moneda funcional de reporte. |
| `unit_system` | `string` | no | — | Sistema de unidades preferido por la fuente. |
| `fiscal_year_end_month` | `int` | sí | — | Mes de cierre del ejercicio fiscal. |
| `parent_carrier_key` | `string` | sí | — | Clave del grupo consolidante. |
| `is_peer` | `bool` | no | — | Identifica peers del análisis. |
| `is_focus` | `bool` | no | — | Identifica la compañía objetivo. |
| `valid_from` | `date` | no | — | Inicio de vigencia de la identidad. |
| `valid_to` | `date` | sí | — | Fin de vigencia de la identidad. |
| `is_current` | `bool` | no | — | Versión vigente de la identidad. |

### `dim_period`

Etapa de materialización: `6`.

Grano declarado: `period_id`.

Clave primaria declarada: `period_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `period_id` | `string` | no | — | Clave de mes |
| `period_type` | `string` | no | dominio: month, quarter, year, ttm | month |
| `period_start_date` | `date` | no | — | Primer día incluido. |
| `period_end_date` | `date` | no | — | Último día incluido. |
| `year` | `int` | no | — | Año calendario de cierre. |
| `quarter` | `int` | sí | — | Trimestre calendario de cierre. |
| `month` | `int` | sí | — | Mes calendario de cierre. |
| `days_in_period` | `int` | no | — | Días calendario incluidos. |
| `is_covid_period` | `bool` | no | — | Periodo entre marzo de 2020 y diciembre de 2021. |
| `prior_period_id` | `string` | sí | — | Periodo comparable inmediatamente anterior. |
| `prior_year_period_id` | `string` | sí | — | Mismo periodo del año previo. |
| `fiscal_period_id` | `string` | no | — | Identificador fiscal por defecto. |
| `calendar_period_id` | `string` | no | — | Identificador calendario. |
| `easter_date` | `date` | no | — | Domingo de Pascua del año. |
| `easter_quarter` | `int` | no | — | Trimestre que contiene Pascua. |
| `easter_days_in_q1` | `int` | no | — | Días de la ventana Domingo de Ramos a lunes de Pascua que caen en Q1. |
| `easter_days_in_q2` | `int` | no | — | Días de la ventana Domingo de Ramos a lunes de Pascua que caen en Q2. |

### `dim_metric`

Etapa de materialización: `6`.

Grano declarado: `metric_key`.

Clave primaria declarada: `metric_key`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `metric_key` | `string` | no | — | Clave estable de la métrica. |
| `metric_name_es` | `string` | no | — | Nombre en español. |
| `metric_name_en` | `string` | no | — | Nombre en inglés. |
| `metric_category` | `string` | no | — | Categoría analítica. |
| `unit_normalized` | `string` | no | — | Unidad normalizada esperada. |
| `consolidation_method` | `string` | no | dominio: sum, weighted, latest, non_additive | Regla explícita para consolidar la métrica entre entidades. |
| `formula` | `string` | sí | — | Fórmula literal. |
| `higher_is_better` | `bool` | sí | — | Sentido favorable; nulo cuando depende del contexto. |
| `business_interpretation_up` | `string` | no | — | Lectura de negocio cuando sube. |
| `business_interpretation_down` | `string` | no | — | Lectura de negocio cuando baja. |
| `why_it_matters` | `string` | no | — | Relevancia de negocio. |
| `typical_range_network` | `string` | sí | — | Referencia aproximada para network carriers. |
| `typical_range_ulcc` | `string` | sí | — | Referencia aproximada para ULCC. |
| `caveats` | `string` | no | — | Advertencias de comparabilidad y definición. |
| `display_format` | `string` | no | — | Formato de presentación. |
| `display_order` | `int` | no | — | Orden sugerido en UI. |
| `glossary_section` | `string` | sí | — | Encabezado fuente en el glosario. |
| `is_dashboard_metric` | `bool` | no | — | Métrica prevista para mostrarse en el dashboard. |

### `dim_route`

Etapa de materialización: `6`.

Grano declarado: `route_key`.

Clave primaria declarada: `route_key`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `route_key` | `string` | no | — | Ruta direccional origen-destino. |
| `origin_iata` | `string` | no | — | Aeropuerto de origen. |
| `dest_iata` | `string` | no | — | Aeropuerto de destino. |
| `origin_country` | `string` | no | — | País de origen. |
| `dest_country` | `string` | no | — | País de destino. |
| `distance_km` | `float` | no | — | Distancia mediana en kilómetros. |
| `distance_miles` | `float` | no | — | Distancia mediana en millas estatuta. |
| `is_domestic_mx` | `bool` | no | — | Ambos extremos están en México. |
| `is_transborder_us` | `bool` | no | — | Ruta México-Estados Unidos. |
| `is_international` | `bool` | no | — | Cruza una frontera. |
| `market_key` | `string` | no | — | Mercado bidireccional canónico. |

### `dim_airport`

Etapa de materialización: `6`.

Grano declarado: `airport_iata`.

Clave primaria declarada: `airport_iata`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `airport_iata` | `string` | no | — | Código IATA de un aeropuerto real. |
| `airport_icao` | `string` | sí | — | Código ICAO. |
| `name` | `string` | sí | — | Nombre del aeropuerto. |
| `city` | `string` | sí | — | Ciudad. |
| `country` | `string` | sí | — | País. |
| `latitude` | `float` | sí | — | Latitud. |
| `longitude` | `float` | sí | — | Longitud. |
| `elevation` | `float` | sí | — | Elevación publicada. |
| `type` | `string` | sí | — | Tipo de instalación. |
| `operator_group` | `string` | sí | — | Grupo operador mexicano. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo bronze fuente. |
| `source_hash` | `string` | no | — | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | — | Fecha de ingesta. |
| `parser_version` | `string` | no | — | Versión del parser. |

### `dim_airport_group`

Etapa de materialización: `6`.

Grano declarado: `airport_group_key`.

Clave primaria declarada: `airport_group_key`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `airport_group_key` | `string` | no | — | Clave estable del grupo aeroportuario. |
| `airport_group_name` | `string` | no | — | Nombre de negocio del grupo aeroportuario. |
| `country` | `string` | no | — | País de los aeropuertos incluidos. |
| `source_system` | `string` | no | — | Sistemas fuente contribuyentes. |
| `source_file` | `string` | no | — | Archivos fuente contribuyentes. |
| `source_hash` | `string` | no | patrón declarado | Fingerprint determinista del linaje agregado. |
| `ingested_at` | `datetime` | no | — | Última fecha de ingesta contribuyente. |

### `dim_events`

Etapa de materialización: `6`.

Grano declarado: `event_date, title`.

Clave primaria declarada: `event_date, title`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `event_date` | `datetime` | no | — | Fecha del evento. |
| `event_type` | `string` | no | — | Tipo de evento. |
| `event_category` | `string` | no | — | Categoría analítica. |
| `title` | `string` | no | — | Título corto. |
| `description` | `string` | no | — | Descripción. |
| `affected_carriers` | `string` | no | — | Entidades afectadas. |
| `impact_direction` | `string` | no | — | Dirección esperada del impacto. |
| `source_url` | `string` | no | — | Fuente primaria. |
| `confidence` | `string` | no | — | Confianza cualitativa. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | sí | — | Archivo bronze fuente. |
| `source_hash` | `string` | sí | — | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | — | Fecha de ingesta. |
| `parser_version` | `string` | no | — | Versión del parser. |

### `dim_fx_period`

Etapa de materialización: `6`.

Grano declarado: `period_id, currency_pair`.

Clave primaria declarada: `period_id, currency_pair`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `rate_avg` | `float` | no | — | Tipo promedio del periodo. |
| `rate_close` | `float` | no | — | Último tipo disponible del periodo. |
| `rate_min` | `float` | no | — | Mínimo del periodo. |
| `rate_max` | `float` | no | — | Máximo del periodo. |
| `period_id` | `string` | no | — | Periodo calendario. |
| `period_type` | `string` | no | — | month |
| `currency_pair` | `string` | no | — | Par cotizado como moneda local por USD. |
| `pnl_conversion_method` | `string` | no | — | Método para flujos de P&L. |
| `balance_conversion_method` | `string` | no | — | Método para saldos. |

### `dim_fuel_period`

Etapa de materialización: `6`.

Grano declarado: `period_id`.

Clave primaria declarada: `period_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `price_avg_usd_per_gallon` | `float` | no | — | Precio promedio. |
| `price_close_usd_per_gallon` | `float` | no | — | Precio de cierre. |
| `price_min_usd_per_gallon` | `float` | no | — | Precio mínimo. |
| `price_max_usd_per_gallon` | `float` | no | — | Precio máximo. |
| `period_id` | `string` | no | — | Periodo calendario. |
| `period_type` | `string` | no | — | month o quarter. |
| `price_avg_yoy_pct` | `float` | sí | — | Variación interanual del promedio. |

### `fx_business_calendar`

Etapa de materialización: `6`.

Grano declarado: `date, currency_pair`.

Clave primaria declarada: `date, currency_pair`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `date` | `datetime` | no | — | Día hábil. |
| `rate_close` | `float` | no | — | Tipo publicado o arrastrado. |
| `is_published` | `bool` | no | — | El valor fue publicado ese día. |
| `fill_method` | `string` | no | — | Método de llenado. |
| `currency_pair` | `string` | no | — | Par de monedas. |

### `fuel_business_calendar`

Etapa de materialización: `6`.

Grano declarado: `date`.

Clave primaria declarada: `date`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `date` | `datetime` | no | — | Día hábil. |
| `price_usd_per_gallon` | `float` | no | — | Precio publicado o arrastrado. |
| `is_published` | `bool` | no | — | El valor fue publicado ese día. |
| `fill_method` | `string` | no | — | Método de llenado. |

### `dim_source`

Etapa de materialización: `6`.

Grano declarado: `source_key`.

Clave primaria declarada: `source_key`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `source_key` | `string` | no | patrón declarado | Clave canónica de la fuente pública o curada. |
| `source_systems` | `string` | no | — | Lista JSON de identificadores técnicos asociados. |
| `display_name` | `string` | no | — | Nombre comprensible de la fuente. |
| `institution` | `string` | no | — | Institución responsable. |
| `business_description` | `string` | no | — | Información de negocio aportada. |
| `coverage` | `string` | no | — | Cobertura temporal y geográfica. |
| `update_frequency` | `string` | no | — | Frecuencia esperada de actualización. |
| `access_method` | `string` | no | — | Método autorizado de obtención. |
| `official_page_url` | `string` | sí | — | Página HTTPS oficial cuando existe. |
| `artifact_link_policy` | `string` | no | dominio: direct, landing_page_only, not_applicable | Política para exponer enlaces de artefactos. |
| `limitations` | `string` | no | — | Limitaciones materiales de cobertura o acceso. |
| `source_kind` | `string` | no | dominio: public, curated, derived, error_evidence | Naturaleza de la fuente. |
| `artifact_expected` | `bool` | no | — | Indica si la fuente debe producir archivos Bronze. |
| `is_active` | `bool` | no | — | Indica si la fuente sigue activa. |

### `dim_source_priority`

Etapa de materialización: `6`.

Grano declarado: `data_domain, source_system`.

Clave primaria declarada: `data_domain, source_system`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `data_domain` | `string` | no | — | Dominio de datos donde aplica la precedencia. |
| `source_system` | `string` | no | — | Fuente o comodín por defecto. |
| `priority` | `int` | no | mín. 0 | Prioridad ascendente; menor es preferible. |
| `is_default` | `bool` | no | — | Identifica la regla de respaldo del dominio. |
| `source_priority_order` | `string` | no | dominio: asc, desc | Orden de la prioridad de fuente. |
| `is_preliminary_order` | `string` | no | dominio: asc, desc | Orden de preferencia para datos preliminares. |
| `confidence_order` | `string` | no | dominio: asc, desc | Orden de preferencia para confianza. |
| `ingested_at_order` | `string` | no | dominio: asc, desc | Orden de desempate por ingesta. |
| `rationale` | `string` | no | — | Justificación de la precedencia. |

### `fact_carrier_metrics`

Etapa de materialización: `6`.

Grano declarado: `carrier_key, period_id, metric_key, segment, source_system, valid_from`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `carrier_key` | `string` | no | — | Aerolínea o grupo. |
| `period_id` | `string` | no | — | Periodo reportado. |
| `calendar_period_id` | `string` | no | — | Periodo calendario comparable. |
| `fiscal_period_id` | `string` | no | — | Periodo fiscal de la fuente. |
| `period_type` | `string` | no | dominio: month, quarter, year, ttm | Granularidad temporal. |
| `period_start_date` | `date` | no | — | Inicio del periodo. |
| `period_end_date` | `date` | no | — | Fin del periodo. |
| `metric_key` | `string` | no | — | Métrica. |
| `segment` | `string` | no | dominio: total, domestic, international, transborder | total |
| `value` | `float` | sí | — | Valor normalizado en la unidad declarada. |
| `value_metric` | `float` | sí | — | Equivalente métrico cuando aplica. |
| `value_imperial` | `float` | sí | — | Equivalente imperial cuando aplica. |
| `value_as_reported` | `float` | sí | — | Valor numérico publicado antes de escala. |
| `unit_as_reported` | `string` | sí | — | Unidad literal publicada. |
| `unit_normalized` | `string` | no | — | Unidad normalizada de value. |
| `currency` | `string` | sí | — | Moneda original. |
| `value_original_currency` | `float` | sí | — | Valor ya escalado en moneda original. |
| `value_usd` | `float` | sí | — | Equivalente en USD. |
| `fx_rate_used` | `float` | sí | — | Tipo de cambio aplicado. |
| `fx_rate_type` | `string` | sí | dominio: average, close | average o close. |
| `is_derived` | `bool` | no | — | Valor calculado por el pipeline. |
| `is_preliminary` | `bool` | no | — | Fuente lo marca preliminar. |
| `is_estimated` | `bool` | no | — | Valor estimado y etiquetado. |
| `derivation_formula` | `string` | sí | — | Fórmula para valores derivados. |
| `valid_from` | `datetime` | no | — | Inicio de vigencia SCD2. |
| `valid_to` | `datetime` | sí | — | Fin de vigencia SCD2. |
| `is_current` | `bool` | no | — | Versión vigente. |
| `restatement_count` | `int` | no | mín. 0 | Número de reexpresiones previas. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo fuente o agregado silver. |
| `source_hash` | `string` | no | — | SHA-256 de linaje. |
| `ingested_at` | `datetime` | no | — | Fecha de ingesta. |
| `confidence` | `float` | no | mín. 0; máx. 1 | Confianza de 0 a 1. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`
- `period_id` → `dim_period(period_id)`
- `metric_key` → `dim_metric(metric_key)`

### `fact_route_traffic`

Etapa de materialización: `6`.

Grano declarado: `carrier_key, route_key, period_id, aircraft_type, service_class`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `carrier_key` | `string` | no | — | Aerolínea. |
| `route_key` | `string` | no | — | Ruta direccional. |
| `period_id` | `string` | no | — | Mes calendario. |
| `calendar_period_id` | `string` | no | — | Mes calendario comparable. |
| `fiscal_period_id` | `string` | no | — | Mes fiscal de la fuente; igual al calendario para T-100. |
| `aircraft_type` | `int` | no | — | Código BTS de aeronave. |
| `service_class` | `string` | no | — | Clase de servicio BTS. |
| `departures_scheduled` | `float` | no | — | Salidas programadas. |
| `departures_performed` | `float` | no | — | Salidas realizadas. |
| `seats` | `float` | no | — | Asientos ofrecidos. |
| `passengers` | `float` | no | — | Pasajeros transportados. |
| `freight_kg` | `float` | no | — | Carga convertida de libras a kg. |
| `mail_kg` | `float` | no | — | Correo convertido de libras a kg. |
| `asm_miles` | `float` | no | — | Available seat miles. |
| `ask_km` | `float` | no | — | Available seat kilometers. |
| `rpm_miles` | `float` | no | — | Revenue passenger miles. |
| `rpk_km` | `float` | no | — | Revenue passenger kilometers. |
| `load_factor` | `float` | sí | — | RPM dividido entre ASM. |
| `distance_miles` | `float` | no | — | Distancia mediana de los segmentos. |
| `distance_km` | `float` | no | — | Distancia en kilómetros. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo silver agregado. |
| `source_hash` | `string` | no | — | Hash determinista del linaje agregado. |
| `ingested_at` | `datetime` | no | — | Última ingesta contribuyente. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`
- `route_key` → `dim_route(route_key)`
- `period_id` → `dim_period(period_id)`

### `fact_airport_traffic`

Etapa de materialización: `6`.

Grano declarado: `airport_iata, period_id, operator_group, source_system`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `airport_iata` | `string` | no | — | Código IATA de un aeropuerto real. |
| `period_id` | `string` | no | — | Mes calendario. |
| `calendar_period_id` | `string` | no | — | Mes calendario comparable. |
| `fiscal_period_id` | `string` | no | — | Mes fiscal de la fuente; igual al calendario. |
| `passengers_domestic` | `int` | sí | — | Pasajeros domésticos. |
| `passengers_international` | `int` | sí | — | Pasajeros internacionales. |
| `passengers_total` | `int` | sí | — | Pasajeros totales. |
| `cargo_tons` | `float` | sí | — | Carga en toneladas. |
| `operations` | `int` | sí | — | Operaciones aéreas. |
| `operator_group` | `string` | no | — | Operador o grupo. |
| `country` | `string` | no | — | País. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo fuente. |
| `source_hash` | `string` | no | — | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | — | Fecha de ingesta. |

Relaciones declaradas:

- `airport_iata` → `dim_airport(airport_iata)`
- `period_id` → `dim_period(period_id)`

### `fact_airport_group_traffic`

Etapa de materialización: `6`.

Grano declarado: `airport_group_key, period_id, source_system`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `airport_group_key` | `string` | no | — | Grupo aeroportuario observado. |
| `period_id` | `string` | no | — | Mes calendario. |
| `calendar_period_id` | `string` | no | — | Mes calendario comparable. |
| `fiscal_period_id` | `string` | no | — | Mes fiscal de referencia; igual al calendario. |
| `passengers_domestic` | `int` | sí | — | Pasajeros domésticos del grupo. |
| `passengers_international` | `int` | sí | — | Pasajeros internacionales del grupo. |
| `passengers_total` | `int` | sí | — | Pasajeros totales del grupo. |
| `cargo_tons` | `float` | sí | — | Carga del grupo en toneladas. |
| `operations` | `int` | sí | — | Operaciones aéreas del grupo. |
| `country` | `string` | no | — | País. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo fuente. |
| `source_hash` | `string` | no | — | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | — | Fecha de ingesta. |

Relaciones declaradas:

- `airport_group_key` → `dim_airport_group(airport_group_key)`
- `period_id` → `dim_period(period_id)`

### `fact_market_data`

Etapa de materialización: `6`.

Grano declarado: `carrier_key, date`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `carrier_key` | `string` | no | — | Emisor. |
| `ticker` | `string` | no | — | Ticker observado. |
| `date` | `datetime` | no | — | Sesión de mercado. |
| `calendar_period_id` | `string` | no | — | Fecha calendario ISO de la sesión. |
| `fiscal_period_id` | `string` | no | — | Fecha fiscal de referencia; igual a la fecha calendario. |
| `close` | `float` | no | — | Precio de cierre. |
| `adj_close` | `float` | no | — | Cierre ajustado. |
| `volume` | `int` | no | — | Volumen. |
| `currency` | `string` | no | — | Moneda de cotización. |
| `return_1d` | `float` | sí | — | Rendimiento diario. |
| `return_ytd` | `float` | sí | — | Rendimiento desde inicio de año. |
| `volatility_30d` | `float` | sí | — | Volatilidad anualizada de 30 sesiones. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo fuente. |
| `source_hash` | `string` | no | — | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | — | Fecha de ingesta. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`

### `fact_macro`

Etapa de materialización: `6`.

Grano declarado: `period_id, indicator_key, aggregation`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `period_id` | `string` | no | — | Mes o trimestre. |
| `period_type` | `string` | no | dominio: month, quarter | month o quarter. |
| `calendar_period_id` | `string` | no | — | Periodo calendario comparable. |
| `fiscal_period_id` | `string` | no | — | Periodo fiscal de referencia; igual al calendario. |
| `indicator_key` | `string` | no | — | Serie exógena. |
| `value` | `float` | no | — | Valor agregado. |
| `unit` | `string` | no | — | Unidad. |
| `aggregation` | `string` | no | dominio: average, close | average o close. |
| `source_system` | `string` | no | — | Sistema fuente. |
| `source_file` | `string` | no | — | Archivo silver fuente. |
| `source_hash` | `string` | no | — | Hash determinista del linaje. |
| `ingested_at` | `datetime` | no | — | Última ingesta contribuyente. |

Relaciones declaradas:

- `period_id` → `dim_period(period_id)`

### `fact_data_quality_issues`

Etapa de materialización: `6`.

Grano declarado: `issue_signature`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `issue_id` | `string` | no | — | Hash estable del issue. |
| `issue_signature` | `string` | no | único; patrón declarado | Firma semántica estable usada para deduplicar incidencias. |
| `issue_origin` | `string` | no | dominio: operational_ledger, derived_reconciliation | Mecanismo que detectó la incidencia. |
| `issue_type` | `string` | no | — | Tipo de problema. |
| `severity` | `string` | no | dominio: info, warning, error, critical | Severidad normalizada. |
| `status` | `string` | no | dominio: open, resolved, accepted | Estado canónico de la incidencia. |
| `resolved` | `bool` | no | — | Indica si la incidencia fue resuelta. |
| `layer` | `string` | no | — | Capa donde se detectó. |
| `dataset_name` | `string` | no | — | Dataset afectado. |
| `source_system` | `string` | no | — | Fuente afectada. |
| `source_file` | `string` | sí | — | Archivo involucrado. |
| `carrier_key` | `string` | sí | — | Aerolínea afectada. |
| `period_id` | `string` | sí | — | Periodo afectado. |
| `calendar_period_id` | `string` | sí | — | Periodo calendario afectado. |
| `fiscal_period_id` | `string` | sí | — | Periodo fiscal afectado. |
| `metric_key` | `string` | sí | — | Métrica afectada. |
| `observed_value` | `float` | sí | — | Valor observado. |
| `expected_value` | `float` | sí | — | Valor de comparación. |
| `difference_pct` | `float` | sí | — | Diferencia relativa. |
| `affected_rows` | `int` | sí | mín. 0 | Número de filas afectadas cuando puede determinarse. |
| `description` | `string` | no | — | Explicación accionable. |
| `evidence` | `string` | no | — | Evidencia estructurada reproducible. |
| `detected_at` | `datetime` | no | — | Fecha reproducible de la evidencia. |
| `resolved_at` | `datetime` | sí | — | Fecha de resolución cuando existe. |

### `fact_forecasts`

Etapa de materialización: `7`.

Grano declarado: `model_run_id, model_name, carrier_key, metric_key, period_id, is_backtest`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `model_run_id` | `string` | no | — | Identificador determinista de corrida. |
| `model_name` | `string` | no | — | Modelo que superó el gate de publicación. |
| `carrier_key` | `string` | no | — | Aerolínea objetivo. |
| `metric_key` | `string` | no | — | Métrica pronosticada. |
| `period_id` | `string` | no | — | Mes de backtest o pronóstico. |
| `forecast_value` | `float` | no | — | Pronóstico puntual. |
| `lower_80` | `float` | no | — | Límite inferior al 80 por ciento. |
| `upper_80` | `float` | no | — | Límite superior al 80 por ciento. |
| `lower_95` | `float` | no | — | Límite inferior al 95 por ciento. |
| `upper_95` | `float` | no | — | Límite superior al 95 por ciento. |
| `is_backtest` | `bool` | no | — | Distingue evaluación histórica de futuro. |
| `actual_value` | `float` | sí | — | Real observado |
| `error` | `float` | sí | — | Real menos pronóstico. |
| `abs_pct_error` | `float` | sí | — | Error porcentual absoluto. |
| `trained_through_period` | `string` | no | — | Último periodo visible al entrenar. |
| `features_used` | `string` | no | — | Variables disponibles al origen. |
| `trained_at` | `datetime` | no | — | Marca reproducible de la evidencia fuente. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`
- `metric_key` → `dim_metric(metric_key)`

### `dim_model_performance`

Etapa de materialización: `7`.

Grano declarado: `model_run_id, model_name, carrier_key, metric_key, evaluation_split`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable del resultado de evaluación. |
| `model_run_id` | `string` | no | — | Identificador determinista de corrida. |
| `model_name` | `string` | no | — | Modelo evaluado. |
| `carrier_key` | `string` | no | — | Aerolínea objetivo. |
| `metric_key` | `string` | no | — | Métrica evaluada. |
| `evaluation_split` | `string` | no | dominio: validation, test | Conjunto de evaluación; nunca train. |
| `validation_smape` | `float` | no | — | sMAPE de validación usado para selección. |
| `mape` | `float` | no | — | MAPE de test. |
| `smape` | `float` | no | — | sMAPE de test. |
| `mae` | `float` | no | — | MAE de test. |
| `rmse` | `float` | no | — | RMSE de test. |
| `mase` | `float` | no | — | MASE contra escala estacional. |
| `observations` | `int` | no | — | Orígenes de test. |
| `is_baseline` | `bool` | no | — | Identifica baseline. |
| `beats_seasonal_naive` | `bool` | no | — | Gate de desempeño en test. |
| `is_published` | `bool` | no | — | Modelo visible en dashboard. |
| `trained_through_period` | `string` | no | — | Corte de entrenamiento antes del test. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`
- `metric_key` → `dim_metric(metric_key)`

### `fact_report_language`

Etapa de materialización: `7`.

Grano declarado: `carrier_key, period_id, accession_number, section`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `carrier_key` | `string` | no | — | Emisor del reporte. |
| `period_id` | `string` | no | — | Periodo del reporte. |
| `accession_number` | `string` | no | — | Accession SEC. |
| `section` | `string` | no | — | Sección analizada. |
| `report_type` | `string` | no | — | Resultados o tráfico. |
| `word_count` | `int` | no | — | Palabras tokenizadas. |
| `readability_score` | `float` | no | — | Flesch Reading Ease aproximado. |
| `passive_ratio` | `float` | no | — | Construcciones pasivas aproximadas por oración. |
| `numeric_density` | `float` | no | — | Tokens numéricos sobre tokens totales. |
| `lm_positive_ratio` | `float` | no | — | Proporción positiva Loughran-McDonald. |
| `lm_negative_ratio` | `float` | no | — | Proporción negativa Loughran-McDonald. |
| `lm_uncertainty_ratio` | `float` | no | — | Proporción de incertidumbre Loughran-McDonald. |
| `lm_litigious_ratio` | `float` | no | — | Proporción litigiosa Loughran-McDonald. |
| `lm_constraining_ratio` | `float` | no | — | Proporción de restricción Loughran-McDonald. |
| `top_terms_json` | `string` | no | — | Términos TF-IDF principales. |
| `new_terms_json` | `string` | no | — | Vocabulario nuevo frente a reporte comparable previo. |
| `dropped_terms_json` | `string` | no | — | Vocabulario ausente frente a reporte comparable previo. |
| `source_file` | `string` | no | — | Archivo SEC fuente. |
| `source_hash` | `string` | no | — | Hash del archivo fuente. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`
- `period_id` → `dim_period(period_id)`

### `fact_anomalies`

Etapa de materialización: `7`.

Grano declarado: `anomaly_id`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `anomaly_id` | `string` | no | — | Hash estable de anomalía. |
| `anomaly_type` | `string` | no | — | Familia de detección. |
| `entity_type` | `string` | no | — | Aerolínea o ruta-año. |
| `entity_key` | `string` | no | — | Entidad afectada. |
| `period_id` | `string` | no | — | Periodo observado. |
| `metric_key` | `string` | no | — | Métrica observada. |
| `observed_value` | `float` | no | — | Valor observado. |
| `expected_value` | `float` | no | — | Referencia del detector. |
| `anomaly_score` | `float` | no | — | Intensidad estandarizada o relativa. |
| `direction` | `string` | no | dominio: above, below | Por encima o por debajo. |
| `severity` | `string` | no | dominio: low, medium, high | Severidad analítica. |
| `event_matched` | `bool` | no | — | Coincidencia temporal con evento conocido. |
| `event_title` | `string` | sí | — | Evento cercano si existe. |
| `event_date` | `datetime` | sí | — | Fecha del evento cercano. |
| `explanation` | `string` | no | — | Lectura accionable. |
| `source_tables` | `string` | no | — | Linaje de tablas. |
| `model_run_id` | `string` | no | — | Corrida determinista. |

### `dim_cluster_assignments`

Etapa de materialización: `7`.

Grano declarado: `model_run_id, exercise, entity_key, period_id`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable del resultado de clustering. |
| `model_run_id` | `string` | no | — | Corrida determinista. |
| `exercise` | `string` | no | — | Rutas o trimestres. |
| `entity_type` | `string` | no | — | Grano del ejercicio. |
| `entity_key` | `string` | no | — | Ruta o aerolínea. |
| `period_id` | `string` | no | — | Año o trimestre. |
| `cluster_id` | `int` | no | — | Etiqueta técnica. |
| `cluster_name` | `string` | no | — | Nombre de negocio. |
| `k` | `int` | no | — | Número elegido de clusters. |
| `silhouette` | `float` | no | — | Silueta global. |
| `stability_ari` | `float` | no | — | ARI promedio entre semillas. |
| `pca_1` | `float` | no | — | Primera componente para visualización. |
| `pca_2` | `float` | no | — | Segunda componente para visualización. |
| `features_json` | `string` | no | — | Features sin perder escala original. |
| `name_validation_status` | `string` | no | — | Estado de revisión del nombre. |

### `fact_study_results`

Etapa de materialización: `7`.

Grano declarado: `model_run_id, study_key`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `study_key` | `string` | no | — | Estudio de alto valor. |
| `title_es` | `string` | no | — | Título de negocio. |
| `finding_es` | `string` | no | — | Hallazgo escrito en español. |
| `estimate` | `float` | sí | — | Estimación principal cuando existe. |
| `unit` | `string` | no | — | Unidad de la estimación. |
| `period_id` | `string` | no | — | Ventana o corte analítico. |
| `comparison` | `string` | no | — | Base de comparación. |
| `confidence` | `string` | no | dominio: alta, media, baja | Confianza cualitativa. |
| `caveat` | `string` | no | — | Limitación material. |
| `source_tables` | `string` | no | — | Linaje de tablas. |
| `model_run_id` | `string` | no | — | Corrida determinista. |

### `fact_route_traffic_summary`

Etapa de materialización: `8`.

Grano declarado: `carrier_key, market_key, period_id`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `carrier_key` | `string` | no | — | Aerolínea. |
| `market_key` | `string` | no | — | Mercado bidireccional. |
| `period_id` | `string` | no | — | Mes calendario. |
| `origin_iata` | `string` | no | — | Primer extremo canónico. |
| `dest_iata` | `string` | no | — | Segundo extremo canónico. |
| `seats` | `float` | no | — | Asientos mensuales agregados. |
| `passengers` | `float` | no | — | Pasajeros mensuales agregados. |
| `asm_miles` | `float` | no | — | ASM mensuales agregados. |
| `rpm_miles` | `float` | no | — | RPM mensuales agregados. |
| `departures` | `float` | no | — | Salidas realizadas agregadas. |
| `load_factor` | `float` | sí | — | RPM dividido entre ASM. |
| `source_files` | `string` | no | — | Archivos contribuyentes. |
| `source_hash` | `string` | no | — | Hash determinista de linaje. |
| `ingested_at` | `datetime` | no | — | Última ingesta contribuyente. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`

### `fact_spread_decomposition`

Etapa de materialización: `8`.

Grano declarado: `period_id, component_key`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `period_id` | `string` | no | — | Trimestre final de la descomposición. |
| `comparison_period_id` | `string` | no | — | Trimestre inicial. |
| `component_key` | `string` | no | — | Precio |
| `component_name_es` | `string` | no | — | Etiqueta para la visualización. |
| `contribution` | `float` | sí | — | Aporte al cambio en centavos por ASK-km. |
| `display_order` | `int` | no | — | Orden del waterfall. |
| `is_identified` | `bool` | no | — | Distingue estimación de componente no identificable. |
| `caveat` | `string` | no | — | Limitación de interpretación. |
| `source_tables` | `string` | no | — | Linaje de tablas. |

### `fact_dashboard_coverage`

Etapa de materialización: `8`.

Grano declarado: `carrier_key, metric_key, period_type, segment`.

Clave primaria declarada: `record_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `record_id` | `string` | no | único; patrón declarado | Identificador estable calculado con la tabla y su grano natural. |
| `carrier_key` | `string` | no | — | Aerolínea. |
| `metric_key` | `string` | no | — | Métrica. |
| `period_type` | `string` | no | dominio: month, quarter, year | Mes |
| `segment` | `string` | no | dominio: total, domestic, international, transborder | Segmento reportado. |
| `observations` | `int` | no | — | Periodos con fila. |
| `first_period` | `string` | no | — | Primer periodo. |
| `last_period` | `string` | no | — | Último periodo. |
| `expected_periods` | `int` | no | — | Periodos calendario entre extremos. |
| `coverage_pct` | `float` | no | — | Observaciones sobre periodos esperados. |
| `null_values` | `int` | no | — | Filas con valor nulo. |

Relaciones declaradas:

- `carrier_key` → `dim_carrier(carrier_key)`
- `metric_key` → `dim_metric(metric_key)`

### `dim_source_artifact`

Etapa de materialización: `9`.

Grano declarado: `source_file, artifact_sha256`.

Clave primaria declarada: `artifact_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `artifact_id` | `string` | no | único; patrón declarado | Identificador estable del archivo Bronze físico. |
| `source_key` | `string` | no | — | Fuente canónica propietaria del artefacto. |
| `source_system` | `string` | no | — | Identificador técnico registrado en el manifiesto. |
| `source_file` | `string` | no | — | Ruta POSIX relativa dentro de Bronze. |
| `source_url` | `string` | no | — | URL HTTPS pública registrada en la descarga. |
| `is_direct_public_artifact` | `bool` | no | — | Indica si la política permite enlazar directamente el archivo. |
| `downloaded_at` | `datetime` | no | — | Fecha de descarga del artefacto. |
| `artifact_sha256` | `string` | no | patrón declarado | SHA-256 de los bytes originales e inmutables. |
| `artifact_format` | `string` | no | — | Extensión o formato físico normalizado. |
| `content_type` | `string` | no | — | Tipo MIME declarado sin parámetros. |
| `byte_size` | `int` | no | mín. 0 | Tamaño físico del archivo. |
| `http_status` | `int` | no | mín. 0 | Estado HTTP conservado por la descarga. |
| `download_method` | `string` | no | — | Método utilizado para obtener el artefacto. |
| `logical_key` | `string` | no | — | Identidad lógica versionada de la descarga. |
| `logical_version` | `int` | no | mín. 1 | Número monotónico de la versión lógica. |
| `filename_version` | `int` | no | mín. 1 | Versión incluida en el nombre inmutable. |
| `is_latest_version` | `bool` | no | — | Indica la última versión conocida de la clave lógica. |

Relaciones declaradas:

- `source_key` → `dim_source(source_key)`

### `bridge_record_lineage`

Etapa de materialización: `9`.

Grano declarado: `lineage_link_id`.

Clave primaria declarada: `lineage_link_id`.

| Columna | Tipo | Nulo | Controles | Descripción |
|---|---|---:|---|---|
| `lineage_link_id` | `string` | no | único; patrón declarado | Identificador estable de la relación de linaje. |
| `record_id` | `string` | no | patrón declarado | Registro Gold o analítico documentado. |
| `table_name` | `string` | no | patrón declarado | Tabla propietaria del record_id. |
| `lineage_type` | `string` | no | dominio: direct_artifact, derived, curated | Tipo explícito de linaje. |
| `link_type` | `string` | no | dominio: artifact, parent_record, declaration | Clase de contribuyente representado por la fila. |
| `lineage_status` | `string` | no | dominio: resolved_to_artifact, resolved_to_parent_record, declared_without_artifact | Estado de resolución del enlace. |
| `has_direct_artifact` | `bool` | no | — | Indica si el registro tiene al menos un archivo directo. |
| `artifact_id` | `string` | sí | patrón declarado | Artefacto contribuyente cuando el enlace es directo. |
| `artifact_sha256` | `string` | sí | patrón declarado | SHA-256 del archivo original; nunca un hash derivado. |
| `parent_record_id` | `string` | sí | patrón declarado | Registro padre cuando el resultado es derivado. |
| `lineage_fingerprint` | `string` | no | patrón declarado | Fingerprint de la combinación completa de contribuyentes. |
| `lineage_note` | `string` | sí | — | Declaración explícita cuando no existe un artefacto directo. |

Relaciones declaradas:

- `artifact_id` → `dim_source_artifact(artifact_id)`

## Catálogo de métricas

Las interpretaciones provienen de `docs/plan/11-glosario-kpis.md`; las métricas técnicas no mostradas en el dashboard conservan una descripción de trazabilidad.

### `adjusted_ebitdar` — EBITDAR ajustado

- Categoría: `profitability`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. utilidad antes de intereses, impuestos, depreciación, amortización y
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. utilidad antes de intereses, impuestos, depreciación, amortización y
- Por qué importa: utilidad antes de intereses, impuestos, depreciación, amortización y
- Advertencias: desde la entrada de estas normas, los arrendamientos van al balance como activo por derecho de uso y pasivo, y la renta se convierte en depreciación + interés. Eso **cambió el significado del EBITDAR** y complica la comparación con periodos anteriores y con empresas bajo la otra norma (Delta, US-GAAP). **Declararlo en el dashboard.** Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: EBITDAR ajustado

### `aircraft_utilization` — Utilización de flota

- Categoría: `operational`
- Unidad: `hours_per_day`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: mejor amortización de un activo carísimo. Los ULCC maximizan esto agresivamente (aviones en el aire 12+ horas/día).
- Si baja: aviones parados = capital ocioso. Puede deberse a mantenimiento, restricciones de slots, o problemas de la cadena de suministro (los motores GTF han tenido a aviones en tierra en toda la industria).
- Por qué importa: horas de vuelo por avión por día.
- Advertencias: un network carrier tiene utilización estructuralmente menor porque opera bancos de conexión en su hub, lo que implica aviones en tierra esperando. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Aircraft Utilization — Utilización de flota

### `ancillary_share` — Participación de ingresos auxiliares

- Categoría: `financial`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `ingreso auxiliar / ingreso total`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. qué proporción del ingreso viene de fuentes distintas al boleto (equipaje, selección de asiento, prioridad, cambios, programa de lealtad, tarjetas cobranded).
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. qué proporción del ingreso viene de fuentes distintas al boleto (equipaje, selección de asiento, prioridad, cambios, programa de lealtad, tarjetas cobranded).
- Por qué importa: comparar Aeroméxico vs Volaris en esta métrica ilustra dos filosofías de negocio opuestas en el mismo mercado.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Ancillary Revenue Share

### `asm_per_aircraft` — ASM por aeronave

- Categoría: `operational`
- Unidad: `miles_per_aircraft`
- Consolidación: `non_additive`
- Fórmula: `ASM / número de aviones`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `ASM / número de aviones` **Uso:** proxy de productividad de flota cuando no se publica la utilización en horas.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `ASM / número de aviones` **Uso:** proxy de productividad de flota cuando no se publica la utilización en horas.
- Por qué importa: proxy de productividad de flota cuando no se publica la utilización en horas.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: ASM per Aircraft

### `asm_total` — ASM — asientos-milla disponibles

- Categoría: `capacity`
- Unidad: `miles`
- Consolidación: `sum`
- Fórmula: `asientos disponibles × distancia volada`, sumado sobre todos los vuelos.
- Si sube: la aerolínea está creciendo su oferta. Bueno **solo si** la demanda (RPK) crece igual o más rápido; si no, el load factor cae y probablemente el yield también.
- Si baja: contracción o disciplina de capacidad. En una industria con sobreoferta, recortar capacidad suele **subir** los precios y el margen unitario. No es automáticamente malo — de hecho, "disciplina de capacidad" es un elogio en el sector.
- Por qué importa: la capacidad que la aerolínea puso a la venta.
- Advertencias: ASK (km) ≠ ASM (millas). Factor: 1 milla = 1.609344 km. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: ASK / ASM — Available Seat Kilometers / Miles

### `average_stage_length` — Etapa promedio

- Categoría: `operational`
- Unidad: `kilometers`
- Consolidación: `non_additive`
- Fórmula: `ASK / asientos ofrecidos` (o `RPK / pasajeros`).
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. la distancia media de un vuelo de la aerolínea.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. la distancia media de un vuelo de la aerolínea.
- Por qué importa: la distancia media de un vuelo de la aerolínea.
- Advertencias: nunca comparar métricas unitarias entre aerolíneas sin ajustar por esto. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Average Stage Length — Etapa promedio

### `break_even_load_factor` — Factor de ocupación de equilibrio

- Categoría: `profitability`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `CASK / Yield`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. qué porcentaje de ocupación necesita la aerolínea para cubrir sus costos.
- Si baja: mayor resiliencia — la aerolínea aguanta una caída de demanda sin perder dinero.
- Por qué importa: graficarlo contra el load factor real. La distancia entre ambos es el **colchón de seguridad** de la aerolínea, y se explica solo visualmente.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Break-even Load Factor

### `cask` — CASK

- Categoría: `unit_cost`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: `gastos operativos totales / ASK`
- Si sube: presión de costos (combustible, salarios, mantenimiento, aeroportuarios) o menor utilización.
- Si baja: eficiencia, escala, o etapas más largas.
- Por qué importa: cuánto cuesta ofrecer un asiento-kilómetro.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK / CASM — Cost per Available Seat Kilometer / Mile

### `cask_ex_fuel` — CASK ex combustible

- Categoría: `unit_cost`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: `(gastos operativos − gasto de combustible) / ASK`
- Si sube: problema real de costos, salvo que se explique por etapas más cortas.
- Si baja: eficiencia estructural genuina. Es la métrica que más valoran los analistas.
- Por qué importa: el costo unitario excluyendo combustible.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK ex-fuel / CASM ex-fuel — la métrica de eficiencia real

### `casm` — CASM

- Categoría: `unit_cost`
- Unidad: `usd_cents`
- Consolidación: `non_additive`
- Fórmula: `gastos operativos totales / ASK`
- Si sube: presión de costos (combustible, salarios, mantenimiento, aeroportuarios) o menor utilización.
- Si baja: eficiencia, escala, o etapas más largas.
- Por qué importa: cuánto cuesta ofrecer un asiento-kilómetro.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK / CASM — Cost per Available Seat Kilometer / Mile

### `casm_ex_fuel` — CASM ex combustible

- Categoría: `unit_cost`
- Unidad: `usd_cents`
- Consolidación: `non_additive`
- Fórmula: `(gastos operativos − gasto de combustible) / ASK`
- Si sube: problema real de costos, salvo que se explique por etapas más cortas.
- Si baja: eficiencia estructural genuina. Es la métrica que más valoran los analistas.
- Por qué importa: el costo unitario excluyendo combustible.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK ex-fuel / CASM ex-fuel — la métrica de eficiencia real

### `fleet_size` — Flota

- Categoría: `operational`
- Unidad: `count`
- Consolidación: `latest`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. número de aeronaves en operación. Aeroméxico: 166 en 1Q26.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. número de aeronaves en operación. Aeroméxico: 166 en 1Q26.
- Por qué importa: denominador de las métricas de productividad de activo.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Fleet Size — Flota

### `fuel_cost_share` — Participación del combustible en costos

- Categoría: `unit_cost`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `gasto de combustible / gasto operativo total`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `gasto de combustible / gasto operativo total` **Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la exposición de la aerolínea.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `gasto de combustible / gasto operativo total` **Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la exposición de la aerolínea.
- Por qué importa: **Fórmula:** `gasto de combustible / gasto operativo total` **Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la exposición de la aerolínea.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Fuel Cost Share

### `jet_fuel_elasticity` — Elasticidad al jet fuel

- Categoría: `unit_cost`
- Unidad: `ratio`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. cuánto sube el CASM cuando sube 1% el precio del jet fuel.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. cuánto sube el CASM cuando sube 1% el precio del jet fuel.
- Por qué importa: escenarios. "Si el jet fuel sube 20%, el margen operativo cae X puntos, todo lo demás constante."
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Elasticidad al jet fuel

### `load_factor_derived` — Factor de ocupación derivado

- Categoría: `demand`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `RPK / ASK`
- Si sube: mejor utilización del activo. Cada avión que despega con más gente reparte sus costos fijos entre más pasajeros.
- Si baja: hay capacidad que se está desperdiciando.
- Por qué importa: qué porcentaje de los asientos ofrecidos se vendió.
- Advertencias: un load factor alto **no** es bueno por sí solo. Se puede llenar cualquier avión bajando el precio lo suficiente. Hay que mirarlo junto con el yield. Un network carrier opera estructuralmente más bajo que un ULCC porque vende conexiones y asientos premium que requieren dejar inventario disponible. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Load Factor — Factor de ocupación

### `load_factor_total` — Factor de ocupación

- Categoría: `demand`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `RPK / ASK`
- Si sube: mejor utilización del activo. Cada avión que despega con más gente reparte sus costos fijos entre más pasajeros.
- Si baja: hay capacidad que se está desperdiciando.
- Por qué importa: qué porcentaje de los asientos ofrecidos se vendió.
- Advertencias: un load factor alto **no** es bueno por sí solo. Se puede llenar cualquier avión bajando el precio lo suficiente. Hay que mirarlo junto con el yield. Un network carrier opera estructuralmente más bajo que un ULCC porque vende conexiones y asientos premium que requieren dejar inventario disponible. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Load Factor — Factor de ocupación

### `market_share_domestic_mx` — Participación doméstica en México

- Categoría: `market`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC)
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC) **Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.**
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC) **Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.**
- Por qué importa: **Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC) **Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.**
- Advertencias: decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.** Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Market Share doméstico

### `on_time_departure_pct` — Puntualidad

- Categoría: `operational`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. porcentaje de vuelos que llegan dentro de la ventana de puntualidad (típicamente 15 minutos).
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. porcentaje de vuelos que llegan dentro de la ventana de puntualidad (típicamente 15 minutos).
- Por qué importa: porcentaje de vuelos que llegan dentro de la ventana de puntualidad (típicamente 15 minutos).
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: OTP — On-Time Performance / Puntualidad

### `operating_margin` — Margen operativo

- Categoría: `profitability`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: `utilidad operativa / ingreso total`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `utilidad operativa / ingreso total` **Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en aviación es sólido; la industria opera históricamente con márgenes delgados. ## Ingresos auxiliares y mix
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `utilidad operativa / ingreso total` **Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en aviación es sólido; la industria opera históricamente con márgenes delgados. ## Ingresos auxiliares y mix
- Por qué importa: **Fórmula:** `utilidad operativa / ingreso total` **Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en aviación es sólido; la industria opera históricamente con márgenes delgados. ## Ingresos auxiliares y mix
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Margen operativo

### `pask` — PASK

- Categoría: `profitability`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: la aerolínea está ganando más por unidad de capacidad. Fin de la discusión.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. la diferencia entre lo que ingresa y lo que cuesta cada asiento-kilómetro.
- Por qué importa: RASK o CASK por separado son media película. Una aerolínea con CASK altísimo puede ser muy rentable si su RASK es aún más alto (Emirates), y una con CASK bajísimo puede perder dinero si su RASK se derrumba. **Lo que importa es el spread.**
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Spread RASK − CASK — el margen unitario (PASK)

### `passengers` — Pasajeros transportados

- Categoría: `demand`
- Unidad: `count`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Por qué importa: conteo de pasajeros.
- Advertencias: un pasajero con conexión puede contarse una o dos veces según la fuente. AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes sin verificar la definición. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Passengers — Pasajeros transportados

### `passengers_afac` — Pasajeros AFAC

- Categoría: `demand`
- Unidad: `count`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Por qué importa: conteo de pasajeros.
- Advertencias: un pasajero con conexión puede contarse una o dos veces según la fuente. AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes sin verificar la definición. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Passengers — Pasajeros transportados

### `passengers_afac_sa` — Pasajeros AFAC desestacionalizados

- Categoría: `demand`
- Unidad: `count`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Por qué importa: conteo de pasajeros.
- Advertencias: un pasajero con conexión puede contarse una o dos veces según la fuente. AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes sin verificar la definición. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Passengers — Pasajeros transportados

### `prask` — PRASK

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Por qué importa: comparar TRASM contra PRASM revela cuánto pesa el ingreso no-boleto.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: PRASM — Passenger Revenue per ASM

### `prasm` — PRASM

- Categoría: `unit_revenue`
- Unidad: `usd_cents`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Por qué importa: comparar TRASM contra PRASM revela cuánto pesa el ingreso no-boleto.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: PRASM — Passenger Revenue per ASM

### `rask` — RASK

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: `ingreso total / ASK`
- Si sube: la aerolínea está monetizando mejor su capacidad — sea por precio, por mejor mix, por más ingreso auxiliar, o por más carga.
- Si baja: presión de precios, exceso de capacidad, o mix desfavorable.
- Por qué importa: cuánto ingreso genera cada asiento-kilómetro ofrecido.
- Advertencias: sube o baja mecánicamente con el stage length. Ajustar. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: RASK / RASM — Revenue per Available Seat Kilometer / Mile

### `route_hhi` — HHI de red

- Categoría: `market`
- Unidad: `index`
- Consolidación: `non_additive`
- Fórmula: `Σ (share_ruta_i)²`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `Σ (share_ruta_i)²` **Uso:** mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub. Un HHI alto significa concentración → mayor exposición a un choque localizado (ej. saturación del AICM). ## Costo de combustible
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `Σ (share_ruta_i)²` **Uso:** mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub. Un HHI alto significa concentración → mayor exposición a un choque localizado (ej. saturación del AICM). ## Costo de combustible
- Por qué importa: mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub. Un HHI alto significa concentración → mayor exposición a un choque localizado (ej. saturación del AICM).
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: HHI — Índice de concentración de la red

### `rpm_total` — RPM — pasajeros-milla de pago

- Categoría: `demand`
- Unidad: `miles`
- Consolidación: `sum`
- Fórmula: `pasajeros de pago × distancia volada`.
- Si sube: más gente volando más lejos. Positivo, casi siempre.
- Si baja: caída de demanda o de red.
- Por qué importa: la demanda efectivamente vendida.
- Advertencias: solo cuenta pasajeros de pago; los pases de empleado y los premios de lealtad suelen excluirse (varía por aerolínea — verificar la definición de cada una). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: RPK / RPM — Revenue Passenger Kilometers / Miles

### `sla_cask` — CASK ajustado por etapa

- Categoría: `unit_cost`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: `gastos operativos totales / ASK`
- Si sube: presión de costos (combustible, salarios, mantenimiento, aeroportuarios) o menor utilización.
- Si baja: eficiencia, escala, o etapas más largas.
- Por qué importa: cuánto cuesta ofrecer un asiento-kilómetro.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK / CASM — Cost per Available Seat Kilometer / Mile

### `sla_rask` — RASK ajustado por etapa

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: `ingreso total / ASK`
- Si sube: la aerolínea está monetizando mejor su capacidad — sea por precio, por mejor mix, por más ingreso auxiliar, o por más carga.
- Si baja: presión de precios, exceso de capacidad, o mix desfavorable.
- Por qué importa: cuánto ingreso genera cada asiento-kilómetro ofrecido.
- Advertencias: sube o baja mecánicamente con el stage length. Ajustar. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: RASK / RASM — Revenue per Available Seat Kilometer / Mile

### `trasm` — TRASM

- Categoría: `unit_revenue`
- Unidad: `usd_cents`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. RASM incluyendo **todo** el ingreso (pasaje + carga + auxiliares + otros).
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. RASM incluyendo **todo** el ingreso (pasaje + carga + auxiliares + otros).
- Por qué importa: captura la capacidad de la aerolínea de generar ingreso por vías distintas al boleto, que es donde está la batalla moderna del sector.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: TRASM — Total Revenue per ASM

### `unit_margin` — Margen unitario

- Categoría: `profitability`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: la aerolínea está ganando más por unidad de capacidad. Fin de la discusión.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. la diferencia entre lo que ingresa y lo que cuesta cada asiento-kilómetro.
- Por qué importa: RASK o CASK por separado son media película. Una aerolínea con CASK altísimo puede ser muy rentable si su RASK es aún más alto (Emirates), y una con CASK bajísimo puede perder dinero si su RASK se derrumba. **Lo que importa es el spread.**
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Spread RASK − CASK — el margen unitario (PASK)

### `yield` — Yield

- Categoría: `unit_revenue`
- Unidad: `usd_cents`
- Consolidación: `non_additive`
- Fórmula: `ingreso de pasaje / RPK`
- Si sube: poder de precio, mejor mix (más premium, más business, menos promoción).
- Si baja: guerra de precios, o la aerolínea está llenando aviones con tarifa baja.
- Por qué importa: el precio promedio por kilómetro-pasajero vendido. Es el "precio unitario" de la aerolínea.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Yield

### `yield_derived` — Yield derivado

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Consolidación: `non_additive`
- Fórmula: `ingreso de pasaje / RPK`
- Si sube: poder de precio, mejor mix (más premium, más business, menos promoción).
- Si baja: guerra de precios, o la aerolínea está llenando aviones con tarifa baja.
- Por qué importa: el precio promedio por kilómetro-pasajero vendido. Es el "precio unitario" de la aerolínea.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Yield

### `adjusted_ebitdar_company_normalized` — Adjusted Ebitdar Company Normalized

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Adjusted Ebitdar Company Normalized sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Adjusted Ebitdar Company Normalized baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Adjusted Ebitdar Company Normalized ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `aircraft_communications_traffic_services` — Aircraft Communications Traffic Services

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Aircraft Communications Traffic Services sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Aircraft Communications Traffic Services baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Aircraft Communications Traffic Services ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `aircraft_leasing_expense` — Arrendamiento de aeronaves

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Arrendamiento de aeronaves sube, aumenta la presión financiera; confirma sus impulsores y el periodo comparable.
- Si baja: Si Arrendamiento de aeronaves baja, puede aliviar la presión financiera; confirma sus impulsores y el periodo comparable.
- Por qué importa: Arrendamiento de aeronaves ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cargo_revenue` — Cargo Revenue

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cargo Revenue sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Cargo Revenue baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Cargo Revenue ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cash_and_cash_equivalents` — Efectivo y equivalentes

- Categoría: `operational`
- Unidad: `usd`
- Consolidación: `latest`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Efectivo y equivalentes sube, puede ser favorable; confirma sus impulsores y el periodo comparable.
- Si baja: Si Efectivo y equivalentes baja, puede presionar el desempeño; confirma sus impulsores y el periodo comparable.
- Por qué importa: Efectivo y equivalentes ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cask_derived` — Cask Derived

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cask Derived sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Cask Derived baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Cask Derived ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cask_ex_fuel_derived` — Cask Ex Fuel Derived

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cask Ex Fuel Derived sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Cask Ex Fuel Derived baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Cask Ex Fuel Derived ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `depreciation_amortization` — Depreciation Amortization

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Depreciation Amortization sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Depreciation Amortization baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Depreciation Amortization ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ebitdar_margin` — Margen EBITDAR ajustado

- Categoría: `financial`
- Unidad: `fraction`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Margen EBITDAR ajustado sube, puede ser favorable; confirma sus impulsores y el periodo comparable.
- Si baja: Si Margen EBITDAR ajustado baja, puede presionar el desempeño; confirma sus impulsores y el periodo comparable.
- Por qué importa: Margen EBITDAR ajustado ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ebitdar_margin_company_normalized` — Ebitdar Margin Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ebitdar Margin Company Normalized sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ebitdar Margin Company Normalized baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ebitdar Margin Company Normalized ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `equity_investees_share` — Equity Investees Share

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Equity Investees Share sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Equity Investees Share baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Equity Investees Share ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `fuel_liters` — Fuel Liters

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Fuel Liters sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Fuel Liters baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Fuel Liters ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `impairment_reversal` — Impairment Reversal

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Impairment Reversal sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Impairment Reversal baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Impairment Reversal ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `income_before_tax` — Income Before Tax

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Income Before Tax sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Income Before Tax baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Income Before Tax ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `income_tax` — Income Tax

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Income Tax sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Income Tax baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Income Tax ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `jet_fuel_expense` — Gasto de combustible

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Gasto de combustible sube, aumenta la presión financiera; confirma sus impulsores y el periodo comparable.
- Si baja: Si Gasto de combustible baja, puede aliviar la presión financiera; confirma sus impulsores y el periodo comparable.
- Por qué importa: Gasto de combustible ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `maintenance_expense` — Gasto de mantenimiento

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Gasto de mantenimiento sube, aumenta la presión financiera; confirma sus impulsores y el periodo comparable.
- Si baja: Si Gasto de mantenimiento baja, puede aliviar la presión financiera; confirma sus impulsores y el periodo comparable.
- Por qué importa: Gasto de mantenimiento ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `net_finance_cost` — Net Finance Cost

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Net Finance Cost sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Net Finance Cost baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Net Finance Cost ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `net_income` — Utilidad neta

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Utilidad neta sube, puede ser favorable; confirma sus impulsores y el periodo comparable.
- Si baja: Si Utilidad neta baja, puede presionar el desempeño; confirma sus impulsores y el periodo comparable.
- Por qué importa: Utilidad neta ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_expenses_total` — Operating Expenses Total

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Expenses Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Operating Expenses Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Operating Expenses Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_income` — Utilidad operativa

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Utilidad operativa sube, puede ser favorable; confirma sus impulsores y el periodo comparable.
- Si baja: Si Utilidad operativa baja, puede presionar el desempeño; confirma sus impulsores y el periodo comparable.
- Por qué importa: Utilidad operativa ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_income_company_normalized` — Operating Income Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Income Company Normalized sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Operating Income Company Normalized baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Operating Income Company Normalized ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_margin_company_normalized` — Operating Margin Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Margin Company Normalized sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Operating Margin Company Normalized baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Operating Margin Company Normalized ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `other_income_loss_net` — Other Income Loss Net

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Other Income Loss Net sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Other Income Loss Net baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Other Income Loss Net ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `other_revenue` — Other Revenue

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Other Revenue sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Other Revenue baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Other Revenue ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `passenger_revenue` — Passenger Revenue

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Passenger Revenue sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Passenger Revenue baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Passenger Revenue ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `passenger_services_expense` — Passenger Services Expense

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Passenger Services Expense sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Passenger Services Expense baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Passenger Services Expense ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `prask_derived` — Prask Derived

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Prask Derived sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Prask Derived baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Prask Derived ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_adjusted_ebitdar` — Qoq Growth Adjusted Ebitdar

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Adjusted Ebitdar sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Adjusted Ebitdar baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Adjusted Ebitdar ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_asm_total` — Qoq Growth Asm Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Asm Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Asm Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Asm Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_cask` — Qoq Growth Cask

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Cask sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Cask baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Cask ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_load_factor_total` — Qoq Growth Load Factor Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Load Factor Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Load Factor Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Load Factor Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_net_income` — Qoq Growth Net Income

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Net Income sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Net Income baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Net Income ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_operating_income` — Qoq Growth Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Operating Income sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Operating Income baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Operating Income ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_passengers` — Qoq Growth Passengers

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Passengers sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Passengers baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Passengers ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_rask` — Qoq Growth Rask

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Rask sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Rask baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Rask ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_rpm_total` — Qoq Growth Rpm Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Rpm Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Rpm Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Rpm Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_total_revenue` — Qoq Growth Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Total Revenue sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Qoq Growth Total Revenue baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Qoq Growth Total Revenue ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `rask_derived` — Rask Derived

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Rask Derived sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Rask Derived baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Rask Derived ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `revenue_per_passenger` — Revenue Per Passenger

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Revenue Per Passenger sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Revenue Per Passenger baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Revenue Per Passenger ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `selling_administrative_expense` — Gastos de venta y administración

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Gastos de venta y administración sube, aumenta la presión financiera; confirma sus impulsores y el periodo comparable.
- Si baja: Si Gastos de venta y administración baja, puede aliviar la presión financiera; confirma sus impulsores y el periodo comparable.
- Por qué importa: Gastos de venta y administración ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_assets` — Activos totales

- Categoría: `operational`
- Unidad: `usd`
- Consolidación: `latest`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Activos totales sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Activos totales baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Activos totales ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_equity` — Capital contable

- Categoría: `operational`
- Unidad: `usd`
- Consolidación: `latest`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Capital contable sube, puede ser favorable; confirma sus impulsores y el periodo comparable.
- Si baja: Si Capital contable baja, puede presionar el desempeño; confirma sus impulsores y el periodo comparable.
- Por qué importa: Capital contable ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_liabilities` — Pasivos totales

- Categoría: `operational`
- Unidad: `usd`
- Consolidación: `latest`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Pasivos totales sube, aumenta la presión financiera; confirma sus impulsores y el periodo comparable.
- Si baja: Si Pasivos totales baja, puede aliviar la presión financiera; confirma sus impulsores y el periodo comparable.
- Por qué importa: Pasivos totales ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_revenue` — Ingreso total

- Categoría: `financial`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ingreso total sube, puede ser favorable; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ingreso total baja, puede presionar el desempeño; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ingreso total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_revenue_company_normalized` — Total Revenue Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Total Revenue Company Normalized sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Total Revenue Company Normalized baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Total Revenue Company Normalized ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `travel_agent_commissions` — Travel Agent Commissions

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Travel Agent Commissions sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Travel Agent Commissions baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Travel Agent Commissions ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_adjusted_ebitdar` — Ttm Adjusted Ebitdar

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Adjusted Ebitdar sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Adjusted Ebitdar baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Adjusted Ebitdar ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_asm_total` — Ttm Asm Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Asm Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Asm Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Asm Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_net_income` — Ttm Net Income

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Net Income sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Net Income baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Net Income ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_operating_income` — Ttm Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Operating Income sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Operating Income baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Operating Income ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_passengers` — Ttm Passengers

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Passengers sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Passengers baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Passengers ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_rpm_total` — Ttm Rpm Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Rpm Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Rpm Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Rpm Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_total_revenue` — Ttm Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Total Revenue sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Ttm Total Revenue baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Ttm Total Revenue ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `wages_salaries_benefits` — Sueldos, salarios y prestaciones

- Categoría: `operational`
- Unidad: `usd`
- Consolidación: `sum`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Sueldos, salarios y prestaciones sube, aumenta la presión financiera; confirma sus impulsores y el periodo comparable.
- Si baja: Si Sueldos, salarios y prestaciones baja, puede aliviar la presión financiera; confirma sus impulsores y el periodo comparable.
- Por qué importa: Sueldos, salarios y prestaciones ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_adjusted_ebitdar` — Yoy Growth Adjusted Ebitdar

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Adjusted Ebitdar sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Adjusted Ebitdar baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Adjusted Ebitdar ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_asm_total` — Yoy Growth Asm Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Asm Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Asm Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Asm Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_cask` — Yoy Growth Cask

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Cask sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Cask baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Cask ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_load_factor_total` — Yoy Growth Load Factor Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Load Factor Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Load Factor Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Load Factor Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_net_income` — Yoy Growth Net Income

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Net Income sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Net Income baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Net Income ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_operating_income` — Yoy Growth Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Operating Income sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Operating Income baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Operating Income ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_passengers` — Yoy Growth Passengers

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Passengers sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Passengers baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Passengers ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_rask` — Yoy Growth Rask

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Rask sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Rask baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Rask ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_rpm_total` — Yoy Growth Rpm Total

- Categoría: `operational`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Rpm Total sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Rpm Total baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Rpm Total ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_total_revenue` — Yoy Growth Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Consolidación: `non_additive`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Total Revenue sube, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Si baja: Si Yoy Growth Total Revenue baja, no es mejor ni peor por sí solo; confirma sus impulsores y el periodo comparable.
- Por qué importa: Yoy Growth Total Revenue ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

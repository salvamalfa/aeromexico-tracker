# Diccionario de datos

> Archivo generado automáticamente por `python -m src.transform.generate_data_dictionary`.
> Contrato: `stage6_v1.0.0`. No editar manualmente.

## Tablas gold

### `dim_carrier`

Clave primaria declarada: `carrier_key`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `carrier_key` | `string` | no | Clave estable de la entidad aérea. |
| `carrier_name` | `string` | no | Razón o nombre operacional. |
| `carrier_name_short` | `string` | no | Nombre corto para visualización. |
| `iata_code` | `string` | sí | Código IATA de dos caracteres. |
| `icao_code` | `string` | sí | Código ICAO. |
| `country` | `string` | sí | País base de la entidad. |
| `business_model` | `string` | no | Modelo de negocio normalizado. |
| `is_public` | `bool` | no | Indica si cotiza en bolsa. |
| `ticker` | `string` | sí | Ticker principal usado por el proyecto. |
| `exchange` | `string` | sí | Bolsa principal o combinación de bolsas. |
| `cik` | `string` | sí | CIK de SEC |
| `reporting_standard` | `string` | sí | IFRS o US-GAAP. |
| `reporting_currency` | `string` | sí | Moneda funcional de reporte. |
| `unit_system` | `string` | no | Sistema de unidades preferido por la fuente. |
| `fiscal_year_end_month` | `int` | sí | Mes de cierre del ejercicio fiscal. |
| `parent_carrier_key` | `string` | sí | Clave del grupo consolidante. |
| `is_peer` | `bool` | no | Identifica peers del análisis. |
| `is_focus` | `bool` | no | Identifica la compañía objetivo. |
| `valid_from` | `date` | no | Inicio de vigencia de la identidad. |
| `valid_to` | `date` | sí | Fin de vigencia de la identidad. |
| `is_current` | `bool` | no | Versión vigente de la identidad. |

### `dim_period`

Clave primaria declarada: `period_id`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `period_id` | `string` | no | Clave de mes |
| `period_type` | `string` | no | month |
| `period_start_date` | `date` | no | Primer día incluido. |
| `period_end_date` | `date` | no | Último día incluido. |
| `year` | `int` | no | Año calendario de cierre. |
| `quarter` | `int` | sí | Trimestre calendario de cierre. |
| `month` | `int` | sí | Mes calendario de cierre. |
| `days_in_period` | `int` | no | Días calendario incluidos. |
| `is_covid_period` | `bool` | no | Periodo entre marzo de 2020 y diciembre de 2021. |
| `prior_period_id` | `string` | sí | Periodo comparable inmediatamente anterior. |
| `prior_year_period_id` | `string` | sí | Mismo periodo del año previo. |
| `fiscal_period_id` | `string` | no | Identificador fiscal por defecto. |
| `calendar_period_id` | `string` | no | Identificador calendario. |
| `easter_date` | `date` | no | Domingo de Pascua del año. |
| `easter_quarter` | `int` | no | Trimestre que contiene Pascua. |
| `easter_days_in_q1` | `int` | no | Días de la ventana Domingo de Ramos a lunes de Pascua que caen en Q1. |
| `easter_days_in_q2` | `int` | no | Días de la ventana Domingo de Ramos a lunes de Pascua que caen en Q2. |

### `dim_metric`

Clave primaria declarada: `metric_key`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `metric_key` | `string` | no | Clave estable de la métrica. |
| `metric_name_es` | `string` | no | Nombre en español. |
| `metric_name_en` | `string` | no | Nombre en inglés. |
| `metric_category` | `string` | no | Categoría analítica. |
| `unit_normalized` | `string` | no | Unidad normalizada esperada. |
| `formula` | `string` | sí | Fórmula literal. |
| `higher_is_better` | `bool` | sí | Sentido favorable; nulo cuando depende del contexto. |
| `business_interpretation_up` | `string` | no | Lectura de negocio cuando sube. |
| `business_interpretation_down` | `string` | no | Lectura de negocio cuando baja. |
| `why_it_matters` | `string` | no | Relevancia de negocio. |
| `typical_range_network` | `string` | sí | Referencia aproximada para network carriers. |
| `typical_range_ulcc` | `string` | sí | Referencia aproximada para ULCC. |
| `caveats` | `string` | no | Advertencias de comparabilidad y definición. |
| `display_format` | `string` | no | Formato de presentación. |
| `display_order` | `int` | no | Orden sugerido en UI. |
| `glossary_section` | `string` | sí | Encabezado fuente en el glosario. |
| `is_dashboard_metric` | `bool` | no | Métrica prevista para mostrarse en el dashboard. |

### `dim_route`

Clave primaria declarada: `route_key`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `route_key` | `string` | no | Ruta direccional origen-destino. |
| `origin_iata` | `string` | no | Aeropuerto de origen. |
| `dest_iata` | `string` | no | Aeropuerto de destino. |
| `origin_country` | `string` | no | País de origen. |
| `dest_country` | `string` | no | País de destino. |
| `distance_km` | `float` | no | Distancia mediana en kilómetros. |
| `distance_miles` | `float` | no | Distancia mediana en millas estatuta. |
| `is_domestic_mx` | `bool` | no | Ambos extremos están en México. |
| `is_transborder_us` | `bool` | no | Ruta México-Estados Unidos. |
| `is_international` | `bool` | no | Cruza una frontera. |
| `market_key` | `string` | no | Mercado bidireccional canónico. |

### `dim_airport`

Clave primaria declarada: `airport_iata`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `airport_iata` | `string` | sí | Código IATA. |
| `airport_icao` | `string` | sí | Código ICAO. |
| `name` | `string` | sí | Nombre del aeropuerto. |
| `city` | `string` | sí | Ciudad. |
| `country` | `string` | sí | País. |
| `latitude` | `float` | sí | Latitud. |
| `longitude` | `float` | sí | Longitud. |
| `elevation` | `float` | sí | Elevación publicada. |
| `type` | `string` | sí | Tipo de instalación. |
| `operator_group` | `string` | sí | Grupo operador mexicano. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | no | Archivo bronze fuente. |
| `source_hash` | `string` | no | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | Fecha de ingesta. |
| `parser_version` | `string` | no | Versión del parser. |

### `dim_events`

Clave primaria declarada: `event_date, title`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `event_date` | `datetime` | no | Fecha del evento. |
| `event_type` | `string` | no | Tipo de evento. |
| `event_category` | `string` | no | Categoría analítica. |
| `title` | `string` | no | Título corto. |
| `description` | `string` | no | Descripción. |
| `affected_carriers` | `string` | no | Entidades afectadas. |
| `impact_direction` | `string` | no | Dirección esperada del impacto. |
| `source_url` | `string` | no | Fuente primaria. |
| `confidence` | `string` | no | Confianza cualitativa. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | sí | Archivo bronze fuente. |
| `source_hash` | `string` | sí | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | Fecha de ingesta. |
| `parser_version` | `string` | no | Versión del parser. |

### `dim_fx_period`

Clave primaria declarada: `period_id, currency_pair`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `rate_avg` | `float` | no | Tipo promedio del periodo. |
| `rate_close` | `float` | no | Último tipo disponible del periodo. |
| `rate_min` | `float` | no | Mínimo del periodo. |
| `rate_max` | `float` | no | Máximo del periodo. |
| `period_id` | `string` | no | Periodo calendario. |
| `period_type` | `string` | no | month |
| `currency_pair` | `string` | no | Par cotizado como moneda local por USD. |
| `pnl_conversion_method` | `string` | no | Método para flujos de P&L. |
| `balance_conversion_method` | `string` | no | Método para saldos. |

### `dim_fuel_period`

Clave primaria declarada: `period_id`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `price_avg_usd_per_gallon` | `float` | no | Precio promedio. |
| `price_close_usd_per_gallon` | `float` | no | Precio de cierre. |
| `price_min_usd_per_gallon` | `float` | no | Precio mínimo. |
| `price_max_usd_per_gallon` | `float` | no | Precio máximo. |
| `period_id` | `string` | no | Periodo calendario. |
| `period_type` | `string` | no | month o quarter. |
| `price_avg_yoy_pct` | `float` | sí | Variación interanual del promedio. |

### `fx_business_calendar`

Clave primaria declarada: `date, currency_pair`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `date` | `datetime` | no | Día hábil. |
| `rate_close` | `float` | no | Tipo publicado o arrastrado. |
| `is_published` | `bool` | no | El valor fue publicado ese día. |
| `fill_method` | `string` | no | Método de llenado. |
| `currency_pair` | `string` | no | Par de monedas. |

### `fuel_business_calendar`

Clave primaria declarada: `date`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `date` | `datetime` | no | Día hábil. |
| `price_usd_per_gallon` | `float` | no | Precio publicado o arrastrado. |
| `is_published` | `bool` | no | El valor fue publicado ese día. |
| `fill_method` | `string` | no | Método de llenado. |

### `fact_carrier_metrics`

Clave primaria declarada: `carrier_key, period_id, metric_key, segment, source_system, valid_from`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `carrier_key` | `string` | no | Aerolínea o grupo. |
| `period_id` | `string` | no | Periodo reportado. |
| `calendar_period_id` | `string` | no | Periodo calendario comparable. |
| `fiscal_period_id` | `string` | no | Periodo fiscal de la fuente. |
| `period_type` | `string` | no | Granularidad temporal. |
| `period_start_date` | `date` | no | Inicio del periodo. |
| `period_end_date` | `date` | no | Fin del periodo. |
| `metric_key` | `string` | no | Métrica. |
| `segment` | `string` | no | total |
| `value` | `float` | sí | Valor normalizado en la unidad declarada. |
| `value_metric` | `float` | sí | Equivalente métrico cuando aplica. |
| `value_imperial` | `float` | sí | Equivalente imperial cuando aplica. |
| `value_as_reported` | `float` | sí | Valor numérico publicado antes de escala. |
| `unit_as_reported` | `string` | sí | Unidad literal publicada. |
| `unit_normalized` | `string` | no | Unidad normalizada de value. |
| `currency` | `string` | sí | Moneda original. |
| `value_original_currency` | `float` | sí | Valor ya escalado en moneda original. |
| `value_usd` | `float` | sí | Equivalente en USD. |
| `fx_rate_used` | `float` | sí | Tipo de cambio aplicado. |
| `fx_rate_type` | `string` | sí | average o close. |
| `is_derived` | `bool` | no | Valor calculado por el pipeline. |
| `is_preliminary` | `bool` | no | Fuente lo marca preliminar. |
| `is_estimated` | `bool` | no | Valor estimado y etiquetado. |
| `derivation_formula` | `string` | sí | Fórmula para valores derivados. |
| `valid_from` | `datetime` | no | Inicio de vigencia SCD2. |
| `valid_to` | `datetime` | sí | Fin de vigencia SCD2. |
| `is_current` | `bool` | no | Versión vigente. |
| `restatement_count` | `int` | no | Número de reexpresiones previas. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | no | Archivo fuente o agregado silver. |
| `source_hash` | `string` | no | SHA-256 de linaje. |
| `ingested_at` | `datetime` | no | Fecha de ingesta. |
| `confidence` | `float` | no | Confianza de 0 a 1. |

### `fact_route_traffic`

Clave primaria declarada: `carrier_key, route_key, period_id, aircraft_type, service_class`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `carrier_key` | `string` | no | Aerolínea. |
| `route_key` | `string` | no | Ruta direccional. |
| `period_id` | `string` | no | Mes calendario. |
| `calendar_period_id` | `string` | no | Mes calendario comparable. |
| `fiscal_period_id` | `string` | no | Mes fiscal de la fuente; igual al calendario para T-100. |
| `aircraft_type` | `int` | no | Código BTS de aeronave. |
| `service_class` | `string` | no | Clase de servicio BTS. |
| `departures_scheduled` | `float` | no | Salidas programadas. |
| `departures_performed` | `float` | no | Salidas realizadas. |
| `seats` | `float` | no | Asientos ofrecidos. |
| `passengers` | `float` | no | Pasajeros transportados. |
| `freight_kg` | `float` | no | Carga convertida de libras a kg. |
| `mail_kg` | `float` | no | Correo convertido de libras a kg. |
| `asm_miles` | `float` | no | Available seat miles. |
| `ask_km` | `float` | no | Available seat kilometers. |
| `rpm_miles` | `float` | no | Revenue passenger miles. |
| `rpk_km` | `float` | no | Revenue passenger kilometers. |
| `load_factor` | `float` | sí | RPM dividido entre ASM. |
| `distance_miles` | `float` | no | Distancia mediana de los segmentos. |
| `distance_km` | `float` | no | Distancia en kilómetros. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | no | Archivo silver agregado. |
| `source_hash` | `string` | no | Hash determinista del linaje agregado. |
| `ingested_at` | `datetime` | no | Última ingesta contribuyente. |

### `fact_airport_traffic`

Clave primaria declarada: `airport_iata, period_id, operator_group, source_system`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `airport_iata` | `string` | no | Código IATA o clave de total de grupo. |
| `period_id` | `string` | no | Mes calendario. |
| `calendar_period_id` | `string` | no | Mes calendario comparable. |
| `fiscal_period_id` | `string` | no | Mes fiscal de la fuente; igual al calendario. |
| `passengers_domestic` | `int` | sí | Pasajeros domésticos. |
| `passengers_international` | `int` | sí | Pasajeros internacionales. |
| `passengers_total` | `int` | sí | Pasajeros totales. |
| `cargo_tons` | `float` | sí | Carga en toneladas. |
| `operations` | `int` | sí | Operaciones aéreas. |
| `operator_group` | `string` | no | Operador o grupo. |
| `country` | `string` | no | País. |
| `is_group_total` | `bool` | no | Fila agregada del grupo. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | no | Archivo fuente. |
| `source_hash` | `string` | no | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | Fecha de ingesta. |

### `fact_market_data`

Clave primaria declarada: `carrier_key, date`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `carrier_key` | `string` | no | Emisor. |
| `ticker` | `string` | no | Ticker observado. |
| `date` | `datetime` | no | Sesión de mercado. |
| `calendar_period_id` | `string` | no | Fecha calendario ISO de la sesión. |
| `fiscal_period_id` | `string` | no | Fecha fiscal de referencia; igual a la fecha calendario. |
| `close` | `float` | no | Precio de cierre. |
| `adj_close` | `float` | no | Cierre ajustado. |
| `volume` | `int` | no | Volumen. |
| `currency` | `string` | no | Moneda de cotización. |
| `return_1d` | `float` | sí | Rendimiento diario. |
| `return_ytd` | `float` | sí | Rendimiento desde inicio de año. |
| `volatility_30d` | `float` | sí | Volatilidad anualizada de 30 sesiones. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | no | Archivo fuente. |
| `source_hash` | `string` | no | SHA-256 fuente. |
| `ingested_at` | `datetime` | no | Fecha de ingesta. |

### `fact_macro`

Clave primaria declarada: `period_id, indicator_key, aggregation`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `period_id` | `string` | no | Mes o trimestre. |
| `period_type` | `string` | no | month o quarter. |
| `calendar_period_id` | `string` | no | Periodo calendario comparable. |
| `fiscal_period_id` | `string` | no | Periodo fiscal de referencia; igual al calendario. |
| `indicator_key` | `string` | no | Serie exógena. |
| `value` | `float` | no | Valor agregado. |
| `unit` | `string` | no | Unidad. |
| `aggregation` | `string` | no | average o close. |
| `source_system` | `string` | no | Sistema fuente. |
| `source_file` | `string` | no | Archivo silver fuente. |
| `source_hash` | `string` | no | Hash determinista del linaje. |
| `ingested_at` | `datetime` | no | Última ingesta contribuyente. |

### `fact_data_quality_issues`

Clave primaria declarada: `issue_id`.

| Columna | Tipo | Nulo | Descripción |
|---|---|---:|---|
| `issue_id` | `string` | no | Hash estable del issue. |
| `issue_type` | `string` | no | Tipo de problema. |
| `severity` | `string` | no | warning o error. |
| `source_system` | `string` | no | Fuente afectada. |
| `carrier_key` | `string` | sí | Aerolínea afectada. |
| `period_id` | `string` | sí | Periodo afectado. |
| `calendar_period_id` | `string` | sí | Periodo calendario afectado. |
| `fiscal_period_id` | `string` | sí | Periodo fiscal afectado. |
| `metric_key` | `string` | sí | Métrica afectada. |
| `observed_value` | `float` | sí | Valor observado. |
| `expected_value` | `float` | sí | Valor de comparación. |
| `difference_pct` | `float` | sí | Diferencia relativa. |
| `detail` | `string` | no | Explicación accionable. |
| `source_file` | `string` | sí | Archivo involucrado. |
| `detected_at` | `datetime` | no | Fecha reproducible de la evidencia. |

## Catálogo de métricas

Las interpretaciones provienen de `docs/plan/11-glosario-kpis.md`; las métricas técnicas no mostradas en el dashboard conservan una descripción de trazabilidad.

### `adjusted_ebitdar` — EBITDAR ajustado

- Categoría: `profitability`
- Unidad: `usd`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. utilidad antes de intereses, impuestos, depreciación, amortización y
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. utilidad antes de intereses, impuestos, depreciación, amortización y
- Por qué importa: utilidad antes de intereses, impuestos, depreciación, amortización y
- Advertencias: desde la entrada de estas normas, los arrendamientos van al balance como activo por derecho de uso y pasivo, y la renta se convierte en depreciación + interés. Eso **cambió el significado del EBITDAR** y complica la comparación con periodos anteriores y con empresas bajo la otra norma (Delta, US-GAAP). **Declararlo en el dashboard.** Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: EBITDAR ajustado

### `aircraft_utilization` — Utilización de flota

- Categoría: `operational`
- Unidad: `hours_per_day`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: mejor amortización de un activo carísimo. Los ULCC maximizan esto agresivamente (aviones en el aire 12+ horas/día).
- Si baja: aviones parados = capital ocioso. Puede deberse a mantenimiento, restricciones de slots, o problemas de la cadena de suministro (los motores GTF han tenido a aviones en tierra en toda la industria).
- Por qué importa: horas de vuelo por avión por día.
- Advertencias: un network carrier tiene utilización estructuralmente menor porque opera bancos de conexión en su hub, lo que implica aviones en tierra esperando. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Aircraft Utilization — Utilización de flota

### `ancillary_share` — Participación de ingresos auxiliares

- Categoría: `financial`
- Unidad: `fraction`
- Fórmula: `ingreso auxiliar / ingreso total`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. qué proporción del ingreso viene de fuentes distintas al boleto (equipaje, selección de asiento, prioridad, cambios, programa de lealtad, tarjetas cobranded).
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. qué proporción del ingreso viene de fuentes distintas al boleto (equipaje, selección de asiento, prioridad, cambios, programa de lealtad, tarjetas cobranded).
- Por qué importa: comparar Aeroméxico vs Volaris en esta métrica ilustra dos filosofías de negocio opuestas en el mismo mercado.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Ancillary Revenue Share

### `asm_per_aircraft` — ASM por aeronave

- Categoría: `operational`
- Unidad: `miles_per_aircraft`
- Fórmula: `ASM / número de aviones`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `ASM / número de aviones` **Uso:** proxy de productividad de flota cuando no se publica la utilización en horas.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `ASM / número de aviones` **Uso:** proxy de productividad de flota cuando no se publica la utilización en horas.
- Por qué importa: proxy de productividad de flota cuando no se publica la utilización en horas.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: ASM per Aircraft

### `asm_total` — ASM — asientos-milla disponibles

- Categoría: `capacity`
- Unidad: `miles`
- Fórmula: `asientos disponibles × distancia volada`, sumado sobre todos los vuelos.
- Si sube: la aerolínea está creciendo su oferta. Bueno **solo si** la demanda (RPK) crece igual o más rápido; si no, el load factor cae y probablemente el yield también.
- Si baja: contracción o disciplina de capacidad. En una industria con sobreoferta, recortar capacidad suele **subir** los precios y el margen unitario. No es automáticamente malo — de hecho, "disciplina de capacidad" es un elogio en el sector.
- Por qué importa: la capacidad que la aerolínea puso a la venta.
- Advertencias: ASK (km) ≠ ASM (millas). Factor: 1 milla = 1.609344 km. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: ASK / ASM — Available Seat Kilometers / Miles

### `average_stage_length` — Etapa promedio

- Categoría: `operational`
- Unidad: `kilometers`
- Fórmula: `ASK / asientos ofrecidos` (o `RPK / pasajeros`).
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. la distancia media de un vuelo de la aerolínea.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. la distancia media de un vuelo de la aerolínea.
- Por qué importa: la distancia media de un vuelo de la aerolínea.
- Advertencias: nunca comparar métricas unitarias entre aerolíneas sin ajustar por esto. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Average Stage Length — Etapa promedio

### `break_even_load_factor` — Factor de ocupación de equilibrio

- Categoría: `profitability`
- Unidad: `fraction`
- Fórmula: `CASK / Yield`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. qué porcentaje de ocupación necesita la aerolínea para cubrir sus costos.
- Si baja: mayor resiliencia — la aerolínea aguanta una caída de demanda sin perder dinero.
- Por qué importa: graficarlo contra el load factor real. La distancia entre ambos es el **colchón de seguridad** de la aerolínea, y se explica solo visualmente.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Break-even Load Factor

### `cask` — CASK

- Categoría: `unit_cost`
- Unidad: `usd_cents_per_km`
- Fórmula: `gastos operativos totales / ASK`
- Si sube: presión de costos (combustible, salarios, mantenimiento, aeroportuarios) o menor utilización.
- Si baja: eficiencia, escala, o etapas más largas.
- Por qué importa: cuánto cuesta ofrecer un asiento-kilómetro.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK / CASM — Cost per Available Seat Kilometer / Mile

### `cask_ex_fuel` — CASK ex combustible

- Categoría: `unit_cost`
- Unidad: `usd_cents_per_km`
- Fórmula: `(gastos operativos − gasto de combustible) / ASK`
- Si sube: problema real de costos, salvo que se explique por etapas más cortas.
- Si baja: eficiencia estructural genuina. Es la métrica que más valoran los analistas.
- Por qué importa: el costo unitario excluyendo combustible.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK ex-fuel / CASM ex-fuel — la métrica de eficiencia real

### `casm` — CASM

- Categoría: `unit_cost`
- Unidad: `usd_cents`
- Fórmula: `gastos operativos totales / ASK`
- Si sube: presión de costos (combustible, salarios, mantenimiento, aeroportuarios) o menor utilización.
- Si baja: eficiencia, escala, o etapas más largas.
- Por qué importa: cuánto cuesta ofrecer un asiento-kilómetro.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK / CASM — Cost per Available Seat Kilometer / Mile

### `casm_ex_fuel` — CASM ex combustible

- Categoría: `unit_cost`
- Unidad: `usd_cents`
- Fórmula: `(gastos operativos − gasto de combustible) / ASK`
- Si sube: problema real de costos, salvo que se explique por etapas más cortas.
- Si baja: eficiencia estructural genuina. Es la métrica que más valoran los analistas.
- Por qué importa: el costo unitario excluyendo combustible.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK ex-fuel / CASM ex-fuel — la métrica de eficiencia real

### `fleet_size` — Flota

- Categoría: `operational`
- Unidad: `count`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. número de aeronaves en operación. Aeroméxico: 166 en 1Q26.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. número de aeronaves en operación. Aeroméxico: 166 en 1Q26.
- Por qué importa: denominador de las métricas de productividad de activo.
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Fleet Size — Flota

### `fuel_cost_share` — Participación del combustible en costos

- Categoría: `unit_cost`
- Unidad: `fraction`
- Fórmula: `gasto de combustible / gasto operativo total`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `gasto de combustible / gasto operativo total` **Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la exposición de la aerolínea.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `gasto de combustible / gasto operativo total` **Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la exposición de la aerolínea.
- Por qué importa: **Fórmula:** `gasto de combustible / gasto operativo total` **Referencia:** típicamente 20–40% según el precio del crudo. Es el termómetro de la exposición de la aerolínea.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Fuel Cost Share

### `jet_fuel_elasticity` — Elasticidad al jet fuel

- Categoría: `unit_cost`
- Unidad: `ratio`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. cuánto sube el CASM cuando sube 1% el precio del jet fuel.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. cuánto sube el CASM cuando sube 1% el precio del jet fuel.
- Por qué importa: escenarios. "Si el jet fuel sube 20%, el margen operativo cae X puntos, todo lo demás constante."
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Elasticidad al jet fuel

### `load_factor_derived` — Factor de ocupación derivado

- Categoría: `demand`
- Unidad: `fraction`
- Fórmula: `RPK / ASK`
- Si sube: mejor utilización del activo. Cada avión que despega con más gente reparte sus costos fijos entre más pasajeros.
- Si baja: hay capacidad que se está desperdiciando.
- Por qué importa: qué porcentaje de los asientos ofrecidos se vendió.
- Advertencias: un load factor alto **no** es bueno por sí solo. Se puede llenar cualquier avión bajando el precio lo suficiente. Hay que mirarlo junto con el yield. Un network carrier opera estructuralmente más bajo que un ULCC porque vende conexiones y asientos premium que requieren dejar inventario disponible. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Load Factor — Factor de ocupación

### `load_factor_total` — Factor de ocupación

- Categoría: `demand`
- Unidad: `fraction`
- Fórmula: `RPK / ASK`
- Si sube: mejor utilización del activo. Cada avión que despega con más gente reparte sus costos fijos entre más pasajeros.
- Si baja: hay capacidad que se está desperdiciando.
- Por qué importa: qué porcentaje de los asientos ofrecidos se vendió.
- Advertencias: un load factor alto **no** es bueno por sí solo. Se puede llenar cualquier avión bajando el precio lo suficiente. Hay que mirarlo junto con el yield. Un network carrier opera estructuralmente más bajo que un ULCC porque vende conexiones y asientos premium que requieren dejar inventario disponible. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Load Factor — Factor de ocupación

### `market_share_domestic_mx` — Participación doméstica en México

- Categoría: `market`
- Unidad: `fraction`
- Fórmula: `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC)
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC) **Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.**
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC) **Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.**
- Por qué importa: **Fórmula:** `pasajeros de la aerolínea / pasajeros totales del mercado` (fuente: AFAC) **Advertencia:** decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.**
- Advertencias: decidir si "Aeroméxico" incluye Aeroméxico Connect. AFAC los reporta separados; los financieros consolidan. **Ser consistente y declararlo.** Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Market Share doméstico

### `on_time_departure_pct` — Puntualidad

- Categoría: `operational`
- Unidad: `fraction`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. porcentaje de vuelos que llegan dentro de la ventana de puntualidad (típicamente 15 minutos).
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. porcentaje de vuelos que llegan dentro de la ventana de puntualidad (típicamente 15 minutos).
- Por qué importa: porcentaje de vuelos que llegan dentro de la ventana de puntualidad (típicamente 15 minutos).
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: OTP — On-Time Performance / Puntualidad

### `operating_margin` — Margen operativo

- Categoría: `profitability`
- Unidad: `fraction`
- Fórmula: `utilidad operativa / ingreso total`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `utilidad operativa / ingreso total` **Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en aviación es sólido; la industria opera históricamente con márgenes delgados. ## Ingresos auxiliares y mix
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `utilidad operativa / ingreso total` **Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en aviación es sólido; la industria opera históricamente con márgenes delgados. ## Ingresos auxiliares y mix
- Por qué importa: **Fórmula:** `utilidad operativa / ingreso total` **Referencia:** Aeroméxico 10.6% en 1Q26. Un margen operativo de doble dígito en aviación es sólido; la industria opera históricamente con márgenes delgados. ## Ingresos auxiliares y mix
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Margen operativo

### `pask` — PASK

- Categoría: `profitability`
- Unidad: `usd_cents_per_km`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: la aerolínea está ganando más por unidad de capacidad. Fin de la discusión.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. la diferencia entre lo que ingresa y lo que cuesta cada asiento-kilómetro.
- Por qué importa: RASK o CASK por separado son media película. Una aerolínea con CASK altísimo puede ser muy rentable si su RASK es aún más alto (Emirates), y una con CASK bajísimo puede perder dinero si su RASK se derrumba. **Lo que importa es el spread.**
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Spread RASK − CASK — el margen unitario (PASK)

### `passengers` — Pasajeros transportados

- Categoría: `demand`
- Unidad: `count`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Por qué importa: conteo de pasajeros.
- Advertencias: un pasajero con conexión puede contarse una o dos veces según la fuente. AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes sin verificar la definición. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Passengers — Pasajeros transportados

### `passengers_afac` — Pasajeros AFAC

- Categoría: `demand`
- Unidad: `count`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Por qué importa: conteo de pasajeros.
- Advertencias: un pasajero con conexión puede contarse una o dos veces según la fuente. AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes sin verificar la definición. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Passengers — Pasajeros transportados

### `passengers_afac_sa` — Pasajeros AFAC desestacionalizados

- Categoría: `demand`
- Unidad: `count`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. conteo de pasajeros.
- Por qué importa: conteo de pasajeros.
- Advertencias: un pasajero con conexión puede contarse una o dos veces según la fuente. AFAC y los reportes de la compañía pueden diferir por esto. **Nunca** mezclar fuentes sin verificar la definición. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Passengers — Pasajeros transportados

### `prask` — PRASK

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Por qué importa: comparar TRASM contra PRASM revela cuánto pesa el ingreso no-boleto.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: PRASM — Passenger Revenue per ASM

### `prasm` — PRASM

- Categoría: `unit_revenue`
- Unidad: `usd_cents`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. solo el ingreso de pasaje sobre la capacidad.
- Por qué importa: comparar TRASM contra PRASM revela cuánto pesa el ingreso no-boleto.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: PRASM — Passenger Revenue per ASM

### `rask` — RASK

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Fórmula: `ingreso total / ASK`
- Si sube: la aerolínea está monetizando mejor su capacidad — sea por precio, por mejor mix, por más ingreso auxiliar, o por más carga.
- Si baja: presión de precios, exceso de capacidad, o mix desfavorable.
- Por qué importa: cuánto ingreso genera cada asiento-kilómetro ofrecido.
- Advertencias: sube o baja mecánicamente con el stage length. Ajustar. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: RASK / RASM — Revenue per Available Seat Kilometer / Mile

### `route_hhi` — HHI de red

- Categoría: `market`
- Unidad: `index`
- Fórmula: `Σ (share_ruta_i)²`
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `Σ (share_ruta_i)²` **Uso:** mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub. Un HHI alto significa concentración → mayor exposición a un choque localizado (ej. saturación del AICM). ## Costo de combustible
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. **Fórmula:** `Σ (share_ruta_i)²` **Uso:** mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub. Un HHI alto significa concentración → mayor exposición a un choque localizado (ej. saturación del AICM). ## Costo de combustible
- Por qué importa: mide qué tan dependiente es la aerolínea de pocas rutas o de un solo hub. Un HHI alto significa concentración → mayor exposición a un choque localizado (ej. saturación del AICM).
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: HHI — Índice de concentración de la red

### `rpm_total` — RPM — pasajeros-milla de pago

- Categoría: `demand`
- Unidad: `miles`
- Fórmula: `pasajeros de pago × distancia volada`.
- Si sube: más gente volando más lejos. Positivo, casi siempre.
- Si baja: caída de demanda o de red.
- Por qué importa: la demanda efectivamente vendida.
- Advertencias: solo cuenta pasajeros de pago; los pases de empleado y los premios de lealtad suelen excluirse (varía por aerolínea — verificar la definición de cada una). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: RPK / RPM — Revenue Passenger Kilometers / Miles

### `sla_cask` — CASK ajustado por etapa

- Categoría: `unit_cost`
- Unidad: `usd_cents_per_km`
- Fórmula: `gastos operativos totales / ASK`
- Si sube: presión de costos (combustible, salarios, mantenimiento, aeroportuarios) o menor utilización.
- Si baja: eficiencia, escala, o etapas más largas.
- Por qué importa: cuánto cuesta ofrecer un asiento-kilómetro.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: CASK / CASM — Cost per Available Seat Kilometer / Mile

### `sla_rask` — RASK ajustado por etapa

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Fórmula: `ingreso total / ASK`
- Si sube: la aerolínea está monetizando mejor su capacidad — sea por precio, por mejor mix, por más ingreso auxiliar, o por más carga.
- Si baja: presión de precios, exceso de capacidad, o mix desfavorable.
- Por qué importa: cuánto ingreso genera cada asiento-kilómetro ofrecido.
- Advertencias: sube o baja mecánicamente con el stage length. Ajustar. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: RASK / RASM — Revenue per Available Seat Kilometer / Mile

### `trasm` — TRASM

- Categoría: `unit_revenue`
- Unidad: `usd_cents`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Cuando sube, revisa su efecto junto con las métricas relacionadas. RASM incluyendo **todo** el ingreso (pasaje + carga + auxiliares + otros).
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. RASM incluyendo **todo** el ingreso (pasaje + carga + auxiliares + otros).
- Por qué importa: captura la capacidad de la aerolínea de generar ingreso por vías distintas al boleto, que es donde está la batalla moderna del sector.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: TRASM — Total Revenue per ASM

### `unit_margin` — Margen unitario

- Categoría: `profitability`
- Unidad: `usd_cents_per_km`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: la aerolínea está ganando más por unidad de capacidad. Fin de la discusión.
- Si baja: Cuando baja, revisa su efecto junto con las métricas relacionadas. la diferencia entre lo que ingresa y lo que cuesta cada asiento-kilómetro.
- Por qué importa: RASK o CASK por separado son media película. Una aerolínea con CASK altísimo puede ser muy rentable si su RASK es aún más alto (Emirates), y una con CASK bajísimo puede perder dinero si su RASK se derrumba. **Lo que importa es el spread.**
- Advertencias: Compara siempre periodos y definiciones homogéneas. Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Spread RASK − CASK — el margen unitario (PASK)

### `yield` — Yield

- Categoría: `unit_revenue`
- Unidad: `usd_cents`
- Fórmula: `ingreso de pasaje / RPK`
- Si sube: poder de precio, mejor mix (más premium, más business, menos promoción).
- Si baja: guerra de precios, o la aerolínea está llenando aviones con tarifa baja.
- Por qué importa: el precio promedio por kilómetro-pasajero vendido. Es el "precio unitario" de la aerolínea.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Yield

### `yield_derived` — Yield derivado

- Categoría: `unit_revenue`
- Unidad: `usd_cents_per_km`
- Fórmula: `ingreso de pasaje / RPK`
- Si sube: poder de precio, mejor mix (más premium, más business, menos promoción).
- Si baja: guerra de precios, o la aerolínea está llenando aviones con tarifa baja.
- Por qué importa: el precio promedio por kilómetro-pasajero vendido. Es el "precio unitario" de la aerolínea.
- Advertencias: Compara siempre periodos y definiciones homogéneas. No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834). Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair.
- Sección del glosario: Yield

### `adjusted_ebitdar_company_normalized` — Adjusted Ebitdar Company Normalized

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Adjusted Ebitdar Company Normalized sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Adjusted Ebitdar Company Normalized baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Adjusted Ebitdar Company Normalized para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `aircraft_communications_traffic_services` — Aircraft Communications Traffic Services

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Aircraft Communications Traffic Services sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Aircraft Communications Traffic Services baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Aircraft Communications Traffic Services para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `aircraft_leasing_expense` — Aircraft Leasing Expense

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Aircraft Leasing Expense sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Aircraft Leasing Expense baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Aircraft Leasing Expense para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cargo_revenue` — Cargo Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cargo Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Cargo Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Cargo Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cash_and_cash_equivalents` — Cash And Cash Equivalents

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cash And Cash Equivalents sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Cash And Cash Equivalents baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Cash And Cash Equivalents para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cask_derived` — Cask Derived

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cask Derived sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Cask Derived baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Cask Derived para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `cask_ex_fuel_derived` — Cask Ex Fuel Derived

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Cask Ex Fuel Derived sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Cask Ex Fuel Derived baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Cask Ex Fuel Derived para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `depreciation_amortization` — Depreciation Amortization

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Depreciation Amortization sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Depreciation Amortization baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Depreciation Amortization para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ebitdar_margin` — Ebitdar Margin

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ebitdar Margin sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ebitdar Margin baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ebitdar Margin para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ebitdar_margin_company_normalized` — Ebitdar Margin Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ebitdar Margin Company Normalized sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ebitdar Margin Company Normalized baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ebitdar Margin Company Normalized para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `equity_investees_share` — Equity Investees Share

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Equity Investees Share sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Equity Investees Share baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Equity Investees Share para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `fuel_liters` — Fuel Liters

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Fuel Liters sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Fuel Liters baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Fuel Liters para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `impairment_reversal` — Impairment Reversal

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Impairment Reversal sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Impairment Reversal baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Impairment Reversal para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `income_before_tax` — Income Before Tax

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Income Before Tax sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Income Before Tax baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Income Before Tax para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `income_tax` — Income Tax

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Income Tax sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Income Tax baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Income Tax para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `jet_fuel_expense` — Jet Fuel Expense

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Jet Fuel Expense sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Jet Fuel Expense baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Jet Fuel Expense para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `maintenance_expense` — Maintenance Expense

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Maintenance Expense sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Maintenance Expense baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Maintenance Expense para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `net_finance_cost` — Net Finance Cost

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Net Finance Cost sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Net Finance Cost baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Net Finance Cost para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `net_income` — Net Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Net Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Net Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Net Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_expenses_total` — Operating Expenses Total

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Expenses Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Operating Expenses Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Operating Expenses Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_income` — Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Operating Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Operating Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_income_company_normalized` — Operating Income Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Income Company Normalized sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Operating Income Company Normalized baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Operating Income Company Normalized para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `operating_margin_company_normalized` — Operating Margin Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Operating Margin Company Normalized sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Operating Margin Company Normalized baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Operating Margin Company Normalized para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `other_income_loss_net` — Other Income Loss Net

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Other Income Loss Net sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Other Income Loss Net baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Other Income Loss Net para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `other_revenue` — Other Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Other Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Other Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Other Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `passenger_revenue` — Passenger Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Passenger Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Passenger Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Passenger Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `passenger_services_expense` — Passenger Services Expense

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Passenger Services Expense sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Passenger Services Expense baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Passenger Services Expense para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `prask_derived` — Prask Derived

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Prask Derived sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Prask Derived baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Prask Derived para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_adjusted_ebitdar` — Qoq Growth Adjusted Ebitdar

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Adjusted Ebitdar sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Adjusted Ebitdar baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Adjusted Ebitdar para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_asm_total` — Qoq Growth Asm Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Asm Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Asm Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Asm Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_cask` — Qoq Growth Cask

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Cask sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Cask baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Cask para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_load_factor_total` — Qoq Growth Load Factor Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Load Factor Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Load Factor Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Load Factor Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_net_income` — Qoq Growth Net Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Net Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Net Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Net Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_operating_income` — Qoq Growth Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Operating Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Operating Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Operating Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_passengers` — Qoq Growth Passengers

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Passengers sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Passengers baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Passengers para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_rask` — Qoq Growth Rask

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Rask sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Rask baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Rask para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_rpm_total` — Qoq Growth Rpm Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Rpm Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Rpm Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Rpm Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `qoq_growth_total_revenue` — Qoq Growth Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Qoq Growth Total Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Qoq Growth Total Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Qoq Growth Total Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `rask_derived` — Rask Derived

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Rask Derived sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Rask Derived baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Rask Derived para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `revenue_per_passenger` — Revenue Per Passenger

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Revenue Per Passenger sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Revenue Per Passenger baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Revenue Per Passenger para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `selling_administrative_expense` — Selling Administrative Expense

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Selling Administrative Expense sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Selling Administrative Expense baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Selling Administrative Expense para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_assets` — Total Assets

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Total Assets sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Total Assets baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Total Assets para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_equity` — Total Equity

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Total Equity sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Total Equity baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Total Equity para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_liabilities` — Total Liabilities

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Total Liabilities sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Total Liabilities baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Total Liabilities para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_revenue` — Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Total Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Total Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Total Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `total_revenue_company_normalized` — Total Revenue Company Normalized

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Total Revenue Company Normalized sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Total Revenue Company Normalized baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Total Revenue Company Normalized para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `travel_agent_commissions` — Travel Agent Commissions

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Travel Agent Commissions sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Travel Agent Commissions baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Travel Agent Commissions para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_adjusted_ebitdar` — Ttm Adjusted Ebitdar

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Adjusted Ebitdar sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Adjusted Ebitdar baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Adjusted Ebitdar para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_asm_total` — Ttm Asm Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Asm Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Asm Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Asm Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_net_income` — Ttm Net Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Net Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Net Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Net Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_operating_income` — Ttm Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Operating Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Operating Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Operating Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_passengers` — Ttm Passengers

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Passengers sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Passengers baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Passengers para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_rpm_total` — Ttm Rpm Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Rpm Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Rpm Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Rpm Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `ttm_total_revenue` — Ttm Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Ttm Total Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Ttm Total Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Ttm Total Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `wages_salaries_benefits` — Wages Salaries Benefits

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Wages Salaries Benefits sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Wages Salaries Benefits baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Wages Salaries Benefits para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_adjusted_ebitdar` — Yoy Growth Adjusted Ebitdar

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Adjusted Ebitdar sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Adjusted Ebitdar baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Adjusted Ebitdar para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_asm_total` — Yoy Growth Asm Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Asm Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Asm Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Asm Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_cask` — Yoy Growth Cask

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Cask sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Cask baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Cask para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_load_factor_total` — Yoy Growth Load Factor Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Load Factor Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Load Factor Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Load Factor Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_net_income` — Yoy Growth Net Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Net Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Net Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Net Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_operating_income` — Yoy Growth Operating Income

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Operating Income sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Operating Income baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Operating Income para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_passengers` — Yoy Growth Passengers

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Passengers sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Passengers baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Passengers para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_rask` — Yoy Growth Rask

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Rask sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Rask baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Rask para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_rpm_total` — Yoy Growth Rpm Total

- Categoría: `operational`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Rpm Total sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Rpm Total baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Rpm Total para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

### `yoy_growth_total_revenue` — Yoy Growth Total Revenue

- Categoría: `financial`
- Unidad: `varies`
- Fórmula: No declarada; valor reportado por la fuente.
- Si sube: Si Yoy Growth Total Revenue sube, valida la definición y sus impulsores antes de concluir.
- Si baja: Si Yoy Growth Total Revenue baja, valida la definición y sus impulsores antes de concluir.
- Por qué importa: Conserva el detalle reportado de Yoy Growth Total Revenue para trazabilidad y análisis especializado.
- Advertencias: Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.
- Sección del glosario: métrica técnica fuera del dashboard

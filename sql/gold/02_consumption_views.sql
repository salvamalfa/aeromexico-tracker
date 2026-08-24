-- Stage 6 documented consumption layer. The consolidated scope is the default.
CREATE OR REPLACE VIEW v_aeromexico_quarterly AS
SELECT
    period_id,
    MAX(value) FILTER (WHERE metric_key = 'total_revenue') AS total_revenue,
    MAX(value) FILTER (WHERE metric_key = 'adjusted_ebitdar') AS adjusted_ebitdar,
    MAX(value) FILTER (WHERE metric_key = 'ebitdar_margin') AS ebitdar_margin,
    MAX(value) FILTER (WHERE metric_key = 'operating_income') AS operating_income,
    MAX(value) FILTER (WHERE metric_key = 'operating_margin') AS operating_margin,
    MAX(value) FILTER (WHERE metric_key = 'net_income') AS net_income,
    MAX(value) FILTER (WHERE metric_key = 'passengers') AS passengers,
    MAX(value) FILTER (WHERE metric_key = 'asm_total') AS asm_miles,
    MAX(value_metric) FILTER (WHERE metric_key = 'asm_total') AS ask_km,
    MAX(value) FILTER (WHERE metric_key = 'rpm_total') AS rpm_miles,
    MAX(value_metric) FILTER (WHERE metric_key = 'rpm_total') AS rpk_km,
    MAX(value) FILTER (WHERE metric_key = 'load_factor_total') AS load_factor_reported,
    MAX(value) FILTER (WHERE metric_key = 'load_factor_derived') AS load_factor_derived,
    MAX(value) FILTER (WHERE metric_key = 'trasm') AS trasm_cents_per_mile,
    MAX(value) FILTER (WHERE metric_key = 'rask') AS rask_cents_per_km,
    MAX(value) FILTER (WHERE metric_key = 'casm') AS casm_cents_per_mile,
    MAX(value) FILTER (WHERE metric_key = 'cask') AS cask_cents_per_km,
    MAX(value) FILTER (WHERE metric_key = 'unit_margin') AS unit_margin_cents_per_km,
    MAX(value) FILTER (WHERE metric_key = 'fleet_size') AS fleet_size
FROM v_carrier_default
WHERE carrier_key = 'AEROMEXICO' AND period_type = 'quarter' AND segment = 'total'
GROUP BY period_id
ORDER BY period_id;

CREATE OR REPLACE VIEW v_peer_comparison AS
SELECT f.*, c.carrier_name_short, c.business_model, c.reporting_standard, c.fiscal_year_end_month
FROM v_carrier_default f
JOIN dim_carrier c USING (carrier_key)
WHERE f.period_type = 'quarter'
  AND f.segment = 'total'
  AND (c.is_focus OR c.is_peer);

CREATE OR REPLACE VIEW v_market_share_mx AS
WITH market AS (
    SELECT period_id, segment, value AS market_passengers
    FROM v_carrier_default
    WHERE carrier_key = 'MARKET_TOTAL_MX' AND metric_key = 'passengers_afac'
), carriers AS (
    SELECT carrier_key, period_id, segment, value AS carrier_passengers
    FROM v_carrier_default
    WHERE carrier_key <> 'MARKET_TOTAL_MX' AND metric_key = 'passengers_afac'
)
SELECT
    c.carrier_key,
    c.period_id,
    c.segment,
    c.carrier_passengers,
    m.market_passengers,
    c.carrier_passengers / NULLIF(m.market_passengers, 0) AS market_share
FROM carriers c
JOIN market m USING (period_id, segment);

CREATE OR REPLACE VIEW v_route_performance AS
SELECT
    f.*,
    r.origin_iata,
    r.dest_iata,
    r.market_key,
    r.is_transborder_us
FROM fact_route_traffic f
JOIN dim_route r USING (route_key);

CREATE OR REPLACE VIEW v_unit_economics AS
SELECT
    carrier_key,
    period_id,
    MAX(value) FILTER (WHERE metric_key = 'rask') AS rask,
    MAX(value) FILTER (WHERE metric_key = 'cask') AS cask,
    MAX(value) FILTER (WHERE metric_key = 'cask_ex_fuel') AS cask_ex_fuel,
    MAX(value) FILTER (WHERE metric_key = 'unit_margin') AS unit_margin,
    MAX(value) FILTER (WHERE metric_key = 'sla_rask') AS sla_rask,
    MAX(value) FILTER (WHERE metric_key = 'sla_cask') AS sla_cask,
    MAX(value) FILTER (WHERE metric_key = 'average_stage_length') AS stage_length_km,
    MAX(value) FILTER (WHERE metric_key = 'break_even_load_factor') AS break_even_load_factor,
    MAX(value) FILTER (WHERE metric_key = 'load_factor_total') AS load_factor
FROM v_carrier_default
WHERE period_type = 'quarter' AND segment = 'total'
GROUP BY carrier_key, period_id;

CREATE OR REPLACE VIEW v_data_health AS
WITH coverage AS (
    SELECT source_system, COUNT(*) AS rows, COUNT(DISTINCT carrier_key) AS carriers,
           MIN(period_start_date) AS first_date, MAX(period_end_date) AS last_date,
           MAX(ingested_at) AS last_ingested_at
    FROM fact_carrier_metrics
    GROUP BY source_system
), issues AS (
    SELECT source_system, COUNT(*) AS issue_count
    FROM fact_data_quality_issues
    GROUP BY source_system
)
SELECT c.*, COALESCE(i.issue_count, 0) AS issue_count
FROM coverage c
LEFT JOIN issues i USING (source_system);

CREATE OR REPLACE VIEW v_restatements AS
SELECT *
FROM fact_carrier_metrics
WHERE restatement_count > 0 OR NOT is_current
ORDER BY carrier_key, period_id, metric_key, source_system, valid_from;

CREATE OR REPLACE VIEW v_events_timeline AS
SELECT * FROM dim_events ORDER BY event_date;

CREATE OR REPLACE VIEW v_seasonally_adjusted AS
SELECT carrier_key, period_id, metric_key, segment, value, derivation_formula
FROM v_carrier_default
WHERE metric_key LIKE '%_sa';

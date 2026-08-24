-- Stage 6 business scopes and source precedence.
CREATE OR REPLACE VIEW v_carrier_standalone AS
SELECT f.*, 'standalone' AS reporting_scope
FROM fact_carrier_metrics f
WHERE f.is_current;

CREATE OR REPLACE VIEW v_carrier_consolidated AS
SELECT
    COALESCE(c.parent_carrier_key, f.carrier_key) AS carrier_key,
    f.period_id,
    f.calendar_period_id,
    f.fiscal_period_id,
    f.period_type,
    f.period_start_date,
    f.period_end_date,
    f.metric_key,
    f.segment,
    SUM(f.value) AS value,
    SUM(f.value_metric) AS value_metric,
    SUM(f.value_imperial) AS value_imperial,
    SUM(f.value_as_reported) AS value_as_reported,
    MIN(f.unit_as_reported) AS unit_as_reported,
    MIN(f.unit_normalized) AS unit_normalized,
    MIN(f.currency) AS currency,
    SUM(f.value_original_currency) AS value_original_currency,
    SUM(f.value_usd) AS value_usd,
    MIN(f.fx_rate_used) AS fx_rate_used,
    MIN(f.fx_rate_type) AS fx_rate_type,
    BOOL_OR(f.is_derived) AS is_derived,
    BOOL_OR(f.is_preliminary) AS is_preliminary,
    BOOL_OR(f.is_estimated) AS is_estimated,
    STRING_AGG(DISTINCT f.derivation_formula, ' | ') FILTER (WHERE f.derivation_formula IS NOT NULL) AS derivation_formula,
    MIN(f.valid_from) AS valid_from,
    MAX(f.valid_to) AS valid_to,
    TRUE AS is_current,
    MAX(f.restatement_count) AS restatement_count,
    f.source_system,
    STRING_AGG(DISTINCT f.source_file, ' | ') AS source_file,
    STRING_AGG(DISTINCT f.source_hash, ' | ') AS source_hash,
    MAX(f.ingested_at) AS ingested_at,
    MIN(f.confidence) AS confidence,
    'consolidated' AS reporting_scope
FROM fact_carrier_metrics f
JOIN dim_carrier c USING (carrier_key)
WHERE f.is_current
GROUP BY ALL;

CREATE OR REPLACE VIEW v_carrier_default AS
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY carrier_key, period_id, metric_key, segment
        ORDER BY
            CASE source_system
                WHEN 'sec_edgar' THEN 0
                WHEN 'aeromexico_ir' THEN 0
                WHEN 'derived_gold' THEN 0
                WHEN 'viva_ir' THEN 1
                WHEN 'peer_profile' THEN 1
                WHEN 'afac' THEN 1
                WHEN 'bmv_xbrl' THEN 5
                ELSE 2
            END,
            ingested_at DESC
    ) AS source_rank
    FROM v_carrier_consolidated
)
SELECT * EXCLUDE (source_rank)
FROM ranked
WHERE source_rank = 1;

CREATE OR REPLACE VIEW v_carrier_metrics_wide AS
SELECT
    carrier_key, period_id, period_type, segment,
    MAX(value) FILTER (WHERE metric_key = 'total_revenue') AS total_revenue,
    MAX(value) FILTER (WHERE metric_key = 'adjusted_ebitdar') AS adjusted_ebitdar,
    MAX(value) FILTER (WHERE metric_key = 'operating_margin') AS operating_margin,
    MAX(value) FILTER (WHERE metric_key = 'passengers') AS passengers,
    MAX(value) FILTER (WHERE metric_key = 'passengers_afac') AS passengers_afac,
    MAX(value) FILTER (WHERE metric_key = 'asm_total') AS asm_total,
    MAX(value) FILTER (WHERE metric_key = 'rpm_total') AS rpm_total,
    MAX(value) FILTER (WHERE metric_key = 'load_factor_total') AS load_factor_total,
    MAX(value) FILTER (WHERE metric_key = 'rask') AS rask,
    MAX(value) FILTER (WHERE metric_key = 'cask') AS cask,
    MAX(value) FILTER (WHERE metric_key = 'unit_margin') AS unit_margin,
    MAX(value) FILTER (WHERE metric_key = 'fleet_size') AS fleet_size
FROM v_carrier_default
GROUP BY carrier_key, period_id, period_type, segment;

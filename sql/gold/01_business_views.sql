-- Stage 6 business scopes and source precedence.
CREATE OR REPLACE VIEW v_carrier_standalone AS
SELECT f.*, 'standalone' AS reporting_scope
FROM fact_carrier_metrics f
WHERE f.is_current;

CREATE OR REPLACE VIEW v_carrier_consolidated AS
WITH annotated AS (
    SELECT
        f.*,
        COALESCE(c.parent_carrier_key, f.carrier_key) AS consolidated_carrier_key,
        m.consolidation_method,
        ROW_NUMBER() OVER (
            PARTITION BY
                COALESCE(c.parent_carrier_key, f.carrier_key),
                f.period_id,
                f.metric_key,
                f.segment,
                f.source_system
            ORDER BY
                CASE WHEN c.parent_carrier_key IS NULL THEN 0 ELSE 1 END,
                f.is_preliminary ASC,
                f.confidence DESC NULLS LAST,
                f.ingested_at DESC NULLS LAST,
                f.carrier_key,
                f.source_file
        ) AS consolidation_rank
    FROM fact_carrier_metrics f
    JOIN dim_carrier c USING (carrier_key)
    LEFT JOIN dim_metric m USING (metric_key)
    WHERE f.is_current
)
SELECT
    consolidated_carrier_key AS carrier_key,
    period_id,
    CASE WHEN consolidation_method = 'sum' THEN MIN(calendar_period_id)
         ELSE MAX(calendar_period_id) FILTER (WHERE consolidation_rank = 1) END AS calendar_period_id,
    CASE WHEN consolidation_method = 'sum' THEN MIN(fiscal_period_id)
         ELSE MAX(fiscal_period_id) FILTER (WHERE consolidation_rank = 1) END AS fiscal_period_id,
    CASE WHEN consolidation_method = 'sum' THEN MIN(period_type)
         ELSE MAX(period_type) FILTER (WHERE consolidation_rank = 1) END AS period_type,
    CASE WHEN consolidation_method = 'sum' THEN MIN(period_start_date)
         ELSE MAX(period_start_date) FILTER (WHERE consolidation_rank = 1) END AS period_start_date,
    CASE WHEN consolidation_method = 'sum' THEN MAX(period_end_date)
         ELSE MAX(period_end_date) FILTER (WHERE consolidation_rank = 1) END AS period_end_date,
    metric_key,
    segment,
    CASE
        WHEN consolidation_method IS NULL THEN error('Missing consolidation rule in dim_metric')
        WHEN consolidation_method = 'sum' THEN SUM(value)
        WHEN consolidation_method IN ('latest', 'non_additive') THEN MAX(value) FILTER (WHERE consolidation_rank = 1)
        WHEN consolidation_method = 'weighted' THEN error('Weighted consolidation requires an explicit weight metric')
        ELSE error('Unsupported consolidation method in dim_metric')
    END AS value,
    CASE WHEN consolidation_method = 'sum' THEN SUM(value_metric)
         ELSE MAX(value_metric) FILTER (WHERE consolidation_rank = 1) END AS value_metric,
    CASE WHEN consolidation_method = 'sum' THEN SUM(value_imperial)
         ELSE MAX(value_imperial) FILTER (WHERE consolidation_rank = 1) END AS value_imperial,
    CASE WHEN consolidation_method = 'sum' THEN SUM(value_as_reported)
         ELSE MAX(value_as_reported) FILTER (WHERE consolidation_rank = 1) END AS value_as_reported,
    MAX(unit_as_reported) FILTER (WHERE consolidation_rank = 1) AS unit_as_reported,
    MAX(unit_normalized) FILTER (WHERE consolidation_rank = 1) AS unit_normalized,
    MAX(currency) FILTER (WHERE consolidation_rank = 1) AS currency,
    CASE WHEN consolidation_method = 'sum' THEN SUM(value_original_currency)
         ELSE MAX(value_original_currency) FILTER (WHERE consolidation_rank = 1) END AS value_original_currency,
    CASE WHEN consolidation_method = 'sum' THEN SUM(value_usd)
         ELSE MAX(value_usd) FILTER (WHERE consolidation_rank = 1) END AS value_usd,
    MAX(fx_rate_used) FILTER (WHERE consolidation_rank = 1) AS fx_rate_used,
    MAX(fx_rate_type) FILTER (WHERE consolidation_rank = 1) AS fx_rate_type,
    CASE WHEN consolidation_method = 'sum' THEN BOOL_OR(is_derived)
         ELSE BOOL_OR(is_derived) FILTER (WHERE consolidation_rank = 1) END AS is_derived,
    CASE WHEN consolidation_method = 'sum' THEN BOOL_OR(is_preliminary)
         ELSE BOOL_OR(is_preliminary) FILTER (WHERE consolidation_rank = 1) END AS is_preliminary,
    CASE WHEN consolidation_method = 'sum' THEN BOOL_OR(is_estimated)
         ELSE BOOL_OR(is_estimated) FILTER (WHERE consolidation_rank = 1) END AS is_estimated,
    CASE WHEN consolidation_method = 'sum'
         THEN STRING_AGG(DISTINCT CAST(derivation_formula AS VARCHAR), ' | ') FILTER (WHERE derivation_formula IS NOT NULL)
         ELSE MAX(CAST(derivation_formula AS VARCHAR)) FILTER (WHERE consolidation_rank = 1) END AS derivation_formula,
    CASE WHEN consolidation_method = 'sum' THEN MIN(valid_from)
         ELSE MAX(valid_from) FILTER (WHERE consolidation_rank = 1) END AS valid_from,
    CASE WHEN consolidation_method = 'sum' THEN MAX(valid_to)
         ELSE MAX(valid_to) FILTER (WHERE consolidation_rank = 1) END AS valid_to,
    TRUE AS is_current,
    CASE WHEN consolidation_method = 'sum' THEN MAX(restatement_count)
         ELSE MAX(restatement_count) FILTER (WHERE consolidation_rank = 1) END AS restatement_count,
    source_system,
    CASE WHEN consolidation_method = 'sum' THEN STRING_AGG(DISTINCT source_file, ' | ')
         ELSE MAX(source_file) FILTER (WHERE consolidation_rank = 1) END AS source_file,
    CASE WHEN consolidation_method = 'sum' THEN STRING_AGG(DISTINCT source_hash, ' | ')
         ELSE MAX(source_hash) FILTER (WHERE consolidation_rank = 1) END AS source_hash,
    CASE WHEN consolidation_method = 'sum' THEN MAX(ingested_at)
         ELSE MAX(ingested_at) FILTER (WHERE consolidation_rank = 1) END AS ingested_at,
    CASE WHEN consolidation_method = 'sum' THEN MIN(confidence)
         ELSE MAX(confidence) FILTER (WHERE consolidation_rank = 1) END AS confidence,
    consolidation_method,
    'consolidated' AS reporting_scope
FROM annotated
GROUP BY consolidated_carrier_key, period_id, metric_key, segment,
         source_system, consolidation_method;

CREATE OR REPLACE VIEW v_carrier_default AS
WITH policy AS (
    SELECT source_system, priority
    FROM dim_source_priority
    WHERE data_domain = 'carrier_metrics' AND NOT is_default
), policy_contract AS (
    SELECT CASE
        WHEN COUNT(*) > 0
         AND BOOL_AND(source_priority_order = 'asc')
         AND BOOL_AND(is_preliminary_order = 'asc')
         AND BOOL_AND(confidence_order = 'desc')
         AND BOOL_AND(ingested_at_order = 'desc')
        THEN 1
        ELSE error('Unsupported carrier_metrics ranking policy')
    END AS policy_is_valid
    FROM dim_source_priority
    WHERE data_domain = 'carrier_metrics'
), default_policy AS (
    SELECT CASE
        WHEN COUNT(*) = 1 THEN MAX(priority)
        ELSE error('carrier_metrics requires exactly one default source priority')
    END AS priority
    FROM dim_source_priority
    WHERE data_domain = 'carrier_metrics' AND is_default AND source_system = '*'
), ranked AS (
    SELECT c.*, ROW_NUMBER() OVER (
        PARTITION BY carrier_key, period_id, metric_key, segment
        ORDER BY
            COALESCE(p.priority, d.priority) ASC,
            c.is_preliminary ASC,
            c.confidence DESC NULLS LAST,
            c.ingested_at DESC NULLS LAST,
            c.source_system ASC,
            c.source_file ASC
    ) AS source_rank
    FROM v_carrier_consolidated c
    LEFT JOIN policy p USING (source_system)
    CROSS JOIN default_policy d
    CROSS JOIN policy_contract pc
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

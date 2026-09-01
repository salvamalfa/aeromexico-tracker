-- Stage 8 bounded dashboard views.
CREATE OR REPLACE VIEW v_dashboard_route_latest12 AS
WITH months AS (
    SELECT DISTINCT period_id FROM fact_route_traffic_summary ORDER BY period_id DESC LIMIT 12
)
SELECT carrier_key, market_key, origin_iata, dest_iata,
       SUM(seats) AS seats, SUM(passengers) AS passengers,
       SUM(asm_miles) AS asm_miles, SUM(rpm_miles) AS rpm_miles,
       SUM(departures) AS departures,
       SUM(rpm_miles) / NULLIF(SUM(asm_miles), 0) AS load_factor
FROM fact_route_traffic_summary
WHERE period_id IN (SELECT period_id FROM months)
GROUP BY ALL;

-- Stage 8 extends the core operational health view with every analytical
-- result consumed by the dashboard. These datasets are produced locally, so a
-- NULL ingestion timestamp is preferable to inventing a runtime timestamp.
CREATE OR REPLACE VIEW v_data_health AS
WITH analytics_coverage AS (
    SELECT 'fact_forecasts' AS dataset_name, 'analytics' AS data_domain,
           'derived_gold' AS source_system, COUNT(*)::BIGINT AS rows,
           COUNT(DISTINCT carrier_key)::BIGINT AS carriers,
           MIN(p.period_start_date)::DATE AS first_date,
           MAX(p.period_end_date)::DATE AS last_date,
           MAX(trained_at)::TIMESTAMP AS last_ingested_at
    FROM fact_forecasts f
    LEFT JOIN dim_period p USING (period_id)
    UNION ALL
    SELECT 'dim_model_performance', 'analytics', 'derived_gold', COUNT(*)::BIGINT,
           COUNT(DISTINCT carrier_key)::BIGINT,
           MIN(p.period_start_date)::DATE, MAX(p.period_end_date)::DATE, NULL::TIMESTAMP
    FROM dim_model_performance f
    LEFT JOIN dim_period p ON p.period_id = f.trained_through_period
    UNION ALL
    SELECT 'fact_report_language', 'analytics', 'sec_edgar', COUNT(*)::BIGINT,
           COUNT(DISTINCT carrier_key)::BIGINT,
           MIN(p.period_start_date)::DATE, MAX(p.period_end_date)::DATE, NULL::TIMESTAMP
    FROM fact_report_language f
    LEFT JOIN dim_period p USING (period_id)
    UNION ALL
    SELECT 'fact_anomalies', 'analytics', 'derived_gold', COUNT(*)::BIGINT,
           COUNT(DISTINCT entity_key)::BIGINT,
           MIN(p.period_start_date)::DATE, MAX(p.period_end_date)::DATE, NULL::TIMESTAMP
    FROM fact_anomalies f
    LEFT JOIN dim_period p USING (period_id)
    UNION ALL
    SELECT 'dim_cluster_assignments', 'analytics', 'derived_gold', COUNT(*)::BIGINT,
           COUNT(DISTINCT entity_key)::BIGINT,
           MIN(p.period_start_date)::DATE, MAX(p.period_end_date)::DATE, NULL::TIMESTAMP
    FROM dim_cluster_assignments f
    LEFT JOIN dim_period p USING (period_id)
    UNION ALL
    SELECT 'fact_study_results', 'analytics', 'derived_gold', COUNT(*)::BIGINT,
           0::BIGINT, NULL::DATE, NULL::DATE, NULL::TIMESTAMP
    FROM fact_study_results
    UNION ALL
    SELECT 'fact_route_traffic_summary', 'analytics', 'bts_t100', COUNT(*)::BIGINT,
           COUNT(DISTINCT carrier_key)::BIGINT,
           MIN(p.period_start_date)::DATE, MAX(p.period_end_date)::DATE,
           MAX(f.ingested_at)::TIMESTAMP
    FROM fact_route_traffic_summary f
    LEFT JOIN dim_period p USING (period_id)
    UNION ALL
    SELECT 'fact_spread_decomposition', 'analytics', 'derived_gold', COUNT(*)::BIGINT,
           0::BIGINT, MIN(p.period_start_date)::DATE, MAX(p.period_end_date)::DATE,
           NULL::TIMESTAMP
    FROM fact_spread_decomposition f
    LEFT JOIN dim_period p USING (period_id)
    UNION ALL
    SELECT 'fact_dashboard_coverage', 'analytics', 'derived_gold', COUNT(*)::BIGINT,
           COUNT(DISTINCT carrier_key)::BIGINT,
           MIN(first_period.period_start_date)::DATE,
           MAX(last_period.period_end_date)::DATE,
           NULL::TIMESTAMP
    FROM fact_dashboard_coverage f
    LEFT JOIN dim_period first_period ON first_period.period_id = f.first_period
    LEFT JOIN dim_period last_period ON last_period.period_id = f.last_period
), analytics_issues AS (
    SELECT dataset_name, source_system, COUNT(*)::BIGINT AS issue_count
    FROM fact_data_quality_issues
    GROUP BY dataset_name, source_system
)
SELECT * FROM v_data_health_core
UNION ALL
SELECT c.*, COALESCE(i.issue_count, 0)::BIGINT AS issue_count
FROM analytics_coverage c
LEFT JOIN analytics_issues i USING (dataset_name, source_system);

CREATE OR REPLACE VIEW v_dashboard_source_freshness AS
SELECT dataset_name, data_domain, source_system, rows, carriers,
       first_date, last_date, last_ingested_at, issue_count,
       DATE_DIFF('day', CAST(last_date AS DATE), CURRENT_DATE) AS age_days
FROM v_data_health;

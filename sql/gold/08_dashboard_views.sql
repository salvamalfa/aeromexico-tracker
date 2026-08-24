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

CREATE OR REPLACE VIEW v_dashboard_source_freshness AS
SELECT source_system, rows, carriers, first_date, last_date, last_ingested_at, issue_count,
       DATE_DIFF('day', CAST(last_date AS DATE), CURRENT_DATE) AS age_days
FROM v_data_health;

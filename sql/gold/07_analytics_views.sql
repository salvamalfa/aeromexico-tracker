-- Stage 7 precomputed analytical views. No model trains at dashboard runtime.
CREATE OR REPLACE VIEW v_forecast_published AS
SELECT f.*, p.smape AS test_smape, p.mase AS test_mase
FROM fact_forecasts f
JOIN dim_model_performance p USING (model_run_id, model_name, carrier_key, metric_key)
WHERE p.is_published;

CREATE OR REPLACE VIEW v_latest_business_findings AS
SELECT * FROM fact_study_results ORDER BY study_key;

CREATE OR REPLACE VIEW v_cluster_summary AS
SELECT exercise, cluster_id, cluster_name, k, silhouette, stability_ari, COUNT(*) AS assignments
FROM dim_cluster_assignments
GROUP BY ALL ORDER BY exercise, cluster_id;

CREATE OR REPLACE VIEW v_report_language AS
SELECT * FROM fact_report_language ORDER BY report_type, period_id;

CREATE OR REPLACE VIEW v_anomaly_investigation AS
SELECT * FROM fact_anomalies WHERE NOT event_matched ORDER BY ABS(anomaly_score) DESC;

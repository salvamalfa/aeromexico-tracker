"""Detect data and business anomalies and match them to known events."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.analytics.common import model_run_id, warehouse_query


def _period_date(period_id: str) -> pd.Timestamp:
    if "M" in period_id:
        return pd.Timestamp(f"{period_id[:4]}-{period_id[-2:]}-01")
    if "Q" in period_id:
        quarter = int(period_id[-1])
        return pd.Timestamp(int(period_id[:4]), quarter * 3, 1) + pd.offsets.MonthEnd(0)
    return pd.Timestamp(f"{period_id}-12-31")


def _match_events(frame: pd.DataFrame) -> pd.DataFrame:
    events = warehouse_query("SELECT event_date, title FROM dim_events ORDER BY event_date")
    events["event_date"] = pd.to_datetime(events["event_date"]).dt.tz_localize(None)
    matches: list[dict[str, object]] = []
    for row in frame.itertuples(index=False):
        date = _period_date(row.period_id)
        if len(events):
            deltas = (events["event_date"] - date).abs()
            nearest_index = deltas.idxmin()
            nearest_days = int(deltas.loc[nearest_index].days)
            matched = nearest_days <= (62 if "Q" in row.period_id else 45)
            event_title = str(events.loc[nearest_index, "title"]) if matched else None
            event_date = events.loc[nearest_index, "event_date"] if matched else pd.NaT
        else:
            matched, event_title, event_date = False, None, pd.NaT
        matches.append({"event_matched": matched, "event_title": event_title, "event_date": event_date})
    return pd.concat([frame.reset_index(drop=True), pd.DataFrame(matches)], axis=1)


def run_anomalies(seasonality: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    run_id = model_run_id({"task": "anomalies", "version": 1})
    rows: list[dict[str, object]] = []
    residual = seasonality["residual"].astype(float)
    median = float(residual.median())
    mad = float(np.median(np.abs(residual - median)))
    robust_z = 0.6745 * (residual - median) / mad if mad else pd.Series(0.0, index=residual.index)
    for index in np.flatnonzero(np.abs(robust_z.to_numpy()) > 3):
        observed = float(seasonality.iloc[index]["observed"])
        expected = float(seasonality.iloc[index]["trend"] + seasonality.iloc[index]["seasonal"])
        rows.append(
            {
                "anomaly_type": "passenger_seasonal_residual",
                "entity_type": "carrier",
                "entity_key": "AEROMEXICO",
                "period_id": str(seasonality.iloc[index]["period_id"]),
                "metric_key": "passengers_afac",
                "observed_value": round(observed, 8),
                "expected_value": round(expected, 8),
                "anomaly_score": round(float(robust_z.iloc[index]), 8),
                "direction": "above" if observed > expected else "below",
                "severity": "high" if abs(robust_z.iloc[index]) >= 5 else "medium",
                "explanation": "Observed passengers differ materially from STL trend plus seasonality.",
                "source_tables": "v_carrier_default|data/analytics/eda_seasonality.parquet",
                "model_run_id": run_id,
            }
        )

    shares = warehouse_query(
        """
        SELECT period_id,
               MAX(market_share) FILTER (WHERE carrier_key='AEROMEXICO' AND segment='total') AS aeromexico_share,
               MAX(market_share) FILTER (WHERE carrier_key='VOLARIS' AND segment='total') AS volaris_share
        FROM v_market_share_mx
        GROUP BY period_id ORDER BY period_id
        """
    ).dropna()
    shares["decoupling"] = shares["aeromexico_share"].pct_change() - shares["volaris_share"].pct_change()
    standard = float(shares["decoupling"].std())
    shares["score"] = (shares["decoupling"] - shares["decoupling"].mean()) / standard if standard else 0.0
    for row in shares.loc[shares["score"].abs().gt(3)].itertuples(index=False):
        rows.append(
            {
                "anomaly_type": "peer_market_share_decoupling", "entity_type": "carrier",
                "entity_key": "AEROMEXICO_vs_VOLARIS", "period_id": row.period_id,
                "metric_key": "market_share", "observed_value": row.aeromexico_share,
                "expected_value": row.volaris_share, "anomaly_score": round(float(row.score), 8),
                "direction": "above" if row.decoupling > 0 else "below", "severity": "medium",
                "explanation": "Aeromexico market-share movement decoupled from Volaris by more than three historical standard deviations.",
                "source_tables": "v_market_share_mx", "model_run_id": run_id,
            }
        )

    route_assignments = assignments[assignments["exercise"].eq("routes")].copy()
    if len(route_assignments):
        for cluster, group in route_assignments.groupby("cluster_id"):
            center_1, center_2 = group["pca_1"].mean(), group["pca_2"].mean()
            distance = np.sqrt((group["pca_1"] - center_1) ** 2 + (group["pca_2"] - center_2) ** 2)
            threshold = distance.quantile(0.99)
            for index in distance[distance.gt(threshold)].index:
                row = route_assignments.loc[index]
                rows.append(
                    {
                        "anomaly_type": "route_cluster_outlier", "entity_type": "route_year",
                        "entity_key": row["entity_key"], "period_id": row["period_id"],
                        "metric_key": "pca_distance", "observed_value": round(float(distance.loc[index]), 8),
                        "expected_value": round(float(distance.median()), 8), "anomaly_score": round(float(distance.loc[index] / max(distance.median(), 1e-9)), 8),
                        "direction": "above", "severity": "low",
                        "explanation": f"Route-year lies in the outer 1% of its {row['cluster_name']} cluster.",
                        "source_tables": "dim_cluster_assignments", "model_run_id": run_id,
                    }
                )

    output = pd.DataFrame(rows)
    output = _match_events(output)
    output["anomaly_id"] = output.apply(
        lambda row: hashlib.sha256(
            f"{row['anomaly_type']}|{row['entity_key']}|{row['period_id']}|{row['metric_key']}".encode()
        ).hexdigest()[:20],
        axis=1,
    )
    columns = [
        "anomaly_id", "anomaly_type", "entity_type", "entity_key", "period_id", "metric_key",
        "observed_value", "expected_value", "anomaly_score", "direction", "severity",
        "event_matched", "event_title", "event_date", "explanation", "source_tables", "model_run_id",
    ]
    return output[columns].sort_values(["period_id", "anomaly_type", "entity_key"]).reset_index(drop=True)


if __name__ == "__main__":
    from src.analytics.eda import run_eda
    from src.analytics.clustering import run_clustering
    eda = run_eda()
    clusters, _ = run_clustering()
    print(run_anomalies(eda["seasonality"], clusters).to_string(index=False))

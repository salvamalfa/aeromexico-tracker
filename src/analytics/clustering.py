"""Business-oriented, deterministic route and quarter clustering."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from src.analytics.common import SEED, model_run_id, warehouse_query


def _choose_k(values: np.ndarray, *, minimum_cluster_size: int) -> tuple[int, np.ndarray, float, float, dict[str, dict[str, float | int]]]:
    best: tuple[float, int, np.ndarray] | None = None
    candidates: dict[str, dict[str, float | int]] = {}
    max_k = min(6, len(values) - 1)
    for k in range(2, max_k + 1):
        labels = KMeans(n_clusters=k, random_state=SEED, n_init=30).fit_predict(values)
        counts = np.bincount(labels)
        score = float(silhouette_score(values, labels))
        candidates[str(k)] = {"silhouette": round(score, 10), "minimum_cluster_rows": int(counts.min())}
        if counts.min() < minimum_cluster_size:
            continue
        if best is None or score > best[0]:
            best = (score, k, labels)
    if best is None:
        raise ValueError("No stable k satisfies the minimum cluster size")
    score, k, labels = best
    stability_scores = []
    for seed in (7, 19, 41, 73, 101, 509, 997):
        alternate = KMeans(n_clusters=k, random_state=seed, n_init=20).fit_predict(values)
        stability_scores.append(adjusted_rand_score(labels, alternate))
    return k, labels, score, float(np.mean(stability_scores)), candidates


def _unique_names(raw: dict[int, str]) -> dict[int, str]:
    used: dict[str, int] = {}
    output: dict[int, str] = {}
    for cluster, name in raw.items():
        used[name] = used.get(name, 0) + 1
        output[cluster] = name if used[name] == 1 else f"{name} {used[name]}"
    return output


def _route_features() -> pd.DataFrame:
    monthly = warehouse_query(
        """
        SELECT f.carrier_key, f.route_key, r.market_key, f.period_id,
               CAST(SUBSTR(f.period_id, 1, 4) AS INTEGER) AS year,
               SUM(f.departures_performed) AS departures,
               SUM(f.seats) AS seats, SUM(f.passengers) AS passengers,
               SUM(f.asm_miles) AS asm_miles, SUM(f.rpm_miles) AS rpm_miles,
               SUM(f.distance_miles * f.departures_performed) / NULLIF(SUM(f.departures_performed), 0) AS distance_miles,
               MODE(f.aircraft_type) AS dominant_aircraft
        FROM fact_route_traffic f
        JOIN dim_route r USING (route_key)
        GROUP BY ALL
        """
    )
    competition = (
        monthly.groupby(["market_key", "year"], as_index=False)
        .agg(competitors=("carrier_key", "nunique"))
    )
    aero = monthly[monthly["carrier_key"].eq("AEROMEXICO")].copy()
    grouped = aero.groupby(["route_key", "market_key", "year"], as_index=False).agg(
        months=("period_id", "nunique"),
        distance_miles=("distance_miles", "median"),
        frequency=("departures", "sum"),
        seats=("seats", "sum"),
        passengers=("passengers", "sum"),
        asm_miles=("asm_miles", "sum"),
        rpm_miles=("rpm_miles", "sum"),
        dominant_aircraft=("dominant_aircraft", lambda values: float(pd.Series(values).mode().iloc[0])),
        monthly_passenger_mean=("passengers", "mean"),
        monthly_passenger_std=("passengers", "std"),
    )
    grouped["load_factor"] = grouped["rpm_miles"] / grouped["asm_miles"].replace(0, np.nan)
    grouped["seasonality_cv"] = grouped["monthly_passenger_std"] / grouped["monthly_passenger_mean"].replace(0, np.nan)
    grouped = grouped.merge(competition, on=["market_key", "year"], how="left")
    grouped = grouped[grouped["months"].ge(6) & grouped["frequency"].gt(0)].copy()
    grouped["seasonality_cv"] = grouped["seasonality_cv"].fillna(0)
    return grouped


def cluster_routes(run_id: str) -> tuple[pd.DataFrame, dict[str, object]]:
    frame = _route_features()
    features = ["distance_miles", "frequency", "seats", "load_factor", "seasonality_cv", "competitors", "dominant_aircraft"]
    values = StandardScaler().fit_transform(frame[features])
    k, labels, silhouette, stability, candidates = _choose_k(values, minimum_cluster_size=5)
    frame["cluster_id"] = labels
    centroids = frame.groupby("cluster_id")[features].mean()
    raw_names: dict[int, str] = {}
    for cluster, row in centroids.iterrows():
        if row["distance_miles"] >= frame["distance_miles"].quantile(0.75):
            name = "Largo alcance"
        elif row["seasonality_cv"] >= frame["seasonality_cv"].quantile(0.70):
            name = "Ocio estacional"
        elif row["frequency"] >= frame["frequency"].quantile(0.70):
            name = "Alta frecuencia"
        elif row["load_factor"] >= frame["load_factor"].quantile(0.70):
            name = "Alta ocupación selectiva"
        else:
            name = "Conectividad equilibrada"
        raw_names[int(cluster)] = name
    names = _unique_names(raw_names)
    pca = PCA(n_components=2, random_state=SEED).fit_transform(values)
    rows = []
    for index, row in frame.reset_index(drop=True).iterrows():
        rows.append(
            {
                "model_run_id": run_id,
                "exercise": "routes",
                "entity_type": "route_year",
                "entity_key": row["route_key"],
                "period_id": str(int(row["year"])),
                "cluster_id": int(row["cluster_id"]),
                "cluster_name": names[int(row["cluster_id"])],
                "k": k,
                "silhouette": round(silhouette, 10),
                "stability_ari": round(stability, 10),
                "pca_1": round(float(pca[index, 0]), 10),
                "pca_2": round(float(pca[index, 1]), 10),
                "features_json": json.dumps({feature: round(float(row[feature]), 8) for feature in features}, sort_keys=True),
                "name_validation_status": "selected_under_user_delegated_authority",
            }
        )
    metadata = {
        "exercise": "routes",
        "rows": len(frame),
        "k": k,
        "silhouette": silhouette,
        "stability_ari": stability,
        "features": features,
        "cluster_names": names,
        "candidate_silhouettes": candidates,
        "k_justification": "highest silhouette among k=2..6 with at least five observations per cluster",
    }
    return pd.DataFrame(rows), metadata


def _quarter_features() -> pd.DataFrame:
    metrics = warehouse_query(
        """
        SELECT period_id, metric_key, value
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND period_type='quarter' AND segment='total'
          AND metric_key IN ('qoq_growth_asm_total','load_factor_total','rask','cask')
        ORDER BY period_id
        """
    ).pivot_table(index="period_id", columns="metric_key", values="value", aggfunc="first").reset_index()
    macro = warehouse_query(
        """
        SELECT period_id,
               MAX(value) FILTER (WHERE indicator_key='jet_fuel_usd_per_gallon') AS jet_fuel,
               MAX(value) FILTER (WHERE indicator_key='usd_mxn_fix') AS usd_mxn
        FROM fact_macro
        WHERE period_type='quarter' AND aggregation='average'
        GROUP BY period_id
        """
    )
    frame = metrics.merge(macro, on="period_id", how="left")
    frame["unit_spread"] = frame["rask"] - frame["cask"]
    return frame.dropna(subset=["qoq_growth_asm_total", "load_factor_total", "unit_spread", "jet_fuel", "usd_mxn"])


def cluster_quarters(run_id: str) -> tuple[pd.DataFrame, dict[str, object]]:
    frame = _quarter_features().reset_index(drop=True)
    features = ["qoq_growth_asm_total", "load_factor_total", "unit_spread", "jet_fuel", "usd_mxn"]
    if len(frame) < 6:
        return pd.DataFrame(), {"exercise": "quarters", "status": "insufficient_data", "rows": len(frame)}
    values = StandardScaler().fit_transform(frame[features])
    try:
        k, labels, silhouette, stability, candidates = _choose_k(values, minimum_cluster_size=2)
    except ValueError:
        return pd.DataFrame(), {
            "exercise": "quarters", "status": "not_published_unstable", "rows": len(frame),
            "reason": "Every feasible k produced at least one singleton quarter; business regimes would be unstable.",
        }
    frame["cluster_id"] = labels
    centroids = frame.groupby("cluster_id")[features].mean()
    raw_names: dict[int, str] = {}
    for cluster, row in centroids.iterrows():
        if row["qoq_growth_asm_total"] > centroids["qoq_growth_asm_total"].median() and row["unit_spread"] > centroids["unit_spread"].median():
            name = "Expansión rentable"
        elif row["qoq_growth_asm_total"] <= centroids["qoq_growth_asm_total"].median() and row["unit_spread"] > centroids["unit_spread"].median():
            name = "Disciplina de capacidad"
        elif row["jet_fuel"] > centroids["jet_fuel"].median():
            name = "Presión de costos"
        else:
            name = "Recuperación operativa"
        raw_names[int(cluster)] = name
    names = _unique_names(raw_names)
    pca = PCA(n_components=2, random_state=SEED).fit_transform(values)
    rows = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "model_run_id": run_id, "exercise": "quarters", "entity_type": "aeromexico_quarter",
                "entity_key": "AEROMEXICO", "period_id": row["period_id"], "cluster_id": int(row["cluster_id"]),
                "cluster_name": names[int(row["cluster_id"])], "k": k, "silhouette": round(silhouette, 10),
                "stability_ari": round(stability, 10), "pca_1": round(float(pca[index, 0]), 10), "pca_2": round(float(pca[index, 1]), 10),
                "features_json": json.dumps({feature: round(float(row[feature]), 8) for feature in features}, sort_keys=True),
                "name_validation_status": "selected_under_user_delegated_authority",
            }
        )
    return pd.DataFrame(rows), {
        "exercise": "quarters", "status": "published_descriptive", "rows": len(frame), "k": k,
        "silhouette": silhouette, "stability_ari": stability, "features": features,
        "cluster_names": names, "k_justification": "highest feasible silhouette with at least two quarters per cluster",
        "candidate_silhouettes": candidates,
        "caveat": "Only complete post-2024 quarters are available; clusters are descriptive, not predictive.",
    }


def run_clustering() -> tuple[pd.DataFrame, list[dict[str, object]]]:
    run_id = model_run_id({"task": "clustering", "seed": SEED, "version": 1})
    routes, route_metadata = cluster_routes(run_id)
    quarters, quarter_metadata = cluster_quarters(run_id)
    metadata = [
        {
            "exercise": "carriers",
            "status": "not_published",
            "reason": "Comparable global stage length is unavailable; all SLA RASK/CASK rows are null, so the requested feature set cannot be built honestly.",
        },
        route_metadata,
        quarter_metadata,
    ]
    assignments = pd.concat([routes, quarters], ignore_index=True) if len(quarters) else routes
    return assignments, metadata


if __name__ == "__main__":
    assignments, metadata = run_clustering()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"assignments={len(assignments)}")

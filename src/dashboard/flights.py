"""Deterministic data contract for the standalone Vuelos review page."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.config import PATHS


SCHEMA_VERSION = "flight_dashboard_payload_v1"
PILOT_PERIOD = "2026Q2"
PILOT_CUTOFF = "2026-07-13"
APPROVED_EVIDENCE_FINGERPRINT = (
    "808256bfb7420d221a3f2f2383c4b95d9889110ad1545fd85f24df8d442a9ff1"
)

QUARTER_QUERY = """
SELECT period_id, passengers, asm_miles, rpm_miles, load_factor_reported
FROM v_aeromexico_quarterly
WHERE passengers IS NOT NULL
  AND asm_miles IS NOT NULL
  AND load_factor_reported IS NOT NULL
ORDER BY period_id
"""

MONTHLY_MIX_QUERY = """
SELECT period_id, metric_key, segment, value, unit_normalized,
       source_file, source_hash
FROM v_carrier_default
WHERE carrier_key = 'AEROMEXICO'
  AND period_type = 'month'
  AND source_system = 'sec_edgar'
  AND metric_key IN ('passengers', 'asm_total', 'rpm_total')
  AND segment IN ('domestic', 'international', 'total')
ORDER BY period_id, metric_key, segment
"""

AFAC_MONTHLY_QUERY = """
SELECT period_id, metric_key, segment, value, unit_normalized, source_system,
       source_file, source_hash, ingested_at
FROM v_carrier_default
WHERE carrier_key = 'AEROMEXICO'
  AND period_type = 'month'
  AND metric_key = 'passengers_afac'
  AND segment IN ('domestic', 'international', 'total')
ORDER BY period_id, metric_key, segment
"""

WORLD_GEOMETRY_PATH = PATHS.root / "src" / "dashboard" / "assets" / "ne_110m_admin_0_countries.geojson"

FORECAST_QUERY = """
SELECT period_id, forecast_value, lower_80, upper_80, lower_95, upper_95,
       is_backtest, actual_value, model_name, trained_through_period,
       trained_at, test_smape, test_mase
FROM v_forecast_published
ORDER BY period_id, is_backtest DESC
"""


def _finite(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite flight metric: {value!r}")
    return number


def _iso(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _quarter_label(period_id: str) -> str:
    return f"{period_id[-1]}T{period_id[2:4]}"


def _normalized_hashes(value: Any) -> str:
    """Make concatenated lineage hashes deterministic across DuckDB scans."""

    return " | ".join(sorted(part.strip() for part in str(value).split("|") if part.strip()))


def _month_date(period_id: str) -> str:
    return f"{period_id[:4]}-{period_id[5:7]}-01"


def _quarter_for_month(period_id: str) -> str:
    month = int(period_id[5:7])
    return f"{period_id[:4]}Q{(month - 1) // 3 + 1}"


def _metric(
    *,
    key: str,
    value: float | None,
    unit: str,
    period_id: str,
    period_type: str,
    period_start: str,
    period_end: str,
    source_id: str,
    cutoff_date: str | None,
    eligible: bool,
    eligibility_reason: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "value": value,
        "unit": unit,
        "period_id": period_id,
        "period_type": period_type,
        "period_start": period_start,
        "period_end": period_end,
        "source_id": source_id,
        "cutoff_date": cutoff_date,
        "agent_eligible": eligible,
        "eligibility_reason": eligibility_reason,
    }


def _quarter_bounds(period_id: str) -> tuple[str, str]:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    end_day = (pd.Timestamp(year, end_month, 1) + pd.offsets.MonthEnd(0)).day
    return f"{year:04d}-{start_month:02d}-01", f"{year:04d}-{end_month:02d}-{end_day:02d}"


def _load_quarters(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    frame = connection.execute(QUARTER_QUERY).df()
    if frame.empty or frame["period_id"].duplicated().any():
        raise ValueError("Quarterly flight source must contain unique quarters")
    records: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        period_id = str(row.period_id)
        start, end = _quarter_bounds(period_id)
        eligible = period_id == PILOT_PERIOD
        reason = (
            "Incluido en el paquete SEC certificado al corte del comunicado 2T26."
            if eligible
            else "No evaluado para el paquete piloto 2T26."
        )
        cutoff = PILOT_CUTOFF if eligible else None
        records.append(
            {
                "period_id": period_id,
                "period_label": _quarter_label(period_id),
                "metrics": {
                    "passengers": _metric(
                        key="passengers", value=_finite(row.passengers), unit="count",
                        period_id=period_id, period_type="quarter", period_start=start,
                        period_end=end, source_id="sec-quarterly", cutoff_date=cutoff,
                        eligible=eligible, eligibility_reason=reason,
                    ),
                    "asm_miles": _metric(
                        key="asm_miles", value=_finite(row.asm_miles), unit="seat_miles",
                        period_id=period_id, period_type="quarter", period_start=start,
                        period_end=end, source_id="sec-quarterly", cutoff_date=cutoff,
                        eligible=eligible, eligibility_reason=reason,
                    ),
                    "rpm_miles": _metric(
                        key="rpm_miles", value=_finite(row.rpm_miles), unit="passenger_miles",
                        period_id=period_id, period_type="quarter", period_start=start,
                        period_end=end, source_id="sec-quarterly", cutoff_date=cutoff,
                        eligible=eligible and _finite(row.rpm_miles) is not None,
                        eligibility_reason=reason,
                    ),
                    "load_factor": _metric(
                        key="load_factor", value=_finite(row.load_factor_reported), unit="fraction",
                        period_id=period_id, period_type="quarter", period_start=start,
                        period_end=end, source_id="sec-quarterly", cutoff_date=cutoff,
                        eligible=eligible, eligibility_reason=reason,
                    ),
                },
            }
        )
    return records


def _load_mix(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    frame = connection.execute(MONTHLY_MIX_QUERY).df()
    if frame.empty:
        return {}
    frame["quarter_id"] = frame["period_id"].map(_quarter_for_month)
    result: dict[str, dict[str, Any]] = {}
    for quarter_id, group in frame.groupby("quarter_id", sort=True):
        expected_months = sorted(group["period_id"].unique())
        if len(expected_months) != 3:
            continue
        complete = True
        metrics: dict[str, dict[str, float]] = {}
        for metric_key in ("passengers", "asm_total", "rpm_total"):
            metric_rows = group[group["metric_key"].eq(metric_key)]
            segments: dict[str, float] = {}
            for segment in ("domestic", "international", "total"):
                rows = metric_rows[metric_rows["segment"].eq(segment)]
                if rows["period_id"].nunique() != 3:
                    complete = False
                    break
                segments[segment] = float(rows["value"].sum())
            metrics[metric_key] = segments
        if not complete:
            continue
        for values in metrics.values():
            # Published monthly tables are rounded (millions for traffic work).
            # Preserve that disclosed precision instead of forcing false exactness.
            tolerance = max(2_000.0, abs(values["total"]) * 0.0005)
            if not math.isclose(
                values["domestic"] + values["international"],
                values["total"],
                rel_tol=0,
                abs_tol=tolerance,
            ):
                raise ValueError(f"Monthly SEC mix does not reconcile for {quarter_id}")
        start, end = _quarter_bounds(str(quarter_id))
        eligible = str(quarter_id) == PILOT_PERIOD
        total_passengers = metrics["passengers"]["total"]
        result[str(quarter_id)] = {
            "period_id": str(quarter_id),
            "period_type": "quarter_from_three_monthly_reports",
            "period_start": start,
            "period_end": end,
            "cutoff_date": PILOT_CUTOFF if eligible else None,
            "source_id": "sec-monthly-traffic",
            "agent_eligible": eligible,
            "eligibility_reason": (
                "Tres comunicados mensuales preservados como anexos del 6-K presentado al corte."
                if eligible else "No evaluado para el paquete piloto 2T26."
            ),
            "months": expected_months,
            "passengers": {
                **metrics["passengers"],
                "domestic_share": metrics["passengers"]["domestic"] / total_passengers,
                "international_share": metrics["passengers"]["international"] / total_passengers,
            },
            "asm_miles": metrics["asm_total"],
            "rpm_miles": metrics["rpm_total"],
            "source_hashes": sorted(set(group["source_hash"].dropna().astype(str))),
        }
    return result


def _load_monthly_passengers(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Load the canonical continuous original AFAC Gold series."""

    frame = connection.execute(AFAC_MONTHLY_QUERY).df()
    if frame.empty:
        return {"period_type": "month", "records": []}
    records: list[dict[str, Any]] = []
    for period_id, group in frame.groupby("period_id", sort=True):
        values: dict[str, float] = {}
        for segment in ("domestic", "international", "total"):
            rows = group[group["metric_key"].eq("passengers_afac") & group["segment"].eq(segment)]
            if len(rows) != 1:
                raise ValueError(f"AFAC Gold needs one {segment} row for {period_id}")
            values[segment] = float(rows.iloc[0]["value"])
        segment_sum = values["domestic"] + values["international"]
        difference = segment_sum - values["total"]
        if abs(difference) > 0.5:
            raise ValueError(f"AFAC Gold passenger segments do not reconcile for {period_id}")
        original_rows = group[group["metric_key"].eq("passengers_afac")]
        records.append({
            "period_id": str(period_id),
            "date": _month_date(str(period_id)),
            "period_type": "month",
            "domestic": values["domestic"],
            "international": values["international"],
            "total_segment_sum": segment_sum,
            "reported_total": values["total"],
            "reconciliation_delta": difference,
            "source_id": "afac-gold-current",
            "source_hash": _normalized_hashes(original_rows.iloc[0]["source_hash"]),
            "cutoff_date": None,
            "agent_eligible": False,
            "availability": "observed",
        })
    expected = pd.period_range(records[0]["period_id"].replace("M", "-"), records[-1]["period_id"].replace("M", "-"), freq="M")
    if len(expected) != len(records):
        raise ValueError("AFAC Gold monthly series must be continuous")
    return {
        "period_type": "month",
        "period_start": records[0]["date"],
        "period_end": str(pd.Timestamp(records[-1]["date"]) + pd.offsets.MonthEnd(0))[:10],
        "source_id": "afac-gold-current",
        "observed_months": len(records),
        "calendar_months": len(records),
        "as_of": _iso(frame["ingested_at"].max()),
        "agent_eligible": False,
        "eligibility_reason": "La copia Gold vigente se ingirió después del corte 2T26.",
        "records": records,
    }


def _load_world_geometry() -> dict[str, Any]:
    """Load a pinned, local Natural Earth geometry for the offline flow map."""

    raw = WORLD_GEOMETRY_PATH.read_bytes()
    geometry = json.loads(raw)
    for index, feature in enumerate(geometry.get("features", [])):
        feature["id"] = f"country-{index}"
        feature["properties"] = {"name": feature.get("properties", {}).get("NAME", "")}
    return {
        "geojson": geometry,
        "topojson": json.loads((WORLD_GEOMETRY_PATH.parent / 'world_110m.topojson').read_bytes()),
        "source_url": "https://github.com/nvkelso/natural-earth-vector/blob/v5.1.2/geojson/ne_110m_admin_0_countries.geojson",
        "version": "Natural Earth 5.1.2 / 1:110m",
        "license": "public domain",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _quarter_months(period_id: str) -> list[str]:
    year = int(period_id[:4])
    quarter = int(period_id[-1])
    first_month = (quarter - 1) * 3 + 1
    return [f"{year}M{month:02d}" for month in range(first_month, first_month + 3)]


def _load_routes(connection: duckdb.DuckDBPyConnection, period_id: str) -> dict[str, Any]:
    expected_months = _quarter_months(period_id)
    available_months = {
        str(row[0])
        for row in connection.execute(
            """SELECT DISTINCT period_id FROM fact_route_traffic_summary
               WHERE carrier_key = 'AEROMEXICO'"""
        ).fetchall()
    }
    current_months = [month for month in expected_months if month in available_months]
    if not current_months:
        return {
            "period_id": period_id,
            "period_label": _quarter_label(period_id),
            "period_type": "quarter",
            "availability": "unavailable",
            "expected_months": expected_months,
            "observed_months": [],
            "route_count": 0,
            "airport_count": 0,
            "totals": {"passengers": 0.0, "seats": 0.0, "departures": 0.0},
            "routes": [],
            "airports": [],
            "agent_eligible": False,
            "eligibility_reason": "T-100 no contiene meses del trimestre seleccionado.",
        }
    prior_months = [f"{int(month[:4]) - 1}{month[4:]}" for month in current_months]
    current_placeholders = ",".join("?" for _ in current_months)
    current = connection.execute(
        f"""
        WITH aggregated AS (
          SELECT market_key, ANY_VALUE(origin_iata) AS origin_iata,
                 ANY_VALUE(dest_iata) AS dest_iata,
                 SUM(seats) AS seats, SUM(passengers) AS passengers,
                 SUM(departures) AS departures,
                 CASE WHEN SUM(seats) > 0 THEN SUM(passengers) / SUM(seats) END AS load_factor
          FROM fact_route_traffic_summary
          WHERE carrier_key = 'AEROMEXICO' AND period_id IN ({current_placeholders})
          GROUP BY market_key
        )
        SELECT r.*, ao.name AS origin_name, ao.city AS origin_city,
               ao.country AS origin_country, ao.latitude AS origin_lat,
               ao.longitude AS origin_lon, ad.name AS dest_name,
               ad.city AS dest_city, ad.country AS dest_country,
               ad.latitude AS dest_lat, ad.longitude AS dest_lon
        FROM aggregated r
        LEFT JOIN dim_airport ao ON r.origin_iata = ao.airport_iata
        LEFT JOIN dim_airport ad ON r.dest_iata = ad.airport_iata
        ORDER BY r.passengers DESC, r.market_key
        """,
        current_months,
    ).df()
    if current.empty or current["market_key"].duplicated().any():
        raise ValueError("Current T-100 route view must contain unique markets")
    coord_columns = ["origin_lat", "origin_lon", "dest_lat", "dest_lon"]
    if current[coord_columns].isna().any().any():
        missing = current[current[coord_columns].isna().any(axis=1)]["market_key"].tolist()
        raise ValueError(f"T-100 routes are missing airport coordinates: {missing[:5]}")
    placeholders = ",".join("?" for _ in prior_months)
    prior = connection.execute(
        f"""
        SELECT market_key, SUM(seats) AS seats, SUM(passengers) AS passengers,
               SUM(departures) AS departures
        FROM fact_route_traffic_summary
        WHERE carrier_key = 'AEROMEXICO' AND period_id IN ({placeholders})
        GROUP BY market_key
        """,
        prior_months,
    ).df()
    prior_by_market = prior.set_index("market_key").to_dict("index") if not prior.empty else {}
    directional = connection.execute(
        f"""
        SELECT d.market_key, d.origin_iata, d.dest_iata,
               SUM(f.passengers) AS passengers,
               SUM(f.seats) AS seats,
               SUM(f.departures_performed) AS departures
        FROM fact_route_traffic f
        JOIN dim_route d ON f.route_key = d.route_key
        WHERE f.carrier_key = 'AEROMEXICO'
          AND f.period_id IN ({current_placeholders})
          AND f.departures_performed > 0
        GROUP BY d.market_key, d.origin_iata, d.dest_iata
        ORDER BY d.market_key, passengers DESC, d.origin_iata, d.dest_iata
        """,
        current_months,
    ).df()
    directions_by_market: dict[str, list[dict[str, Any]]] = {}
    for row in directional.itertuples(index=False):
        directions_by_market.setdefault(str(row.market_key), []).append(
            {
                "origin_iata": str(row.origin_iata),
                "destination_iata": str(row.dest_iata),
                "passengers": _finite(row.passengers),
                "seats": _finite(row.seats),
                "departures": _finite(row.departures),
            }
        )

    routes: list[dict[str, Any]] = []
    airports: dict[str, dict[str, Any]] = {}
    for row in current.itertuples(index=False):
        market = str(row.market_key)
        previous = prior_by_market.get(market, {})
        route = {
            "market_key": market,
            "origin": {
                "iata": str(row.origin_iata), "name": str(row.origin_name),
                "city": str(row.origin_city), "country": str(row.origin_country),
                "lat": _finite(row.origin_lat), "lon": _finite(row.origin_lon),
            },
            "destination": {
                "iata": str(row.dest_iata), "name": str(row.dest_name),
                "city": str(row.dest_city), "country": str(row.dest_country),
                "lat": _finite(row.dest_lat), "lon": _finite(row.dest_lon),
            },
            "passengers": _finite(row.passengers),
            "seats": _finite(row.seats),
            "departures": _finite(row.departures),
            "load_factor": _finite(row.load_factor),
            "directions": directions_by_market.get(market, []),
            "previous": {
                "passengers": _finite(previous.get("passengers")),
                "seats": _finite(previous.get("seats")),
                "departures": _finite(previous.get("departures")),
            },
            "operation_status": "operated_observed",
            "carrier_role": "operator_reporting_carrier",
            "marketing_carrier": None,
        }
        if route["departures"] is not None and route["departures"] > 0:
            for metric in ("passengers", "seats", "departures"):
                directional_total = sum(float(item[metric] or 0) for item in route["directions"])
                if not math.isclose(directional_total, float(route[metric] or 0), rel_tol=0, abs_tol=.5):
                    raise ValueError(f"Directional route {metric} do not reconcile for {market}")
            routes.append(route)
        for endpoint in (route["origin"], route["destination"]):
            airports[str(endpoint["iata"])] = endpoint

    totals = {
        metric: float(sum(float(route[metric] or 0) for route in routes))
        for metric in ("passengers", "seats", "departures")
    }
    source_rows = connection.execute(
        f"""SELECT DISTINCT source_hash, source_files, ingested_at
            FROM fact_route_traffic_summary
            WHERE carrier_key = 'AEROMEXICO' AND period_id IN ({current_placeholders})
            ORDER BY source_hash""",
        current_months,
    ).df()
    ingested_at = source_rows["ingested_at"].max() if not source_rows.empty else None
    requested_start = _month_date(expected_months[0])
    requested_end = str(pd.Timestamp(_month_date(expected_months[-1])) + pd.offsets.MonthEnd(0))[:10]
    return {
        "period_id": period_id,
        "period_label": _quarter_label(period_id),
        "period_type": "quarter" if len(current_months) == 3 else "quarter_to_date",
        "availability": "complete" if len(current_months) == 3 else "partial",
        "expected_months": expected_months,
        "observed_months": current_months,
        "requested_period_start": requested_start,
        "requested_period_end": requested_end,
        "period_start": _month_date(current_months[0]),
        "period_end": str(pd.Timestamp(_month_date(current_months[-1])) + pd.offsets.MonthEnd(0))[:10],
        "comparison_period_start": _month_date(prior_months[0]),
        "comparison_period_end": str(pd.Timestamp(_month_date(prior_months[-1])) + pd.offsets.MonthEnd(0))[:10],
        "latest_available_period": max(available_months),
        "source_id": "bts-t100-current",
        "source_as_of": _iso(ingested_at),
        "cutoff_date": PILOT_CUTOFF,
        "agent_eligible": False,
        "eligibility_reason": (
            "La copia local fue descargada y revisada después del corte 2T26; "
            "no preserva la versión T-100 exacta disponible el 13 jul 2026."
        ),
        "coverage": "México–Estados Unidos; segmentos internacionales sin escala con al menos un punto en EE.UU.",
        "operator": "Aeromexico (AM), operador/reportante BTS",
        "marketing_carrier": None,
        "announced_routes_available": False,
        "route_count": len(routes),
        "airport_count": len(airports),
        "totals": totals,
        "routes": routes,
        "airports": sorted(airports.values(), key=lambda item: str(item["iata"])),
        "source_hashes": sorted(set(source_rows["source_hash"].dropna().astype(str))),
    }


def _load_forecast(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    frame = connection.execute(FORECAST_QUERY).df()
    if frame.empty:
        return {"available": False}
    history = connection.execute(
        """SELECT period_id, value
           FROM v_carrier_default
           WHERE carrier_key = 'AEROMEXICO' AND metric_key = 'passengers_afac'
             AND segment = 'total' AND period_type = 'month'
           ORDER BY period_id DESC LIMIT 36"""
    ).df().sort_values("period_id")
    first = frame.iloc[0]
    points = []
    for row in frame.itertuples(index=False):
        points.append(
            {
                "period_id": str(row.period_id),
                "date": _month_date(str(row.period_id)),
                "forecast": _finite(row.forecast_value),
                "lower_80": _finite(row.lower_80), "upper_80": _finite(row.upper_80),
                "lower_95": _finite(row.lower_95), "upper_95": _finite(row.upper_95),
                "is_backtest": bool(row.is_backtest),
                "actual": _finite(row.actual_value),
            }
        )
    return {
        "available": True,
        "period_type": "monthly_model_vintage",
        "period_start": points[0]["date"],
        "period_end": str(pd.Timestamp(points[-1]["date"]) + pd.offsets.MonthEnd(0))[:10],
        "source_id": "forecast-current",
        "cutoff_date": PILOT_CUTOFF,
        "agent_eligible": False,
        "eligibility_reason": "Modelo entrenado después del corte del comunicado 2T26.",
        "model_name": str(first["model_name"]).upper(),
        "trained_at": _iso(first["trained_at"]),
        "trained_through_period": str(frame.iloc[-1]["trained_through_period"]),
        "test_smape": _finite(first["test_smape"]),
        "test_mase": _finite(first["test_mase"]),
        "history": [
            {"period_id": str(row.period_id), "date": _month_date(str(row.period_id)), "actual": _finite(row.value)}
            for row in history.itertuples(index=False)
        ],
        "points": points,
    }


def build_flight_payload(database_path: str | Path | None = None) -> dict[str, Any]:
    """Build the complete review payload without mutating Gold or approved evidence."""

    path = Path(database_path) if database_path is not None else PATHS.warehouse
    with duckdb.connect(str(path), read_only=True) as connection:
        quarters = _load_quarters(connection)
        mixes = _load_mix(connection)
        monthly_passengers = _load_monthly_passengers(connection)
        route_networks = {
            record["period_id"]: _load_routes(connection, record["period_id"])
            for record in quarters
        }
        from src.dashboard.international_routes import extend_networks
        from src.dashboard.domestic_routes import (
            load_domestic_monthly_networks,
            load_domestic_networks,
        )
        international_networks = extend_networks(connection, route_networks)
        domestic_networks = load_domestic_networks(connection, quarters)
        domestic_monthly_networks = load_domestic_monthly_networks(connection)
        route_network = {
            **route_networks[PILOT_PERIOD],
            "world_geometry": _load_world_geometry(),
        }
        forecast = _load_forecast(connection)
        for record in quarters:
            record["passenger_mix"] = mixes.get(record["period_id"])
        source_rows = connection.execute(
            """SELECT artifact_id, source_file, source_url, downloaded_at, artifact_sha256
               FROM dim_source_artifact
               WHERE artifact_sha256 IN (
                 '6207b9a113074f68e0d8196f9597ddf35f40a32b5f53ca97c5cd2c0a2f0ac781',
                 'd19b0dd3cadf8d197a2f05b27a3a518d5dcab7995d1fac8ab634d0bb8d98914a',
                 '84729abb1c160f7238b2ee22e52e370d46ca82d3cac526d8f318406ae880f9e6',
                 '3874b8fd4e16ab2748c0e48f3fd5dc21f92006dbb1e1d6fac7fd2e120345676a'
               ) ORDER BY source_file"""
        ).df()
    traffic_source_rows = source_rows[
        ~source_rows["artifact_sha256"].eq(
            "6207b9a113074f68e0d8196f9597ddf35f40a32b5f53ca97c5cd2c0a2f0ac781"
        )
    ]
    sources = [
        {
            "source_id": "sec-quarterly",
            "name": "Grupo Aeroméxico 2T26, anexo 99.1 del 6-K",
            "source_system": "SEC EDGAR",
            "source_url": "https://www.sec.gov/Archives/edgar/data/1561861/000119312526302103/d112634dex991.htm",
            "artifact_sha256": "6207b9a113074f68e0d8196f9597ddf35f40a32b5f53ca97c5cd2c0a2f0ac781",
            "available_at_cutoff": True,
        },
        {
            "source_id": "sec-monthly-traffic",
            "name": "Comunicados de tráfico abril–junio 2026, anexos 99.2–99.4 del mismo 6-K",
            "source_system": "SEC EDGAR",
            "source_urls": traffic_source_rows["source_url"].dropna().astype(str).tolist(),
            "artifact_sha256": traffic_source_rows["artifact_sha256"].dropna().astype(str).tolist(),
            "available_at_cutoff": True,
        },
        {
            "source_id": "afac-gold-current",
            "name": "AFAC Gold consolidado · pasajeros mensuales",
            "source_system": "AFAC / Gold local",
            "available_at_cutoff": False,
        },
        {
            "source_id": "afac-aerodatabox-route-carrier-estimate",
            "name": "AFAC + AeroDataBox · pasajeros nacionales estimados por ruta y operador",
            "source_system": "AFAC / AeroDataBox via RapidAPI / modelo IPF temporal",
            "source_url": "https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404",
            "available_at_cutoff": False,
        },
        {
            "source_id": "bts-t100-current",
            "name": "BTS T-100 International Segment (All Carriers)",
            "source_system": "BTS TranStats",
            "source_url": "https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=Nv4+Pn44vr45&gnoyr_VQ=FJE",
            "available_at_cutoff": False,
        },
        {
            "source_id": "natural-earth-5.1.2",
            "name": "Natural Earth Admin 0 Countries, 1:110m",
            "source_system": "Natural Earth 5.1.2 · dominio público",
            "source_url": route_network["world_geometry"]["source_url"],
            "artifact_sha256": route_network["world_geometry"]["sha256"],
            "available_at_cutoff": True,
        },
        {
            "source_id": "forecast-current",
            "name": "Forecast publicado en fact_forecasts",
            "source_system": "Modelo local versionado",
            "available_at_cutoff": False,
        },
    ]
    sources.extend([
        {"source_id":"anac-current", "name":"ANAC Brasil · tráfico por empresa y ruta", "source_system":"ANAC Brasil", "source_url":"https://www.anac.gov.br/acesso-a-informacao/dados-abertos", "available_at_cutoff":False},
        {"source_id":"aerocivil-current", "name":"Aerocivil · operaciones por explotador y ruta", "source_system":"Aerocivil Colombia", "source_url":"https://www.datos.gov.co/Transportation/Operaciones-a-reas-acumuladas-en-Colombia/jh8x-n6h6", "available_at_cutoff":False},
        {"source_id":"caa-current", "name":"CAA · vuelos cotejados y puntualidad", "source_system":"CAA Reino Unido", "source_url":"https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/", "available_at_cutoff":False},
        {"source_id":"aicm-am-slots-2026", "name":"AICM · horarios históricos asignados a vuelos AM, verano 2026", "source_system":"AICM", "source_url":"https://www.aicm.com.mx/archivos/Negocios/Slots/verano/2026/amx.pdf", "available_at_cutoff":False},
    ])
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "title": "Aeroméxico Tracker · Vuelos",
            "pilot_period": PILOT_PERIOD,
            "default_period": PILOT_PERIOD,
            "cutoff_date": PILOT_CUTOFF,
            "approved_evidence_fingerprint": APPROVED_EVIDENCE_FINGERPRINT,
            "review_status": "first_increment_unapproved",
            "scope": "Vuelos; prototipo autónomo, local y sin integración en navegación",
        },
        "quarters": quarters,
        "monthly_passengers": monthly_passengers,
        "route_network": route_network,
        "route_networks": route_networks,
        "international_networks": international_networks,
        "domestic_networks": domestic_networks,
        "domestic_monthly_networks": domestic_monthly_networks,
        "forecast": forecast,
        "sources": sources,
        "agent_eligibility": {
            "status": "candidate_unapproved",
            "eligible": ["quarterly_core", "quarterly_passenger_mix"],
            "excluded": {
                "bts_t100": route_network["eligibility_reason"],
                "international_routes": "ANAC, Aerocivil y CAA: las versiones actuales no acreditan disponibilidad al corte histórico.",
                "aicm_slots": "El PDF descargado hoy conserva una fecha interna anterior al corte, pero no acredita que esta versión exacta estuviera publicada el 13 de julio de 2026; además son slots programados.",
                "afac": "No hay versión certificada disponible al corte dentro de este paquete.",
                "domestic_route_carrier_estimate": "Estimación retrospectiva AFAC + AeroDataBox; no existía ni estaba aprobada al corte histórico y permanece fuera del Analysis Agent.",
                "forecast": forecast.get("eligibility_reason", "No disponible."),
                "announced_routes": "No existe una fuente estructurada, versionada y fechada.",
                "marketing_carrier": "T-100 identifica al operador/reportante, no al comercializador.",
            },
        },
    }

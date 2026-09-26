"""Whitelist the Vuelos payload fields exported to the published page.

The HTML renderers this module used to hold (``render_flights_html``,
``render_flights_panel``, ``integrated_flights_css``, ``standalone_flight_
payload``) were retired in P7 (see ``docs/arquitectura/migracion-estado.md``)
along with the legacy Streamlit/single-file HTML path. ``web/`` is now the
only rendered view. ``integration_flight_payload`` survives because
``src/web_export/flights.py`` still uses it as the single, tested source of
truth for which Vuelos fields are public.
"""

from __future__ import annotations

from typing import Any


def integration_flight_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only data consumed by the three blocks included in the main dashboard."""

    if payload.get("schema_version") != "flight_dashboard_payload_v1":
        raise ValueError("Unsupported flight dashboard payload")
    endpoint_keys = ("iata", "city", "name", "lat", "lon")
    metric_keys = ("passengers", "seats", "departures", "load_factor")

    def endpoint(value: dict[str, Any]) -> dict[str, Any]:
        return {key: value[key] for key in endpoint_keys}

    def compact_number(value: Any, digits: int = 1) -> Any:
        return round(float(value), digits) if value is not None else None

    def monthly_item(item: dict[str, Any], estimated: bool) -> dict[str, Any]:
        keys = (
            "period_id", "carrier_key", "carrier_label", "origin_iata",
            "destination_iata", "support_observed_in_period",
            "support_source_periods", "support_month_gap",
        )
        result = {key: item.get(key) for key in keys}
        for key in ("passengers", "passengers_low", "passengers_high", "seats", "departures"):
            result[key] = compact_number(item.get(key)) if estimated else item.get(key)
        result["load_factor"] = compact_number(item.get("load_factor"), 4) if estimated else item.get("load_factor")
        result["capacity_estimated"] = item.get("capacity_estimated", False)
        return result

    def route(value: dict[str, Any]) -> dict[str, Any]:
        estimated = value.get("passengers_estimated", False)
        metrics = {key: value[key] for key in metric_keys}
        if estimated:
            metrics = {
                "passengers": compact_number(value.get("passengers")),
                "seats": compact_number(value.get("seats")),
                "departures": compact_number(value.get("departures")),
                "load_factor": compact_number(value.get("load_factor"), 4),
            }
        return {
            "market_key": value["market_key"],
            "coverage_note": value.get("coverage_note", ""),
            "source_label": value.get("source_label", "BTS T-100"),
            "operation_status": value.get("operation_status", "operated_observed"),
            "context": value.get("context"),
            "passengers_low": compact_number(value.get("passengers_low")) if estimated else value.get("passengers_low"),
            "passengers_high": compact_number(value.get("passengers_high")) if estimated else value.get("passengers_high"),
            "passengers_estimated": estimated,
            "capacity_estimated": value.get("capacity_estimated", False),
            "seats_low": compact_number(value.get("seats_low")) if estimated else value.get("seats_low"),
            "seats_high": compact_number(value.get("seats_high")) if estimated else value.get("seats_high"),
            "load_factor_low": compact_number(value.get("load_factor_low"), 4) if estimated else value.get("load_factor_low"),
            "load_factor_high": compact_number(value.get("load_factor_high"), 4) if estimated else value.get("load_factor_high"),
            "load_factor_status": value.get("load_factor_status"),
            "support_repair_applied": value.get("support_repair_applied", False),
            "months_covered": value.get("months_covered"),
            "months_selected": value.get("months_selected"),
            "origin": endpoint(value["origin"]),
            "destination": endpoint(value["destination"]),
            **metrics,
            "previous": {key: value["previous"].get(key) for key in metric_keys},
            "directions": [] if estimated else [
                {
                    key: direction.get(key)
                    for key in (
                        "origin_iata",
                        "destination_iata",
                        "passengers",
                        "passengers_low",
                        "passengers_high",
                        "seats",
                        "departures",
                    )
                }
                for direction in value.get("directions", [])
            ],
            "monthly": [monthly_item(item, estimated) for item in value.get("monthly", [])],
        }

    def network(value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value[key]
            for key in ("period_label", "expected_months", "observed_months")
        } | {
            "routes": [route(item) for item in value["routes"]],
            "airports": [endpoint(item) for item in value["airports"]],
            "coverage_by_source": value.get("coverage_by_source", {}),
            "mode": value.get("mode", "observed_international"),
            "source_url": value.get("source_url"),
            "availability": value.get("availability"),
            "agent_eligible": value.get("agent_eligible", False),
            "eligibility_reason": value.get("eligibility_reason"),
            "represented_passengers": value.get("represented_passengers"),
            "represented_movements": value.get("represented_movements"),
            "aena_airport_activity": [
                {key: item[key] for key in (
                    "airport_iata", "passengers", "operations", "observed_months",
                    "expected_months", "coverage_status",
                )}
                for item in value.get("aena_airport_activity", [])
            ],
        }

    monthly_domestic = {
        period_id: network(value)
        for period_id, value in payload.get("domestic_monthly_networks", {}).items()
    }
    return {
        "schema_version": payload["schema_version"],
        "metadata": payload["metadata"],
        "quarters": payload["quarters"],
        "monthly_passengers": payload["monthly_passengers"],
        "route_network": {"world_geometry": payload["route_network"]["world_geometry"]},
        "route_networks": {
            period_id: network(value)
            for period_id, value in payload.get("international_networks", payload["route_networks"]).items()
        },
        "domestic_networks": {
            period_id: network(value)
            for period_id, value in payload.get("domestic_networks", {}).items()
        } if not monthly_domestic else {},
        "domestic_monthly_networks": monthly_domestic,
    }

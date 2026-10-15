"""Metric-level route status and provenance from published route evidence."""

from __future__ import annotations

from typing import Any


def value_kind(network: dict[str, Any], route: dict[str, Any], metric: str) -> str:
    override = (route.get("metric_value_kinds") or {}).get(metric)
    if override in {"reported", "observed", "estimated", "scheduled", "mixed", "missing"}:
        return override
    if metric == "passengers" and route.get("passengers_estimated"):
        return "estimated"
    if metric in {"seats", "load_factor"} and (
        route.get("capacity_estimated") or route.get("load_factor_status") == "estimated"
    ):
        return "estimated"
    status = str(route.get("operation_status") or "").lower()
    source = str(route.get("source_label") or "").lower()
    # Several canonical statuses exist, including scheduled_from_dated_release.
    # Classify the departures metric from that status; route notes may mention
    # an unrelated schedule alongside observed passengers.
    if metric == "departures" and (status.startswith("scheduled_") or status == "assigned_slot_not_flown"):
        return "scheduled"
    if status == "carrier_inferred_market_observed":
        return "estimated"
    if status.startswith("estimated_"):
        return "estimated"
    if "observed" in status or "t-100" in source:
        return "observed"
    if metric in {"passengers", "seats", "departures", "load_factor"} and route.get("capacity_estimated"):
        return "estimated"
    return "observed"


def metric_provenance(
    network: dict[str, Any], route: dict[str, Any], metric: str, entity_id: str
) -> dict[str, Any]:
    """Describe selected metric evidence; leave absent published details explicit."""
    declared = (route.get("metric_provenance") or {}).get(metric)
    if isinstance(declared, dict):
        return dict(declared)

    status = str(route.get("operation_status") or "")
    source = route.get("source_label")
    result: dict[str, Any] = {
        "source_label": source,
        "inputs": [],
        "method": None,
        "version": None,
    }
    if metric == "departures" and status == "carrier_inferred_market_observed":
        result.update(
            inputs=["AFAC all-carrier city-pair movements", "carrier-route attribution roster"],
            method="market_total_attribution_not_observed_carrier_operations",
        )
    elif metric == "departures" and value_kind(network, route, metric) == "estimated":
        result.update(
            source_label=("AeroDataBox · frecuencias históricas estimadas"
                          if "aerodatabox" in str(source).lower() else source),
            inputs=["Published historical frequency estimate; no new provider retrieval"],
            method="historical_frequency_estimate_as_published",
        )
    elif metric == "passengers" and route.get("passengers_estimated"):
        note = str(route.get("coverage_note") or "")
        if "Pasajeros estimados de " in note:
            result["source_label"] = "AFAC + AeroDataBox"
            result["inputs"] = ["AFAC passenger margins", "AeroDataBox route-frequency seed"]
        result["method"] = route.get("estimator_version")
        result["version"] = route.get("estimator_version")
    elif metric in {"seats", "load_factor"} and route.get("capacity_estimated"):
        if network.get("mode") == "observed_international":
            if entity_id == "AEROMEXICO_GROUP":
                result.update(
                    source_label="AeroDataBox + aircraft configuration reference",
                    inputs=["AeroDataBox captured schedule", "Aeromexico aircraft seat-capacity reference"],
                    method="captured_schedule_x_operator_aircraft_configuration_v1",
                    version="v1",
                )
            elif entity_id in {"VOLARIS", "VIVA_AEROBUS"}:
                result.update(
                    source_label="AeroDataBox + BTS T-100 fleet gauge",
                    inputs=["AeroDataBox estimated departures", "prior 12 months of carrier BTS T-100 seats/departures"],
                    method="departures_x_t100_fleet_gauge_v1",
                    version="v1",
                )
            elif entity_id == "INDUSTRY":
                result.update(
                    source_label="AeroDataBox + carrier capacity methods",
                    inputs=["AeroDataBox route estimates", "carrier-specific aircraft or fleet capacity evidence"],
                    method="carrier_specific_capacity_methods_v1",
                    version="v1",
                )
        else:
            # The published route does not expose enough detail to name its
            # capacity inputs safely. Never reuse an unrelated route source.
            result.update(source_label="Capacidad estimada · procedencia detallada no publicada")
    elif metric == "departures" and status.startswith("scheduled_"):
        result["method"] = status
        result["inputs"] = [source] if source else []
    elif metric == "departures" and status == "assigned_slot_not_flown":
        result["method"] = status
        result["inputs"] = [source] if source else []
    return result


def metric_source_label(
    network: dict[str, Any], route: dict[str, Any], metric: str, entity_id: str
) -> str | None:
    provenance = metric_provenance(network, route, metric, entity_id)
    label = provenance.get("source_label")
    return label if isinstance(label, str) else None


def capacity_provenance(
    network: dict[str, Any], route: dict[str, Any], entity_id: str
) -> dict[str, Any] | None:
    """Use the published capacity component provenance when it is available."""
    declared = route.get("capacity_provenance")
    if isinstance(declared, dict):
        return dict(declared)
    if not route.get("capacity_estimated"):
        return None
    return metric_provenance(network, route, "seats", entity_id)

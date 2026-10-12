"""Complete-month quarterly projections for published domestic route snapshots."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

_ADDITIVE_METRICS = ("passengers", "seats", "departures")


def quarter_months(period: str) -> list[str]:
    year, quarter = int(period[:4]), int(period[-1])
    first_month = (quarter - 1) * 3 + 1
    return [f"{year:04d}M{month:02d}" for month in range(first_month, first_month + 3)]


def rollup_complete_quarter(
    period: str,
    networks: list[dict[str, Any]],
    value_kind: Callable[[dict[str, Any], dict[str, Any], str], str],
) -> dict[str, Any] | None:
    """Sum a quarter only when all three published monthly networks are complete."""
    months = quarter_months(period)
    if len(networks) != 3:
        return None
    for month, network in zip(months, networks, strict=True):
        expected = set(network.get("expected_months") or [])
        observed = set(network.get("observed_months") or [])
        if network.get("availability") != "complete" or expected != {month} or observed != {month}:
            return None

    route_maps = [
        {route["market_key"]: route for route in network.get("routes", []) if route.get("market_key")}
        for network in networks
    ]
    routes = []
    for market_key in sorted(set.union(*(set(routes.keys()) for routes in route_maps))):
        month_routes = [route_map.get(market_key) for route_map in route_maps]
        base = next((route for route in month_routes if route is not None), {})
        route = copy.deepcopy(base)
        route["market_key"] = market_key
        route["quarter_rollup"] = True
        route["source_periods"] = [
            {
                "period": month,
                "source_label": item.get("source_label") if item else None,
            }
            for month, item in zip(months, month_routes, strict=True)
        ]
        labels = list(
            dict.fromkeys(
                item.get("source_label") for item in month_routes if item and item.get("source_label")
            )
        )
        if len(labels) == 1:
            route["source_label"] = labels[0]
        elif labels:
            route["source_label"] = "Agregado trimestral · " + " / ".join(labels)
        route["coverage_note"] = (
            "Agregado derivado de los tres archivos mensuales publicados; "
            "un mes/ruta/métrica sin valor permanece N/D, nunca se suma como cero."
        )

        metric_kinds: dict[str, str] = {}
        for metric in _ADDITIVE_METRICS:
            values = [item.get(metric) if item else None for item in month_routes]
            route[metric] = (
                sum(values)
                if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values)
                else None
            )
            kinds = {
                value_kind(network, item, metric)
                for network, item in zip(networks, month_routes, strict=True)
                if item is not None and item.get(metric) is not None
            }
            metric_kinds[metric] = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "missing"

        passenger_values = [item.get("passengers") if item else None for item in month_routes]
        seat_values = [item.get("seats") if item else None for item in month_routes]
        monthly_load_factors = [item.get("load_factor") if item else None for item in month_routes]
        monthly_load_factor_statuses = [
            item.get("load_factor_status") if item else None for item in month_routes
        ]
        valid_monthly_load_factors = all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and 0 <= value <= 1
            and status in {None, "estimated", "reported", "observed"}
            for value, status in zip(monthly_load_factors, monthly_load_factor_statuses, strict=True)
        )
        if valid_monthly_load_factors and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in passenger_values
        ) and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
            for value in seat_values
        ):
            route["load_factor"] = sum(passenger_values) / sum(seat_values)
        else:
            route["load_factor"] = None
        load_factor_kinds = {
            value_kind(network, item, "load_factor")
            for network, item in zip(networks, month_routes, strict=True)
            if item is not None and item.get("load_factor") is not None
        }
        if route["load_factor"] is None:
            metric_kinds["load_factor"] = "missing"
        else:
            metric_kinds["load_factor"] = (
                next(iter(load_factor_kinds))
                if len(load_factor_kinds) == 1
                else "mixed"
                if load_factor_kinds
                else "missing"
            )
        route["metric_value_kinds"] = metric_kinds
        route["passengers_estimated"] = any(
            bool(item and item.get("passengers_estimated")) for item in month_routes
        )
        route["capacity_estimated"] = any(
            bool(item and item.get("capacity_estimated")) for item in month_routes
        )
        if route["load_factor"] is not None:
            route["load_factor_status"] = (
                "estimated" if metric_kinds["load_factor"] == "estimated" else base.get("load_factor_status")
            )
        elif "inconsistent_inputs" in monthly_load_factor_statuses:
            route["load_factor_status"] = "inconsistent_inputs"
        else:
            route["load_factor_status"] = "capacity_incomplete"
        routes.append(route)

    eligibility = [network.get("agent_eligible") for network in networks]
    source_map: dict[str, list[str]] = {}
    for month, network in zip(months, networks, strict=True):
        for source, source_months in (network.get("coverage_by_source") or {}).items():
            selected = source_map.setdefault(source, [])
            selected.extend(item for item in source_months if item not in selected)
    reasons = list(
        dict.fromkeys(
            network.get("eligibility_reason") for network in networks if network.get("eligibility_reason")
        )
    )
    source_urls = list(
        dict.fromkeys(network.get("source_url") for network in networks if network.get("source_url"))
    )
    return {
        "period_label": f"{period[-1]}T{int(period[:4]) % 100:02d}",
        "period_type": "quarter",
        "availability": "complete",
        "expected_months": months,
        "observed_months": months,
        "agent_eligible": False
        if False in eligibility
        else True
        if all(value is True for value in eligibility)
        else None,
        "eligibility_reason": "; ".join(str(reason) for reason in reasons),
        "coverage_by_source": source_map,
        "source_urls": source_urls,
        "source_url": source_urls[0] if len(source_urls) == 1 else None,
        "routes": routes,
        "derived_from_months": months,
    }

"""Update only changed observed markets; preserve unrelated source comparators."""

import copy
from collections import defaultdict

from src.dashboard.flight_cells import apply_flight_cells, resolve_cells
from src.dashboard.flights_html import integration_flight_payload
from src.dashboard.map_periods import period_label, period_months, refresh_network_availability
from src.dashboard.recorded_movements import LABEL as MOVEMENT_LABEL
from src.web_export.flights import _validate
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.route_support import comparable_previous_departures
from src.web_export.schemas import NETWORK_FILE_SCHEMA


def refresh_observed_network(network, cells, months, label, endpoints, selected, previous_network=None):
    network = copy.deepcopy(network)
    old = [cell for route in network["routes"] for cell in route.get("flight_components", [])]
    fresh_keys = {
        (cell["carrier_key"], cell["origin_iata"], cell["destination_iata"], cell["period_id"])
        for cell in cells
    }
    removed = [
        cell
        for cell in old
        if cell["source_label"] == label
        and cell["period_id"] in months
        and (cell["carrier_key"], cell["origin_iata"], cell["destination_iata"], cell["period_id"])
        not in fresh_keys
    ]
    if removed:
        raise ValueError("Source revision removes an observed cell; explicit missing-value review required")
    retained = [cell for cell in old if not (cell["source_label"] == label and cell["period_id"] in months)]
    resolved = resolve_cells([*retained, *cells])
    # Unmapped BTS geography must not be silently dropped by the generic resolver.
    if any(cell[key] not in endpoints for cell in cells for key in ("origin_iata", "destination_iata")):
        raise ValueError("Observed source airport lacks an exact physical reference")

    def by_market(items):
        grouped = defaultdict(list)
        for cell in items:
            grouped["<>".join(sorted((cell["origin_iata"], cell["destination_iata"])))].append(cell)
        return grouped

    def ordered(items):
        return sorted(
            items,
            key=lambda cell: tuple(
                cell[key]
                for key in (
                    "carrier_key",
                    "origin_iata",
                    "destination_iata",
                    "period_id",
                    "kind",
                    "source_label",
                )
            ),
        )

    old_by_market, fresh_by_market = by_market(old), by_market(resolved)
    changed = {
        key
        for key in old_by_market.keys() | fresh_by_market.keys()
        if ordered(old_by_market[key]) != ordered(fresh_by_market[key])
    }
    expected, caption = period_months(selected), period_label(selected)
    if not changed and network.get("expected_months") == expected and network.get("period_label") == caption:
        _validate(NETWORK_FILE_SCHEMA, network, what="unchanged selective native source")
        check_privacy(network, load_privacy_rules())
        return network
    network.update(expected_months=expected, period_label=caption)
    original_routes = {route["market_key"]: copy.deepcopy(route) for route in network["routes"]}
    prior_routes = {route["market_key"]: route for route in (previous_network or {}).get("routes", [])}
    previous_cells = [cell for route in prior_routes.values() for cell in route.get("flight_components", [])]
    prior_by_market = by_market(previous_cells)
    patch = {
        **network,
        "routes": [copy.deepcopy(route) for key, route in original_routes.items() if key in changed],
    }
    changed_cells = [cell for key in sorted(changed) for cell in fresh_by_market[key]]
    apply_flight_cells(patch, changed_cells, endpoints.__getitem__, previous_cells=previous_cells)
    updated = {}
    for route in patch["routes"]:
        key = route["market_key"]
        prior = copy.deepcopy(original_routes.get(key, {}).get("previous", route.get("previous", {})))
        # Passenger history is not a flight-count update. Revalidate only the
        # affected departure comparator against the physical year-ago network.
        prior["departures"] = comparable_previous_departures(
            network,
            route.get("flight_components", []),
            prior_by_market[key],
            prior_routes.get(key, {}).get("departures"),
        )
        route["previous"] = prior
        updated[key] = route
    network["routes"] = [updated.pop(route["market_key"], route) for route in network["routes"]]
    network["routes"].extend(updated[key] for key in sorted(updated))
    coverage = defaultdict(set)
    for cell in resolved:
        coverage[cell["source_label"]].add(cell["period_id"])
    for route in network["routes"]:
        if not route.get("flight_components"):
            coverage[route.get("source_label", "Fuente no detallada")].update(
                route.get("observed_months")
                or route.get("scheduled_months")
                or route.get("estimated_months", [])
            )
    network["coverage_by_source"] = {key: sorted(value) for key, value in sorted(coverage.items())}
    movement_months = {
        month
        for route in network["routes"]
        for month in route.get("recorded_movements", {}).get("observed_months", [])
    }
    if movement_months:
        network["coverage_by_source"][MOVEMENT_LABEL] = sorted(movement_months)
    network["observed_months"] = sorted(
        {cell["period_id"] for cell in resolved if cell["kind"] == "observed"}
        | {
            month
            for route in network["routes"]
            if not route.get("flight_components")
            for month in route.get("observed_months", [])
        }
    )
    network["airports"] = sorted(
        {
            point["iata"]: point
            for route in network["routes"]
            for point in (route["origin"], route["destination"])
        }.values(),
        key=lambda point: point["iata"],
    )
    refresh_network_availability(network)
    network = integration_flight_payload(
        dict(
            schema_version="flight_dashboard_payload_v1",
            metadata={},
            quarters=[],
            monthly_passengers=[],
            route_network={"world_geometry": {}},
            route_networks={selected: network},
        )
    )["route_networks"][selected]
    _validate(NETWORK_FILE_SCHEMA, network, what="selective native observed source")
    check_privacy(network, load_privacy_rules())
    return network

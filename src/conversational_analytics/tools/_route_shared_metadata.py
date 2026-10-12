"""Compact provenance catalog for shared-route results."""

from __future__ import annotations

from typing import Any

from src.conversational_analytics.tools._route_provenance import (
    capacity_provenance as _capacity_provenance,
)


def build_shared_carrier_metadata(
    entity_ids: list[str],
    labels: dict[str, str],
    networks: dict[str, dict[str, Any]],
    routes: dict[str, dict[str, dict[str, Any]]],
    source_ids: dict[str, dict[str, str]],
    source_labels: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Store each route source once and keep capacity provenance available."""
    metadata = {}
    for entity_id in entity_ids:
        network = networks.get(entity_id)
        route_map = routes.get(entity_id, {})
        capacity_route = next(
            (route for route in route_map.values() if route.get("capacity_estimated")), None
        )
        metadata[entity_id] = {
            "label": labels[entity_id],
            "source_labels": {
                source_ids[entity_id][label]: label for label in source_labels[entity_id]
            },
            "capacity_provenance": (
                _capacity_provenance(network, capacity_route, entity_id)
                if capacity_route and network
                else None
            ),
        }
    return metadata

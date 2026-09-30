"""Which carriers each Vuelos map entity covers (Dashboard v2, fase 3).

Grupo Aeroméxico keeps every source and layer the page has always shown.
Volaris, Viva and Industria (the three together) show, by the owner's
decision of 30 Sep 2026: domestic routes estimated from AFAC + AeroDataBox
(IPF), Mexico–United States observed by BTS T-100, and the rest of the
international network estimated. They carry no Aeroméxico-only layer
(AICM slots, AIFA single-operator markets, OMA releases, ANAC/Aerocivil/
CAA/Aena authority observations). Their seat capacity (fase 4) is the
fleet-average estimate of ``src.analytics.fleet_capacity``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RouteEntity:
    key: str
    label: str
    # Estimate-table carrier keys -> label (the IPF keeps Aerovías and Connect apart).
    estimate_carriers: dict[str, str]
    # T-100 carrier keys (Connect does not report to BTS separately).
    t100_carriers: tuple[str, ...]
    group_key: str
    group_label: str
    aeromexico_layers: bool
    capacity: bool
    # Estimate/T-100 carrier key -> dashboard entity, for the per-route
    # breakdown Industria shows. Empty for a single airline.
    breakdown: dict[str, str] = field(default_factory=dict)
    # Carriers whose seats come from the T-100 fleet gauge instead of the
    # aircraft-model configuration (Dashboard v2 fase 4).
    fleet_capacity_carriers: tuple[str, ...] = ()

    @property
    def domestic_estimated_label(self) -> str:
        suffix = " + flota" if self.capacity else ""
        return f"AFAC + AeroDataBox{suffix} · {self.group_label} estimado"

    @property
    def international_estimated_label(self) -> str:
        return f"AFAC + AeroDataBox · {self.group_label} estimado"


AEROMEXICO_ROUTES = RouteEntity(
    key="AEROMEXICO",
    label="Grupo Aeroméxico",
    estimate_carriers={"AEROMEXICO": "Aerovías de México", "AEROMEXICO_CONNECT": "Aeroméxico Connect"},
    t100_carriers=("AEROMEXICO",),
    group_key="AEROMEXICO_GROUP",
    group_label="Grupo Aeroméxico",
    aeromexico_layers=True,
    capacity=True,
)

VOLARIS_ROUTES = RouteEntity(
    key="VOLARIS",
    label="Volaris",
    estimate_carriers={"VOLARIS": "Volaris"},
    t100_carriers=("VOLARIS",),
    group_key="VOLARIS",
    group_label="Volaris",
    aeromexico_layers=False,
    capacity=True,
    fleet_capacity_carriers=("VOLARIS",),
)

VIVA_ROUTES = RouteEntity(
    key="VIVA_AEROBUS",
    label="Viva",
    estimate_carriers={"VIVA_AEROBUS": "Viva Aerobus"},
    t100_carriers=("VIVA_AEROBUS",),
    group_key="VIVA_AEROBUS",
    group_label="Viva",
    aeromexico_layers=False,
    capacity=True,
    fleet_capacity_carriers=("VIVA_AEROBUS",),
)

INDUSTRY_ROUTES = RouteEntity(
    key="INDUSTRY",
    label="Industria",
    estimate_carriers={
        **AEROMEXICO_ROUTES.estimate_carriers,
        **VOLARIS_ROUTES.estimate_carriers,
        **VIVA_ROUTES.estimate_carriers,
    },
    t100_carriers=("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"),
    group_key="INDUSTRY",
    group_label="Industria",
    aeromexico_layers=False,
    capacity=True,
    fleet_capacity_carriers=("VOLARIS", "VIVA_AEROBUS"),
    breakdown={
        "AEROMEXICO": "AEROMEXICO",
        "AEROMEXICO_CONNECT": "AEROMEXICO",
        "VOLARIS": "VOLARIS",
        "VIVA_AEROBUS": "VIVA_AEROBUS",
    },
)

# Entities exported next to Grupo Aeroméxico's historical files.
EXTRA_ROUTE_ENTITIES: tuple[RouteEntity, ...] = (INDUSTRY_ROUTES, VOLARIS_ROUTES, VIVA_ROUTES)


def breakdown_totals(entity: RouteEntity, rows: list[tuple[str, float]]) -> dict[str, float] | None:
    """Sum (carrier_key, passengers) pairs into the entity's dashboard keys."""

    if not entity.breakdown:
        return None
    totals: dict[str, float] = {}
    for carrier_key, passengers in rows:
        target = entity.breakdown.get(carrier_key)
        if target is None:
            raise ValueError(f"{carrier_key} is not part of {entity.key}")
        totals[target] = totals.get(target, 0.0) + float(passengers)
    return {key: round(value, 1) for key, value in sorted(totals.items())}

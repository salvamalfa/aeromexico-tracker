"""Validation and projection for the frontend's dashboard context contract."""

from __future__ import annotations

import re
from typing import Any

from src.conversational_analytics.semantic.plan import ENTITY_IDS, PERIOD_RE, SEGMENTS, PlanValidationError

TABS = {"reading", "economy", "flights", "market", "news"}
REGIONS = {"norteamerica", "sudamerica", "europa", "asia"}
CONTEXT_ENTITY_IDS = ENTITY_IDS - {"MEXICAN_CARRIERS"}
CARD_IDS = {
    "market-chart",
    "market-card",
    "unit-chart",
    "unit-card",
    "volume-chart",
    "volume-card",
    "load-chart",
    "load-card",
    "flight-kpis",
    "panel-reading",
    "panel-economy",
    "pick-kpis",
    "reading-card",
    "flights",
    "flights-shell",
    "flow-map",
    "route-flow-map",
    "mix-chart",
    "kpi-passengers",
    "kpi-asm_miles",
    "kpi-rpm_miles",
    "kpi-load_factor",
    "kpi-rask_cents_per_km",
    "kpi-cask_cents_per_km",
    "kpi-ask_km",
    "kpi-unit_margin_cents_per_km",
    "flight-kpi-passengers",
    "flight-kpi-asm_miles",
    "flight-kpi-rpm_miles",
    "flight-kpi-load_factor",
}
FILTER_KEYS = {
    "segment",
    "start",
    "end",
    "entities",
    "network_mode",
    "domestic_months",
    "region",
    "range",
    "flight_evidence",
    "map_schema_version",
    "map_dataset_version",
    "map_scope",
    "map_region",
    "map_carriers",
    "map_months",
    "map_grain",
}

OFFICIAL_SCOPES = {"national", "us", "international"}
OFFICIAL_REGIONS = {"canada", "central_america_caribbean", "south_america", "europe", "asia"}
OFFICIAL_CARRIERS = ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS")


def _validate_official_filters(filters: dict[str, Any], tab: Any, card: Any, entity: Any) -> None:
    official = {key for key in filters if key.startswith("map_")}
    if not official:
        return
    required = {"map_scope", "map_dataset_version", "map_months", "map_grain"}
    if not required <= official or tab != "market" or card not in {None, "route-flow-map", "flow-map"}:
        raise PlanValidationError("El mapa oficial requiere vista Mercado, versión, alcance, meses y grano")
    if set(filters) - {key for key in FILTER_KEYS if key.startswith("map_")}:
        raise PlanValidationError("El mapa oficial no admite filtros de evidencia o métricas heredadas")
    scope = filters["map_scope"]
    if not isinstance(scope, str) or scope not in OFFICIAL_SCOPES:
        raise PlanValidationError("map_scope no reconocido")
    if filters.get("map_schema_version", "official_route_network_v1") != "official_route_network_v1":
        raise PlanValidationError("map_schema_version no reconocido")
    version = filters["map_dataset_version"]
    if not isinstance(version, str) or not re.fullmatch(r"[a-f0-9]{64}", version):
        raise PlanValidationError("map_dataset_version debe ser la identidad SHA-256 del dataset oficial")
    grain = "airport_pair" if scope == "us" else "city_pair"
    if filters["map_grain"] != grain:
        raise PlanValidationError("map_grain no corresponde al alcance oficial")
    region = filters.get("map_region")
    if region is not None and (
        scope != "international" or not isinstance(region, str) or region not in OFFICIAL_REGIONS
    ):
        raise PlanValidationError("map_region sólo admite regiones internacionales oficiales")
    carriers = filters.get("map_carriers", [])
    if (
        not isinstance(carriers, list)
        or len(carriers) != len(set(item for item in carriers if isinstance(item, str)))
        or any(not isinstance(item, str) or item not in OFFICIAL_CARRIERS for item in carriers)
        or (scope == "us" and not 1 <= len(carriers) <= 3)
        or (scope != "us" and (carriers or entity is not None))
    ):
        raise PlanValidationError(
            "AFAC conserva todas las aerolíneas; EEUU admite de una a tres seleccionadas"
        )
    months = filters["map_months"]
    if (
        not isinstance(months, list)
        or len(months) > 3
        or any(not isinstance(month, str) or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", month)
               for month in months)
        or len(set(months)) != len(months)
    ):
        raise PlanValidationError("map_months debe contener los meses oficiales observados sin duplicados")


def validate_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {}
    if not isinstance(context, dict) or set(context) - {"tab", "period", "entity", "card_id", "filters"}:
        raise PlanValidationError("Contexto contiene claves no permitidas")
    out: dict[str, Any] = {}
    tab = context.get("tab")
    if tab is not None:
        if not isinstance(tab, str) or tab not in TABS:
            raise PlanValidationError("Pestaña no reconocida")
        out["tab"] = tab
    period = context.get("period")
    if period is not None:
        if period != "" and (not isinstance(period, str) or not PERIOD_RE.fullmatch(period)):
            raise PlanValidationError("Periodo de contexto inválido")
        out["period"] = period or None
    entity = context.get("entity")
    if entity is not None:
        entities = [entity] if isinstance(entity, str) else entity
        if (
            not isinstance(entities, list)
            or not 1 <= len(entities) <= 4
            or any(not isinstance(item, str) or item not in CONTEXT_ENTITY_IDS for item in entities)
        ):
            raise PlanValidationError("entity debe ser ID canónico o lista de hasta 4 IDs canónicos")
        out["entity"] = entity
    card = context.get("card_id")
    if card is not None:
        if not isinstance(card, str) or card not in CARD_IDS:
            raise PlanValidationError("Tarjeta de contexto desconocida")
        out["card_id"] = card
    filters = context.get("filters")
    if filters is not None:
        if not isinstance(filters, dict) or set(filters) - FILTER_KEYS:
            raise PlanValidationError("Filtros de contexto no reconocidos")
        clean: dict[str, Any] = {}
        for key, value in filters.items():
            if key == "segment" and (not isinstance(value, str) or value not in SEGMENTS):
                raise PlanValidationError("segment debe ser total, domestic o international")
            if key in {"start", "end"} and (not isinstance(value, str) or not PERIOD_RE.fullmatch(value)):
                raise PlanValidationError(f"{key} debe ser un periodo publicado con formato válido")
            if key == "entities" and (
                not isinstance(value, list)
                or not 1 <= len(value) <= 4
                or any(not isinstance(item, str) or item not in CONTEXT_ENTITY_IDS for item in value)
            ):
                raise PlanValidationError("filters.entities debe contener IDs canónicos")
            if key == "network_mode" and (
                not isinstance(value, str) or value not in {"domestic", "international"}
            ):
                raise PlanValidationError("network_mode inválido")
            if key == "domestic_months" and (
                not isinstance(value, list)
                or len(value) > 5
                or any(
                    not isinstance(m, str)
                    or not m.startswith(tuple(str(y) for y in range(2019, 2031)))
                    or not PERIOD_RE.fullmatch(m)
                    or "M" not in m
                    for m in value
                )
            ):
                raise PlanValidationError("domestic_months debe contener máximo cinco periodos mensuales")
            if key == "region" and (not isinstance(value, str) or value not in REGIONS):
                raise PlanValidationError("region no reconocida")
            if key == "range" and (not isinstance(value, str) or value not in {"all", "12", "8", "4"}):
                raise PlanValidationError("range debe ser all, 12, 8 o 4")
            clean[key] = value
        if "flight_evidence" in clean and (
            clean["flight_evidence"] != "north_america_observed"
            or tab != "flights"
            or clean.get("network_mode") != "international"
            or clean.get("region") not in {None, "norteamerica"}
            or card not in {None, "route-flow-map", "flow-map"}
        ):
            raise PlanValidationError(
                "flight_evidence sólo admite la vista internacional observada de Norteamérica"
            )
        if "start" in clean and "end" in clean:
            if clean["start"] > clean["end"] or clean["start"][4] != clean["end"][4]:
                raise PlanValidationError("Filtros start/end deben ser un rango cronológico del mismo grano")
        _validate_official_filters(clean, tab, card, entity)
        out["filters"] = clean
    return out


__all__ = ["validate_context", "CARD_IDS", "TABS"]

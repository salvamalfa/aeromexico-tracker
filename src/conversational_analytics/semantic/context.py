"""Validation and projection for the frontend's dashboard context contract."""

from __future__ import annotations

from typing import Any

from src.conversational_analytics.semantic.plan import ENTITY_IDS, PERIOD_RE, SEGMENTS, PlanValidationError

TABS = {"reading", "economy", "flights"}
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
FILTER_KEYS = {"segment", "start", "end", "entities", "network_mode", "domestic_months", "region", "range"}


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
        if "start" in clean and "end" in clean:
            if clean["start"] > clean["end"] or clean["start"][4] != clean["end"][4]:
                raise PlanValidationError("Filtros start/end deben ser un rango cronológico del mismo grano")
        out["filters"] = clean
    return out


__all__ = ["validate_context", "CARD_IDS", "TABS"]

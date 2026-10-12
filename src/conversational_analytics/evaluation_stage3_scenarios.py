"""Frozen F2.9 business scenario actions and numeric derivations."""

from __future__ import annotations

import math
from typing import Any


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _latest_prior(periods: list[str], current: str, years: int = 1) -> str | None:
    if "Q" in current:
        year, quarter = current.split("Q")
        target = f"{int(year) - years:04d}Q{quarter}"
    elif "M" in current:
        year, month = current.split("M")
        target = f"{int(year) - years:04d}M{month}"
    else:
        return None
    return target if target in periods else None


def _scenario_calls(
    case_id: str, periods: dict[str, Any]
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    """Return tool actions derived from the frozen question's intent, not its old status."""
    economic = periods["economic_quarters"]
    market = periods["market_quarters"]
    months = periods["market_months"]
    flights = periods["flight"]
    latest_econ = economic[-1] if economic else None
    latest_market = market[-1] if market else None
    intl = flights.get("international", [])
    dom_monthly = flights.get("domestic_monthly", [])
    latest_flight = (dom_monthly or intl or [None])[-1]
    prior_econ = _latest_prior(economic, latest_econ) if latest_econ else None
    prior_market = _latest_prior(market, latest_market) if latest_market else None
    actions: list[tuple[str, dict[str, Any]]] = []
    scope_limit: str | None = None

    def query(metric: str, entities: list[str], selected: list[str], segment: str | None = None):
        args: dict[str, Any] = {"metric_ids": [metric], "entity_ids": entities, "periods": selected}
        if segment:
            args["segment"] = segment
        actions.append(("query_metrics", args))

    def series(metric: str, entity: str, selected: list[str], segment: str | None = None):
        if not selected:
            return
        args: dict[str, Any] = {
            "metric_id": metric,
            "entity_id": entity,
            "start_period": selected[0],
            "end_period": selected[-1],
            "limit": 20,
        }
        if segment:
            args["segment"] = segment
        actions.append(("get_time_series", args))

    if case_id == "N01":
        actions.append(
            (
                "query_business_metrics",
                {"metric_id": "company_passengers", "entity_id": "AEROMEXICO", "period": "2025"},
            )
        )
    elif case_id == "N02":
        query("load_factor", ["AEROMEXICO"], [latest_econ] if latest_econ else [])
    elif case_id == "N03":
        query("cask_cents_per_km", ["AEROMEXICO", "VOLARIS"], [latest_econ] if latest_econ else [])
    elif case_id == "N04":
        actions.extend(
            [
                ("get_business_metric_definition", {"metric_id": "total_revenue"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "total_revenue",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
    elif case_id == "N05":
        query("afac_passengers", ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"], ["2025Q4"], "total")
        scope_limit = (
            "Debe aclararse qué significa ‘más grande’ (pasajeros, ingresos, flota u otra medida). "
            "La consulta solo explora pasajeros AFAC de 4T25 para Aeroméxico, Volaris y Viva; "
            "no cubre todas las aerolíneas de México y no sustenta un ganador del mercado."
        )
    elif case_id == "N06":
        if prior_econ and latest_econ:
            for metric in ("company_passengers", "load_factor", "cask_cents_per_km"):
                actions.append(
                    (
                        "compare_metrics",
                        {
                            "metric_id": metric,
                            "entity_id": "AEROMEXICO",
                            "periods": [prior_econ, latest_econ],
                        },
                    )
                )
        scope_limit = (
            "La pregunta no define una métrica única; las comparaciones separadas no forman "
            "una calificación global."
        )
    elif case_id in {"N07", "N08"}:
        selected = [period for period in (prior_market, latest_market) if period]
        if selected:
            query("market_share", ["AEROMEXICO", "VOLARIS"], selected, "domestic")
            actions.append(("get_source_references", {"metric_ids": ["market_share"]}))
        if case_id == "N08":
            scope_limit = (
                "Se comparan trimestres equivalentes: 2T25 frente a 2T26, con cambio expresado en "
                "puntos porcentuales. Esto no compara años calendario completos ni otros trimestres."
            )
    elif case_id == "N09":
        if latest_flight:
            prior = _latest_prior(dom_monthly or intl, latest_flight)
            args: dict[str, Any] = {
                "entity_id": "AEROMEXICO_GROUP",
                "segment": "domestic",
                "period": latest_flight,
                "metric": "passengers",
                "top_n": 5,
            }
            if prior:
                args["comparison_period"] = prior
                args["order_by"] = "absolute_change"
            actions.append(("query_routes", args))
        scope_limit = (
            "La consulta devuelve rutas del periodo mensual seleccionado, pero no mide crecimiento del "
            "año sin una serie comparable."
        )
    elif case_id == "N10":
        if latest_flight:
            actions.append(
                (
                    "find_shared_routes",
                    {
                        "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
                        "segment": "domestic",
                        "period": latest_flight,
                        "metric": "passengers",
                        "top_n": 20,
                    },
                )
            )
    elif case_id == "N11":
        if prior_econ and latest_econ:
            query("load_factor", ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"], [prior_econ, latest_econ])
    elif case_id == "N12":
        history = [period for period in economic if period >= "2024Q3"]
        series("cask_cents_per_km", "AEROMEXICO", history)
        actions.append(("get_source_references", {"metric_ids": ["cask_cents_per_km"]}))
    elif case_id == "N13":
        if prior_market and latest_market:
            actions.append(
                (
                    "compare_metrics",
                    {
                        "metric_id": "afac_passengers",
                        "entity_id": "INDUSTRY",
                        "periods": [prior_market, latest_market],
                        "segment": "international",
                    },
                )
            )
    elif case_id == "N14":
        selected_months = [period for period in months if period.startswith("2026M")]
        if selected_months:
            query("afac_passengers", ["AEROMEXICO"], selected_months, "total")
        else:
            actions.append(
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "AEROMEXICO", "period": "2026H1"},
                )
            )
    elif case_id == "N15":
        if latest_econ:
            query("cask_cents_per_km", ["AEROMEXICO"], [latest_econ], None)
        actions.append(("get_business_metric_definition", {"metric_id": "fuel_expense"}))
        actions.append(
            (
                "query_business_metrics",
                {"metric_id": "fuel_expense", "entity_id": "AEROMEXICO", "period": latest_econ or "2026Q2"},
            )
        )
        scope_limit = "La causa del cambio requiere el componente financiero publicado y su aprobación."
    elif case_id == "N16":
        actions.extend(
            [
                (
                    "search_reports",
                    {
                        "query": "combustible costos Aeromexico",
                        "company": "Aeromexico",
                        "period": None,
                        "limit": 5,
                    },
                ),
                ("get_business_metric_definition", {"metric_id": "fuel_expense"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "fuel_expense",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
        scope_limit = "Las herramientas de referencia no buscan ni extraen texto de reportes."
    elif case_id == "N17":
        actions.append(
            (
                "search_news",
                {
                    "query": "caída pasajeros junio 2026 Aeromexico",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "company": None,
                    "limit": 5,
                },
            )
        )
        scope_limit = "No hay una herramienta de búsqueda de noticias o atribución de eventos."
    elif case_id == "N18":
        if prior_econ and latest_econ:
            actions.append(
                (
                    "compare_metrics",
                    {
                        "metric_id": "load_factor",
                        "entity_id": "VOLARIS",
                        "periods": [prior_econ, latest_econ],
                    },
                )
            )
        scope_limit = "La serie permite medir el cambio, pero no identifica su causa."
    elif case_id == "N19":
        actions.append(("get_business_metric_definition", {"metric_id": "fuel_expense"}))
        for entity in ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"):
            actions.append(
                (
                    "query_business_metrics",
                    {"metric_id": "fuel_expense", "entity_id": entity, "period": latest_econ or "2026Q2"},
                )
            )
    elif case_id == "N20":
        if latest_econ:
            actions.append(
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "AEROMEXICO", "period": latest_econ},
                )
            )
        scope_limit = "El snapshot publica datos históricos; no incluye un pronóstico para 2027."
    elif case_id == "N21":
        if latest_market:
            query("market_share", ["VOLARIS", "VIVA_AEROBUS"], [latest_market], "domestic")
            actions.append(("get_source_references", {"metric_ids": ["market_share"]}))
    elif case_id == "N22":
        actions.extend(
            [
                ("get_business_metric_definition", {"metric_id": "fuel_expense"}),
                ("get_business_metric_definition", {"metric_id": "operating_costs"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "fuel_expense",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "operating_costs",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
    elif case_id == "N23":
        actions.extend(
            [
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "VIVA_AEROBUS", "period": "2026H1"},
                ),
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "VOLARIS", "period": "2026H1"},
                ),
            ]
        )
    elif case_id == "N24":
        actions.append(("get_dashboard_context", {}))
        query("company_passengers", ["AEROMEXICO", "VOLARIS"], [latest_econ] if latest_econ else [])
        if prior_econ and latest_econ:
            query("company_passengers", ["AEROMEXICO", "VOLARIS"], [prior_econ, latest_econ])
        actions.append(("get_source_references", {"metric_ids": ["company_passengers"]}))
        scope_limit = "Pasajeros describe un aspecto de 2T26, pero no resume el desempeño general de la aerolínea."
    elif case_id in {"N25", "N26"}:
        actions.append(("get_dashboard_context", {}))
        query(
            "load_factor",
            ["AEROMEXICO"],
            ["2026Q2"] if "2026Q2" in economic else ([latest_econ] if latest_econ else []),
        )
        actions.append(("get_source_references", {"metric_ids": ["load_factor"]}))
        # Follow-up turns are deliberately satisfied from the retained first-turn result.
    elif case_id == "N27":
        scope_limit = "No existe una definición única publicada de la mejor aerolínea."
    elif case_id == "N28":
        scope_limit = "El análisis no ofrece recomendaciones de inversión."
    elif case_id == "N29":
        actions.extend(
            [
                ("get_business_metric_definition", {"metric_id": "operating_income"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "operating_income",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "company_passengers",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
    elif case_id == "N30":
        actions.append(("get_data_catalog", {}))
        scope_limit = "El catálogo no ofrece conteos diarios de vuelos cancelados."
    else:
        scope_limit = "No hay un escenario determinista para el caso."

    return actions, scope_limit



def _derived_calculations(case_id: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive comparison cells only from finite values returned by the tools."""
    by_key = {
        (item.get("metric_id"), item.get("entity_id"), item.get("period")): item
        for item in evidence
        if item.get("availability") == "available" and _numeric(item.get("value"))
    }

    def value(metric: str, entity: str, period: str) -> float | None:
        row = by_key.get((metric, entity, period))
        return float(row["value"]) if row is not None else None

    calculations: list[dict[str, Any]] = []
    if case_id == "N03":
        period = "2026Q2"
        am = value("cask_cents_per_km", "AEROMEXICO", period)
        competitor = value("cask_cents_per_km", "VOLARIS", period)
        if am is not None and competitor is not None:
            calculations.append(
                {
                    "calculation": "AEROMEXICO_minus_VOLARIS",
                    "value": am - competitor,
                    "unit": "USD_cents_per_ASK_km",
                    "period": period,
                }
            )
    elif case_id == "N07":
        for entity in ("AEROMEXICO", "VOLARIS"):
            prior = value("market_share", entity, "2025Q2")
            current = value("market_share", entity, "2026Q2")
            if prior is not None and current is not None:
                calculations.append(
                    {
                        "calculation": f"{entity}_share_change",
                        "value": (current - prior) * 100,
                        "unit": "percentage_points",
                        "periods": ["2025Q2", "2026Q2"],
                    }
                )
    elif case_id == "N11":
        for entity in ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"):
            prior = value("load_factor", entity, "2025Q2")
            current = value("load_factor", entity, "2026Q2")
            if prior is not None and current is not None:
                calculations.append(
                    {
                        "calculation": f"{entity}_load_factor_change",
                        "value": (current - prior) * 100,
                        "unit": "percentage_points",
                        "periods": ["2025Q2", "2026Q2"],
                    }
                )
    elif case_id == "N21":
        volaris = value("market_share", "VOLARIS", "2026Q2")
        viva = value("market_share", "VIVA_AEROBUS", "2026Q2")
        if volaris is not None and viva is not None:
            calculations.append(
                {
                    "calculation": "VOLARIS_plus_VIVA_AEROBUS_market_share",
                    "value": math.fsum((volaris, viva)),
                    "unit": "fraction",
                    "period": "2026Q2",
                }
            )
    elif case_id == "N23":
        viva = value("company_passengers", "VIVA_AEROBUS", "2026H1")
        volaris = value("company_passengers", "VOLARIS", "2026H1")
        if viva is not None and volaris is not None:
            calculations.append(
                {
                    "calculation": "VIVA_AEROBUS_minus_VOLARIS_passengers",
                    "value": viva - volaris,
                    "unit": "passengers",
                    "period": "2026H1",
                }
            )
    return calculations

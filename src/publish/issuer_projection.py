"""Project one source-replayed issuer quarter into existing dashboard charts."""

from __future__ import annotations

import copy
import math
from dataclasses import asdict

from src.dashboard.entities import ENTITY_BY_KEY
from src.dashboard.executive_summary import (
    _entity_kpi_definitions,
    _period_label,
    _period_view,
    _point_comparison,
    _previous_quarter,
)

MILE_KM = 1.609344
ENTITIES = {"VOLARIS", "VIVA_AEROBUS"}


def executive_projection(baseline: dict, package: dict) -> dict:
    """Replay primary inputs; change only the issuer's selected quarter and views.

    Candidate source-observation Gold is never copied over the harmonized fact.
    The approved evidence package is the boundary into this public projection.
    """
    from src.analysis_agent.issuer_quarter import calculate, verify

    verify(package)
    entity = package["entity_key"]
    period = package["period_id"]
    if entity not in ENTITIES or period != "2026Q3":
        raise ValueError("Reviewed Viva/Volaris 3Q26 issuer profile required")
    nodes = calculate(package)["nodes"]
    indexed = {}
    for node in nodes:
        identity = node["period_id"], node["key"]
        if identity in indexed:
            raise ValueError("Duplicate issuer calculation identity")
        indexed[identity] = node["value"]

    def record(selected):
        def get(key):
            value = indexed[selected, key]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Issuer chart values must be finite reported/calculated quantities")
            return value

        if not 0 <= get("load") <= 1 or get("asm") <= 0:
            raise ValueError("Issuer occupancy/capacity outside physical domain")
        return {
            "period_id": selected,
            "period_label": _period_label(selected),
            "passengers": get("passengers"),
            "ask_km": get("asm") * MILE_KM,
            "rpk_km": get("rpm") * MILE_KM,
            "load_factor": get("load"),
            "load_factor_basis": "reported",
            "rask_cents_per_km": get("trasm") / MILE_KM,
            "cask_cents_per_km": get("casm") / MILE_KM,
            "cask_ex_fuel_cents_per_km": get("casm_ex") / MILE_KM,
            "unit_margin_cents_per_km": (get("trasm") - get("casm")) / MILE_KM,
        }

    current, comparative = record(period), record("2025Q3")
    doc = copy.deepcopy(baseline)
    block = doc["entities"][entity]
    prior = {r["period_id"]: r for r in block["records"]}
    # The report's comparator informs this edition's YoY only. It does not
    # overwrite an older published historical point with a revised comparator.
    prior["2025Q3"] = comparative
    definitions = [dict(d) for d in _entity_kpi_definitions(ENTITY_BY_KEY[entity], "reported")]
    for definition in definitions:
        if definition["key"] == "passengers":
            definition.update(
                label="Pasajeros con boleto",
                description=(
                    "Clientes con boleto según el reporte; no equivale a pasajeros observados en vuelo."
                ),
            )
    view = _period_view(
        current,
        prior,
        definitions=tuple(definitions),
        load_key="load_factor",
        subject=ENTITY_BY_KEY[entity].subject,
        load_verb="reportó",
        industry=None,
    )
    previous = prior.get(_previous_quarter(period))
    for kpi in view["kpis"]:
        if kpi["key"] == "load_factor":
            kpi["yoy"] = asdict(_point_comparison(current["load_factor"], comparative["load_factor"]))
            kpi["qoq"] = asdict(
                _point_comparison(
                    current["load_factor"],
                    previous["load_factor"] if previous is not None else None,
                )
            )
    notes = [
        "Julio–septiembre de 2026; comparativo anual del mismo reporte. "
        "Los nueve meses acumulados y los saldos al cierre quedan separados.",
        "Pasajeros significa clientes con boleto. La ocupación reportada corresponde a servicios regulares; "
        "no se fuerza su igualdad con RPM/ASM cuando estos incluyen otra cobertura.",
        "Ingreso y costo unitarios reportados por asiento-milla convertidos a centavos USD por "
        "asiento-kilómetro con 1 milla = 1,609344 km. El margen unitario es su diferencia, "
        "no el margen operativo porcentual.",
    ]
    notes.extend(package.get("public_notes", []))
    if entity == "VOLARIS":
        notes.append(
            "Procedencia: transcripción visible reconstruida del reporte SEC, "
            "verificada contra su expediente; "
            "no se conservan aquí los bytes originales de SEC."
        )
    view["narrative"] = {
        "headline": f"Bases de los indicadores {ENTITY_BY_KEY[entity].label} 3T26",
        "paragraphs": notes,
    }
    block["records"] = [r for r in block["records"] if r["period_id"] != period] + [current]
    block["records"].sort(key=lambda r: r["period_id"])
    block["views"][period] = view
    block["first_period"] = block["records"][0]["period_id"]
    block["last_period"] = block["records"][-1]["period_id"]
    block["quarter_count"] = len(block["records"])
    return doc


def require_scope(before: dict, after: dict, entity: str, period: str) -> None:
    """Reject historical/peer/root mutation independently of a pinned full hash."""
    if entity not in ENTITIES or period != "2026Q3":
        raise ValueError("Unsupported issuer scope")
    expected = copy.deepcopy(after)
    old, new = before["entities"][entity], expected["entities"][entity]
    old_history = [r for r in old["records"] if r["period_id"] != period]
    new_history = [r for r in new["records"] if r["period_id"] != period]
    if old_history != new_history or sum(r["period_id"] == period for r in new["records"]) != 1:
        raise ValueError("Issuer update changed historical records or duplicated the quarter")
    if {k: v for k, v in new["views"].items() if k != period} != {
        k: v for k, v in old["views"].items() if k != period
    }:
        raise ValueError("Issuer update changed historical views")
    if (
        new["last_period"] != max(r["period_id"] for r in new["records"])
        or new["quarter_count"] != len(new["records"])
        or new["first_period"] != min(r["period_id"] for r in new["records"])
        or period not in new["views"]
        or new["views"][period]["period_id"] != period
    ):
        raise ValueError("Issuer coverage metadata differs")
    for key in ("records", "views", "first_period", "last_period", "quarter_count"):
        new[key] = copy.deepcopy(old[key])
    if expected != before:
        raise ValueError("Issuer update changed another entity, root, notes or unrelated metadata")

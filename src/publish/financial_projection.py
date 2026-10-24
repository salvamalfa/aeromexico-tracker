"""Aeromexico 3Q26 financial projection; reported and calculated bases stay distinct."""

from __future__ import annotations

import copy

from src.analysis_agent.quarterly_release import calculate, verify
from src.dashboard.executive_summary import _period_view

PERIOD = "2026Q3"
MILE_KM = 1.609344
METHOD = "aeromexico_3q26_reported_units_v1"


def reconciliation(package: dict) -> dict:
    """Reproduce the total-revenue numerator and ASM denominator, not passenger yield."""
    verify(package)
    values = {(m["period_id"], m["metric_key"]): m["value"] for m in package["metrics"]}
    rows = {}
    for period in (PERIOD, "2025Q3"):
        get = lambda key: values[period, key]
        computed = get("revenue") / get("asm") * 100
        if round(computed, 1) != get("trasm"):
            raise ValueError("Total-revenue/ASM cannot reproduce the printed TRASM precision")
        rows[period] = {
            "total_revenue_usd": get("revenue"),
            "asm_seat_miles": get("asm"),
            "trasm_reported_cents_usd_per_asm": get("trasm"),
            "trasm_from_printed_totals": computed,
            "rask_reported_converted_cents_usd_per_ask": get("trasm") / MILE_KM,
            "casm_reported_cents_usd_per_asm": get("casm"),
            "statement_operating_expenses_usd": get("expenses"),
            "casm_implied_cost_usd_not_statement_expenses": get("casm") * get("asm") / 100,
            "load_reported": get("load"),
        }
    current, prior = rows[PERIOD], rows["2025Q3"]
    totals_growth = (current["trasm_from_printed_totals"] / prior["trasm_from_printed_totals"] - 1) * 100
    reported = values[PERIOD, "trasm_yoy"]
    if round(totals_growth, 1) != reported:
        raise ValueError("Reported TRASM growth is inconsistent with total revenue and capacity")
    return {
        "method": METHOD,
        "mile_to_km": MILE_KM,
        "numerator": "total revenue including passenger, cargo, loyalty and other revenue; not passenger-only revenue",
        "native_denominator": "available seat miles (ASM)",
        "converted_denominator": "available seat kilometres (ASK)",
        "periods": rows,
        "reported_trasm_growth_percent": reported,
        "growth_from_printed_total_revenue_and_asm_percent": totals_growth,
        "growth_from_rounded_unit_values_percent": (values[PERIOD, "trasm"] / values["2025Q3", "trasm"] - 1)
        * 100,
        "reported_casm_growth_percent": values[PERIOD, "casm_yoy"],
        "casm_growth_from_rounded_unit_values_percent": (
            values[PERIOD, "casm"] / values["2025Q3", "casm"] - 1
        )
        * 100,
        "limit": "Printed totals are themselves rounded. This reproduces reported growth at its displayed precision, not unpublished unrounded inputs. CASM is preserved as reported and is not replaced by statement expenses/ASM.",
    }


def executive_projection(baseline: dict, package: dict) -> dict:
    """Append one quarter without rewriting any prior record/view or peer block."""
    recon = reconciliation(package)
    nodes = {n["key"]: n["value"] for n in calculate(package)["nodes"] if n["period_id"] == PERIOD}
    doc = copy.deepcopy(baseline)
    if PERIOD in doc["views"] or any(r["period_id"] == PERIOD for r in doc["records"]):
        raise ValueError("Financial quarter already exists")
    record = {
        "period_id": PERIOD,
        "period_label": "3T26",
        "passengers": nodes["passengers"],
        "ask_km": nodes["ask"],
        "load_factor_reported": nodes["load"],
        "rask_cents_per_km": nodes["rask"],
        "cask_cents_per_km": nodes["cask"],
        "unit_margin_cents_per_km": nodes["spread"],
    }
    prior = {r["period_id"]: r for r in doc["records"]}
    view = _period_view(record, prior)
    for kpi in view["kpis"]:
        key = {
            "rask_cents_per_km": "trasm_yoy",
            "cask_cents_per_km": "casm_yoy",
            "ask_km": "asm_yoy",
            "passengers": "passengers_yoy",
        }.get(kpi["key"])
        if key:
            percent = nodes[key]
            kpi["yoy"] = {
                "available": True,
                "raw": percent / 100,
                "display": f"{percent:+.1f}%",
                "direction": "up" if percent > 0 else "down" if percent < 0 else "flat",
            }
        elif kpi["key"] == "load_factor_reported":
            points = round((nodes["load"] - recon["periods"]["2025Q3"]["load_reported"]) * 100, 1)
            kpi["yoy"] = {
                "available": True,
                "raw": points,
                "display": f"{points:+.1f} pp",
                "direction": "up" if points > 0 else "down" if points < 0 else "flat",
            }
    notes = [
        "Fuente: resultados no auditados de Grupo Aeroméxico 3T26, publicados el 19 de octubre de 2026. RASK usa el ingreso total: es el TRASM reportado por asiento-milla convertido a centavos USD por asiento-kilómetro con 1 milla = 1,609344 km. Incluye ingreso de pasajeros, carga, lealtad y otros; no es tarifa ni ingreso de pasajeros por sí solo.",
        "Las variaciones anuales de RASK, CASK, ASK, pasajeros y ocupación usan el comparativo del reporte 3T26. Las variaciones trimestrales y del margen unitario se calculan con la serie publicada. Los indicadores unitarios están redondeados: 17,2/15,4 − 1 da 11,7%; el emisor reporta crecimiento TRASM de 12,2%, reproducible a esa precisión con ingresos totales y ASM del reporte. La conversión milla-kilómetro no cambia el crecimiento porcentual.",
        "Para ocupación, el reporte 3T26 compara 88,3% con 88,2% de 3T25: +0,1 pp. La serie histórica conserva el 88,3% publicado previamente para 3T25; no se ha sustituido ese dato. El punto histórico y el comparativo del reporte tienen versiones distintas.",
        "CASK conserva el CASM reportado convertido por distancia: la variación anual reportada es 19,4%; el cociente de valores unitarios redondeados 15,1/12,7 − 1 da 18,9%. No se reconstruye a partir del gasto del estado de resultados. El margen unitario es RASK menos CASK, en centavos por asiento-kilómetro; no equivale al margen operativo porcentual. Estas cifras corresponden a julio–septiembre, no a nueve meses acumulados ni a saldos al cierre.",
    ]
    view["narrative"] = {"headline": "Bases de los indicadores Aeroméxico 3T26", "paragraphs": notes}
    doc["records"].append(record)
    doc["views"][PERIOD] = view
    block = doc["entities"]["AEROMEXICO"]
    entity_record = {
        **record,
        "load_factor": record["load_factor_reported"],
        "load_factor_basis": "reported",
        "rpk_km": nodes["rpm"] * MILE_KM,
        "cask_ex_fuel_cents_per_km": nodes["casm_ex"] / MILE_KM,
    }
    del entity_record["load_factor_reported"]
    block["records"].append(entity_record)
    block["views"][PERIOD] = copy.deepcopy(view)
    block["last_period"] = PERIOD
    block["quarter_count"] = len(block["records"])
    # Keep the global default at its existing common cut: peers/industry have no Q3.
    doc["metadata"].update(
        last_period=PERIOD,
        quarter_count=len(doc["records"]),
        coverage_label="23 trimestres de Aeroméxico · 1T21–3T26",
        data_as_of="19 oct 2026 · reporte financiero 3T26",
    )
    doc["metadata"]["source_view"] += " + resultados financieros Aeroméxico 3T26"
    doc["metadata"]["method_note"] += " " + " ".join(notes)
    doc["metadata"]["load_rask_interpretation"] += " Cálculo histórico conservado hasta 2T26."
    return doc

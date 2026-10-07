"""Deterministic calculations over one frozen, temporally eligible package."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
from html import escape
import json
import math
from pathlib import Path

from src.analysis_agent.evidence import canonical, digest, validate
from src.config import PATHS

OUTPUT = PATHS.root / "docs/referencias/etapa-15"
MILES_TO_KM = 1.609344
INPUTS = {
    "asm_total": "seat_miles", "trasm": "cents_USD_per_ASM", "casm": "cents_USD_per_ASM",
    "passengers": "count", "load_factor_total": "fraction", "total_revenue": "USD",
    "operating_expenses_total": "USD", "operating_income": "USD", "operating_margin": "fraction",
    "adjusted_ebitdar": "USD", "ebitdar_margin": "fraction", "net_income": "USD",
    "jet_fuel_expense": "USD", "fuel_liters": "liters", "casm_ex_fuel": "cents_USD_per_ASM",
}
SOURCE_UNITS = {"seat_miles": "miles", "cents_USD_per_ASM": "usd_cents", "USD": "usd",
                "count": "count", "fraction": "fraction", "liters": "liters"}


def previous(period, quarters):
    index = int(period[:4]) * 4 + int(period[-1]) - 1 - quarters
    return f"{index // 4}Q{index % 4 + 1}"


def formatted(value, unit):
    if value is None:
        return "No disponible"
    if unit == "fraction":
        return f"{value * 100:,.1f}%"
    decimals = 1 if unit in {"percent_change", "pp"} else (2 if "cents" in unit or unit == "USD_per_liter" else 3)
    suffix = "%" if unit == "percent_change" else unit
    return f"{value:,.{decimals}f} {suffix}"


def input_tolerance(metric):
    # Silver floats may drop trailing zeroes. Use the conservative precision that
    # survives serialization, never claim an extra decimal absent from metadata.
    exponent = Decimal(str(metric["value_raw"])).normalize().as_tuple().exponent
    decimals = max(0, -exponent)
    return .5 * 10 ** -decimals * abs(metric["scale_multiplier"])


def node(period, key, unit, value, bounds, inputs, formula, reason=None, basis=None):
    result = {"period_id": period, "key": key, "unit": unit, "value": value,
              "interval": bounds, "input_ids": inputs, "formula": formula,
              "status": "unavailable" if value is None else "available", "reason": reason,
              "basis": basis or {}, "formatted_value": formatted(value, unit)}
    result["calculation_id"] = "calc_" + digest(result)
    return result


def calculate(period, key, operation, inputs, unit, factor=1):
    ids = [x["calculation_id"] for x in inputs if x]
    if not inputs or any(x is None or x["value"] is None for x in inputs):
        return node(period, key, unit, None, None, ids, operation, "Missing or unavailable exact input")
    a = inputs[0]
    b = inputs[1] if len(inputs) > 1 else None
    if operation in {"subtract", "add"} and a["unit"] != b["unit"]:
        raise ValueError("Incompatible units")
    if operation == "scale":
        value = a["value"] * factor
        bounds = sorted(v * factor for v in a["interval"])
        formula = f"input × {factor}"
    elif operation in {"subtract", "add"}:
        sign = -1 if operation == "subtract" else 1
        value = a["value"] + sign * b["value"]
        bounds = [a["interval"][0] - b["interval"][1], a["interval"][1] - b["interval"][0]] if sign == -1 else [a["interval"][0] + b["interval"][0], a["interval"][1] + b["interval"][1]]
        formula = "input[0] " + ("−" if sign == -1 else "+") + " input[1]"
    elif operation == "divide":
        if b["value"] <= 0 or b["interval"][0] <= 0:
            return node(period, key, unit, None, None, ids, "division", "Denominator not strictly positive within published precision")
        value = a["value"] / b["value"] * factor
        ratios = [x / y * factor for x in a["interval"] for y in b["interval"]]
        bounds, formula = [min(ratios), max(ratios)], f"input[0] / input[1] × {factor}"
    elif operation == "multiply":
        value = a["value"] * b["value"] * factor
        products = [x * y * factor for x in a["interval"] for y in b["interval"]]
        bounds, formula = [min(products), max(products)], f"input[0] × input[1] × {factor}"
    else:
        raise ValueError("Unknown operation")
    return node(period, key, unit, value, bounds, ids, formula,
                basis={"input_bases": [x["basis"] for x in inputs]})


def comparison(current, base, period, key, mode):
    if current is None or base is None:
        return node(period, key, "percent_change" if mode == "percent" else "unknown", None, None,
                    [], mode, "Exact calendar comparable missing")
    compatible = current["unit"] == base["unit"] and current["basis"] == base["basis"]
    if not compatible:
        return node(period, key, current["unit"], None, None, [current["calculation_id"], base["calculation_id"]],
                    mode, "Incompatible unit, scope, currency or adjustment definition")
    if mode == "percent":
        if base["value"] is None or base["value"] <= 0:
            return node(period, key, "percent_change", None, None, [current["calculation_id"], base["calculation_id"]],
                        "(current / base − 1) × 100", "Zero or negative base; use absolute change")
        ratio = calculate(period, key, "divide", [current, base], "percent_change", 100)
        if ratio["value"] is None:
            return ratio
        return node(period, key, "percent_change", ratio["value"] - 100,
                    [x - 100 for x in ratio["interval"]], ratio["input_ids"], "(current / base − 1) × 100")
    delta = calculate(period, key, "subtract", [current, base], current["unit"])
    if current["unit"] == "fraction":
        return calculate(period, key, "scale", [delta], "pp", 100), delta
    return delta


def build(package):
    validate(package)
    if package["readiness"] == "blocked":
        raise ValueError("Blocked evidence cannot enter the quantitative engine")
    nodes, lookup, checks, bridges, identity_bridges = [], {}, [], [], []
    def put(n):
        lookup[(n["period_id"], n["key"])] = n
        nodes.append(n)
        return n
    for m in package["metrics"]:
        if m["metric_key"] not in INPUTS:
            continue
        unit = INPUTS[m["metric_key"]]
        if m["unit"] != SOURCE_UNITS[unit]:
            raise ValueError("Unexpected source unit")
        tol = input_tolerance(m)
        put(node(m["period_id"], m["metric_key"], unit, m["value"], [m["value"] - tol, m["value"] + tol],
                 [m["metric_id"]], "Reported normalized value; no new estimate",
                 basis={k: m[k] for k in ("scope", "currency", "condition")}))
    for q in sorted({m["period_id"] for m in package["metrics"]}):
        get = lambda k: lookup.get((q, k))
        for key, source, factor, unit in [("ask", "asm_total", MILES_TO_KM, "seat_km"),
                ("rask", "trasm", 1 / MILES_TO_KM, "cents_USD_per_ASK"),
                ("cask", "casm", 1 / MILES_TO_KM, "cents_USD_per_ASK"),
                ("cask_ex_fuel", "casm_ex_fuel", 1 / MILES_TO_KM, "cents_USD_per_ASK")]:
            put(calculate(q, key, "scale", [get(source)], unit, factor))
        for key, operation, keys, unit, factor in [
            ("spread", "subtract", ["rask", "cask"], "cents_USD_per_ASK", 1),
            ("fuel_cask", "divide", ["jet_fuel_expense", "ask"], "cents_USD_per_ASK", 100),
            ("other_cask", "subtract", ["cask", "fuel_cask"], "cents_USD_per_ASK", 1),
            ("effective_fuel_cost", "divide", ["jet_fuel_expense", "fuel_liters"], "USD_per_liter", 1),
            ("fuel_intensity", "divide", ["fuel_liters", "ask"], "liters_per_ASK", 1),
            ("revenue_per_ask", "divide", ["total_revenue", "ask"], "USD_per_ASK", 1),
            ("operating_margin_derived", "divide", ["operating_income", "total_revenue"], "fraction", 1),
            ("ebitdar_margin_derived", "divide", ["adjusted_ebitdar", "total_revenue"], "fraction", 1),
            ("operating_income_identity", "subtract", ["total_revenue", "operating_expenses_total"], "USD", 1),
            ("rask_revenue_identity", "divide", ["total_revenue", "ask"], "cents_USD_per_ASK", 100),
            ("cask_cost_identity", "divide", ["operating_expenses_total", "ask"], "cents_USD_per_ASK", 100),
        ]:
            put(calculate(q, key, operation, [get(k) for k in keys], unit, factor))
        for actual_key, identity in [("operating_income", "operating_income_identity"),
                ("operating_margin", "operating_margin_derived"), ("ebitdar_margin", "ebitdar_margin_derived"),
                ("rask", "rask_revenue_identity"), ("cask", "cask_cost_identity")]:
            a, b = get(actual_key), get(identity)
            usable = a and b and a["value"] is not None and b["value"] is not None
            passed = usable and max(a["interval"][0], b["interval"][0]) <= min(a["interval"][1], b["interval"][1])
            cross_definition = identity == "cask_cost_identity"
            checks.append({"period_id": q, "identity": identity, "status": "passed" if passed else ("not_reconciled" if usable and cross_definition else "failed" if usable else "unavailable"),
                           "input_ids": [n["calculation_id"] for n in (a, b) if n],
                           "difference": a["value"] - b["value"] if usable else None,
                           "reason": "Published CASM and financial expense scope are not proven equivalent; unexplained difference, no financial-margin attribution" if cross_definition and not passed else "Intervals from published rounding overlap" if passed else "Missing inputs or failed identity"})
    quarter = package["period_id"]
    compare_keys = list(INPUTS) + ["ask", "rask", "cask", "spread", "fuel_cask", "other_cask", "effective_fuel_cost", "fuel_intensity"]
    for label, lag in [("QoQ", 1), ("YoY", 4)]:
        base_q = previous(quarter, lag)
        for key in compare_keys:
            a, b = lookup.get((quarter, key)), lookup.get((base_q, key))
            for mode in (["absolute"] if key in {"spread", "fuel_cask", "other_cask"} or (a and a["unit"] == "fraction") else ["absolute", "percent"]):
                result = comparison(a, b, quarter, f"{key}_{label}_{mode}", mode)
                if isinstance(result, tuple):
                    final, intermediate = result
                    put(intermediate);put(final)
                else:
                    put(result)
        contributions = []
        for key, sign in [("rask", 1), ("fuel_cask", -1), ("other_cask", -1)]:
            delta = lookup[(quarter, f"{key}_{label}_absolute")]
            contributions.append(put(calculate(quarter, f"bridge_{key}_{label}", "scale", [delta], "cents_USD_per_ASK", sign)))
        total = put(calculate(quarter, f"bridge_partial_{label}", "add", contributions[:2], "cents_USD_per_ASK"))
        total = put(calculate(quarter, f"bridge_total_{label}", "add", [total, contributions[2]], "cents_USD_per_ASK"))
        spread = lookup[(quarter, f"spread_{label}_absolute")]
        error = None if total["value"] is None or spread["value"] is None else total["value"] - spread["value"]
        bridges.append({"comparison": label, "base_period": base_q, "contribution_ids": [n["calculation_id"] for n in contributions],
                        "total_id": total["calculation_id"], "spread_change_id": spread["calculation_id"],
                        "error": error, "status": "unavailable" if error is None else ("passed" if abs(error) < 1e-10 else "failed"),
                        "interpretation": "Accounting decomposition only. Other cost is an unexplained residual, not structural efficiency; RASK is not airfare."})
        for name, volume, rate, amount in [("revenue", "ask", "revenue_per_ask", "total_revenue"),
                                           ("fuel_expense", "fuel_liters", "effective_fuel_cost", "jet_fuel_expense")]:
            changes, averages = [], []
            for key in (volume, rate):
                current, old = lookup.get((quarter, key)), lookup.get((base_q, key))
                unit = current["unit"] if current else "unknown"
                changes.append(put(calculate(quarter, f"{name}_{key}_change_{label}", "subtract", [current, old], unit)))
                summed = put(calculate(quarter, f"{name}_{key}_sum_{label}", "add", [current, old], unit))
                averages.append(put(calculate(quarter, f"{name}_{key}_average_{label}", "scale", [summed], unit, .5)))
            left = put(calculate(quarter, f"{name}_volume_contribution_{label}", "multiply", [changes[0], averages[1]], "USD"))
            right = put(calculate(quarter, f"{name}_rate_contribution_{label}", "multiply", [changes[1], averages[0]], "USD"))
            total = put(calculate(quarter, f"{name}_bridge_total_{label}", "add", [left, right], "USD"))
            actual = lookup[(quarter, f"{amount}_{label}_absolute")]
            error = None if total["value"] is None or actual["value"] is None else total["value"] - actual["value"]
            identity_bridges.append({"name": name, "comparison": label, "base_period": base_q,
                "contribution_ids": [left["calculation_id"], right["calculation_id"]], "total_id": total["calculation_id"],
                "actual_change_id": actual["calculation_id"], "error": error,
                "status": "unavailable" if error is None else "passed" if abs(error) < 1e-5 else "failed",
                "interpretation": "Symmetric accounting allocation: delta volume × mean rate + delta rate × mean volume. Rate is realized revenue per ASK or effective fuel cost, not market price or causality."})
    failures = [c for c in checks + bridges + identity_bridges if c["status"] == "failed"]
    result = {"schema_version": "quantitative_v1", "period_id": quarter, "package_id": package["package_id"],
              "evidence_fingerprint": package["evidence_fingerprint"], "nodes": nodes, "checks": checks,
              "bridges": bridges, "status": "failed" if failures else "validated",
              "identity_bridges": identity_bridges,
              "analysis_constraints": {"allow_spread_to_financial_margin_attribution": False,
                  "unreconciled_cost_periods": [c["period_id"] for c in checks if c["status"] == "not_reconciled"]},
              "precision_policy": "Conservative half-step of source float precision × published scale; interval arithmetic. Missing trailing zeroes widen tolerance.",
              "limits": ["Effective fuel cost is not market fuel price", "No isolated FX, hedge or route-mix contributions", "Spread differs from operating and EBITDAR margins", "Unreconciled cost/ASK comparisons remain explicit; linking their spread to financial margin is not supported"],
              "code_fingerprint": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    result["calculation_fingerprint"] = digest(result)
    return result


def run(path):
    package = json.loads(Path(path).read_bytes())
    result = build(package)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "calculations.json").write_bytes(canonical(result))
    if result["status"] != "validated":
        raise ValueError("Reconciliation failed; inspect calculations.json")
    root = PATHS.root / "analysis_runs/quantitative"
    root.mkdir(parents=True, exist_ok=True)
    target = root / (result["calculation_fingerprint"] + ".json")
    data = canonical(result)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("Immutable calculation differs")
    else:
        with target.open("xb") as stream:
            stream.write(data)
    print(json.dumps({"status": result["status"], "nodes": len(result["nodes"]), "checks": len(result["checks"]), "bridges": result["bridges"]}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__);p.add_argument("package")
    run(p.parse_args().package)

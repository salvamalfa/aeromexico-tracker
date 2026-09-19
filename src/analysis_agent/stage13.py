"""Reproducible financial extraction review, conversions and reconciliation."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl

from src.config import PATHS
from src.parse.aeromexico_ir_financial import OUTPUT as SILVER, TARGETS, run as extract

OUTPUT = PATHS.root / "docs/referencias/etapa-13"
LABELS = {
    "total_revenue": "Ingresos totales", "adjusted_ebitdar": "UAFIDAR ajustada",
    "ebitdar_margin": "Margen UAFIDAR ajustada", "ebitdar_reported": "UAFIDAR reportada",
    "ebitdar_reported_margin": "Margen UAFIDAR reportada", "operating_income": "Resultado operativo contable",
    "operating_margin": "Margen operativo reportado", "net_income": "Resultado neto contable",
    "operating_expenses_total": "Gastos totales, incl. rentas y depreciación",
    "jet_fuel_expense": "Combustible", "fuel_liters": "Consumo de combustible",
    "cask_ex_fuel": "CASK sin combustible", "wages_salaries_benefits": "Fuerza de trabajo",
    "maintenance_expense": "Mantenimiento", "depreciation_amortization": "Depreciación y amortización",
    "aircraft_leasing_expense": "Renta de equipo de vuelo",
    "rent_depreciation_amortization_combined": "Rentas, depreciación y amortización (agrupadas)",
    "ebitdar_ex_restructuring": "UAFIDAR sin efectos de reestructura",
    "ebitdar_margin_ex_restructuring": "Margen UAFIDAR sin reestructura",
    "operating_margin_ex_restructuring": "Margen operativo sin reestructura",
    "cask_ex_fuel_ex_restructuring": "CASK sin combustible ni efectos de reestructura",
    "operating_margin_ex_plm": "Margen operativo excluyendo PLM PPA",
    "operating_income_ex_plm": "Resultado operativo excluyendo PLM PPA",
    "reported_fx_rate": "Tipo de cambio publicado (MXN por USD)",
    "income_before_tax": "Resultado antes de impuestos", "income_tax": "Impuesto a la utilidad",
}


def normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rates = {(r["period_id"], r["source_hash"]): r for r in rows if r["metric_key"] == "reported_fx_rate"}
    out = []
    for row in rows:
        r = dict(row)
        value, unit = r["value_normalized"], r["unit_normalized"]
        r.update(value_usd=None, fx_rate_used=None, fx_record_id=None, normalization_formula="value_raw × scale_multiplier",
                 conversion_type="scale_only", normalization_inputs=[r["record_id"]])
        if unit == "mxn":
            rate = rates[(r["period_id"], r["source_hash"])]
            if rate["value_raw"] <= 0:
                raise ValueError("FX denominator must be positive")
            r.update(value_usd=value / rate["value_raw"], fx_rate_used=rate["value_raw"],
                     fx_record_id=rate["record_id"], normalization_formula="value_raw × 1,000,000 / reported_fx_rate",
                     conversion_type=rate["definition_type"], normalization_inputs=[r["record_id"], rate["record_id"]])
        elif unit == "usd":
            r["value_usd"] = value
        elif unit == "usd_per_km":
            r.update(normalized_review_value=value * 100, normalized_review_unit="USD cents per ASK-km",
                     normalization_formula="value_raw × 100")
        out.append(r)
    return out


def tolerance(row: dict[str, Any], *, usd: bool = False) -> float:
    half_step = .5 * 10 ** -row["published_decimals"] * row["scale_multiplier"]
    if usd and row["unit_normalized"] == "mxn":
        rate = row["fx_rate_used"]
        half_step /= rate
        # FX rounded to 2 decimals (average) or 4 (convenience close).
        rate_step = .005 if row["conversion_type"] == "reported_average" else .00005
        half_step += abs(row["value_normalized"]) * rate_step / (rate * (rate - rate_step))
    return half_step


def reconcile(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    groups = sorted({(r["period_id"], r["source_hash"]) for r in rows})
    for q, digest in groups:
        d = {r["metric_key"]: r for r in rows if (r["period_id"], r["source_hash"]) == (q, digest)}
        def check(name: str, difference: float, allowed: float, inputs: list[str], note: str = "") -> None:
            checks.append({"period_id": q, "source_hash": digest, "check": name,
                           "difference": difference, "tolerance": allowed,
                           "status": "passed" if abs(difference) <= allowed + 1e-8 else "unexplained",
                           "inputs": [d[k]["record_id"] for k in inputs], "note": note})
        keys = ["total_revenue", "operating_expenses_total", "operating_income"]
        check("Ingresos − gastos = resultado operativo", d[keys[0]]["value_normalized"] - d[keys[1]]["value_normalized"] - d[keys[2]]["value_normalized"],
              sum(tolerance(d[k]) for k in keys), keys, "En moneda original; cada cifra admite media unidad de su precisión publicada.")
        keys = ["income_before_tax", "income_tax", "net_income"]
        check("Resultado antes de impuestos − impuesto = resultado neto", d[keys[0]]["value_normalized"] - d[keys[1]]["value_normalized"] - d[keys[2]]["value_normalized"],
              sum(tolerance(d[k]) for k in keys), keys, "En moneda original; los beneficios fiscales conservan su signo negativo.")
        for numerator, margin in (("operating_income", "operating_margin"), ("adjusted_ebitdar", "ebitdar_margin"),
                                  ("ebitdar_reported", "ebitdar_reported_margin"), ("operating_income_ex_plm", "operating_margin_ex_plm")):
            if numerator not in d or margin not in d:
                continue
            revenue, profit, ratio = d["total_revenue"], d[numerator], d[margin]
            denom, num = revenue["value_usd"], profit["value_usd"]
            if denom is None or denom <= 0 or num is None:
                raise ValueError(f"{q}: unsupported margin denominator")
            allowed = tolerance(ratio) + (tolerance(profit, usd=True) + abs(num / denom) * tolerance(revenue, usd=True)) / (denom - tolerance(revenue, usd=True))
            check(margin + " = resultado / ingresos", ratio["value_normalized"] - num / denom, allowed,
                  [margin, numerator, "total_revenue"], "Fracciones; tolerancia por redondeo de numerador, denominador y margen.")
        for key, row in d.items():
            if row["reported_usd_millions"] is not None:
                check(key + ": conversión de conveniencia vs columna USD", row["value_usd"] - row["reported_usd_millions"] * 1e6,
                      tolerance(row, usd=True) + 500_000, [key, "reported_fx_rate"], "La columna USD del apéndice está redondeada a millones enteros.")
    return checks


def build() -> dict[str, Any]:
    rows = normalize(pl.read_parquet(SILVER).to_dicts())
    gaps = json.loads((PATHS.silver / "aeromexico_ir_financial_gaps.json").read_text(encoding="utf-8"))
    baseline = json.loads((OUTPUT / "baseline.json").read_text(encoding="utf-8"))
    checks = reconcile(rows)
    coverage = []
    for q in sorted({r["period_id"] for r in baseline if "2021Q1" <= r["period_id"] <= "2026Q2"}):
        found = {r["metric_key"] for r in rows if r["period_id"] == q}
        before = {r["metric_key"] for r in baseline if r["period_id"] == q and r["value"] is not None}
        coverage.append({"period_id": q, "before": len(set(TARGETS) & before),
                         "extracted_targets": len(set(TARGETS) & found),
                         "other_definitions": len(found - set(TARGETS) - {"reported_fx_rate"}),
                         "documented_gaps": sum(g["period_id"] == q for g in gaps),
                         "scope": "Extraído de su propio reporte" if found else "Cobertura vigente; fuera del alcance de extracción de Etapa 13"})
    comparison = []
    sec_rows = [r for name in ("sec_financials", "sec_operating_metrics")
                for r in pl.read_parquet(PATHS.silver / (name + ".parquet")).to_dicts()]
    documented = json.loads((PATHS.root / "config/stage13_source_differences.json").read_text(encoding="utf-8"))
    for r in rows:
        if not "2024Q3" <= r["period_id"] <= "2025Q2":
            continue
        prior = next((p for p in baseline if p["period_id"] == r["period_id"] and p["metric_key"] == r["metric_key"]), None)
        if prior is None:
            continue
        value = r["value_usd"] if r["value_usd"] is not None else r["value_normalized"]
        diff = value - prior["value"]
        allowance = tolerance(r) + 1e-8
        prior_metric = "casm_ex_fuel" if r["metric_key"] == "cask_ex_fuel" else r["metric_key"]
        prior_rows = [s for s in sec_rows if s["period_id"] == r["period_id"] and s["metric_key"] == prior_metric
                      and (s["source_file"] == prior["source_file"] or prior_metric == "casm_ex_fuel")]
        prior_row = next((s for s in prior_rows if abs(s["value_normalized"] / (1.609344 if prior_metric == "casm_ex_fuel" else 1) - prior["value"]) < 1e-6), None)
        prior_hash, prior_excerpt = None, None
        if prior_row:
            raw = format(prior_row["value_raw"], "g")
            decimals = len(raw.split(".")[-1]) if "." in raw else 0
            allowance += .5 * 10 ** -decimals * prior_row["scale_multiplier"] / (1.609344 if prior_metric == "casm_ex_fuel" else 1)
            prior_hash, prior_excerpt = prior_row["source_hash"], prior_row["metric_label_raw"]
        status = "rounding_compatible" if abs(diff) <= allowance else "unexplained"
        explanation = "Intervalos de redondeo de ambas fuentes compatibles; se conserva la precisión del PDF."
        if prior_metric == "casm_ex_fuel":
            explanation = "CASK publicado en centavos/ASK frente a CASM publicado y convertido /1.609344. Se considera el redondeo independiente de ambas unidades."
        for note in documented:
            if (note["period_id"], note["metric_key"], note["ir_source_hash"], note["current_source_hash"], note["ir_value"], note["current_value"]) == (r["period_id"], r["metric_key"], r["source_hash"], prior_hash, value, prior["value"]):
                current_path = PATHS.bronze / note["current_source"]
                if hashlib.sha256(current_path.read_bytes()).hexdigest() != prior_hash:
                    raise ValueError("Documented comparison source hash changed")
                status, explanation = "documented_source_difference", note["explanation"]
                prior_excerpt = " | ".join(note["current_excerpt"])
        comparison.append({"period_id": r["period_id"], "metric_key": r["metric_key"], "ir_value": value,
                           "current_value": prior["value"], "difference": diff, "tolerance": allowance,
                           "status": status,
                           "record_id": r["record_id"], "current_source": prior["source_file"],
                           "current_source_hash": prior_hash, "current_excerpt": prior_excerpt,
                           "explanation": explanation})
    failures = [r for r in checks + comparison if r["status"] == "unexplained"]
    return {"schema_version": 1, "rows": rows, "gaps": gaps, "coverage": coverage,
            "checks": checks, "comparison": comparison, "unexplained": failures}


def run() -> dict[str, Any]:
    extract()
    result = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "financial_review.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    for name in ("coverage", "gaps", "checks", "comparison"):
        dataset = result[name]
        with (OUTPUT / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dataset[0]))
            writer.writeheader()
            writer.writerows(dataset)
    if result["unexplained"]:
        raise ValueError(f"Unexplained differences: {result['unexplained']}")
    return {"financial_records": len(result["rows"]), "documented_gaps": len(result["gaps"]),
            "checks": len(result["checks"]), "source_comparisons": len(result["comparison"]), "unexplained": 0}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))

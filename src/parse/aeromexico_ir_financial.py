"""Source-faithful quarterly financial extraction; no historical eligibility claims.

Rotated appendices require pypdf's plain mode, while summary tables require layout
mode. Silver contains published units only. Review conversions live in stage13.
"""
from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
from typing import Any

import polars as pl
from pypdf import PdfReader

from src.config import PATHS
from src.parse.aeromexico_ir import _verified_bytes, _row
from src.parse.sec.common import write_parquet_atomic
from src.transform.stage9_lineage import make_record_id, _make_artifact_id

PARSER_VERSION = "aeromexico_ir_financial_v1.0.0"
OUTPUT = PATHS.silver / "aeromexico_ir_financial_history.parquet"
LAST_PERIOD = "2025Q2"
NUMBER = r"\(?-?\d[\d,]*(?:\.\d+)?%?\)?"
STATEMENT = {
    "total_revenue": r"Total (?:de )?Ingresos",
    "operating_expenses_total": r"Total gastos",
    "operating_income": r"Utilidad de Operaci.n",
    "net_income": r"Utilidad Neta",
    "income_before_tax": r"Utilidad (?:\(P.rdida\) )?antes de Impuestos(?: a la Utilidad)?",
    "income_tax": r"Impuesto a la Utilidad",
    "jet_fuel_expense": r"Combustible",
    "wages_salaries_benefits": r"Fuerza de Trabajo",
    "maintenance_expense": r"Mantenimiento",
    "depreciation_amortization": r"Depreciaci.n y Amortizaci.n",
    "aircraft_leasing_expense": r"Renta de equipo de vuelo",
    "rent_depreciation_amortization_combined": r"Rentas, Depreciaci.n y Amortizaci.n",
}
TARGETS = ("total_revenue", "adjusted_ebitdar", "ebitdar_margin", "operating_income",
           "operating_margin", "net_income", "operating_expenses_total", "jet_fuel_expense",
           "fuel_liters", "cask_ex_fuel", "wages_salaries_benefits", "maintenance_expense",
           "depreciation_amortization", "aircraft_leasing_expense")


def records() -> list[dict[str, Any]]:
    # Preserve every registered version; version selection belongs to Stage 14.
    result = []
    for line in (PATHS.bronze / "_manifest.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("source_system") != "aeromexico_ir":
            continue
        q = r["logical_key"].split("|")[2]
        if "2021Q1" <= q <= LAST_PERIOD:
            result.append(r | {"period_id": q})
    if len({r["period_id"] for r in result}) != 18:
        raise ValueError("Expected all 18 quarterly IR reports, 2021Q1–2025Q2")
    return sorted(result, key=lambda r: (r["period_id"], r.get("logical_version", 1)))


def number(token: str) -> float:
    value = float(token.replace(",", "").replace("%", "").strip("()"))
    return -value if token.startswith("(") else value


def clean(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\u00a0", " ")


def first_row(pages: list[str], pattern: str) -> tuple[int, str, str]:
    for page, text in enumerate(pages, 1):
        m = re.search(r"^\s*(?:" + pattern + r")\s+(?P<value>" + NUMBER + r")(?=\s|$)", text, re.I | re.M)
        if m:
            return page, m.group(0).strip(), m["value"]
    raise ValueError(f"Missing quarterly row: {pattern}")


def parse_report(record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(_verified_bytes(record)))
    plain = [clean(p.extract_text() or "") for p in reader.pages]
    layout = [clean(p.extract_text(extraction_mode="layout") or "") for p in reader.pages]
    q = record["period_id"]
    old = q <= "2022Q3"
    dual = q in ("2022Q4", "2023Q1")
    currency = "MXN" if old or dual else "USD"
    basis = "mxn_reported" if old else ("usd_convenience_translation" if dual else "usd_functional_presentation")
    all_text = " ".join(" ".join(plain).split())
    currency_proof = "millones de pesos" if old else ("conveniencia" if dual else "moneda funcional")
    if currency_proof not in all_text:
        raise ValueError(f"{q}: reporting currency basis not supported by document")
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    # Restrict to a quarterly income statement, not financial-position/cashflow or YTD.
    candidates = [(i, p) for i, p in enumerate(plain, 1)
                  if re.search(r"^\s*Combustible\s+" + NUMBER, p, re.M | re.I)
                  and re.search(r"^\s*Utilidad Neta\s+" + NUMBER, p, re.M | re.I)]
    if not candidates:
        raise ValueError(f"{q}: no income statement found")
    page_no, statement = candidates[0]
    if not re.search(r"Tres\s+Meses", statement, re.I):
        raise ValueError(f"{q}: quarterly column header not verified on page {page_no}")
    if not re.search(q[:4], statement):
        raise ValueError(f"{q}: missing current year header")

    def add(key: str, page: int, label: str, token: str, unit: str,
            definition: str = "reported", usd_token: str | None = None) -> None:
        scale = .01 if unit == "percent" else (1000 if unit == "thousand liters" else (1e6 if "millions" in unit else 1))
        normalized = {"MXN millions": "mxn", "USD millions": "usd", "percent": "fraction",
                      "thousand liters": "liters", "USD cents per ASK-km": "usd_cents_per_km",
                      "MXN per USD": "mxn_per_usd"}[unit]
        row = _row(record, metric_key=key, label=label, value_raw=number(token), unit_raw=unit,
                   scale_multiplier=scale, unit_normalized=normalized, extraction_method="pdf_quarterly_table")
        row.update(parser_version=PARSER_VERSION, source_page=page,
                   source_locator=f"page={page}; row={label}; column={q}",
                   source_excerpt=label, definition_type=definition, reporting_basis=basis,
                   published_token=token, published_decimals=len(token.strip("()%").split(".")[1]) if "." in token else 0,
                   reported_usd_millions=number(usd_token) if usd_token else None,
                   original_currency=unit[:3] if "millions" in unit else None,
                   source_url=record["source_url"], source_version=int(record.get("logical_version", 1)),
                   temporal_status="not_certified")
        row["artifact_id"] = _make_artifact_id(record["source_file"], record["sha256"])
        row["record_id"] = make_record_id("aeromexico_ir_financial_history", {
            "source_hash": record["sha256"], "period_id": q, "metric_key": key})
        rows.append(row)

    for key, pat in STATEMENT.items():
        if key == "operating_expenses_total" and not old:
            pat = r"Total gastos de operaci.n"
        try:
            _, label, token = first_row([statement], pat)
        except ValueError:
            if key in ("depreciation_amortization", "aircraft_leasing_expense") and old:
                missing.append({"period_id": q, "metric_key": key, "status": "not_separately_reported",
                                "reason": "El estado trimestral publica rentas, depreciación y amortización agrupadas; no se reparte el total.",
                                "source_page": page_no, "source_hash": record["sha256"]})
                continue
            if key == "rent_depreciation_amortization_combined" and not old:
                continue
            raise
        usd = None
        if dual:
            # MXN current, MXN prior, variation, USD current, USD prior, variation.
            full = next(line for line in statement.splitlines() if line.strip().startswith(label))
            tail = re.sub(r"^\s*(?:" + pat + r")\s+", "", full, flags=re.I)
            cells = tail.split()
            if len(cells) != 6:
                raise ValueError(f"{q}: unexpected dual-currency columns: {full}")
            usd = cells[3]
        add(key, page_no, label, token, currency + " millions", usd_token=usd)

    # Rejoin wrapped labels without moving numbers across columns.
    for i, text in enumerate(layout):
        lines = text.splitlines()
        for j in range(len(lines) - 1):
            continuation = lines[j + 1].strip()
            if continuation in ("(USD)****", "(pesos)****", "USD)", "combustible (USD)****", "(centavos de USD)") and "Costo total" in lines[j]:
                m = re.search(r"\s{2,}(?=" + NUMBER + r")", lines[j])
                if m:
                    lines[j] = lines[j][:m.start()] + " " + continuation + lines[j][m.start():]
                    lines[j + 1] = ""
        layout[i] = "\n".join(lines)
    # Summary tables supply non-IFRS definitions and reported ratios, never YTD.
    for key, pat, unit in (
        ("ebitdar", r"UAFIDAR[^\n]*?", ("MXN" if old else "USD") + " millions"),
        ("ebitdar_ratio", r"Margen UAFIDAR[^\n]*?", "percent"),
        ("operating_margin", r"Margen de operaci.n[^\n]*?", "percent"),
        ("fuel_liters", r"Litros de combustible(?: \(miles\))?\*?", "thousand liters"),
        ("cask_ex_fuel", r"Costo total\s*(?:(?:excl\.?|excluyendo) combustible\s*/\s*ASK|/\s*ASK excluyendo combustible)\s*\((?:centavos de USD|USD)\)\*{0,4}", "USD cents per ASK-km"),
    ):
        if key == "ebitdar":
            try:
                page, label, token = first_row(layout, r"UAFIDAR ajustad[oa]\*?(?:\s*\(Ex\. PLM PPA\))?(?:\s*\(3\))?")
            except ValueError:
                page, label, token = first_row(layout, pat)
        else:
            page, label, token = first_row(layout, pat)
        if q in ("2021Q4", "2022Q1") and key in ("ebitdar", "ebitdar_ratio", "operating_margin"):
            if "reestructura" not in layout[page - 1]:
                raise ValueError(f"{q}: missing restructuring column explanation")
            adjusted_key = {"ebitdar": "ebitdar_ex_restructuring", "ebitdar_ratio": "ebitdar_margin_ex_restructuring",
                            "operating_margin": "operating_margin_ex_restructuring"}[key]
            add(adjusted_key, page, label, token, unit, "company_adjusted_ex_restructuring")
            # The published current unadjusted column is second in 4Q21, third in 1Q22.
            line = next(line for line in layout[page - 1].splitlines() if line.strip().startswith(label))
            tail = line.strip()[len(label) - len(token):]
            tokens = re.findall(NUMBER, tail)
            token = tokens[1 if q == "2021Q4" else 2]
            label = line.strip() + " [columna reportada sin ajuste]"
        definition = "reported_non_ifrs" if key.startswith("ebitdar") else "reported"
        if key in ("ebitdar", "ebitdar_ratio"):
            adjusted = "ajustad" in label.lower()
            if key == "ebitdar_ratio" and any(r["metric_key"] == "adjusted_ebitdar" for r in rows):
                adjusted = True
            key = ("adjusted_ebitdar" if adjusted else "ebitdar_reported") if key == "ebitdar" else ("ebitdar_margin" if adjusted else "ebitdar_reported_margin")
            definition = "company_adjusted_ex_plm" if "plm" in label.lower() else ("company_adjusted" if adjusted else "reported_non_ifrs")
        elif key == "operating_margin" and "plm" in label.lower():
            key, definition = "operating_margin_ex_plm", "company_adjusted_ex_plm"
        if key == "cask_ex_fuel" and q in ("2021Q4", "2022Q1"):
            key, definition = "cask_ex_fuel_ex_restructuring", "company_adjusted_ex_restructuring"
        if key.startswith("cask_ex_fuel") and "centavos" not in label:
            # Preserve USD/ASK as originally published; conversion is not a Silver value.
            add(key, page, label, token, unit, definition)
            rows[-1].update(unit_raw="USD per ASK-km", unit_normalized="usd_per_km", value_normalized=number(token))
        else:
            add(key, page, label, token, unit, definition)

    if any(r["metric_key"] == "operating_margin_ex_plm" for r in rows):
        page, label, token = first_row(layout, r"Utilidad (?:ajustada )?de operaci.n(?: \(perdida\))? \(Ex\. PLM PPA\)")
        add("operating_income_ex_plm", page, label, token, "USD millions", "company_adjusted_ex_plm")
    if q == "2022Q4":
        for page, text in enumerate(layout, 1):
            m = re.search(r"La UAFIDAR ascendi. a \$(?P<value>[\d,.]+) millones en el 4T22", text)
            if m:
                add("ebitdar_reported", page, m.group(0), m["value"], "USD millions", "reported_non_ifrs")
                break
        else:
            raise ValueError("4Q22: missing unadjusted EBITDAR explanation")

    if old or dual:
        pattern = (r"a un promedio de\s*\$\s*(?P<value>\d+\.\d+)" if old else
                   r"a una tasa de\s*(?P<value>\d+\.\d+) MXN por USD")
        for page, text in enumerate(layout, 1):
            m = re.search(pattern, text, re.I)
            if m:
                add("reported_fx_rate", page, m.group(0), m["value"], "MXN per USD",
                    "reported_average" if old else "company_convenience_close")
                break
        else:
            raise ValueError(f"{q}: source FX rate not found")
    # Preserve the source's adjustment and accounting notes as localizable context.
    for row in rows:
        p = row["source_page"] - 1
        row["source_page_text"] = plain[p]
    for key in TARGETS:
        if key not in {r["metric_key"] for r in rows} and key not in {m["metric_key"] for m in missing}:
            missing.append({"period_id": q, "metric_key": key, "status": "different_definition_reported",
                            "reason": "Se conserva la variante reportada con su propia definición; no se etiqueta como la métrica objetivo.",
                            "source_hash": record["sha256"], "source_page": next(r["source_page"] for r in rows if r["metric_key"].startswith("ebitdar") or r["metric_key"] == "adjusted_ebitdar")})
    return rows, missing


def run() -> dict[str, Any]:
    rows, missing = [], []
    for record in records():
        extracted, gaps = parse_report(record)
        rows.extend(extracted)
        missing.extend(gaps)
    frame = pl.DataFrame(rows, infer_schema_length=None,
                         schema_overrides={"reported_usd_millions": pl.Float64, "original_currency": pl.String})
    if frame.select(pl.struct("source_hash", "period_id", "metric_key").is_duplicated().any()).item():
        raise ValueError("Duplicate financial evidence grain")
    write_parquet_atomic(frame.sort(["period_id", "source_version", "metric_key"]), OUTPUT)
    output = PATHS.silver / "aeromexico_ir_financial_gaps.json"
    output.write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": len(rows), "gaps": len(missing), "periods": 18, "output": str(OUTPUT)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))

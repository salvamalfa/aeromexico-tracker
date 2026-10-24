"""Aeromexico 3Q26: replay issuer HTML, preserving native units and periods.

This deliberately separate edition does not refresh Gold, monthly traffic or
historical SEC evidence. The ordinary analyst and lifecycle still own drafting,
independent audit, exact-version human approval and consumption.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.config import PATHS
from .evidence import canonical, compact, digest

SCHEMA = "quarterly_release_v1"
PERIOD = "2026Q3"
RELEASE = "https://www.globenewswire.com/fr/news-release/2026/10/19/3383928/0/en/aerom%C3%A9xico-reports-unaudited-third-quarter-2026-results.html"
PRESENTATION = "https://ir.aeromexico.com/static-files/1338d53e-2740-4b3a-8d44-cac3ac17d28f"
INDEX = "https://ir.aeromexico.com/financial-information/quarterly-results"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(text):
    text = text.replace(",", "").replace(" ", "")
    matches = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(matches) != 1:
        raise ValueError("Expected exactly one numeric table cell")
    value = float(matches[0])
    return -value if "(" in text else value


def extract(raw, pdf):
    """Replay selected quarterly columns and exact narrative amounts."""
    soup = BeautifulSoup(raw, "lxml")
    if soup.find("time", datetime="2026-10-19T21:06:37Z") is None:
        raise ValueError("Issuer release publication timestamp changed")
    text = compact(soup.get_text(" ", strip=True))
    if "Grupo Aeroméxico" not in text or "three months ended September 30, 2026" not in text:
        raise ValueError("Wrong issuer or quarter")
    excerpts, metrics = [], []

    def excerpt(locator, text, source="release"):
        item = dict(
            artifact_id=source, locator=locator, text=text, period_id=PERIOD, source_content_is_untrusted=True
        )
        item["excerpt_id"] = "exc_" + digest(item)
        if item not in excerpts:
            excerpts.append(item)
        return item["excerpt_id"]

    def metric(key, value, unit, eid, period=PERIOD, definition="quarter"):
        item = dict(
            period_id=period,
            metric_key=key,
            value=value,
            unit=unit,
            excerpt_id=eid,
            artifact_id=next(e["artifact_id"] for e in excerpts if e["excerpt_id"] == eid),
            definition=definition,
            scope="Grupo Aeroméxico consolidated",
            currency="USD" if unit in {"USD", "cents_USD_per_ASM", "cents_USD_per_RPM"} else None,
        )
        item["metric_id"] = "metric_" + digest(item)
        metrics.append(item)

    tables = soup.find_all("table")

    def row(table, label):
        rows = [
            [compact(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"], recursive=False)]
            for tr in tables[table].find_all("tr")
        ]
        matches = [(i, r) for i, r in enumerate(rows) if r and r[0] == label]
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous table row: {label}")
        i, values = matches[0]
        eid = excerpt(f"table[{table + 1}]/tr[{i + 1}]", " | ".join(values))
        return values, eid

    # Both the duration and the column order are verified before reading cells.
    for table in (1, 2, 5, 9):
        heading = compact(tables[table].get_text(" ", strip=True))
        if "Three Months Ended September 30 Nine Months Ended September 30" not in heading:
            raise ValueError("Quarter/YTD column order changed")
        if "2026 2025 Var." not in heading:
            raise ValueError("Year/comparison column order changed")
    specs = [
        (1, "Adjusted EBITDAR (1) (USD millions)", "ebitdar_rounded", "USD", 1e6),
        (1, "Total operating income (loss) (USD millions)", "operating_income_rounded", "USD", 1e6),
        (9, "Net income (loss)", "net_income_rounded", "USD", 1e6),
        (1, "Total revenue (USD millions)", "revenue", "USD", 1e6),
        (1, "Passengers ('000)", "passengers", "count", 1e3),
        (1, "Total ASMs (millions)", "asm", "seat_miles", 1e6),
        (1, "Total revenue / ASM (USD cents)", "trasm", "cents_USD_per_ASM", 1),
        (1, "Total cost / ASM (USD cents)", "casm", "cents_USD_per_ASM", 1),
        (1, "Total cost excluding fuel / ASM (USD cents)", "casm_ex", "cents_USD_per_ASM", 1),
        (1, "Operating income margin (% of revenue)", "operating_margin", "fraction", 0.01),
        (1, "Adjusted EBITDAR margin (1) (% of revenue)", "ebitdar_margin", "fraction", 0.01),
        (2, "Domestic", "domestic_revenue", "USD", 1e6),
        (2, "International", "international_revenue", "USD", 1e6),
        (5, "Total operating expenses", "expenses", "USD", 1e6),
        (5, "Jet-fuel", "fuel", "USD", 1e6),
        (9, "Total RPMs (millions)", "rpm", "passenger_miles", 1e6),
        (9, "Load factor on scheduled flights (%)", "load", "fraction", 0.01),
        (9, "Yield (USD cents) (2)", "yield", "cents_USD_per_RPM", 1),
        (9, "Total liters of fuel ('000)", "fuel_liters", "liters", 1e3),
    ]
    for table, label, key, unit, factor in specs:
        values, eid = row(table, label)
        for column, period in ((1, PERIOD), (2, "2025Q3")):
            metric(key, number(values[column]) * factor, unit, eid, period)
        # Reported percentages retain issuer precision; do not recompute from rounded columns.
        if "%" in values[3] and "p.p." not in values[3]:
            metric(key + "_yoy", number(values[3]), "percent_change", eid, definition="quarter_yoy_change")

    paragraphs = [compact(p.get_text(" ", strip=True)) for p in soup.find_all("p")]

    def paragraph(needle):
        found = [(i, p) for i, p in enumerate(paragraphs) if needle in p]
        if len(found) != 1:
            raise ValueError(f"Missing or ambiguous issuer paragraph: {needle}")
        i, value = found[0]
        return value, excerpt(f"p[{i + 1}]", value)

    for key, needle, pattern, definition in [
        ("ebitdar", "amounted to $389.2 million", r"amounted to \$([\d.]+) million", "quarter"),
        ("operating_income", "Operating income for the third quarter", r"was \$([\d.]+) million", "quarter"),
        ("net_income", "Net income in 3Q26", r"\$([\d.]+) million", "quarter"),
        (
            "breakage",
            "updated its loyalty program breakage",
            r"recognition of \$([\d.]+) million",
            "quarter_non_cash_estimate",
        ),
        (
            "cash",
            "reported cash and cash equivalents of",
            r"equivalents of \$([\d.]+) million",
            "instant_2026-09-30",
        ),
        (
            "cashflow_ytd",
            "generated $541.7 million",
            r"generated \$([\d.]+) million",
            "YTD_2026-01-01_2026-09-30",
        ),
        (
            "fuel_delta",
            "Fuel expense increased by approximately",
            r"approximately \$([\d.]+) million year-over-year",
            "quarter_yoy_change",
        ),
    ]:
        value, eid = paragraph(needle)
        match = re.search(pattern, value)
        if not match:
            raise ValueError("Narrative extraction changed")
        metric(
            key,
            float(match[1]) * 1e6,
            "USD",
            eid,
            period="2026YTD9" if key == "cashflow_ytd" else PERIOD,
            definition=definition,
        )
    value, eid = paragraph("reported cash and cash equivalents of")
    match = re.search(r"to \$([\d.]+) million", value)
    metric("revolver", float(match[1]) * 1e6, "USD", eid, definition="available_credit_2026-09-30")
    value, eid = paragraph("Fuel cost per gallon")
    metric(
        "fuel_price_yoy",
        float(re.search(r"increased by ([\d.]+)%", value)[1]),
        "percent_change",
        eid,
        definition="quarter_yoy_change",
    )
    value, eid = paragraph("Our premium revenue")
    metric(
        "premium",
        float(re.search(r"reached ([\d.]+)%", value)[1]) * 0.01,
        "fraction",
        eid,
        definition="quarter_share_of_passenger_revenue_products_above_Basic_Classic",
    )
    for table, label, key, unit in [
        (11, "Adjusted net debt (1)", "net_debt", "USD"),
        (12, "Net leverage ratio (1)", "leverage", "multiple"),
    ]:
        heading = compact(tables[table].get_text(" ", strip=True))
        if "As of September 30, 2026 As of December 31, 2025" not in heading:
            raise ValueError("Balance sheet comparison dates changed")
        values, eid = row(table, label)
        for column, period in ((1, PERIOD), (2, "2025Q4")):
            metric(
                key,
                number(values[column]) * (1e6 if unit == "USD" else 1),
                unit,
                eid,
                period,
                definition="instant_2026-09-30" if column == 1 else "instant_2025-12-31",
            )
    # Qualitative claims resolve to the complete primary release and PDF pages,
    # whose bytes are pinned and replayed. No snippets are treated as instructions.
    excerpt("complete release", text)
    pages = PdfReader(io.BytesIO(pdf)).pages
    for page in (3, 5, 6, 7, 9, 11):
        page_text = compact(pages[page - 1].extract_text() or "")
        eid = excerpt(f"page={page}", page_text, "presentation")
        if page == 6:
            match = re.search(r"([\d.]+)%", page_text)
            if not match or "Fuel Cost Recapture" not in page_text:
                raise ValueError("Missing issuer fuel-recoupment ratio")
            metric(
                "fuel_recapture_reported",
                float(match[1]) * 0.01,
                "fraction",
                eid,
                definition="incremental_total_revenue_including_breakage_divided_by_incremental_fuel",
            )
    return metrics, excerpts


def verify(package, verify_files=True):
    if "editorial_extension" in package:
        if not verify_files:
            raise ValueError("Editorial sources always require original-file replay")
        from .quarterly_editorial import verify as editorial_verify
        return editorial_verify(package)
    payload = {k: v for k, v in package.items() if k not in ("package_id", "evidence_fingerprint")}
    if (
        package["period_id"] != PERIOD
        or package.get("entity_key") != "AEROMEXICO"
        or digest(payload) != package["evidence_fingerprint"]
        or package["package_id"] != PERIOD + "_" + digest(payload)
    ):
        raise ValueError("Quarterly release identity changed")
    if package["code_fingerprint"] != sha(Path(__file__).read_bytes()):
        raise ValueError("Quarterly replay changed; create a new reviewed package")
    if verify_files:
        sources = package["sources"]
        if [(s["artifact_id"], s["source_url"]) for s in sources] != [
            ("release", RELEASE),
            ("presentation", PRESENTATION),
            ("index", INDEX),
        ]:
            raise ValueError("Unexpected quarterly sources")
        contents = {}
        for source in sources:
            relative = Path(source["source_file"])
            path = (PATHS.bronze / relative).resolve()
            if not path.is_relative_to(PATHS.bronze.resolve()):
                raise ValueError("Quarterly source escapes Bronze")
            raw = path.read_bytes()
            if sha(raw) != source["artifact_sha256"]:
                raise ValueError("Quarterly original changed")
            proof_path = Path(str(path) + ".meta.json")
            proof_raw = proof_path.read_bytes()
            if sha(proof_raw) != source["capture_proof_sha256"]:
                raise ValueError("Quarterly capture proof changed")
            proof = json.loads(proof_raw)
            if (
                proof["url"] != source["source_url"]
                or proof["status"] != 200
                or proof["sha256"] != source["artifact_sha256"]
                or proof["captured_at"] != source["captured_at"]
                or proof["bytes"] != len(raw)
            ):
                raise ValueError("Quarterly capture proof disagrees with original")
            capture = datetime.fromisoformat(source["captured_at"])
            if capture.tzinfo is None or capture.date().isoformat() > package["cutoff_date"]:
                raise ValueError("Quarterly capture is beyond the retrospective cutoff")
            contents[source["artifact_id"]] = raw
        metrics, excerpts = extract(contents["release"], contents["presentation"])
        if metrics != package["metrics"] or excerpts != package["excerpts"]:
            raise ValueError("Quarterly source extraction differs")
        index = BeautifulSoup(contents["index"], "lxml")
        if "Quarterly Results" not in index.get_text() or not index.find(string=re.compile(r"2026")):
            raise ValueError("Missing primary index context")
    return {"status": "passed", "package_id": package["package_id"], "metrics": len(package["metrics"])}


def calculate(package):
    from .quantitative import node, calculate as operation

    verify(package)
    nodes = []
    lookup = {}

    def put(n):
        nodes.append(n)
        lookup[(n["period_id"], n["key"])] = n
        return n

    for metric in package["metrics"]:
        # Native precision is retained in the source. These are displayed values,
        # not estimates with an invented statistical confidence interval.
        value = metric["value"]
        n = node(
            metric["period_id"],
            metric["metric_key"],
            metric["unit"],
            value,
            [value, value],
            [metric["metric_id"]],
            "Reported normalized value; original published precision",
            basis={"definition": metric["definition"]},
        )
        if metric["unit"] == "multiple":
            n["formatted_value"] = f"{value:.1f}x"
        if metric["unit"] == "cents_USD_per_ASM":
            n["formatted_value"] = f"{value:.1f} centavos de dólar por asiento-milla ofrecido"
        n["calculation_id"] = "calc_" + digest({k: v for k, v in n.items() if k != "calculation_id"})
        put(n)

    def calc(key, op, keys, unit, factor=1):
        return put(operation(PERIOD, key, op, [lookup[(PERIOD, k)] for k in keys], unit, factor))

    calc("liquidity", "add", ["cash", "revolver"], "USD")
    calc("revenue_ex_breakage", "subtract", ["revenue", "breakage"], "USD")
    calc("ebitdar_ex_breakage", "subtract", ["ebitdar", "breakage"], "USD")
    calc("margin_ex_breakage", "divide", ["ebitdar_ex_breakage", "revenue_ex_breakage"], "fraction")
    # Explicitly illustrative arithmetic; neither the issuer's normalized result
    # nor cash flow. Prior-year reported revenue is in the same release.
    put(
        operation(
            PERIOD,
            "revenue_delta",
            "subtract",
            [lookup[(PERIOD, "revenue")], lookup[("2025Q3", "revenue")]],
            "USD",
        )
    )
    calc("revenue_delta_ex_breakage", "subtract", ["revenue_delta", "breakage"], "USD")
    calc("fuel_recapture_illustrative", "divide", ["revenue_delta_ex_breakage", "fuel_delta"], "fraction")
    calc("ask", "scale", ["asm"], "seat_km", 1.609344)
    calc("rask", "scale", ["trasm"], "cents_USD_per_ASK", 1 / 1.609344)
    calc("cask", "scale", ["casm"], "cents_USD_per_ASK", 1 / 1.609344)
    calc("spread", "subtract", ["rask", "cask"], "cents_USD_per_ASK")
    result = dict(
        schema_version="quantitative_v1",
        period_id=PERIOD,
        package_id=package["package_id"],
        evidence_fingerprint=package["evidence_fingerprint"],
        nodes=nodes,
        status="validated",
        checks=[],
        bridges=[],
        identity_bridges=[],
        analysis_constraints={"allow_spread_to_financial_margin_attribution": False},
        limits=[
            "Retrospective selection at capture; unaudited issuer figures.",
            "Mechanical breakage exclusions are illustrative, not issuer-normalized measures.",
            "Quarterly unit metrics use native miles; UI converts by 1.609344.",
            "Financial statement expenses and CASM are not equated.",
        ],
        code_fingerprint=sha(Path(__file__).read_bytes()),
    )
    result["calculation_fingerprint"] = digest(result)
    return result


def prepare(folder):
    metadata = json.loads((folder / "captures.json").read_bytes())
    sources = []
    for name, url in (("release.html", RELEASE), ("presentation.pdf", PRESENTATION), ("index.html", INDEX)):
        raw = (folder / name).read_bytes()
        capture = next((r for r in metadata if r["name"] == name), None)
        if not capture or capture["url"] != url or capture["status"] != 200 or capture["sha256"] != sha(raw):
            raise ValueError("Missing or mismatched successful capture receipt")
        relative = "quarterly/2026Q3/" + sha(raw) + Path(name).suffix
        target = PATHS.bronze / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Immutable source collision")
        target.write_bytes(raw)
        proof = canonical(capture)
        proof_path = Path(str(target) + ".meta.json")
        if proof_path.exists() and proof_path.read_bytes() != proof:
            raise ValueError("Immutable capture proof collision")
        proof_path.write_bytes(proof)
        sources.append(
            dict(
                artifact_id=name.split(".")[0],
                source_file=relative,
                source_url=url,
                artifact_sha256=sha(raw),
                captured_at=capture["captured_at"],
                capture_proof_sha256=sha(proof),
            )
        )
    metrics, excerpts = extract(
        (folder / "release.html").read_bytes(), (folder / "presentation.pdf").read_bytes()
    )
    package = dict(
        schema_version=SCHEMA,
        entity_key="AEROMEXICO",
        period_id=PERIOD,
        cutoff_date="2026-10-21",
        release_date="2026-10-19",
        presentation_date="2026-10-20",
        readiness="limited",
        sources=sources,
        metrics=metrics,
        excerpts=excerpts,
        coverage={"financial_thesis_possible": True},
        reasons=["Retrospective capture; no claim that captured bytes were available on release day."],
        code_fingerprint=sha(Path(__file__).read_bytes()),
    )
    package["evidence_fingerprint"] = digest(package)
    package["package_id"] = PERIOD + "_" + package["evidence_fingerprint"]
    verify(package)
    calculations = calculate(package)
    from .lifecycle import atomic_json

    for category, key, value in (
        ("evidence", package["package_id"], package),
        ("quantitative", calculations["calculation_fingerprint"], calculations),
    ):
        target = PATHS.root / "analysis_runs" / category / (key + ".json")
        if not target.exists():
            atomic_json(target, value)
    return package, calculations


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    package, calculations = prepare(parser.parse_args().folder)
    print(
        json.dumps(
            {
                "package_id": package["package_id"],
                "calculation_fingerprint": calculations["calculation_fingerprint"],
            }
        )
    )

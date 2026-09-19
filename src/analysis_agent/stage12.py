"""Read-only coverage diagnosis and illustrative review page for Stage 12.

This is not the quarterly agent: it never generates, validates, or approves an
analysis. Only the explicitly named diagnostic outputs are written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import duckdb

from src.config import PATHS
from src.dashboard.executive_summary import build_executive_payload


OUTPUT = PATHS.root / "docs/referencias/etapa-12"
HTML_OUTPUT = PATHS.root / "prototypes/etapa-12/analysis_agent.html"
GROUPS = {
    "operating": ("rask", "cask", "asm_total", "load_factor_total", "passengers"),
    "financial": ("total_revenue", "adjusted_ebitdar", "ebitdar_margin",
                  "operating_income", "operating_margin", "net_income"),
    "costs": ("operating_expenses_total", "jet_fuel_expense", "fuel_liters",
              "cask_ex_fuel", "wages_salaries_benefits", "maintenance_expense",
              "depreciation_amortization", "aircraft_leasing_expense"),
}
GROUP_LABELS = {"operating": "Operación", "financial": "Finanzas", "costs": "Costos y consumo"}
FIRST_PERIOD, LAST_PERIOD = "2021Q1", "2026Q2"


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def quarter_months(period: str) -> list[str]:
    if not re.fullmatch(r"\d{4}Q[1-4]", period):
        raise ValueError(f"Invalid quarter: {period}")
    first = (int(period[-1]) - 1) * 3 + 1
    return [f"{period[:4]}M{month:02d}" for month in range(first, first + 3)]


def coverage(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    """Count distinct usable metrics, never duplicate rows or missing values."""
    seen: set[str] = set()
    for row in rows:
        key = row["metric_key"]
        if key not in keys:
            continue
        if key in seen:
            raise ValueError(f"Duplicate selected metric: {key}")
        seen.add(key)
    available = {
        row["metric_key"] for row in rows
        if row["metric_key"] in keys and row["value"] is not None
        and math.isfinite(float(row["value"]))
    }
    return {"available": sorted(available), "missing": sorted(set(keys) - available),
            "count": len(available), "expected": len(keys)}


def verify_artifact(artifact: dict[str, Any], bronze: Path) -> dict[str, Any]:
    relative = Path(artifact["source_file"])
    path = (bronze / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(bronze.resolve()):
        raise ValueError("Artifact path leaves Bronze")
    status = "missing_local_file"
    if path.is_file():
        status = "verified_hash" if file_hash(path) == artifact["artifact_sha256"] else "hash_mismatch"
    # Only public metadata enters the review payload, never a machine path.
    return {key: artifact[key] for key in ("artifact_id", "source_url", "artifact_sha256")} | {
        "integrity_status": status,
        "publication_date": None,
        "temporal_status": "not_verified",
    }


def _records(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    result = connection.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row, strict=True)) for row in result.fetchall()]


def build_diagnosis(database: Path = PATHS.warehouse, bronze: Path = PATHS.bronze,
                    silver: Path = PATHS.silver) -> dict[str, Any]:
    presentation = build_executive_payload(str(database))
    periods = [r["period_id"] for r in presentation["records"]
               if FIRST_PERIOD <= r["period_id"] <= LAST_PERIOD]
    with duckdb.connect(str(database), read_only=True) as c:
        selected = _records(c, """SELECT period_id, metric_key, value, source_system, source_file
            FROM v_carrier_default WHERE carrier_key='AEROMEXICO'
            AND period_type='quarter' AND segment='total' ORDER BY period_id, metric_key""")
        artifacts = _records(c, """SELECT * FROM dim_source_artifact
            WHERE source_system='aeromexico_ir' AND is_latest_version ORDER BY logical_key, artifact_id""")
        macro = _records(c, """SELECT DISTINCT period_id, indicator_key FROM fact_macro
            WHERE period_type='month' AND aggregation='average' AND value IS NOT NULL""")
        afac = {r[0] for r in c.execute("""SELECT DISTINCT period_id FROM fact_carrier_metrics
            WHERE carrier_key='AEROMEXICO' AND source_system='afac' AND period_type='month'
            AND segment='total' AND metric_key='passengers' AND is_current AND value IS NOT NULL""").fetchall()}
        airports = {r[0] for r in c.execute("""SELECT DISTINCT period_id FROM fact_airport_traffic
            WHERE passengers_total IS NOT NULL""").fetchall()}
        airport_groups = {r[0] for r in c.execute("""SELECT DISTINCT period_id FROM fact_airport_group_traffic
            WHERE passengers_total IS NOT NULL""").fetchall()}
        peers = {r[0] for r in c.execute("""SELECT DISTINCT period_id FROM v_carrier_default
            WHERE carrier_key <> 'AEROMEXICO' AND period_type='quarter'
            AND segment='total' AND metric_key='total_revenue' AND value IS NOT NULL""").fetchall()}
        artifact_columns = [r[0] for r in c.execute("DESCRIBE dim_source_artifact").fetchall()]

    sec_documents: dict[str, dict[str, Any]] = {}
    sec_paths = [silver / name for name in ("sec_filing_documents.parquet", "sec_filings_index.parquet",
                                           "sec_report_text.parquet")]
    if all(path.is_file() for path in sec_paths):
        with duckdb.connect(":memory:") as c:
            for name, path in zip(("documents", "filings", "reports"), sec_paths, strict=True):
                c.read_parquet(str(path)).create_view(name)
            for row in _records(c, """SELECT DISTINCT d.source_file, f.filing_date,
                r.period_id AS report_period_id, d.source_url FROM documents d
                JOIN filings f USING (accession_number)
                JOIN reports r ON r.source_file=d.source_file
                WHERE r.report_type='earnings' ORDER BY d.source_file, r.period_id"""):
                if row["source_file"] in sec_documents and sec_documents[row["source_file"]] != row:
                    raise ValueError("Ambiguous SEC report mapping")
                sec_documents[row["source_file"]] = row

    rows = []
    for period in periods:
        metrics = [r for r in selected if r["period_id"] == period]
        groups = {key: coverage(metrics, values) for key, values in GROUPS.items()}
        docs = [verify_artifact(a, bronze) for a in artifacts
                if a["logical_key"].split("|")[2] == period]
        months = set(quarter_months(period))
        contextual = {
            "fx_months": sorted(months & {r["period_id"] for r in macro if r["indicator_key"] == "usd_mxn_fix"}),
            "fuel_months": sorted(months & {r["period_id"] for r in macro if r["indicator_key"] == "jet_fuel_usd_per_gallon"}),
            "afac_months": sorted(months & afac),
            "airport_months_with_any_data": sorted(months & airports),
            "airport_group_months_with_any_data": sorted(months & airport_groups),
            "any_peer_revenue": period in peers,
        }
        candidates = []
        for metric in metrics:
            if metric["metric_key"] != "total_revenue":
                continue
            sec = sec_documents.get(metric["source_file"])
            if sec:
                candidates.append({"metric_key": "total_revenue",
                    "report_period_id": sec["report_period_id"],
                    "filing_date": sec["filing_date"].isoformat() if sec["filing_date"] else None,
                    "source_url": sec["source_url"],
                    "from_later_report": sec["report_period_id"] > period})
        gaps = ["publication_and_version_proof_missing"]
        if groups["financial"]["missing"] or groups["costs"]["missing"]:
            gaps.append("historical_extraction_missing")
        if any(r["from_later_report"] for r in candidates):
            gaps.append("financial_values_from_later_comparative")
        if not docs or any(d["integrity_status"] != "verified_hash" for d in docs):
            gaps.append("release_integrity_unresolved")
        rows.append({"period_id": period, "label": f"{period[-1]}T{period[2:4]}",
            "groups": groups, "artifacts": docs, "sec_candidates": candidates,
            "context": contextual, "gaps": gaps, "cutoff_date": None,
            "temporal_status": "not_verified", "analysis_status": "not_started",
            "kpis": presentation["views"][period]["kpis"]})
    dependencies = {"warehouse": file_hash(database)}
    dependencies.update({p.name: file_hash(p) for p in sec_paths if p.is_file()})
    return {"schema_version": "stage12.diagnosis.v1", "purpose": "diagnosis_not_analysis",
        "baseline": "current_warehouse_not_point_in_time", "input_sha256": dependencies,
        "publication_fields_in_artifact_catalog": [x for x in artifact_columns if x in
            ("published_at", "publication_date", "version_available_at")],
        "groups": {key: {"label": GROUP_LABELS[key], "metrics": list(values)} for key, values in GROUPS.items()},
        "summary": {"quarters": len(rows),
            "complete_operating": sum(r["groups"]["operating"]["count"] == len(GROUPS["operating"]) for r in rows),
            "complete_financial": sum(r["groups"]["financial"]["count"] == len(GROUPS["financial"]) for r in rows),
            "complete_costs": sum(r["groups"]["costs"]["count"] == len(GROUPS["costs"]) for r in rows),
            "verified_releases": sum(any(a["integrity_status"] == "verified_hash" for a in r["artifacts"]) for r in rows),
            "later_comparative_quarters": sum("financial_values_from_later_comparative" in r["gaps"] for r in rows),
            "temporally_verified": 0},
        "rows": rows}


def render_html(diagnosis: dict[str, Any]) -> str:
    # Check outgoing links before serializing source metadata into a portable page.
    for row in diagnosis["rows"]:
        for source in row["artifacts"] + row["sec_candidates"]:
            url = urlsplit(source["source_url"])
            if url.scheme != "https" or url.hostname not in {"ir.aeromexico.com", "www.sec.gov", "sec.gov"} or url.username or url.password:
                raise ValueError("Non-official source URL in review page")
    payload = json.dumps(diagnosis, ensure_ascii=False, sort_keys=True, allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    template = Path(__file__).with_name("stage12_template.html").read_text(encoding="utf-8")
    return template.replace("__DIAGNOSIS_JSON__", payload)


def write_outputs(diagnosis: dict[str, Any], output: Path = OUTPUT,
                  html_output: Path = HTML_OUTPUT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    html_output.parent.mkdir(parents=True, exist_ok=True)
    (output / "diagnostico.json").write_text(json.dumps(diagnosis, ensure_ascii=False,
        sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output / "cobertura.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["period_id", "operating", "financial", "costs", "verified_releases",
                         "fx_months", "fuel_months", "afac_months", "airport_months_with_any_data",
                         "airport_group_months_with_any_data", "any_peer_revenue", "cutoff_date",
                         "temporal_status", "sec_filing_candidate", "gaps"])
        for row in diagnosis["rows"]:
            writer.writerow([row["period_id"], *[f"{row['groups'][g]['count']}/{row['groups'][g]['expected']}" for g in GROUPS],
                sum(a["integrity_status"] == "verified_hash" for a in row["artifacts"]),
                *[len(row["context"][key]) for key in ("fx_months", "fuel_months", "afac_months",
                    "airport_months_with_any_data", "airport_group_months_with_any_data")],
                row["context"]["any_peer_revenue"], "", row["temporal_status"],
                ";".join(c["filing_date"] or "" for c in row["sec_candidates"]), ";".join(row["gaps"])])
    html_output.write_text(render_html(diagnosis), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--html-output", type=Path, default=HTML_OUTPUT)
    args = parser.parse_args()
    diagnosis = build_diagnosis()
    write_outputs(diagnosis, args.output_dir, args.html_output)
    print(json.dumps(diagnosis["summary"], ensure_ascii=False))
    print("Stage 12 diagnostic outputs created; no analysis generated or approved.")


if __name__ == "__main__":
    main()

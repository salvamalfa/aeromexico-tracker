"""Orchestrate the complete SEC bronze-to-silver Stage 1 parse."""

from __future__ import annotations

import json

import polars as pl

from src.config import PATHS
from src.ingest.sec.discover import rebuild_discovery_from_bronze
from src.parse.sec.common import write_parquet_atomic
from src.parse.sec.crosscheck import build_crosscheck
from src.parse.sec.definitions import extract_reference_text, extract_report_text
from src.parse.sec.earnings_release import parse_all_earnings
from src.parse.sec.traffic_report import parse_all_traffic


def _has_stage5_peer_bronze() -> bool:
    manifest = PATHS.bronze / "_manifest.jsonl"
    if not manifest.exists():
        return False
    return '"source_system": "viva_ir"' in manifest.read_text(encoding="utf-8")


def run_sec_parse() -> dict[str, object]:
    discovery = rebuild_discovery_from_bronze()
    quarterly, financial = parse_all_earnings()
    monthly = parse_all_traffic()
    inputs = [quarterly, monthly]
    peer_summary: dict[str, object] | None = None
    if _has_stage5_peer_bronze():
        from src.parse.peers.stage5 import build_peer_metrics

        peer_summary = build_peer_metrics()
        inputs.append(pl.read_parquet(PATHS.silver / "peer_operating_metrics.parquet"))
    operating = pl.concat(inputs, how="diagonal_relaxed").sort(
        ["period_type", "period_id", "metric_key", "segment", "accession_number"]
    )
    write_parquet_atomic(
        operating, PATHS.silver / "sec_operating_metrics.parquet"
    )
    reports = extract_report_text()
    references = extract_reference_text()
    crosscheck = build_crosscheck(operating)
    return {
        "filing_rows": discovery["filing_count"],
        "filing_document_rows": discovery["downloaded_document_count"],
        "network_used": discovery["network_used"],
        "operating_rows": operating.height,
        "financial_rows": financial.height,
        "report_text_rows": reports.height,
        "reference_text_rows": references.height,
        "crosscheck_rows": crosscheck.height,
        "quarterly_period_min": quarterly["period_id"].min(),
        "quarterly_period_max": quarterly["period_id"].max(),
        "monthly_period_min": monthly["period_id"].min(),
        "monthly_period_max": monthly["period_id"].max(),
        "peer_summary": peer_summary,
    }


def main() -> int:
    print(json.dumps(run_sec_parse(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

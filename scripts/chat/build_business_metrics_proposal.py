"""Build a non-production F2.3 review artifact from versioned public Gold.

The required --dry-run flag makes the closed approval boundary explicit. The
output contains proposed numeric series and provenance for owner review; it is
not consumed by the chat Snapshot, semantic catalog, or production registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data/gold"
METRIC_MAP = {
    "total_revenue": "total_revenue",
    "operating_costs": "operating_expenses_total",
    "fuel_expense": "jet_fuel_expense",
    "operating_income": "operating_income",
}
ENTITIES = ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS")
PERIODS = (
    "2025Q1",
    "2025Q2",
    "2025Q3",
    "2025Q4",
    "2025H1",
    "2025H2",
    "2025",
    "2026Q1",
    "2026Q2",
    "2026H1",
)
APPROVAL_STATUS = "owner_review_required_nonproduction_candidate"


def _source_priority() -> dict[str, int]:
    rows = duckdb.sql(
        "SELECT source_system, priority FROM read_parquet(?) WHERE data_domain = 'carrier_metrics'",
        params=[str(GOLD / "dim_source_priority.parquet")],
    ).fetchall()
    return {source: priority for source, priority in rows if source != "*"}


def _source_refs(
    source_files: set[str], sources: dict[str, tuple[str | None, str | None]]
) -> list[dict[str, Any]]:
    refs = []
    for source_file in sorted(source_files):
        url, digest = sources.get(source_file, (None, None))
        refs.append({"url": url, "sha256": digest, "public_artifact": bool(url)})
    return refs


def _load_quarter_rows() -> tuple[
    dict[tuple[str, str, str], dict[str, Any]], dict[str, tuple[str | None, str | None]]
]:
    fact_path = str(GOLD / "fact_carrier_metrics.parquet")
    artifact_path = str(GOLD / "dim_source_artifact.parquet")
    priority = _source_priority()
    relation = duckdb.sql(
        """
        SELECT f.metric_key, f.carrier_key, f.period_id, f.value_usd, f.value_as_reported,
               f.currency, f.unit_as_reported, f.unit_normalized, f.is_derived,
               f.is_estimated, f.source_system, f.source_file, f.source_hash,
               a.source_url
        FROM read_parquet(?) AS f
        LEFT JOIN read_parquet(?) AS a ON a.source_file = f.source_file
        WHERE f.metric_key IN (?, ?, ?, ?)
          AND f.carrier_key IN (?, ?, ?)
          AND f.period_type = 'quarter'
          AND f.is_current
        """,
        params=[fact_path, artifact_path, *METRIC_MAP.values(), *ENTITIES],
    )
    records = relation.fetchall()
    names = relation.columns
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    source_registry: dict[str, tuple[str | None, str | None]] = {}
    for row in records:
        item = dict(zip(names, row, strict=True))
        source_registry[item["source_file"]] = (item["source_url"], item["source_hash"])
        grouped[(item["metric_key"], item["carrier_key"], item["period_id"])].append(item)

    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, candidates in grouped.items():
        best_priority = min(priority.get(row["source_system"], priority.get("*", 999)) for row in candidates)
        preferred = [
            row
            for row in candidates
            if priority.get(row["source_system"], priority.get("*", 999)) == best_priority
        ]
        normalized = {row["value_usd"] for row in preferred}
        if len(normalized) != 1 or None in normalized or not all(math.isfinite(float(v)) for v in normalized):
            selected[key] = {
                "availability": "source_conflict",
                "value": None,
                "source_rows": preferred,
            }
            continue
        # Equal-priority, equal-value observations collapse into one amount and
        # keep every supporting citation. Never average duplicate sources.
        chosen = sorted(preferred, key=lambda row: (row["source_system"], row["source_file"]))[0]
        selected[key] = {
            "availability": "available",
            "value": float(chosen["value_usd"]),
            "value_as_reported": chosen["value_as_reported"],
            "currency_as_reported": chosen["currency"],
            "unit_as_reported": chosen["unit_as_reported"],
            "unit_normalized": chosen["unit_normalized"],
            "source_system": chosen["source_system"],
            "derived": bool(chosen["is_derived"]),
            "estimated": bool(chosen["is_estimated"]),
            "source_files": {row["source_file"] for row in preferred},
        }
    return selected, source_registry


def _quarters_for(period: str) -> list[str]:
    if len(period) == 6 and period[4] == "Q":
        return [period]
    year = int(period[:4])
    if period.endswith("H1"):
        return [f"{year}Q1", f"{year}Q2"]
    if period.endswith("H2"):
        return [f"{year}Q3", f"{year}Q4"]
    return [f"{year}Q{i}" for i in range(1, 5)]


def build_proposal() -> dict[str, Any]:
    selected, source_registry = _load_quarter_rows()
    rows = []
    for candidate_id, gold_metric in METRIC_MAP.items():
        for entity in ENTITIES:
            for period in PERIODS:
                expected = _quarters_for(period)
                observed = [
                    selected.get((gold_metric, entity, quarter), {"availability": "missing"})
                    for quarter in expected
                ]
                problems = [
                    expected[index]
                    for index, item in enumerate(observed)
                    if item["availability"] != "available"
                ]
                available = not problems
                value = math.fsum(item["value"] for item in observed) if available else None
                support = [item for item in observed if item["availability"] == "available"]
                sources = {source_file for item in support for source_file in item.get("source_files", set())}
                source_refs = _source_refs(sources, source_registry)
                rows.append(
                    {
                        "metric_id": candidate_id,
                        "gold_metric_key": gold_metric,
                        "entity_id": entity,
                        "period": period,
                        "value": value,
                        "unit": "USD",
                        "availability": "available"
                        if available
                        else (
                            "source_conflict"
                            if any(item["availability"] == "source_conflict" for item in observed)
                            else "incomplete"
                        ),
                        "value_kind": "candidate_reported_gold_derived_sum",
                        "approval_status": APPROVAL_STATUS,
                        "aggregation": "deterministic_sum_of_selected_quarter_value_usd",
                        "expected_quarters": expected,
                        "included_quarters": [
                            q
                            for q, item in zip(expected, observed, strict=True)
                            if item["availability"] == "available"
                        ],
                        "missing_or_conflicting_quarters": problems,
                        "source_references": source_refs,
                        "source_systems": sorted(
                            {item.get("source_system") for item in support if item.get("source_system")}
                        ),
                        "currency_as_reported": sorted(
                            {
                                item.get("currency_as_reported")
                                for item in support
                                if item.get("currency_as_reported")
                            }
                        ),
                        "any_derived": any(item.get("derived", False) for item in support),
                        "any_estimated": any(item.get("estimated", False) for item in support),
                    }
                )
    return {
        "metadata": {
            "artifact_id": "chat_business_metrics_f23_candidate_v1",
            "approval_status": APPROVAL_STATUS,
            "production_enabled": False,
            "source_tables": [
                "data/gold/fact_carrier_metrics.parquet",
                "data/gold/dim_source_priority.parquet",
                "data/gold/dim_source_artifact.parquet",
            ],
            "input_hashes": {
                relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                for relative in (
                    "data/gold/fact_carrier_metrics.parquet",
                    "data/gold/dim_source_priority.parquet",
                    "data/gold/dim_source_artifact.parquet",
                )
            },
            "source_selection": (
                "Lowest dim_source_priority.priority per metric/entity/quarter. Equal-rank records collapse "
                "only when normalized USD values match; mismatches are marked as conflicts."
            ),
            "currency_basis": (
                "Uses Gold value_usd and retains each source currency; this script computes no conversion."
            ),
            "period_rule": (
                "Years and semesters sum complete selected calendar quarters; native annual Gold rows are "
                "excluded from those sums."
            ),
            "limitations": [
                "Review artifact over versioned public Gold; this is not an approved chat payload.",
                "No raw filings or untracked bronze/silver/warehouse data are read.",
                (
                    "Financial definitions, source precedence, USD normalization, entity scope, and coverage "
                    "require owner review before activation."
                ),
            ],
        },
        "coverage": {
            "source_quarter_coverage": {
                f"{metric_id}:{entity}": sorted(
                    period
                    for metric, carrier, period in selected
                    if metric == gold_metric and carrier == entity
                )
                for metric_id, gold_metric in METRIC_MAP.items()
                for entity in ENTITIES
            },
            "requested_periods": list(PERIODS),
            "period_rows": len(rows),
            "available_rows": sum(row["availability"] == "available" for row in rows),
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", required=True, help="Required: generate a review-only proposal"
    )
    parser.add_argument("--out", type=Path, required=True, help="Output JSON proposal path")
    args = parser.parse_args()
    output = args.out if args.out.is_absolute() else ROOT / args.out
    proposal = build_proposal()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": output.relative_to(ROOT).as_posix(),
                "approval_status": APPROVAL_STATUS,
                **proposal["coverage"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

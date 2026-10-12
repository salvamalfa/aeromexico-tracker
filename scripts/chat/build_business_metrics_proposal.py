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
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
PERIODS = tuple(
    [
        f"{year}Q{quarter}"
        for year in range(2020, 2027)
        for quarter in range(1, 5)
        if (year, quarter) <= (2026, 2)
    ]
    + [f"{year}H{half}" for year in range(2020, 2027) for half in (1, 2)]
    + [str(year) for year in range(2020, 2027)]
)
APPROVAL_STATUS = "owner_review_required_nonproduction_candidate"
SEC_Q2_2026_IDENTITY_CHECK = {
    "url": "https://www.sec.gov/Archives/edgar/data/1561861/000119312526302103/d112634dex991.htm",
    "gold_capture_sha256": "6207b9a113074f68e0d8196f9597ddf35f40a32b5f53ca97c5cd2c0a2f0ac781",
    "gold_capture_bytes": 230275,
    "current_sha256": "ce94b0feac78c8621f5c4ec9e82b5953847f048a202b43ab829d45956e2e7cd6",
    "current_bytes": 230386,
    "checked_at": "2026-10-11",
    "status": "byte_identity_mismatch_factual_values_match",
    "note": (
        "The current SEC URL returns different bytes than the dated Gold capture. F25 read-only review "
        "confirmed the relevant reported figures match; this is not evidence of a restatement."
    ),
    "reported_values_usd_millions": {
        "total_revenue": 1479.0,
        "operating_costs": 1411.0,
        "fuel_expense": 493.8,
        "operating_income": 67.9,
    },
}


def _source_priority() -> dict[str, int]:
    rows = duckdb.sql(
        "SELECT source_system, priority FROM read_parquet(?) WHERE data_domain = 'carrier_metrics'",
        params=[str(GOLD / "dim_source_priority.parquet")],
    ).fetchall()
    return {source: priority for source, priority in rows}


def _preferred_sources(candidates: list[dict[str, Any]], priority: dict[str, int]) -> list[dict[str, Any]]:
    """Return the top-ranked rows, applying the configured wildcard default."""
    default_priority = priority.get("*", 999)
    best_priority = min(priority.get(row["source_system"], default_priority) for row in candidates)
    return [
        row for row in candidates if priority.get(row["source_system"], default_priority) == best_priority
    ]


def _sources_have_compatible_usd_basis(rows: list[dict[str, Any]]) -> bool:
    """Reject amounts whose USD normalization or conversion trail is ambiguous."""
    if not rows or any(str(row.get("unit_normalized", "")).lower() != "usd" for row in rows):
        return False
    for row in rows:
        currency = row.get("currency")
        if not isinstance(currency, str) or not currency.strip():
            return False
        if currency.upper() != "USD":
            rate = row.get("fx_rate_used")
            if not isinstance(rate, (int, float)) or not math.isfinite(float(rate)) or float(rate) <= 0:
                return False
            if not isinstance(row.get("fx_rate_type"), str) or not row["fx_rate_type"].strip():
                return False
    return True


def _load_quarter_rows() -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    fact_path = str(GOLD / "fact_carrier_metrics.parquet")
    artifact_path = str(GOLD / "dim_source_artifact.parquet")
    priority = _source_priority()
    relation = duckdb.sql(
        """
        SELECT f.metric_key, f.carrier_key, f.period_id, f.calendar_period_id,
               f.fiscal_period_id, f.value_usd, f.value_as_reported,
               f.currency, f.fx_rate_used, f.fx_rate_type, f.unit_as_reported,
               f.unit_normalized, f.is_derived, f.is_preliminary,
               f.is_estimated, f.source_system, f.source_file, f.source_hash,
               a.source_url, a.downloaded_at AS source_downloaded_at,
               a.byte_size AS source_byte_size
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
    source_registry: dict[str, dict[str, Any]] = {}
    for row in records:
        item = dict(zip(names, row, strict=True))
        source_registry[item["source_file"]] = {
            "url": item["source_url"],
            "sha256": item["source_hash"],
            "captured_at": (
                item["source_downloaded_at"].isoformat() + "Z" if item["source_downloaded_at"] else None
            ),
            "captured_bytes": item["source_byte_size"],
        }
        grouped[(item["metric_key"], item["carrier_key"], item["period_id"])].append(item)

    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, candidates in grouped.items():
        preferred = _preferred_sources(candidates, priority)
        normalized = {row["value_usd"] for row in preferred}
        if (
            len(normalized) != 1
            or None in normalized
            or not all(math.isfinite(float(v)) for v in normalized)
            or not _sources_have_compatible_usd_basis(preferred)
        ):
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
            "carrier_key": chosen["carrier_key"],
            "period_id": chosen["period_id"],
            "calendar_period_id": chosen["calendar_period_id"],
            "fiscal_period_id": chosen["fiscal_period_id"],
            "value_as_reported": chosen["value_as_reported"],
            "value_usd": chosen["value_usd"],
            "currency_as_reported": chosen["currency"],
            "fx_rate_used": chosen["fx_rate_used"],
            "fx_rate_type": chosen["fx_rate_type"],
            "unit_as_reported": chosen["unit_as_reported"],
            "unit_normalized": chosen["unit_normalized"],
            "source_system": chosen["source_system"],
            "derived": bool(chosen["is_derived"]),
            "estimated": bool(chosen["is_estimated"]),
            "preliminary": bool(chosen["is_preliminary"]),
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


def _public_source_refs(
    items: list[dict[str, Any]], source_registry: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deduplicate public citations without leaking internal source file paths."""
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        source_files = item.get("source_files", set())
        if not source_files and item.get("source_file"):
            source_files = {item["source_file"]}
        for source_file in source_files:
            source = source_registry.get(source_file, {})
            citation_url = source.get("url")
            parsed = urlsplit(citation_url or "")
            member = None
            display_url = citation_url
            system = item.get("source_system") or "fuente pública"
            entity = item.get("carrier_key", "")
            period = item.get("period_id", item.get("calendar_period_id", ""))
            label = f"{system} · {entity} · {period}"
            if parsed.fragment:
                member_candidate = parsed.fragment.removeprefix("member=")
                match = (
                    parsed.scheme == "https"
                    and parsed.netloc == "www.bmv.com.mx"
                    and parsed.path.startswith("/docs-pub/ifrsxbrl/")
                    and parsed.path.endswith(".zip")
                    and not parsed.query
                    and parsed.fragment.startswith("member=")
                    and re.fullmatch(r"[A-Za-z0-9_.-]+\.json", member_candidate) is not None
                )
                if not match:
                    raise ValueError(f"Unrecognized source citation fragment: {citation_url}")
                member = parsed.fragment.removeprefix("member=")
                display_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
                label = f"BMV XBRL · {entity} · {period} · {member}"
            url, digest = display_url, source.get("sha256")
            identity_check = None
            if (
                source.get("url") == SEC_Q2_2026_IDENTITY_CHECK["url"]
                and digest == SEC_Q2_2026_IDENTITY_CHECK["gold_capture_sha256"]
                and source.get("captured_bytes") == SEC_Q2_2026_IDENTITY_CHECK["gold_capture_bytes"]
            ):
                identity_check = {
                    key: SEC_Q2_2026_IDENTITY_CHECK[key]
                    for key in (
                        "current_sha256",
                        "current_bytes",
                        "checked_at",
                        "status",
                        "note",
                        "reported_values_usd_millions",
                    )
                }
            key = (url, digest, item.get("source_system"), member, label)
            unique[key] = {
                "url": url,
                "citation_url": citation_url,
                "member": member,
                "label": label,
                "sha256": digest,
                "source_system": item.get("source_system"),
                "captured_at": source.get("captured_at"),
                "captured_bytes": source.get("captured_bytes"),
                "current_identity_check": identity_check,
            }
    return [unique[key] for key in sorted(unique, key=lambda value: tuple(str(part or "") for part in value))]


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
                cited = [
                    source
                    for item in observed
                    for source in (
                        item.get("source_rows", []) if item["availability"] == "source_conflict" else [item]
                    )
                ]
                source_refs = _public_source_refs(cited, source_registry)
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
                        "quarter_sources": [
                            {
                                "calendar_period_id": item.get("calendar_period_id", quarter),
                                "fiscal_period_id": item.get("fiscal_period_id", quarter),
                                "value": item.get("value"),
                                "value_as_reported": item.get("value_as_reported"),
                                "currency_as_reported": item.get("currency_as_reported"),
                                "unit_as_reported": item.get("unit_as_reported"),
                                "unit_normalized": item.get("unit_normalized"),
                                "fx_rate_used": item.get("fx_rate_used"),
                                "fx_rate_type": item.get("fx_rate_type"),
                                "is_preliminary": item.get("preliminary", False),
                                "source_system": item.get("source_system"),
                                "source_references": _public_source_refs([item], source_registry),
                            }
                            for quarter, item in zip(expected, observed, strict=True)
                            if item["availability"] == "available"
                        ],
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
                        "any_preliminary": any(item.get("preliminary", False) for item in support),
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
            "external_identity_checks": [SEC_Q2_2026_IDENTITY_CHECK],
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

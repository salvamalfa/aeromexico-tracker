"""Canonical data-quality ledger assembled from operational and analytical issues."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.config import PATHS


REFERENCE_OPERATIONAL_LEDGER = (
    PATHS.data / "reference" / "stage9_operational_quality_issues.jsonl"
)
RUNTIME_OPERATIONAL_LEDGER = PATHS.quality / "issues.jsonl"


QUALITY_COLUMNS = [
    "issue_id",
    "issue_signature",
    "issue_origin",
    "issue_type",
    "severity",
    "status",
    "resolved",
    "layer",
    "dataset_name",
    "source_system",
    "source_file",
    "carrier_key",
    "period_id",
    "calendar_period_id",
    "fiscal_period_id",
    "metric_key",
    "observed_value",
    "expected_value",
    "difference_pct",
    "affected_rows",
    "description",
    "evidence",
    "detected_at",
    "resolved_at",
]


_TABLE_SOURCE = {
    "afac_monthly_stats": "afac",
    "bmv_sec_reconciliation": "bmv_xbrl",
    "bmv_financials": "bmv_xbrl",
    "sec_operating_metrics": "sec_edgar",
    "sec_financials": "sec_edgar",
    "bts_t100_segment": "bts_t100",
    "fx_rates": "banxico_sie",
    "fuel_prices": "eia",
    "market_prices": "yahoo_finance",
    "airport_traffic": "airport_public_sources",
    "news_headlines": "news_public_feeds",
}


def _stable_issue_id(record: dict[str, Any]) -> str:
    return f"dqi_{_stable_issue_signature(record)}"


def _stable_issue_signature(record: dict[str, Any]) -> str:
    """Return a semantic signature independent of historical issue identifiers."""

    signature = {
        key: record.get(key)
        for key in (
            "issue_origin",
            "issue_type",
            "layer",
            "dataset_name",
            "source_system",
            "source_file",
            "carrier_key",
            "period_id",
            "metric_key",
            "observed_value",
            "expected_value",
            "affected_rows",
            "description",
        )
    }
    payload = json.dumps(
        signature,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_system(table_name: str | None, source_file: str | None) -> str:
    table = str(table_name or "").strip()
    if table in _TABLE_SOURCE:
        return _TABLE_SOURCE[table]
    prefix = str(source_file or "").replace("\\", "/").split("/", 1)[0].lower()
    return {
        "afac": "afac",
        "bmv": "bmv_xbrl",
        "sec": "sec_edgar",
        "bts": "bts_t100",
        "banxico": "banxico_sie",
        "eia": "eia",
        "market": "yahoo_finance",
        "news": "news_public_feeds",
    }.get(prefix, "unattributed")


def _operational_source_system(
    table_name: str | None,
    source_file: str | None,
    description: str | None,
) -> str:
    dataset = str(table_name or "").strip()
    detail = str(description or "").casefold()
    if dataset == "news_headlines":
        if "gdelt" in detail:
            return "gdelt"
        if "economista" in detail:
            return "news_http_error"
    return _source_system(dataset, source_file)


def _manifest_detection_context() -> tuple[dict[str, pd.Timestamp], dict[str, pd.Timestamp], pd.Timestamp | None]:
    """Return deterministic Bronze timestamps for operational issue detection."""

    manifest = PATHS.bronze / "_manifest.jsonl"
    if not manifest.is_file():
        return {}, {}, None
    by_file: dict[str, pd.Timestamp] = {}
    by_source: dict[str, pd.Timestamp] = {}
    latest: pd.Timestamp | None = None
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Bronze manifest JSON at line {line_number}") from exc
        timestamp = pd.to_datetime(record.get("downloaded_at"), utc=True, errors="coerce")
        if pd.isna(timestamp):
            raise ValueError(f"Invalid Bronze downloaded_at at manifest line {line_number}")
        source_file = str(record.get("source_file") or "")
        source_system = str(record.get("source_system") or "")
        by_file[source_file] = max(by_file.get(source_file, timestamp), timestamp)
        by_source[source_system] = max(by_source.get(source_system, timestamp), timestamp)
        latest = timestamp if latest is None else max(latest, timestamp)
    return by_file, by_source, latest


def read_operational_issues(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the append-only operational ledger and fail on malformed evidence."""

    target = path or RUNTIME_OPERATIONAL_LEDGER
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid quality ledger JSON at {target}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Quality ledger row must be an object at {target}:{line_number}")
        records.append(value)
    return records


def _canonical_operational(
    record: dict[str, Any],
    detection_context: tuple[dict[str, pd.Timestamp], dict[str, pd.Timestamp], pd.Timestamp | None],
) -> dict[str, Any]:
    resolved = bool(record.get("resolved", False))
    dataset = str(record.get("table_name") or "unknown_dataset")
    source_file = str(record.get("source_file") or "")
    source_system = _operational_source_system(
        dataset,
        source_file,
        str(record.get("description") or ""),
    )
    by_file, by_source, bronze_latest = detection_context
    deterministic_detected_at = (
        by_file.get(source_file)
        or by_source.get(source_system)
        or bronze_latest
        or record.get("detected_at")
    )
    canonical: dict[str, Any] = {
        "issue_origin": "operational_ledger",
        "issue_type": str(record.get("issue_type") or "unknown_issue"),
        "severity": str(record.get("severity") or "warning"),
        "status": "resolved" if resolved else "open",
        "resolved": resolved,
        "layer": str(record.get("layer") or "unknown"),
        "dataset_name": dataset,
        "source_system": source_system,
        "source_file": source_file or None,
        "carrier_key": None,
        "period_id": None,
        "calendar_period_id": None,
        "fiscal_period_id": None,
        "metric_key": None,
        "observed_value": None,
        "expected_value": None,
        "difference_pct": None,
        "affected_rows": record.get("affected_rows"),
        "description": str(record.get("description") or "Operational quality issue"),
        "evidence": json.dumps(
            {
                "table_name": dataset,
                "source_file": source_file or None,
                "detected_at_basis": (
                    "source_artifact"
                    if source_file in by_file
                    else "source_snapshot"
                    if source_system in by_source
                    else "bronze_snapshot"
                    if bronze_latest is not None
                    else "operational_ledger"
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        "detected_at": deterministic_detected_at,
        "resolved_at": record.get("resolved_at"),
        "issue_id": record.get("issue_id"),
    }
    canonical["issue_id"] = _stable_issue_id(canonical)
    canonical["issue_signature"] = _stable_issue_signature(canonical)
    return canonical


def _canonical_derived(record: dict[str, Any]) -> dict[str, Any]:
    period_id = record.get("period_id")
    canonical: dict[str, Any] = {
        "issue_origin": "derived_reconciliation",
        "issue_type": str(record.get("issue_type") or "reported_derived_discrepancy"),
        "severity": str(record.get("severity") or "warning"),
        "status": "open",
        "resolved": False,
        "layer": "gold",
        "dataset_name": "fact_carrier_metrics",
        "source_system": str(record.get("source_system") or "derived_gold"),
        "source_file": record.get("source_file"),
        "carrier_key": record.get("carrier_key"),
        "period_id": period_id,
        "calendar_period_id": record.get("calendar_period_id", period_id),
        "fiscal_period_id": record.get("fiscal_period_id", period_id),
        "metric_key": record.get("metric_key"),
        "observed_value": record.get("observed_value"),
        "expected_value": record.get("expected_value"),
        "difference_pct": record.get("difference_pct"),
        "affected_rows": 1,
        "description": str(record.get("detail") or record.get("description") or "Derived value differs from reported value."),
        "evidence": json.dumps(
            {
                "observed_value": record.get("observed_value"),
                "expected_value": record.get("expected_value"),
                "difference_pct": record.get("difference_pct"),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
        "detected_at": record.get("detected_at"),
        "resolved_at": None,
        "issue_id": record.get("issue_id"),
    }
    canonical["issue_id"] = _stable_issue_id(canonical)
    canonical["issue_signature"] = _stable_issue_signature(canonical)
    return canonical


def build_canonical_quality_issues(
    derived_issues: pd.DataFrame,
    *,
    operational_records: Iterable[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Merge both issue mechanisms with deterministic de-duplication evidence."""

    if operational_records is None:
        baseline = read_operational_issues(REFERENCE_OPERATIONAL_LEDGER)
        runtime = read_operational_issues(RUNTIME_OPERATIONAL_LEDGER)
        operational = baseline + runtime
        baseline_rows = len(baseline)
        runtime_rows = len(runtime)
    else:
        operational = list(operational_records)
        baseline_rows = 0
        runtime_rows = len(operational)
    detection_context = _manifest_detection_context()
    operational_rows = [
        _canonical_operational(record, detection_context) for record in operational
    ]
    derived_rows = [
        _canonical_derived(record) for record in derived_issues.to_dict("records")
    ]
    rows = operational_rows + derived_rows
    frame = pd.DataFrame(rows, columns=QUALITY_COLUMNS)
    if frame.empty:
        frame = pd.DataFrame(columns=QUALITY_COLUMNS)
    else:
        frame["detected_at"] = pd.to_datetime(frame["detected_at"], utc=True).dt.tz_convert(None)
        frame["resolved_at"] = pd.to_datetime(frame["resolved_at"], utc=True, errors="coerce").dt.tz_convert(None)
        frame["affected_rows"] = pd.to_numeric(frame["affected_rows"], errors="coerce").astype("Int64")
        for column in ("observed_value", "expected_value", "difference_pct"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = (
            frame.sort_values(
                ["issue_signature", "detected_at", "issue_id"],
                kind="stable",
            )
            .drop_duplicates("issue_signature", keep="last")
            .sort_values(["severity", "detected_at", "issue_id"])
            .reset_index(drop=True)
        )
    operational_unique_rows = len(
        {record["issue_signature"] for record in operational_rows}
    )
    combined_unique_rows = len({record["issue_signature"] for record in rows})
    raw_combined_rows = len(operational) + len(derived_rows)
    reconciliation = {
        "operational_baseline_rows": baseline_rows,
        "operational_run_rows": runtime_rows,
        "operational_raw_input_rows": len(operational),
        "operational_input_rows": operational_unique_rows,
        "operational_duplicate_rows": len(operational) - operational_unique_rows,
        "derived_input_rows": len(derived_rows),
        "combined_raw_input_rows": raw_combined_rows,
        "combined_input_rows": combined_unique_rows,
        "canonical_rows": len(frame),
        "deduplicated_rows": raw_combined_rows - len(frame),
    }
    return frame, reconciliation

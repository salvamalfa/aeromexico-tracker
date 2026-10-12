"""Fail-closed builder/exporter for owner-approved F2.3 public totals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.web_export.business_metrics_approval import (
    BusinessMetricsApprovalError,
    validate_approval_receipt,
)
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.writer import write_json

ROOT = Path(__file__).resolve().parents[2]
BUSINESS_SCHEMA_PATH = ROOT / "contracts/web/business_metrics.schema.json"

def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise BusinessMetricsApprovalError(f"Expected JSON object: {path}")
    return value, raw


def build_approved_payload(
    proposal_path: Path,
    definitions_path: Path,
    receipt_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build public quarter-grain payload only for an exact owner receipt.

    Receipt hashes bind both the candidate definitions and the exact review
    artifact bytes. No receipt is bundled or inferred by this code.
    """
    proposal, proposal_raw = _load_json(proposal_path)
    definitions, definitions_raw = _load_json(definitions_path)
    receipt, _ = _load_json(receipt_path)
    receipt_sha256 = validate_approval_receipt(receipt)
    if receipt["definitions_sha256"] != _sha256(definitions_raw):
        raise BusinessMetricsApprovalError("Approval receipt does not match current metric definitions")
    if receipt["proposal_sha256"] != _sha256(proposal_raw):
        raise BusinessMetricsApprovalError("Approval receipt does not match exact candidate proposal bytes")
    candidates = {item["id"] for item in definitions.get("candidate_metrics", [])}
    approved = set(receipt["approved_metric_ids"])
    if not approved or not approved <= candidates:
        raise BusinessMetricsApprovalError("Approval receipt contains unknown or empty metric coverage")

    quarter_rows = []
    for source_row in proposal.get("rows", []):
        metric_id = source_row.get("metric_id")
        period = source_row.get("period", "")
        if metric_id not in approved or len(period) != 6 or period[4] != "Q":
            continue
        quarter_sources = source_row.get("quarter_sources", [])
        fx_converted = any(
            item.get("currency_as_reported") not in (None, "USD")
            and item.get("fx_rate_used") is not None
            for item in quarter_sources
        )
        quarter_rows.append(
            {
                "metric_id": metric_id,
                "entity_id": source_row["entity_id"],
                "period": period,
                "value": source_row.get("value"),
                "unit": source_row.get("unit", "USD"),
                "availability": source_row["availability"],
                "value_kind": (
                    "owner_approved_gold_fx_converted" if fx_converted else "owner_approved_gold_reported"
                ),
                "any_preliminary": source_row.get("any_preliminary", False),
                "calendar_period_id": quarter_sources[0]["calendar_period_id"] if quarter_sources else period,
                "fiscal_period_ids": sorted({item["fiscal_period_id"] for item in quarter_sources}),
                "currency_as_reported": sorted(
                    {
                        item["currency_as_reported"]
                        for item in quarter_sources
                        if item.get("currency_as_reported")
                    }
                ),
                "quarter_sources": [
                    {
                        key: item.get(key)
                        for key in (
                            "calendar_period_id",
                            "fiscal_period_id",
                            "value_as_reported",
                            "currency_as_reported",
                            "unit_as_reported",
                            "unit_normalized",
                            "fx_rate_used",
                            "fx_rate_type",
                            "is_preliminary",
                            "source_system",
                            "source_references",
                        )
                    }
                    for item in quarter_sources
                ],
                "source_references": [
                    {
                        key: ref.get(key)
                        for key in (
                            "url",
                            "citation_url",
                            "member",
                            "label",
                            "sha256",
                            "source_system",
                            "captured_at",
                            "captured_bytes",
                            "current_identity_check",
                        )
                    }
                    for ref in source_row.get("source_references", [])
                ],
            }
        )
    payload = {
        "schema_version": "business_metrics_v1",
        "metadata": {
            "definitions_sha256": _sha256(definitions_raw),
            "proposal_sha256": _sha256(proposal_raw),
            "approval_receipt_sha256": receipt_sha256,
            "metric_ids": sorted(approved),
            "currency_basis": "USD; reported currency and any FX metadata retained per quarter",
        },
        "rows": sorted(quarter_rows, key=lambda row: (row["metric_id"], row["entity_id"], row["period"])),
    }
    schema = json.loads(BUSINESS_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    if errors:
        raise BusinessMetricsApprovalError(f"Approved payload does not match schema: {errors[0].message}")
    check_privacy(payload, load_privacy_rules())
    return payload, receipt


def export_approved_business_metrics(
    proposal_path: Path,
    definitions_path: Path,
    receipt_path: Path,
    out_dir: Path,
) -> list[Path]:
    payload, receipt = build_approved_payload(proposal_path, definitions_path, receipt_path)
    out_dir = Path(out_dir)
    payload_path = out_dir / "business_metrics.json"
    receipt_path_out = out_dir / "business_metrics.approval.json"
    write_json(payload_path, payload)
    write_json(receipt_path_out, receipt)
    return [payload_path, receipt_path_out]

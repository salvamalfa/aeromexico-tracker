"""External trust checks for financial business-metrics approval receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
APPROVAL_SCHEMA_PATH = ROOT / "contracts/web/business_metrics_approval.schema.json"
APPROVAL_RECEIPT_SHA256_ENV = "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256"
APPROVED_OWNER_ID = "salvamalfa"


class BusinessMetricsApprovalError(ValueError):
    """Approval receipt is absent, stale, incomplete, or malformed."""


def canonical_receipt_sha256(receipt: dict[str, Any]) -> str:
    """Hash the receipt object, independent of its JSON whitespace or key order."""
    encoded = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_approval_receipt(receipt: dict[str, Any]) -> str:
    """Validate receipt scope and compare its canonical hash with an external pin."""
    schema = json.loads(APPROVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt)
    )
    if errors:
        location = ".".join(str(item) for item in errors[0].absolute_path) or "root"
        raise BusinessMetricsApprovalError(
            f"Invalid approval receipt at {location}: {errors[0].message}"
        )
    if receipt.get("owner_id") != APPROVED_OWNER_ID:
        raise BusinessMetricsApprovalError("Approval receipt owner is not the trusted owner")
    approved_at = receipt.get("approved_at")
    if not isinstance(approved_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        approved_at,
    ):
        raise BusinessMetricsApprovalError("Approval receipt approved_at is not a valid date-time")
    try:
        datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise BusinessMetricsApprovalError(
            "Approval receipt approved_at is not a valid date-time"
        ) from error
    decision_reference = receipt.get("decision_reference")
    if not isinstance(decision_reference, str) or not decision_reference.strip():
        raise BusinessMetricsApprovalError("Approval receipt decision_reference is missing")

    expected_sha256 = os.environ.get(APPROVAL_RECEIPT_SHA256_ENV, "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise BusinessMetricsApprovalError(
            f"{APPROVAL_RECEIPT_SHA256_ENV} must pin the approved receipt SHA-256"
        )
    actual_sha256 = canonical_receipt_sha256(receipt)
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise BusinessMetricsApprovalError("Approval receipt does not match the externally pinned SHA-256")
    return actual_sha256

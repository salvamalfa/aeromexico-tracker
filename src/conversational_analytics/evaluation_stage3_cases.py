"""Current coverage expectations for Stage 3, without rewriting frozen questions."""

from __future__ import annotations

import copy
from typing import Any

STAGE3_GRADING_MODE = "current_coverage_pending_blinded_owner_review"


def current_stage3_cases(
    fixture_cases: list[dict[str, Any]], coverage: dict[str, Any]
) -> list[dict[str, Any]]:
    """Replace historical grading expectations with current, pinned tool evidence."""
    derived = coverage.get("cases")
    if not isinstance(derived, list) or [row.get("case_id") for row in derived] != [
        case.get("id") for case in fixture_cases
    ]:
        raise ValueError("Las expectativas stage3 no coinciden con los casos congelados")
    result = copy.deepcopy(fixture_cases)
    for case, evidence in zip(result, derived, strict=True):
        status = evidence.get("status")
        if status not in {"supported", "coverage_missing", "approval_blocked"}:
            raise ValueError("La cobertura stage3 contiene un estado desconocido")
        case["grading_mode"] = STAGE3_GRADING_MODE
        case["expected"] = {
            "status": "supported" if status == "supported" else "unsupported",
            "coverage_status": status,
            "coverage_campaign_sha256": coverage["campaign_sha256"],
            "current_coverage": copy.deepcopy(evidence),
        }
    return result

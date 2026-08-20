from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from src.common.quality import log_issue


def test_quality_issue_is_appended_with_required_fields(tmp_path: Path) -> None:
    target = tmp_path / "issues.jsonl"
    detected_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    stored = log_issue(
        "silver",
        "sec_operating_metrics",
        "filing.pdf",
        "error",
        "parse_failure",
        "Expected operating metrics table was not found.",
        affected_rows=1,
        issues_path=target,
        detected_at=detected_at,
    )

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == stored
    assert stored["resolved"] is False
    assert stored["detected_at"] == "2026-08-20T12:00:00+00:00"


@pytest.mark.parametrize(
    ("severity", "issue_type", "affected_rows"),
    [
        ("severe", "parse_failure", 1),
        ("error", "invented_issue", 1),
        ("error", "parse_failure", -1),
    ],
)
def test_invalid_quality_issue_is_rejected(
    tmp_path: Path,
    severity: str,
    issue_type: str,
    affected_rows: int,
) -> None:
    with pytest.raises(ValueError):
        log_issue(
            "silver",
            "table",
            "source",
            severity,
            issue_type,
            "description",
            affected_rows,
            issues_path=tmp_path / "issues.jsonl",
        )

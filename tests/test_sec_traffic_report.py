from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest

from src.parse.sec.traffic_report import parse_traffic_content


def test_frozen_monthly_traffic_exhibit() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sec" / "traffic_2026M06.htm"
    content = fixture.read_bytes()
    document = {
        "accession_number": "fixture-accession",
        "source_file": fixture.as_posix(),
        "source_hash": hashlib.sha256(content).hexdigest(),
        "ingested_at": datetime(2026, 8, 20, tzinfo=UTC).isoformat(),
    }

    rows = parse_traffic_content(content, document)
    current_total = {
        row["metric_key"]: row
        for row in rows
        if row["period_id"] == "2026M06" and row["segment"] == "total"
    }

    assert current_total["passengers"]["value_normalized"] == 1_851_000
    assert current_total["asm_total"]["value_normalized"] == 3_027_000_000
    assert current_total["rpm_total"]["value_normalized"] == 2_497_000_000
    assert current_total["load_factor_total"]["value_normalized"] == pytest.approx(0.827)
    assert all(row["unit_normalized"] is not None for row in rows)

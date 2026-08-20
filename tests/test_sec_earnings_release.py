from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest

from src.parse.sec.earnings_release import parse_earnings_content


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sec"
EXPECTED = {
    "earnings_2025Q3.htm": {
        "period": "2025Q3",
        "total_revenue": 1425.0,
        "adjusted_ebitdar": 441.6,
        "operating_income": 252.8,
        "load_factor_total": 88.3,
        "casm_ex_fuel": 9.5,
        "trasm": 15.4,
        "fleet_size": 162.0,
    },
    "earnings_2025Q4.htm": {
        "period": "2025Q4",
        "total_revenue": 1438.0,
        "adjusted_ebitdar": 501.6,
        "operating_income": 303.1,
        "load_factor_total": 87.2,
        "casm_ex_fuel": 10.4,
        "trasm": 16.4,
        "fleet_size": 165.0,
    },
    "earnings_2026Q1.htm": {
        "period": "2026Q1",
        "total_revenue": 1341.0,
        "adjusted_ebitdar": 335.8,
        "ebitdar_margin": 25.0,
        "operating_income": 141.8,
        "operating_margin": 10.6,
        "load_factor_total": 84.4,
        "casm_ex_fuel": 10.2,
        "trasm": 15.6,
        "fleet_size": 166.0,
        "passengers": 5791.0,
    },
    "earnings_2026Q2.htm": {
        "period": "2026Q2",
        "total_revenue": 1479.0,
        "adjusted_ebitdar": 264.2,
        "operating_income": 67.9,
        "load_factor_total": 84.9,
        "casm_ex_fuel": 10.0,
        "trasm": 16.0,
        "fleet_size": 169.0,
    },
}


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_frozen_quarterly_exhibit_metrics(filename: str) -> None:
    fixture = FIXTURE_ROOT / filename
    content = fixture.read_bytes()
    document = {
        "accession_number": "fixture-accession",
        "source_file": fixture.as_posix(),
        "source_hash": hashlib.sha256(content).hexdigest(),
        "ingested_at": datetime(2026, 8, 20, tzinfo=UTC).isoformat(),
    }

    operating, financial = parse_earnings_content(content, document)
    expected = EXPECTED[filename]
    current = {
        row["metric_key"]: row
        for row in (*operating, *financial)
        if row["period_id"] == expected["period"]
    }

    for metric_key, expected_value in expected.items():
        if metric_key == "period":
            continue
        assert current[metric_key]["value_raw"] == pytest.approx(expected_value)
        assert current[metric_key]["unit_normalized"] is not None
        assert current[metric_key]["source_hash"] == document["source_hash"]


def test_2026q1_fixture_preserves_prior_year_load_factor() -> None:
    fixture = FIXTURE_ROOT / "earnings_2026Q1.htm"
    content = fixture.read_bytes()
    document = {
        "accession_number": "fixture-accession",
        "source_file": fixture.as_posix(),
        "source_hash": hashlib.sha256(content).hexdigest(),
        "ingested_at": datetime(2026, 8, 20, tzinfo=UTC).isoformat(),
    }

    operating, _ = parse_earnings_content(content, document)
    prior = next(
        row
        for row in operating
        if row["period_id"] == "2025Q1"
        and row["metric_key"] == "load_factor_total"
    )

    assert prior["value_normalized"] == pytest.approx(0.823)

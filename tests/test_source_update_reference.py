from datetime import UTC, datetime
import hashlib

import pandas as pd
import pytest

from src.source_updates.reference import check_snapshot


def inputs():
    digest = hashlib.sha256(b"reference").hexdigest()
    frame = pd.DataFrame(
        {
            "airport_iata": ["MEX"],
            "latitude": [19.4],
            "longitude": [-99.1],
            "country": ["MX"],
            "source_file": ["reference.csv"],
            "source_hash": [digest],
        }
    )
    spec = {
        "kind": "reference",
        "product": "airports_reference",
        "table": "dim_airport",
        "layer": "gold",
        "sha256": digest,
        "required_codes": ["MEX"],
        "countries": {"MEX": "MX"},
    }
    artifacts = {
        "reference.csv": {
            "sha256": digest,
            "source_system": "ourairports",
            "downloaded_at": "2026-10-18T12:00:00+00:00",
        }
    }
    return spec, frame, artifacts


def test_reference_is_a_snapshot_not_a_fabricated_month(tmp_path):
    spec, frame, artifacts = inputs()
    result = check_snapshot(tmp_path, spec, frame, artifacts, datetime(2026, 10, 19, tzinfo=UTC))
    assert result["status"] == "checks_passed"
    assert result["latest_validated_period"] is None
    assert result["validated_snapshot_sha256"] == spec["sha256"]


@pytest.mark.parametrize("case", ["latitude", "required_code", "country", "hash", "capture"])
def test_reference_rejects_invalid_geography_identity_or_vintage(tmp_path, case):
    spec, frame, artifacts = inputs()
    if case == "latitude":
        frame["latitude"] = 91.0
    elif case == "required_code":
        spec["required_codes"] = ["CUN"]
    elif case == "country":
        frame["country"] = "US"
    elif case == "hash":
        spec["sha256"] = "f" * 64
    else:
        artifacts["reference.csv"]["downloaded_at"] = "2027-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        check_snapshot(tmp_path, spec, frame, artifacts, datetime(2026, 10, 19, tzinfo=UTC))

"""src.publish.gate's verification step against the real local ledger.

Marked local_data: needs analysis_runs/ (the local approval ledger) and
the real warehouse (src/dashboard/ generators export_data calls into).
Does not run `npm ci && npm run build` (see tests/test_publish_manifest.py
for pure manifest coverage and tests/test_site_parity.py for a full,
built-site parity check against the currently committed site/) — this
file is about the refusal path task 1(a) of this package requires: a
record that fails verification must produce PublicationRefused and write
nothing.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.publish.gate import PublicationRefused, export_data, verify_records

pytestmark = pytest.mark.local_data

DRAFTS_ROOT = Path(__file__).resolve().parent.parent / "analysis_runs" / "drafts"


def _any_record_path() -> Path:
    for period_dir in sorted(DRAFTS_ROOT.iterdir()) if DRAFTS_ROOT.is_dir() else []:
        if not period_dir.is_dir():
            continue
        for record_path in sorted(period_dir.glob("*.json")):
            return record_path
    pytest.skip(f"no analysis_runs/drafts/ records in this checkout ({DRAFTS_ROOT})")


def _any_approved_record_path() -> Path:
    if not DRAFTS_ROOT.is_dir():
        pytest.skip(f"{DRAFTS_ROOT} does not exist in this checkout")
    for period_dir in sorted(DRAFTS_ROOT.iterdir()):
        if not period_dir.is_dir():
            continue
        for record_path in sorted(period_dir.glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            try:
                if flow.state(record)["state"] in ("approved", "published"):
                    return record_path
            except Exception:  # noqa: BLE001 - not every record need be well-formed here
                continue
    pytest.skip(f"no currently-approved analysis_runs/drafts/ record in this checkout ({DRAFTS_ROOT})")


def test_verify_records_accepts_a_currently_approved_record() -> None:
    record_path = _any_approved_record_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    entries = verify_records([record])
    assert len(entries) == 1
    _, authorized, _, _ = entries[0]
    assert authorized["period_id"] == record["draft"]["period_id"]
    assert authorized["version"] == record["version"]


def test_verify_records_refuses_a_record_with_a_tampered_content_hash() -> None:
    record_path = _any_record_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    tampered = copy.deepcopy(record)
    tampered["content_hash"] = "0" * 64
    with pytest.raises(PublicationRefused):
        verify_records([tampered])


def test_verify_records_refuses_an_empty_record_list() -> None:
    from src.publish.gate import publish

    with pytest.raises(PublicationRefused):
        publish([], Path("/tmp/should-not-be-created-by-this-test"))


def test_export_data_writes_only_the_given_records_analysis_periods(tmp_path: Path) -> None:
    record_path = _any_approved_record_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    entries = verify_records([record])
    export_data(entries, tmp_path)

    analysis_dir = tmp_path / "analysis"
    written_periods = {p.stem for p in analysis_dir.glob("*.json")}
    assert written_periods == {record["draft"]["period_id"]}
    assert (tmp_path / "executive.json").is_file()
    assert (tmp_path / "flights" / "quarters.json").is_file()

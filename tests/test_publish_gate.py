"""src.publish.gate's verification step against the real local ledger, plus
a pure unit test of the pre-swap re-verification (no local data needed).

Most tests here are marked local_data (individually, not module-wide, since
the race test below needs none of it): they need analysis_runs/ (the
local approval ledger) and the real warehouse (src/dashboard/ generators
export_data calls into). None of them run `npm ci && npm run build` (see
tests/test_publish_manifest.py for pure manifest coverage and
tests/test_site_parity.py for a full, built-site parity check against the
currently committed site/) — this file is about the refusal paths: a
record that fails verification must produce PublicationRefused and write
nothing, whether caught by the first check (task 1(a)) or, after
export/build already ran, by the second one immediately before the swap.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.publish.gate import PublicationRefused, export_data, verify_records

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


@pytest.mark.local_data
def test_verify_records_accepts_a_currently_approved_record() -> None:
    record_path = _any_approved_record_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    entries = verify_records([record])
    assert len(entries) == 1
    _, authorized, _, _ = entries[0]
    assert authorized["period_id"] == record["draft"]["period_id"]
    assert authorized["version"] == record["version"]


@pytest.mark.local_data
def test_verify_records_refuses_a_record_with_a_tampered_content_hash() -> None:
    record_path = _any_record_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    tampered = copy.deepcopy(record)
    tampered["content_hash"] = "0" * 64
    with pytest.raises(PublicationRefused):
        verify_records([tampered])


@pytest.mark.local_data
def test_verify_records_refuses_an_empty_record_list() -> None:
    from src.publish.gate import publish

    with pytest.raises(PublicationRefused):
        publish([], Path("/tmp/should-not-be-created-by-this-test"))


@pytest.mark.local_data
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


# ---------------------------------------------------------------------------
# publish() must re-verify under the ledger lock immediately before the
# swap, and hold the lock through it -- a revocation landing after
# export_data/build_web (both run with the lock released) but before the
# swap must abort with nothing written to out_dir. Pure unit test: every
# heavy step (export, npm build) is monkeypatched out, so no local_data is
# needed -- only src.publish.gate's own control flow is under test.
# ---------------------------------------------------------------------------


def test_publish_reverifies_under_the_lock_before_the_swap_and_aborts_on_revocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.publish.gate as gate

    ledger_root = tmp_path / "ledger"
    out_dir = tmp_path / "site"
    web_dir = tmp_path / "web"
    web_data_v1 = tmp_path / "web_data_v1"
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>\n", encoding="utf-8")

    fake_record = {"draft": {"period_id": "2026Q2"}, "version": "v1", "content_hash": "c" * 64}
    fake_authorized = {
        "period_id": "2026Q2",
        "version": "v1",
        "content_hash": "c" * 64,
        "evidence_fingerprint": "e" * 64,
        "approval_event": "a" * 64,
        "audit_hash": "h" * 64,
    }
    fake_entry = (fake_record, fake_authorized, object(), object())

    calls = {"n": 0}

    def fake_verify_under_lock(records, root):
        calls["n"] += 1
        if calls["n"] == 1:
            return [fake_entry]
        raise ValueError("approval revoked between build and swap")

    monkeypatch.setattr(gate, "_verify_under_lock", fake_verify_under_lock)
    monkeypatch.setattr(gate, "load_records", lambda paths: [fake_record])
    monkeypatch.setattr(gate, "export_data", lambda entries, out_dir: None)
    monkeypatch.setattr(gate, "build_web", lambda web_dir: dist_dir)
    # The dirty-tree guard is covered in test_publish_manifest.py; isolate it here.
    monkeypatch.setattr(gate.manifest_mod, "refuse_if_build_inputs_dirty", lambda *a, **k: None)

    with pytest.raises(gate.PublicationRefused, match="just before publish"):
        gate.publish(
            [Path("unused.json")],
            out_dir,
            root=ledger_root,
            web_dir=web_dir,
            web_data_v1=web_data_v1,
        )

    assert calls["n"] == 2, "expected one verify from verify_records() and one under the pre-swap lock"
    assert not out_dir.exists(), "site/ must be untouched when the pre-swap re-check fails"


def test_publish_aborts_when_the_approval_changes_during_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revoke-and-re-approve during the build passes the second check with a
    new approval_event; the built payload no longer matches, so abort."""

    import src.publish.gate as gate

    out_dir = tmp_path / "site"
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>\n", encoding="utf-8")

    fake_record = {"draft": {"period_id": "2026Q2"}, "version": "v1", "content_hash": "c" * 64}
    first = {k: k[0] * 64 for k in gate.ANALYSIS_MANIFEST_FIELDS} | {"period_id": "2026Q2", "version": "v1"}
    second = first | {"approval_event": "b" * 64, "audit_hash": "i" * 64}
    answers = iter([[(fake_record, first, object(), object())], [(fake_record, second, object(), object())]])

    monkeypatch.setattr(gate, "_verify_under_lock", lambda records, root: next(answers))
    monkeypatch.setattr(gate, "load_records", lambda paths: [fake_record])
    monkeypatch.setattr(gate, "export_data", lambda entries, out_dir: None)
    monkeypatch.setattr(gate, "build_web", lambda web_dir: dist_dir)
    # The dirty-tree guard is covered in test_publish_manifest.py; isolate it here.
    monkeypatch.setattr(gate.manifest_mod, "refuse_if_build_inputs_dirty", lambda *a, **k: None)

    with pytest.raises(gate.PublicationRefused, match="approval changed"):
        gate.publish(
            [Path("unused.json")],
            out_dir,
            root=tmp_path / "ledger",
            web_dir=tmp_path / "web",
            web_data_v1=tmp_path / "web_data_v1",
        )

    assert not out_dir.exists()

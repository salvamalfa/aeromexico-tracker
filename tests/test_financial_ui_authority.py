"""A receipt-free later UI build cannot erase the financial authority or its final guard."""

import copy
import json
from types import SimpleNamespace
import pytest
from financial_fixtures import financial_release, install_authorization, git, put
from src.publish import financial_scope as f, financial_sources as source


@pytest.fixture
def release(tmp_path, monkeypatch):
    r = install_authorization(financial_release(tmp_path))
    put(r["repo"] / f.ANCHOR, f.encoded(r["spec"]))
    git(r["repo"], "add", f.ANCHOR)
    git(r["repo"], "commit", "-qm", "exact financial consent pin")
    monkeypatch.setattr(source, "PATHS", SimpleNamespace(root=r["repo"]))
    path = r["repo"] / "record.json"
    put(path, f.encoded({"version": r["spec"]["analysis_entry"]["version"]}))
    r["records"] = [path]
    return r


@pytest.mark.parametrize("part", ["root_record", "root_view", "entity_record", "entity_view"])
def test_removing_one_financial_signal_cannot_hide_the_exposure(release, part):
    r = release
    doc = copy.deepcopy(r["projection"])
    if part == "root_record":
        doc["records"].pop()
    if part == "root_view":
        doc["views"].pop("2026Q3")
    if part == "entity_record":
        doc["entities"]["AEROMEXICO"]["records"].pop()
    if part == "entity_view":
        doc["entities"]["AEROMEXICO"]["views"].pop("2026Q3")
    put(r["site"] / f.EXECUTIVE, f.encoded(doc))
    (r["repo"] / f.ANCHOR).unlink()
    with pytest.raises(ValueError, match="Partial financial"):
        source.verify_preserved_financial(r["records"], r["site"], r["repo"] / "ledger")


def test_existing_financial_quarter_requires_anchor_even_without_any_receipt(release):
    r = release
    (r["repo"] / f.ANCHOR).unlink()
    (r["site"] / f.PROOF).unlink()
    with pytest.raises(ValueError, match="requires its committed financial anchor"):
        source.verify_preserved_financial(r["records"], r["site"], r["repo"] / "ledger")


def test_no_financial_exposure_needs_no_new_authorization(release):
    r = release
    put(r["site"] / f.EXECUTIVE, f.encoded(r["before"]))
    (r["site"] / f.PROOF).unlink()
    (r["repo"] / f.ANCHOR).unlink()
    assert source.verify_preserved_financial(r["records"], r["site"], r["repo"] / "ledger") is None


def test_fast_guard_after_slow_verifier_uses_authority_without_another_slow_replay(release, monkeypatch):
    r = release
    calls = []

    def replay(*args):
        calls.append(True)
        return r["projection"]

    monkeypatch.setattr(source, "approved_projection", replay)
    monkeypatch.setattr(source, "source_snapshot", lambda *args: {"source": "unchanged"})
    snapshot = source.verify_preserved_financial(r["records"], r["site"], r["repo"] / "ledger")
    from src.publish.frozen_data import data_identities

    expected = data_identities(r["site"], flights=True)
    source.validate_ui_financial_candidate(
        r["records"], r["site"], r["site"], r["repo"] / "ledger", snapshot, expected
    )
    assert calls == [True]
    put(r["authorization_path"], r["authorization_path"].read_bytes() + b" ")
    with pytest.raises(ValueError, match="authorization changed"):
        source.validate_ui_financial_candidate(
            r["records"], r["site"], r["site"], r["repo"] / "ledger", snapshot, expected
        )

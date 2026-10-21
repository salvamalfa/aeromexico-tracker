"""Contract tests for primary reference verification, separate from live extraction proof."""

import json
from copy import deepcopy
from urllib.parse import urlencode

import pytest

from src.source_updates import operator_registry as registry


@pytest.fixture
def captures(tmp_path):
    callback = "https://www.iata.org/PublicationDetails/Search/?currentBlock=123&currentPage=456"
    form = (
        '<form data-callback-url="/PublicationDetails/Search/?currentBlock=123&amp;currentPage=456">'
        '<input name="airline.search"></form>'
    )
    data = [("iata-code-search.html", registry.IATA, form)]
    for filename, system, code, cells in registry.EXPECTED:
        url = (
            callback + "&" + urlencode({"airline.search": code})
            if system == "IATA"
            else registry.FAA.format(code[0])
        )
        body = "<table><tr>" + "".join("<td>" + cell + "</td>" for cell in cells) + "</tr></table>"
        data.append((filename, url, body))
    records = []
    for filename, url, body in data:
        path = tmp_path / filename
        path.write_text(body)
        records.append(
            {
                "source_file": filename,
                "source_url": url,
                "sha256": registry.sha(path),
                "bytes": path.stat().st_size,
                "http_status": 200,
                "captured_at": "2026-10-21T00:00:00Z",
                "source_system": "operator_registry_audit_only",
                "catalogue_registration": "not_active_no_alias_relabelling",
            }
        )
    (tmp_path / "capture-results.json").write_text(json.dumps(records))
    return tmp_path, records


def test_literal_primary_rows_do_not_authorize_group_join(captures):
    root, _ = captures
    result = registry.verify(root, "2026-10-21T01:00:00Z")
    assert len(result["records"]) == 4
    assert {r["code"] for r in result["records"]} == {"VB", "FR", "VIV", "RYR"}
    assert all(
        r["issuer_assignment"] is None and not r["group_to_operator_join_verified"] for r in result["records"]
    )
    assert result["network_requests"] == result["writes"] == 0
    assert not result["silver_gold_certification"] and result["activation"] == "none"


@pytest.mark.parametrize("field,value", [("http_status", 403), ("sha256", "0" * 64), ("bytes", 0)])
def test_failed_response_or_tampered_body_is_not_reference(captures, field, value):
    root, records = captures
    records[1][field] = value
    (root / "capture-results.json").write_text(json.dumps(records))
    with pytest.raises(ValueError, match="body/hash/size/HTTP"):
        registry.verify(root, "2026-10-21T01:00:00Z")


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("source_system", "faa_iasa", "active source aliases"),
        ("source_url", "https://example.com/registry", "official query"),
        ("captured_at", "2026-10-22T00:00:00Z", "after the explicit cutoff"),
    ],
)
def test_no_alias_borrowing_url_substitution_or_future_capture(captures, field, value, match):
    root, records = captures
    records[1][field] = value
    (root / "capture-results.json").write_text(json.dumps(records))
    with pytest.raises(ValueError, match=match):
        registry.verify(root, "2026-10-21T01:00:00Z")


def test_callback_must_be_discovered_public_iata_form(captures):
    root, records = captures
    path = root / "iata-code-search.html"
    path.write_text(path.read_text().replace("/PublicationDetails/Search/", "https://example.com/search/"))
    records[0].update(sha256=registry.sha(path), bytes=path.stat().st_size)
    (root / "capture-results.json").write_text(json.dumps(records))
    with pytest.raises(ValueError, match="Unverified public IATA callback"):
        registry.verify(root, "2026-10-21T01:00:00Z")


def test_changed_entity_or_duplicate_code_requires_review(captures):
    root, records = captures
    path = root / "iata-fr.html"
    original = path.read_text()
    path.write_text(original.replace("Ryanair Ltd.", "Ryanair Holdings plc"))
    records[2].update(sha256=registry.sha(path), bytes=path.stat().st_size)
    (root / "capture-results.json").write_text(json.dumps(records))
    with pytest.raises(ValueError, match="review exact entity"):
        registry.verify(root, "2026-10-21T01:00:00Z")
    path.write_text(original + original)
    records[2].update(sha256=registry.sha(path), bytes=path.stat().st_size)
    (root / "capture-results.json").write_text(json.dumps(records))
    with pytest.raises(ValueError, match="review exact entity"):
        registry.verify(root, "2026-10-21T01:00:00Z")


def test_duplicate_receipt_and_symlink_rejected(captures):
    root, records = captures
    records.append(deepcopy(records[1]))
    (root / "capture-results.json").write_text(json.dumps(records))
    with pytest.raises(ValueError, match="Exactly one capture identity"):
        registry.verify(root, "2026-10-21T01:00:00Z")
    records.pop()
    (root / "capture-results.json").write_text(json.dumps(records))
    path = root / "iata-vb.html"
    body = path.read_bytes()
    path.unlink()
    other = root / "other.html"
    other.write_bytes(body)
    path.symlink_to(other)
    with pytest.raises(ValueError, match="symlinks"):
        registry.verify(root, "2026-10-21T01:00:00Z")

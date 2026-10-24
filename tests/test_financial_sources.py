import copy
import json
import pytest
from financial_fixtures import financial_release, install_authorization, put
from src.publish import financial_scope as f
from src.publish import financial_sources as source


@pytest.fixture
def release(tmp_path):
    return install_authorization(financial_release(tmp_path))


def test_exact_financial_consent_is_separate_from_analysis_approval(release):
    r = release
    assert source.authorization(r["spec"], r["repo"]) == r["authorization"]
    assert not (r["repo"] / "analysis_runs/lifecycle").exists()


@pytest.mark.parametrize(
    "change", ["revoked", "output", "package", "baseline", "producer", "new_cards", "consent"]
)
def test_replacing_and_repinning_private_consent_cannot_broaden_or_revoke_scope(release, change):
    r = release
    value = copy.deepcopy(r["authorization"])
    if change == "revoked":
        value["state"] = "revoked"
    if change == "output":
        value["binding"]["executive_sha256"] = "f" * 64
    if change == "package":
        value["binding"]["package_id"] = "another source"
    if change == "baseline":
        value["binding"]["baseline_commit"] = "f" * 40
    if change == "producer":
        value["binding"]["producer_commit"] = "f" * 40
    if change == "new_cards":
        value["constraints"]["new_cards"] = True
    if change == "consent":
        value["owner_consent"] = {}
    raw = f.encoded(value)
    spec = dict(r["spec"], authorization_sha256=f.sha(raw))
    put(
        r["repo"]
        / "analysis_runs/financial_updates/authorizations"
        / (spec["authorization_sha256"] + ".json"),
        raw,
    )
    with pytest.raises(ValueError):
        source.authorization(spec, r["repo"])


def test_private_authorization_byte_change_and_review_byte_change_fail(release):
    r = release
    put(r["authorization_path"], r["authorization_path"].read_bytes() + b" ")
    with pytest.raises(ValueError, match="authorization changed"):
        source.authorization(r["spec"], r["repo"])
    put(r["authorization_path"], f.encoded(r["authorization"]))
    put(r["review_path"], r["review_path"].read_bytes() + b" ")
    with pytest.raises(ValueError, match="review changed"):
        source.authorization(r["spec"], r["repo"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_release_passed", False),
        ("unresolved_findings", ["open"]),
        ("producer_commit", "f" * 40),
        ("executive_sha256", "f" * 64),
    ],
)
def test_even_rehashed_review_must_cover_a_passing_exact_producer(release, field, value):
    r = release
    report = json.loads(r["review_path"].read_bytes())
    report[field] = value
    raw = f.encoded(report)
    report_sha = f.sha(raw)
    put(r["repo"] / "analysis_runs/financial_updates/reviews" / (report_sha + ".json"), raw)
    auth = copy.deepcopy(r["authorization"])
    auth["independent_review_sha256"] = report_sha
    authraw = f.encoded(auth)
    spec = dict(r["spec"], authorization_sha256=f.sha(authraw))
    put(
        r["repo"]
        / "analysis_runs/financial_updates/authorizations"
        / (spec["authorization_sha256"] + ".json"),
        authraw,
    )
    with pytest.raises(ValueError, match="independent review does not cover"):
        source.authorization(spec, r["repo"])

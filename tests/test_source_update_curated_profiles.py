"""Public contract fixtures; real retained-document replay is a separate local proof."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.source_updates import curated_profiles as candidate

RY = """Fiscal year ended March 31 2026 2025 2024 2023 2022
Available seat miles (ASM) 174bn 166bn 152bn 138bn 91bn
Average Sector Length (miles) 790 783 780 766 772
Passengers Booked (millions) 208 200 184 169 97
Booked Passenger Load Factor 94%"""
VIVA = """Grupo Viva Aerobus, S.A. de C.V. and Subsidiaries
Three-month period ended June 30, 2026 and 2025
Financial Information in Thousands of U.S. Dollars, unless otherwise stated
2Q 2026 2Q 2025 % Var
Total operating revenue 608,874 549,204 10.9%
ASMs (millions) 5,789 6,273 -7.7% Domestic 4,786 5,075 -5.7% International 1,003 1,198 -16.2%
RPMs (millions) 4,953 5,355 -7.5% Domestic 4,175 4,436 -5.9% International 778 919 -15.3%
Booked Passengers (thousands) 7,208 7,482 -3.7% Domestic 6,513 6,671 -2.4% International 695 811 -14.4%
Load Factor (scheduled, RPM/ASM) 85.9% 85.8% 0.1pp
TRASM (US cents) 10.52 8.75 20.1%
CASM (US cents) 11.18 8.21 36.2%"""


@pytest.fixture
def fixture_report(tmp_path, monkeypatch):
    ry = tmp_path / "source.html"
    ry.write_text("<html><body>" + RY + "</body></html>")
    viva = tmp_path / "source.pdf"
    viva.write_bytes(b"unit contract fixture, not retained source evidence")
    verified = []
    monkeypatch.setattr(candidate.primary_review, "verify", lambda *args: verified.append(True) or {})
    monkeypatch.setattr(
        candidate.primary_review,
        "original",
        lambda root, source: ry if source["source_id"] == "ry_annual" else viva,
    )
    monkeypatch.setattr(
        candidate,
        "PdfReader",
        lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: VIVA)] * 12),
    )
    bundle = {"sources": {}}
    for source_id, sha in candidate.EDITIONS.items():
        bundle["sources"][source_id] = {
            "source_id": source_id,
            "sha256": sha,
            "source_system": "viva_ir" if source_id == "viva_q2" else "sec",
            "source_file": "fixture_" + source_id,
            "source_url": "https://example.com/fixture",
            "downloaded_at": "2026-08-24T03:14:57Z",
        }
    return bundle, {"old_public": tmp_path}, tmp_path, ry, verified


def build(fixture_report):
    bundle, roots, repository, _, _ = fixture_report
    return candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z")


def test_native_units_entity_and_annual_scope_are_explicit(fixture_report):
    result = build(fixture_report)
    gold = result[candidate.OUTPUTS[1]]
    by_key = {(r["source_id"], r["metric"]): r for r in gold["records"]}
    assert len(by_key) == 11
    assert by_key["ry_annual", "asm"]["value_normalized"] == "174000000000"
    assert by_key["ry_annual", "asm"]["unit_normalized"] == "seat_miles"
    assert by_key["ry_annual", "asm"]["period"] == "FY2026"
    assert by_key["viva_q2", "passengers_booked"]["value_normalized"] == "7208000"
    assert by_key["viva_q2", "total_operating_revenue"]["value_normalized"] == "608874000"
    assert by_key["viva_q2", "total_operating_revenue"]["unit_raw"] == "thousand USD"
    assert all(
        r["operating_carrier_iata"] is None and r["operating_carrier_icao"] is None for r in gold["records"]
    )
    assert all(r["publication_date"] is None and r["release_lag_days"] is None for r in gold["records"])
    assert not gold["agent_eligible"] and gold["activation"] == "none"
    assert fixture_report[-1] == [True]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("unit_normalized", "seat_kilometers", "unit/scale"),
        ("scale_multiplier", "1000", "unit/scale"),
        ("period", "2026Q2", "annual issuer scope"),
        ("entity_id", "RYANAIR_DAC", "annual issuer scope"),
        ("operating_carrier_icao", "RYR", "operator attribution"),
        ("publication_date", "2026-06-22", "first publication"),
        ("source_sha256", "0" * 64, "Unverified edition"),
    ],
)
def test_unverified_relabels_and_inferred_dates_rejected(fixture_report, field, value, reason):
    rows = deepcopy(build(fixture_report)[candidate.OUTPUTS[1]]["records"])
    rows[0][field] = value
    with pytest.raises(ValueError, match=reason):
        candidate.validate(rows, normalized=True)


def test_wrong_period_header_and_changed_edition_fail_closed(fixture_report, monkeypatch):
    bundle, roots, repository, _, _ = fixture_report
    monkeypatch.setattr(
        candidate,
        "PdfReader",
        lambda path: SimpleNamespace(
            pages=[SimpleNamespace(extract_text=lambda: VIVA.replace("2Q 2026", "6M 2026"))] * 12
        ),
    )
    with pytest.raises(ValueError, match="header changed"):
        candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z")
    bundle["sources"]["viva_q2"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="edition has not been reviewed"):
        candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z")


def test_duplicate_row_wrong_totals_and_missing_not_zero(fixture_report, monkeypatch):
    bundle, roots, repository, ry, _ = fixture_report
    ry.write_text("<html>" + RY + " Booked Passenger Load Factor 94%</html>")
    with pytest.raises(ValueError, match="exactly one"):
        candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z")
    ry.write_text("<html>" + RY + "</html>")
    monkeypatch.setattr(
        candidate,
        "PdfReader",
        lambda path: SimpleNamespace(
            pages=[SimpleNamespace(extract_text=lambda: VIVA.replace("4,786", "4,785"))] * 12
        ),
    )
    with pytest.raises(ValueError, match="totals do not reconcile"):
        candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z")
    for token in ["", "N/A", "NaN", "Infinity", "1,23", None, True]:
        with pytest.raises(ValueError, match="source number"):
            candidate.number(token)


def test_normalized_contract_and_grain(fixture_report):
    rows = deepcopy(build(fixture_report)[candidate.OUTPUTS[1]]["records"])
    rows[0]["value_normalized"] = "174"
    with pytest.raises(ValueError, match="Normalized value"):
        candidate.validate(rows, normalized=True)
    rows = deepcopy(build(fixture_report)[candidate.OUTPUTS[1]]["records"])
    with pytest.raises(ValueError, match="Duplicate"):
        candidate.validate(rows + [rows[0]], normalized=True)
    with pytest.raises(ValueError, match="missing a required"):
        candidate.validate(rows[1:], normalized=True)


def test_dry_run_idempotent_replay_no_overwrite_and_explicit_baseline(fixture_report, monkeypatch):
    bundle, roots, repository, _, _ = fixture_report
    workspace = repository / "candidate"
    monkeypatch.setattr(candidate, "safe_workspace", lambda path: path)
    monkeypatch.setattr("src.source_updates.collection.safe_workspace", lambda path: path)
    args = (bundle, roots, repository, workspace)
    assert candidate.run(*args, as_of="2026-10-21T00:00:00Z")["writes"] == 0
    assert not workspace.exists()
    assert candidate.run(*args, as_of="2026-10-21T00:00:00Z", execute=True)["writes"] == 3
    before = {p: p.read_bytes() for p in workspace.rglob("*.json")}
    assert candidate.run(*args, as_of="2026-10-21T00:00:00Z", execute=True)["status"] == "idempotent_existing"
    assert candidate.run(*args, as_of="2026-10-21T00:00:00Z", check=True)["status"] == "verified_identical"
    baseline = json.loads((workspace / candidate.OUTPUTS[1]).read_text())
    comparison = candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z", baseline=baseline)[
        candidate.OUTPUTS[-1]
    ]["revision"]
    assert comparison["unchanged"] == 11 and comparison["changed"] == 0
    baseline["approval_granted"] = True
    with pytest.raises(ValueError, match="cannot confer approval"):
        candidate.build(bundle, roots, repository, as_of="2026-10-21T00:00:00Z", baseline=baseline)
    target = workspace / candidate.OUTPUTS[1]
    target.write_text("invalid")
    with pytest.raises(ValueError, match="replay differs"):
        candidate.run(*args, as_of="2026-10-21T00:00:00Z", check=True)
    with pytest.raises(ValueError, match="different artifacts"):
        candidate.run(*args, as_of="2026-10-21T00:00:00Z", execute=True)
    assert target.read_text() == "invalid"
    assert all(p.read_bytes() == b for p, b in before.items() if p != target)


def test_invalid_source_never_writes_candidate(fixture_report, monkeypatch):
    bundle, roots, repository, _, _ = fixture_report
    monkeypatch.setattr(candidate, "safe_workspace", lambda path: path)
    bundle["sources"]["ry_annual"]["sha256"] = "f" * 64
    workspace = repository / "candidate"
    with pytest.raises(ValueError, match="edition has not been reviewed"):
        candidate.run(bundle, roots, repository, workspace, as_of="2026-10-21T00:00:00Z", execute=True)
    assert not workspace.exists()


@pytest.mark.parametrize("check", [False, True])
def test_candidate_inventory_cannot_hide_an_unreviewed_gold_file(fixture_report, monkeypatch, check):
    bundle, roots, repository, _, _ = fixture_report
    workspace = repository / "candidate"
    monkeypatch.setattr(candidate, "safe_workspace", lambda path: path)
    monkeypatch.setattr("src.source_updates.collection.safe_workspace", lambda path: path)
    args = (bundle, roots, repository, workspace)
    candidate.run(*args, as_of="2026-10-21T00:00:00Z", execute=True)
    stray = workspace / "gold/unreviewed.json"
    stray.write_text('{"approval_granted":true}')
    with pytest.raises(ValueError, match="artifacts"):
        candidate.run(*args, as_of="2026-10-21T00:00:00Z", check=check, execute=not check)
    assert stray.read_text() == '{"approval_granted":true}'


@pytest.mark.parametrize("cutoff", ["2026-08-01T00:00:00Z", "2026-10-21T00:00:00"])
def test_explicit_cutoff_cannot_accept_later_capture_or_naive_time(fixture_report, cutoff):
    bundle, roots, repository, _, _ = fixture_report
    with pytest.raises(ValueError):
        candidate.build(bundle, roots, repository, as_of=cutoff)

"""Monthly publication extends, rather than replaces, P1 routing controls."""

import json
import subprocess

import pytest

from scripts import source_update_handoffs as handoffs
from scripts import source_update_handoff_routing as routing
from scripts import source_update_monthly_handoff as monthly
from tests.test_check_pages_publication import manifest
from scripts.check_pages_publication import verifier_for


@pytest.mark.parametrize(
    "receipts,expected",
    [
        (
            [
                "issuer-publication.json",
                "aerocivil-movements-publication.json",
                "source-data-publication.json",
            ],
            "src.publish.source_data_scope",
        ),
        (
            [
                "source-data-publication.json",
                "issuer-publication.json",
                "aerocivil-movements-publication.json",
            ],
            "src.publish.movements_scope",
        ),
    ],
)
def test_current_git_baseline_decides_between_monthly_and_movements(tmp_path, receipts, expected):
    repo = manifest(tmp_path, receipts)
    assert verifier_for(tmp_path, repo) == expected


@pytest.mark.parametrize(
    "product,outer,native,cadence,adapter",
    [
        ("aerocivil", "2026Q3", "2026M07", "quarterly", "aerocivil"),
        ("afac_carriers", "2026M09", "2026M08", "monthly", "afac_carriers"),
        ("bts_segments", "2026M09", "2026M07", "monthly", "bts_segments"),
    ],
)
def test_expected_binding_chains_monthly_and_aerocivil_native_periods(
    product, outer, native, cadence, adapter
):
    item = {
        "id": product,
        "product": product,
        "period": outer,
        "source_period": native,
        "cadence": cadence,
        "adapter": adapter,
        "used": True,
        "required": True,
        "depends_on": [],
        "workspace": "/retained/candidate",
        "receipt_id": "retained",
        "candidate_as_of": "2026-10-28T00:00:00Z",
    }
    source = {"source_binding": {"item": item}, "checked": {"output_sha256": {"gold/fact": "a" * 64}}}
    assert handoffs.expected_binding(source)["period"] == native
    assert routing.native_item(monthly.native_item(item))["period"] == native
    assert source["source_binding"]["item"]["period"] == outer


@pytest.mark.parametrize("product", ["viva_traffic", "volaris_traffic_ir"])
def test_peer_monthly_envelope_names_its_corporate_booked_basis(product):
    scope = monthly.publication_scope(product)
    assert "booked passenger" in scope and "airport-demand" not in scope
    assert "preserve AFAC" in scope and "same-edition" in scope


def test_afac_airport_scope_is_a_separate_finite_basis():
    scope = monthly.publication_scope("afac_airports")
    assert "AFAC alternative" in scope and "selected existing" in scope
    assert "preserve direct issuer reports" in scope and "no new airports" in scope


def release_spec(commit):
    return {
        "product": "am_traffic_ir",
        "period_id": "2026M09",
        "baseline_commit": commit,
        "source_binding": {
            "product": "am_traffic_ir",
            "period": "2026M09",
            "receipt_id": "a" * 32,
            "candidate_as_of": "2026-10-28T00:00:00Z",
            "output_sha256": {"gold/fact": "b" * 64},
        },
        "projection": {},
    }


def test_recovery_replays_frozen_target_bytes_not_the_already_changed_site(tmp_path):
    from src.publish.source_data_nochange import frozen_target_baseline

    repo = tmp_path / "repo"
    site = repo / "site"
    target = site / "data/v1/flights/quarters.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"edition": "original-inspected-baseline"}))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "add", "site"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
        cwd=repo,
        check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    original = target.read_bytes()
    target.write_text(json.dumps({"edition": "already-published-new-data"}))
    changed = target.read_bytes()
    with frozen_target_baseline(repo, release_spec(commit)) as baseline:
        frozen = baseline
        assert (baseline / "data/v1/flights/quarters.json").read_bytes() == original
        assert baseline != site and target.read_bytes() == changed
        assert [p.relative_to(baseline).as_posix() for p in baseline.rglob("*") if p.is_file()] == [
            "data/v1/flights/quarters.json"
        ]
    assert not frozen.exists() and target.read_bytes() == changed
    with pytest.raises(subprocess.CalledProcessError):
        with frozen_target_baseline(repo, release_spec("f" * 40)):
            pytest.fail("Missing frozen Git bytes must not fall back to the current site")
    assert target.read_bytes() == changed


def test_recovery_rejects_a_redirected_scratch_directory(tmp_path):
    from src.publish.source_data_nochange import frozen_target_baseline

    repo, external = tmp_path / "repo", tmp_path / "elsewhere"
    repo.mkdir()
    external.mkdir()
    (repo / "tmp").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="physical scratch"):
        with frozen_target_baseline(repo, release_spec("f" * 40)):
            pytest.fail("Redirected scratch cannot receive a recovered baseline")
    assert not list(external.iterdir())

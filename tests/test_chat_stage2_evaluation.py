from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.conversational_analytics.evaluation import verify_observation


def test_quarter_aliases_accept_equivalents_and_reject_wrong_period() -> None:
    from src.conversational_analytics.evaluation_response_checks import (
        response_term_present as _response_term_present,
    )

    for actual in ("2026Q2", "2026 Q2", "2Q26", "2T26"):
        assert _response_term_present("2026Q2", f"Public dashboard period: {actual}.")
    for actual in ("2026Q1", "1Q26", "2T25"):
        assert not _response_term_present("2026Q2", f"Public dashboard period: {actual}.")


def test_stage2_fixture_is_frozen_to_budget_and_preserves_source_lineage() -> None:
    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.evaluation import (
        BUSINESS_FIXTURE_PATH,
        SAFETY_CURRENT_FIXTURE_PATH,
        STAGE2_PILOT_FIXTURE_PATH,
        phase_cases,
    )
    from src.conversational_analytics.semantic.context import validate_context
    from src.conversational_analytics.service import validate_context as validate_service_context
    from src.conversational_analytics.tools.registry import ToolRegistry

    business = json.loads(BUSINESS_FIXTURE_PATH.read_text(encoding="utf-8"))
    safety = json.loads(SAFETY_CURRENT_FIXTURE_PATH.read_text(encoding="utf-8"))
    derived = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    selected = phase_cases(business["cases"], safety["cases"], 2)
    assert [case["id"] for case in selected] == [case["id"] for case in derived["cases"]]
    assert len(selected) == 15
    for source_name, path in (
        ("business_proposed", BUSINESS_FIXTURE_PATH),
        ("safety_current", SAFETY_CURRENT_FIXTURE_PATH),
    ):
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert derived["lineage"]["source_fixtures"][source_name]["sha256"] == digest
    originals = {
        case["id"]: case
        for source in (business["cases"], safety["cases"])
        for case in source
    }
    for case in derived["cases"]:
        original = originals[case["id"]]
        for field in ("question", "locale", "turns", "rubric", "critical_failures"):
            if field in original:
                assert case.get(field) == original[field]
    registry = ToolRegistry(Snapshot("site"))
    context_case_ids = set()
    for case in derived["cases"]:
        if case.get("context"):
            context_case_ids.add(case["id"])
            semantic_context = validate_context(case["context"])
            service_context = validate_service_context(case["context"])
            result = registry.invoke("get_dashboard_context", {}, context=case["context"])
            assert service_context == semantic_context == result["context"] == case["context"]
    assert {
        "N02", "N11", "N12", "N13", "en_relative_share_change", "es_ratio_average"
    } <= context_case_ids


def test_stage2_snapshot_audit_is_reproducible_and_does_not_grade_model_quality(
    tmp_path: Path, monkeypatch,
) -> None:
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH, audit_snapshot
    from tests._news_runtime_fixtures import _pin_approved_content
    from tests._stage2_historical_snapshot import historical_stage2_snapshot

    _pin_approved_content(monkeypatch)
    fixture_bytes = STAGE2_PILOT_FIXTURE_PATH.read_bytes()
    payload = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    with historical_stage2_snapshot(tmp_path / "historical-stage2") as snapshot:
        assert snapshot.version != payload["expected_versions"]["data_version"]
        report = audit_snapshot(snapshot, payload["cases"], expected_versions=payload["expected_versions"])

    from src.conversational_analytics.evidence_index import EvidenceIndex, EvidenceIndexError

    # The historical exception ends with the exact audit; today's trusted pin
    # must reject the old index outside that context.
    with pytest.raises(EvidenceIndexError, match="SHA-256"):
        EvidenceIndex(snapshot.project_root / "config/chat/evidence/approved-index.json")

    assert report["mode"] == "offline-snapshot-audit"
    assert report["cases_total"] == 15
    assert report["snapshot_cases_checked"] == report["snapshot_cases_passed"] == 13
    # A pinned historical publication preserves all thirteen frozen numeric
    # references. Its identity still differs from the earlier campaign fixture.
    mismatch = {
        "data_version": {
            "expected": payload["expected_versions"]["data_version"],
            "actual": snapshot.version,
        },
        "semantic_version": {
            "expected": payload["expected_versions"]["semantic_version"],
            "actual": snapshot.semantic_version,
        },
    }
    assert report["snapshot_cases_failed"] == [{"id": "fixture-version", "failures": mismatch}]
    assert report["fixture_version_mismatches"] == mismatch
    assert set(report["model_quality_cases_pending"]) == {"N20", "es_ratio_average"}
    assert report["quality_denominator"] == 0
    assert STAGE2_PILOT_FIXTURE_PATH.read_bytes() == fixture_bytes


def _stage2_market_publication(site, root):
    """Follow exact Fare parents without replacing the separate strong gate replay."""
    import io
    import re
    import tarfile
    import tempfile
    from contextlib import ExitStack

    from scripts.check_pages_publication import verifier_for
    from src.publish import editorial, fare_scope, manifest
    from tests._site_publication_parity import _active_module

    profile = verifier_for(site, root)
    if profile != "src.publish.fare_scope":
        return profile, None
    edition, seen = None, set()
    with ExitStack() as stack:
        while profile == "src.publish.fare_scope":
            if edition is None:
                proof, current = fare_scope.read_proof(site, root)
            else:
                # This whole edition was just matched to its pinned Git manifest.
                # Historical policy/contract bytes belong to its own producer.
                raw = (site / fare_scope.PROOF).read_bytes()
                proof = json.loads(raw)
                assert set(proof) == fare_scope.FIELDS and proof["schema_version"] == fare_scope.SCHEMA
                assert all(re.fullmatch("[a-f0-9]{64}", proof[key])
                           for key in fare_scope.FIELDS - {"schema_version", "baseline_commit"})
                assert re.fullmatch("[a-f0-9]{40}", proof["baseline_commit"])
                producer = current["code_commit"]
                assert proof["baseline_commit"] != producer
                editorial._git(root, "merge-base", "--is-ancestor", producer, edition)
                editorial._git(root, "merge-base", "--is-ancestor", proof["baseline_commit"], producer)
                pin = next(row for row in current["files"] if row["path"] == fare_scope.PROOF)
                assert (pin["sha256"], pin["bytes"]) == (fare_scope.sha(raw), len(raw))
                for field, path in (
                    ("policy_sha256", fare_scope.POLICY),
                    ("public_contract_sha256", "contracts/web/fare-averages.schema.json"),
                ):
                    assert proof[field] == fare_scope.sha(editorial._git(root, "show", f"{producer}:{path}"))
                assert proof["aggregate_sha256"] == fare_scope.sha((site / fare_scope.DATA).read_bytes())
            baseline, raw = editorial.baseline(root, proof)
            assert current["analysis_manifest"] == baseline["analysis_manifest"]
            retained = {row["path"]: (row["sha256"], row["bytes"]) for row in baseline["files"]}
            assert fare_scope.protected(fare_scope.public_files(site)) == fare_scope.protected(retained)
            edition = proof["baseline_commit"]
            assert edition not in seen, "Cyclic Fare baseline"
            seen.add(edition)
            folder = stack.enter_context(tempfile.TemporaryDirectory(prefix="stage2-fare-parent-"))
            archive = editorial._git(root, "archive", edition, "site")
            with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
                stream.extractall(folder, filter="data")
            site = Path(folder) / "site"
            assert (site / manifest.MANIFEST_NAME).read_bytes() == raw
            assert {row["path"]: (row["sha256"], row["bytes"])
                    for row in manifest.file_entries(site)} == retained
            current = baseline
            profile = _active_module(site, root, current, edition)
        source_spec = None
        if profile == "src.publish.source_data_scope":
            from src.publish import source_data_scope

            producer = current["code_commit"]
            editorial._git(root, "merge-base", "--is-ancestor", producer, edition)
            raw = editorial._git(root, "show", f"{producer}:{source_data_scope.ANCHOR}")
            source_spec = json.loads(raw)
            receipt = json.loads((site / source_data_scope.PROOF).read_bytes())
            assert receipt["anchor_sha256"] == fare_scope.sha(raw)
            assert receipt["remote_witness"]["baseline_commit"] == source_spec["baseline_commit"]
            assert receipt["remote_witness"]["manifest_sha256"] == source_spec["baseline_manifest_sha256"]
        return profile, source_spec


def test_stage2_fare_market_parent_rejects_rewritten_market_and_proof(tmp_path):
    import shutil

    from scripts.check_pages_publication import verifier_for
    from src.publish import editorial, fare_scope

    root = Path(__file__).resolve().parents[1]
    original = root / "site"
    if verifier_for(original, root) != "src.publish.fare_scope":
        pytest.skip("Current publication is not a Fare overlay")
    site = tmp_path / "site"
    shutil.copytree(original, site)
    assert _stage2_market_publication(site, root)[0] == "src.publish.source_data_scope"
    market = site / "data/v1/market.json"
    raw = market.read_bytes()
    market.write_bytes(raw + b"\n")
    with pytest.raises(AssertionError):
        _stage2_market_publication(site, root)
    market.write_bytes(raw)
    proof = site / fare_scope.PROOF
    proof_raw = proof.read_bytes()
    proof.write_bytes(proof_raw + b"\n")
    with pytest.raises(ValueError, match="proof differs"):
        _stage2_market_publication(site, root)
    manifest_path = site / "publication_manifest.json"
    manifest_raw = manifest_path.read_bytes()
    for field, value, error in (
        ("baseline_manifest_sha256", "0" * 64, "Baseline manifest differs"),
        ("baseline_commit", editorial._git(root, "rev-parse", "HEAD").decode().strip(),
         "outside publication history"),
    ):
        forged = {**json.loads(proof_raw), field: value}
        raw = json.dumps(forged).encode()
        proof.write_bytes(raw)
        changed = json.loads(manifest_raw)
        pin = next(row for row in changed["files"] if row["path"] == fare_scope.PROOF)
        pin.update(sha256=fare_scope.sha(raw), bytes=len(raw))
        manifest_path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match=error):
            _stage2_market_publication(site, root)
    manifest_path.write_bytes(manifest_raw)
    proof.write_bytes(proof_raw)
    changed = json.loads(manifest_raw)
    assert len(changed["analysis_manifest"]) == 8
    changed["analysis_manifest"].pop()
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(AssertionError):
        _stage2_market_publication(site, root)


def test_stage2_market_follows_two_committed_fare_layers(tmp_path, monkeypatch):
    import io
    import shutil
    import subprocess
    import tarfile

    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH, audit_snapshot
    from src.publish import editorial, fare_scope
    from tests._news_runtime_fixtures import _pin_approved_content

    _pin_approved_content(monkeypatch)
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "git-view"
    subprocess.run(["git", "clone", "--shared", "--no-checkout", str(root), str(repo)],
                   check=True, capture_output=True)
    editorial._git(repo, "read-tree", "HEAD")
    editorial._git(repo, "-c", "user.name=Stage2 fixture", "-c", "user.email=fixture@example.invalid",
                   "commit", "--allow-empty", "-qm", "metadata-only nested Fare fixture")
    # The real selector executes its composition check in this isolated checkout.
    archive = editorial._git(repo, "archive", "HEAD", "src", "config", "contracts")
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(repo, filter="data")
    site = repo / "site"
    shutil.copytree(root / "site", site)
    # Wrap the genuinely committed first Fare edition, preserving all its data.
    parent = editorial._git(root, "log", "-1", "--format=%H", "--", "site").decode().strip()
    parent_raw = editorial._git(root, "show", f"{parent}:site/publication_manifest.json")
    current = json.loads((site / "publication_manifest.json").read_bytes())
    proof = json.loads((site / fare_scope.PROOF).read_bytes())
    proof.update(baseline_commit=parent, baseline_manifest_sha256=fare_scope.sha(parent_raw))
    raw = json.dumps(proof).encode()
    (site / fare_scope.PROOF).write_bytes(raw)
    pin = next(row for row in current["files"] if row["path"] == fare_scope.PROOF)
    pin.update(sha256=fare_scope.sha(raw), bytes=len(raw))
    current["code_commit"] = editorial._git(repo, "rev-parse", "HEAD").decode().strip()
    (site / "publication_manifest.json").write_text(json.dumps(current), encoding="utf-8")
    editorial._git(repo, "add", "site")
    editorial._git(repo, "-c", "user.name=Stage2 fixture", "-c", "user.email=fixture@example.invalid",
                   "commit", "-qm", "nested Fare site metadata fixture")
    assert (site / "publication_manifest.json").read_bytes() == editorial._git(
        repo, "show", "HEAD:site/publication_manifest.json"
    )
    profile, spec = _stage2_market_publication(site, repo)
    assert profile == "src.publish.source_data_scope" and spec["product"] == "official_routes"
    assert current["analysis_manifest"] == json.loads(parent_raw)["analysis_manifest"]
    fixture_raw = STAGE2_PILOT_FIXTURE_PATH.read_bytes()
    fixture = json.loads(fixture_raw)
    report = audit_snapshot(Snapshot(site), fixture["cases"], expected_versions=fixture["expected_versions"])
    assert (report["snapshot_cases_checked"], report["snapshot_cases_passed"]) == (13, 11)
    failures = report["snapshot_cases_failed"]
    assert [row["id"] for row in failures] == [
        "fixture-version", "en_relative_share_change", "es_am_market_share",
    ]
    assert len(failures[1]["failures"]) == 2 and len(failures[2]["failures"]) == 1
    assert report["quality_denominator"] == 0
    assert STAGE2_PILOT_FIXTURE_PATH.read_bytes() == fixture_raw


def test_stage2_current_snapshot_reports_both_exact_afac_drifts_without_rewriting_gold(monkeypatch):
    import hashlib

    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH, audit_snapshot
    from tests._news_runtime_fixtures import _pin_approved_content

    _pin_approved_content(monkeypatch)
    fixture_bytes = STAGE2_PILOT_FIXTURE_PATH.read_bytes()
    payload = json.loads(fixture_bytes)
    root = Path(__file__).resolve().parents[1]
    market_raw = (root / "site/data/v1/market.json").read_bytes()
    profile, source_spec = _stage2_market_publication(root / "site", root)
    native = profile == "src.publish.afac_history_scope"
    if profile == "src.publish.source_data_scope":
        from src.publish import source_data_scope

        # The official map overlays the site without changing the AFAC market data.
        spec = source_spec if source_spec is not None else source_data_scope.anchor(root)
        assert spec["product"] == "official_routes"
        assert [row["path"] for row in spec["data_files"]] == ["data/v1/official-routes.json"]
        baseline, _ = source_data_scope.transport.baseline(root, spec)
        retained = {row["path"]: row["sha256"] for row in baseline["files"]}
        assert hashlib.sha256(market_raw).hexdigest() == retained["data/v1/market.json"]
        afac_proof = "afac-history-publication.json"
        assert hashlib.sha256((root / "site" / afac_proof).read_bytes()).hexdigest() == retained[afac_proof]
        native = True
    assert native or profile == "src.publish.quarterly_story_scope"
    anchor_name = "afac-history-release.json" if native else "quarterly-story-release.json"
    anchor = json.loads((root / "config/publish" / anchor_name).read_bytes())
    pin = next(row for row in anchor["scope"]["data_files"] if row["path"] == "data/v1/market.json")
    assert pin["sha256"] == (
        "10abb8b86ae0f4a7153691e479d9c8da1fc163badf625d172a6197646a096b88" if native
        else "6421acaf6b424b6dfa2684e5dedc77294ab9a5887a33675dee64d4785cda30e0"
    )
    assert hashlib.sha256(market_raw).hexdigest() == pin["sha256"]
    market = json.loads(market_raw)
    months = [
        row["segments"]["domestic"] for row in market["months"]
        if row["period_id"] in {"2026M04", "2026M05", "2026M06"}
    ]
    assert len(months) == 3
    denominator = sum(row["mexican_carriers_passengers"] for row in months)
    passengers = sum(row["carriers"]["AEROMEXICO"]["passengers"] for row in months)
    assert denominator == 15_861_764 and passengers == 3_856_840
    current = passengers / denominator
    frozen = passengers / 15_847_210
    assert current == 0.24315328358182609 and frozen == 0.24337659436582212
    previous = next(row for row in market["quarters"] if row["period_id"] == "2025Q2")["segments"]["domestic"]
    assert previous["carriers"]["AEROMEXICO"]["passengers"] == 4_039_797
    assert previous["mexican_carriers_passengers"] == (15_952_449 if native else 15_936_290)
    previous_share = 4_039_797 / previous["mexican_carriers_passengers"]
    frozen_previous = 4_039_797 / 15_936_290
    snapshot = Snapshot(root / "site")
    report = audit_snapshot(snapshot, payload["cases"], expected_versions=payload["expected_versions"])
    assert report["snapshot_cases_checked"] == 13
    assert report["snapshot_cases_passed"] == 11
    assert set(report["fixture_version_mismatches"]) == {"data_version", "semantic_version"}
    failures = report["snapshot_cases_failed"]
    assert failures[0] == {"id": "fixture-version", "failures": report["fixture_version_mismatches"]}
    current_failure = f"valor incorrecto para market_share: {current} != {frozen}"
    previous_failure = f"valor incorrecto para market_share: {previous_share} != {frozen_previous}"
    assert failures[1:] == [
        {"id": "en_relative_share_change", "failures": (
            (previous_failure, current_failure) if native else (current_failure,)
        )},
        {"id": "es_am_market_share", "failures": (current_failure,)},
    ]
    assert set(report["model_quality_cases_pending"]) == {"N20", "es_ratio_average"}
    assert report["quality_denominator"] == 0
    assert STAGE2_PILOT_FIXTURE_PATH.read_bytes() == fixture_bytes
    assert (root / "site/data/v1/market.json").read_bytes() == market_raw


def test_clarification_accepts_imperatives_without_invented_numeric_answers() -> None:
    from src.conversational_analytics.evaluation_live_scoring import score_live_case

    case = {
        "id": "clarify-case",
        "expected": {"status": "clarify"},
    }
    options = {
        "expected_versions": {},
        "scope": {},
        "metric_dimensions": {},
    }
    _, reasonable = score_live_case(
        case, [], "Please specify the quarter and segment.", **options
    )
    assert reasonable["passed"], reasonable["failures"]

    _, questionless = score_live_case(
        case, [], "Which quarter should I use to compare the carriers", **options
    )
    assert questionless["passed"], questionless["failures"]

    _, invented = score_live_case(
        case, [], "Please specify the quarter; the share fell by 8.9%.", **options
    )
    assert not invented["passed"]
    assert "numeric_answer_given_when_clarification_expected" in invented["failures"]


def test_relative_share_gold_rejects_percentage_points_labeled_as_percent() -> None:
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH

    payload = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    case = next(case for case in payload["cases"] if case["id"] == "en_relative_share_change")
    rows = [
        {
            **row,
            "availability": "available",
        }
        for row in case["expected"]["rows"]
    ]
    valid = verify_observation(
        case,
        {
            "status": "supported",
            "plan": case["expected"]["plan"],
            "rows": rows,
            "response": "Relative change: -3.99% from 2T25 to 2T26; separate share-point delta is -1.01 pp.",
        },
    )
    assert valid.passed, valid.failures

    confused = verify_observation(
        case,
        {
            "status": "supported",
            "plan": case["expected"]["plan"],
            "rows": rows,
            "response": "Relative change: -3.99% from 2T25 to 2T26; this is the same as -1.01%.",
        },
    )
    assert not confused.passed
    assert "percentage_point_delta_mislabelled_as_relative_percent" in confused.failures


def test_viva_missing_company_gold_allows_labeled_afac_with_evidence_only() -> None:
    from src.conversational_analytics.evaluation import STAGE2_PILOT_FIXTURE_PATH
    from src.conversational_analytics.evaluation_live_scoring import score_live_case

    payload = json.loads(STAGE2_PILOT_FIXTURE_PATH.read_text(encoding="utf-8"))
    case = next(case for case in payload["cases"] if case["id"] == "es_viva_missing_company_passengers")
    versions = payload["expected_versions"]
    scope = {}
    metric_dimensions = {
        "afac_passengers": ["segment"],
        "company_passengers": ["segment"],
    }
    plan = case["expected"]["plan"]
    row = case["expected"]["rows"][0]
    tool_calls = [{
        "name": "query_metrics",
        "arguments": {
            "metric_ids": plan["metric_ids"],
            "entity_ids": plan["entity_ids"],
            "periods": plan["periods"],
            "segment": "total",
        },
        "scope": scope,
        "result": {**versions, "rows": [row], "truncated": False},
    }]
    options = {
        "expected_versions": versions,
        "scope": scope,
        "metric_dimensions": metric_dimensions,
    }
    _, labeled_afac = score_live_case(
        case,
        tool_calls,
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22 y comparó la serie con 1T23; "
            "la serie reportada por la empresa no está disponible."
        ),
        **options,
    )
    assert labeled_afac["passed"], labeled_afac["failures"]

    absent_only_response = (
        "Para Viva no hay dato de empresa publicado para 2T22; "
        "la serie de pasajeros de la compañía no está disponible."
    )
    absent_only_observation, absent_only = score_live_case(
        case, [], absent_only_response, **options
    )
    assert absent_only_observation["status"] == "supported_alternative"
    assert absent_only["passed"], absent_only
    assert absent_only["automatic_grade_type"] == "fixture_defined_safe_response_alternative"

    unavailable_company_query = [{
        "name": "query_metrics",
        "arguments": {
            "metric_ids": ["company_passengers"],
            "entity_ids": ["VIVA_AEROBUS"],
            "periods": ["2022Q2"],
            "segment": "total",
        },
        "scope": scope,
        "result": {**versions, "rows": [], "truncated": False},
    }]
    queried_absence_observation, queried_absence = score_live_case(
        case, unavailable_company_query, absent_only_response, **options
    )
    assert queried_absence_observation["status"] == "supported_alternative"
    assert queried_absence["passed"], queried_absence

    for response in (
        (
            "Viva reportó 4,876,764 pasajeros; la cifra también aparece en AFAC y no está disponible "
            "para la empresa."
        ),
        (
            "En 2T22, 4,876,764 pasajeros fueron reportados por Viva según AFAC; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC reportó 4,876,764 pasajeros para Viva; Viva informó 4,876,764 pasajeros; "
            "la serie no está disponible para la empresa."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22, cifra que la empresa reportó; "
            "la serie de pasajeros no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22, cifra que Viva comunicó; "
            "la serie de pasajeros no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22, "
            "cifra reportada por la compañía; la serie no está disponible para la empresa."
        ),
    ):
        _, misattributed = score_live_case(case, tool_calls, response, **options)
        assert not misattributed["passed"]
        assert "AFAC_value_misrepresented_as_company_report" in misattributed["failures"]

    _, invented = score_live_case(
        case,
        tool_calls,
        (
            "AFAC registró 4,876,764 pasajeros de Viva y 5,000,000 pasajeros; "
            "la serie de empresa no está disponible."
        ),
        **options,
    )
    assert not invented["passed"]
    assert "unsupported_or_incorrect_passenger_count" in invented["failures"]

    for response in (
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22; el dato corregido sería 5,000,000; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22; la cifra comparable fue 5,000,000; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22 y la variación fue 8.9%; "
            "la serie de empresa no está disponible."
        ),
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22, pero el dato correcto fue 2025Q2; "
            "la serie de empresa no está disponible."
        ),
    ):
        _, ungrounded = score_live_case(case, tool_calls, response, **options)
        assert not ungrounded["passed"]
        assert "response_contains_numeric_claim_without_fixture_evidence" in ungrounded["failures"]

    _, no_evidence = score_live_case(
        case,
        [],
        (
            "AFAC registró 4,876,764 pasajeros de Viva en 2T22; "
            "la serie reportada por la empresa no está disponible."
        ),
        **options,
    )
    assert not no_evidence["passed"]
    assert "supported_answer_not_observed" in no_evidence["failures"]

    _, unsupported_alternative = score_live_case(
        case,
        unavailable_company_query,
        "Para Viva no hay dato de empresa publicado para 2T22; el valor sería 4,000,000 pasajeros.",
        **options,
    )
    assert not unsupported_alternative["passed"]
    assert "supported_answer_not_observed" in unsupported_alternative["failures"]

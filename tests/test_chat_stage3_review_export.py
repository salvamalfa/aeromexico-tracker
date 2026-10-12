from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.chat import export_stage3_review as exporter
from src.conversational_analytics.evaluation_stage3_coverage import CAMPAIGN_CANDIDATE

FIXTURE_PATH = Path("tests/fixtures/chat_evals/business_proposed.json")


def _inputs() -> tuple[dict, dict, dict, str]:
    raw = FIXTURE_PATH.read_bytes()
    fixture = json.loads(raw)
    fixture_sha = hashlib.sha256(raw).hexdigest()
    identity = {
        "candidate": CAMPAIGN_CANDIDATE,
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "text_verbosity": "medium",
        "snapshot_data_version": "data",
        "snapshot_semantic_version": "semantic",
        "tool_specs_sha256": "tools",
        "prompt_content_sha256": "prompt",
        "case_fixture_sha256": fixture_sha,
        "limits": {"max_tool_calls": 16},
    }
    cases = [
        {
            "case_id": case["id"],
            "status": "supported",
            "status_basis": "numeric_tool_evidence_with_public_sources",
            "limitation": None,
            "derived_expectations": [{
                "value": 100,
                "availability": "available",
                "metric_id": "company_passengers",
                "entity_id": "AEROMEXICO",
                "period": "2025",
                "unit": "pasajeros",
            }],
            "derived_calculations": [],
            "source_references": [],
        }
        for case in fixture["cases"]
    ]
    identity["derived_coverage_sha256"] = exporter._canonical_hash(cases)
    campaign_sha = exporter._canonical_hash(identity)
    coverage = {
        "kind": "f2_9_stage3_derived_coverage",
        "provider_calls": 0,
        "campaign_sha256": campaign_sha,
        "campaign_identity": identity,
        "pins": {"data_version": "data", "semantic_version": "semantic"},
        "cases": cases,
    }
    live_identity = {
        **identity,
        "coverage_campaign_sha256": campaign_sha,
        "trusted_receipt_sha256": "c" * 64,
        "run_id": "f29-stage3-sol-low-r2-proposed",
        "case_ids": [case["id"] for case in fixture["cases"]],
        "case_ids_sha256": hashlib.sha256(
            json.dumps([case["id"] for case in fixture["cases"]], separators=(",", ":")).encode()
        ).hexdigest(),
    }
    live = {
        "mode": "live-evaluation",
        "probe_only": False,
        "campaign_identity_hash": "b" * 64,
        "data_version": "data",
        "semantic_version": "semantic",
        "run_identity": live_identity,
        "run_identity_hash": exporter._canonical_hash(live_identity),
        "models": [{
            "candidate_id": f"{CAMPAIGN_CANDIDATE}@medium",
            "model": "gpt-6.1-sol",
            "reasoning_effort": "low",
            "text_verbosity": "medium",
            "cases": [
                {
                    "case_id": case["id"],
                    "model_turn_completed": True,
                    "turn_responses": [
                        f"Respuesta sintética {index}" for index, _ in enumerate(case["turns"])
                    ],
                }
                for case in fixture["cases"]
            ],
        }],
    }
    return fixture, coverage, live, fixture_sha


def _write_consolidated_report(directory: Path, report: dict) -> Path:
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    path = directory / f"f29-stage3-sol-low-r2-proposed.consolidated-{digest}.json"
    path.write_bytes(encoded)
    return path


def test_stage3_export_accepts_producer_report_shape_and_maps_all_expectations() -> None:
    fixture, coverage, live, fixture_sha = _inputs()
    dataset, mapping = exporter.build_dataset(coverage, live, fixture, fixture_sha)

    assert dataset["available_count"] == 30
    assert [question["id"] for question in dataset["questions"]] == [f"N{i:02d}" for i in range(1, 31)]
    assert all(question["candidates"][0]["alias"] == "A" for question in dataset["questions"])
    assert dataset["questions"][0]["expected"]["numeric_evidence"][0]["value"] == 100
    assert mapping["candidate_aliases"] == {"A": CAMPAIGN_CANDIDATE}


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("candidate_id", "gpt-6.1-sol@medium@medium"),
        ("text_verbosity", "low"),
        ("reasoning_effort", "medium"),
        ("model", "gpt-6-luna"),
    ],
)
def test_stage3_export_rejects_wrong_model_settings(field: str, wrong: str) -> None:
    fixture, coverage, live, fixture_sha = _inputs()
    live["models"][0][field] = wrong

    with pytest.raises(ValueError, match="no coincide con Sol low"):
        exporter.build_dataset(coverage, live, fixture, fixture_sha)


def test_stage3_export_rejects_different_live_prompt_pin() -> None:
    fixture, coverage, live, fixture_sha = _inputs()
    live["run_identity"]["prompt_content_sha256"] = "different-prompt"
    live["run_identity_hash"] = exporter._canonical_hash(live["run_identity"])

    with pytest.raises(ValueError, match="todos los pins de cobertura"):
        exporter.build_dataset(coverage, live, fixture, fixture_sha)


@pytest.mark.parametrize(
    "tamper",
    ["campaign", "case_digest", "derived_value", "calculation", "status", "source"],
)
def test_stage3_export_rejects_tampered_coverage_hashes(tamper: str) -> None:
    fixture, coverage, live, fixture_sha = _inputs()
    if tamper == "campaign":
        coverage["campaign_sha256"] = "f" * 64
    elif tamper == "derived_value":
        coverage["cases"][0]["derived_expectations"][0]["value"] = 101
    elif tamper == "calculation":
        coverage["cases"][0]["derived_calculations"] = [{"formula": "alterada", "value": 101}]
    elif tamper == "status":
        coverage["cases"][0]["status"] = "unsupported"
    elif tamper == "source":
        coverage["cases"][0]["source_references"] = [{
            "label": "Fuente alterada", "url": "https://example.org/changed"
        }]
    else:
        coverage["campaign_identity"]["derived_coverage_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA|sha"):
        exporter.build_dataset(coverage, live, fixture, fixture_sha)


def test_stage3_export_rejects_live_identity_with_wrong_coverage_campaign_hash() -> None:
    fixture, coverage, live, fixture_sha = _inputs()
    live["run_identity"]["coverage_campaign_sha256"] = "f" * 64
    live["run_identity_hash"] = exporter._canonical_hash(live["run_identity"])

    with pytest.raises(ValueError, match="no coincide con Sol low"):
        exporter.build_dataset(coverage, live, fixture, fixture_sha)


def test_stage3_export_cli_rejects_mutated_fixture_before_writing(tmp_path: Path, monkeypatch) -> None:
    fixture, coverage, live, _fixture_sha = _inputs()
    altered_fixture = json.loads(json.dumps(fixture))
    altered_fixture["cases"][0]["turns"][0] += " Pregunta alterada."
    fixture_path = tmp_path / "custom-fixture.json"
    fixture_path.write_text(json.dumps(altered_fixture), encoding="utf-8")
    coverage_path, live_path = tmp_path / "coverage.json", tmp_path / "live.json"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    live_path = _write_consolidated_report(tmp_path, live)
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    output_dir = tmp_path / ".state" / "review"

    with pytest.raises(ValueError, match="fixture no coincide"):
        exporter.main([
            "--coverage", str(coverage_path),
            "--live-report", str(live_path),
            "--fixture", str(fixture_path),
            "--output-dir", str(output_dir),
        ])
    assert not output_dir.exists()


def test_stage3_export_cli_accepts_content_addressed_live_report(tmp_path: Path, monkeypatch) -> None:
    fixture, coverage, live, _fixture_sha = _inputs()
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    live_path = _write_consolidated_report(tmp_path, live)
    fixture_path = FIXTURE_PATH
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    output_dir = tmp_path / ".state" / "review"

    assert exporter.main([
        "--coverage", str(coverage_path),
        "--live-report", str(live_path),
        "--fixture", str(fixture_path),
        "--output-dir", str(output_dir),
    ]) == 0
    dataset = json.loads((output_dir / "review.json").read_text(encoding="utf-8"))
    report_digest = live_path.name.split(".consolidated-")[1].removesuffix(".json")
    assert dataset["dataset_id"] == exporter._canonical_hash({
        "coverage_sha256": coverage["campaign_sha256"],
        "live_campaign_identity_hash": live["campaign_identity_hash"],
        "live_report_sha256": report_digest,
        "case_ids": [f"N{i:02d}" for i in range(1, 31)],
    })


def test_stage3_export_cli_rejects_edited_live_response_before_writing(tmp_path: Path, monkeypatch) -> None:
    _fixture, coverage, live, _fixture_sha = _inputs()
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
    live_path = _write_consolidated_report(tmp_path, live)
    tampered = json.loads(live_path.read_text(encoding="utf-8"))
    tampered["models"][0]["cases"][0]["turn_responses"][0] = "Respuesta editada después de consolidar"
    live_path.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    output_dir = tmp_path / ".state" / "review"

    with pytest.raises(ValueError, match="SHA del reporte live"):
        exporter.main([
            "--coverage", str(coverage_path),
            "--live-report", str(live_path),
            "--fixture", str(FIXTURE_PATH),
            "--output-dir", str(output_dir),
        ])
    assert not output_dir.exists()

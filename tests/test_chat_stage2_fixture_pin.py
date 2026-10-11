from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.chat import evaluate_campaign

ROOT = Path(__file__).resolve().parents[1]
APPROVED_FIXTURE = ROOT / "tests/fixtures/chat_evals/f2_9_stage2.json"


def _args(fixture: Path, tmp_path: Path) -> Namespace:
    return Namespace(
        fixture=fixture,
        prompt_proposed=evaluate_campaign.DEFAULT_STAGE2_PROMPT_PATH,
        snapshot=ROOT / "site",
        max_message_chars=8_000,
        max_tool_result_bytes=16_000,
        max_turn_seconds=180,
        text_verbosity="medium",
        output_dir=tmp_path / "outputs",
        campaign_state=tmp_path / "campaign.json",
    )


def test_approved_fixture_completes_offline_preflight_from_an_external_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external_fixture = tmp_path / "same-approved-content.json"
    external_fixture.write_bytes(APPROVED_FIXTURE.read_bytes())
    monkeypatch.setattr(evaluate_campaign, "_verify_private_destination", lambda *a, **k: None)

    plan, runs, cases, _, _, _ = evaluate_campaign.prepare(_args(external_fixture, tmp_path))

    assert plan["fixture_file_sha256"] == evaluate_campaign.APPROVED_STAGE2_FIXTURE_SHA256
    assert plan["fixture_source"] == "external"
    assert len(cases) == 15
    assert len(runs) == 4
    assert plan["live_execution_started"] is False


@pytest.mark.parametrize(
    ("case_id", "field", "mutate"),
    [
        ("N13", "question", lambda value: value + " (cambio)"),
        ("N13", "context", lambda value: {**value, "period": "2026Q1"}),
        ("N13", "rubric", lambda value: {**value, "modified": True}),
    ],
)
def test_same_ids_with_modified_approved_content_fail_before_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    field: str,
    mutate,
) -> None:
    payload = json.loads(APPROVED_FIXTURE.read_text(encoding="utf-8"))
    case = next(case for case in payload["cases"] if case["id"] == case_id)
    case[field] = mutate(case[field])
    changed_fixture = tmp_path / "changed.json"
    changed_fixture.write_text(json.dumps(payload), encoding="utf-8")

    def preparation_must_not_start(*args, **kwargs):
        raise AssertionError("Se intentó preparar la campaña antes de validar el pin")

    monkeypatch.setattr(evaluate_campaign, "_load_json", preparation_must_not_start)
    with pytest.raises(ValueError, match="fixture stage2 no coincide byte por byte"):
        evaluate_campaign.prepare(_args(changed_fixture, tmp_path))

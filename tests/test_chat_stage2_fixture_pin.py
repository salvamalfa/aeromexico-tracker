from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.chat import evaluate_campaign

ROOT = Path(__file__).resolve().parents[1]
APPROVED_FIXTURE = ROOT / "tests/fixtures/chat_evals/f2_9_stage2.json"


def _args(fixture: Path, tmp_path: Path, snapshot: Path | None = None) -> Namespace:
    return Namespace(
        fixture=fixture,
        prompt_proposed=evaluate_campaign.DEFAULT_STAGE2_PROMPT_PATH,
        snapshot=snapshot or ROOT / "site",
        max_message_chars=8_000,
        max_tool_result_bytes=16_000,
        max_turn_seconds=180,
        text_verbosity="medium",
        output_dir=tmp_path / "outputs",
        campaign_state=tmp_path / "campaign.json",
    )


def test_approved_external_fixture_rejects_current_snapshot_version_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external_fixture = tmp_path / "same-approved-content.json"
    external_fixture.write_bytes(APPROVED_FIXTURE.read_bytes())
    def preparation_must_not_write(*args, **kwargs):
        raise AssertionError("La deriva de versión debe bloquear los destinos de la campaña")

    monkeypatch.setattr(evaluate_campaign, "_verify_private_destination", preparation_must_not_write)
    from tests._pre_financial_snapshot import copy_pre_financial_snapshot
    baseline = copy_pre_financial_snapshot(tmp_path / "pre-financial")
    from src.conversational_analytics.data.snapshot import Snapshot
    approved = json.loads(external_fixture.read_text(encoding="utf-8"))
    assert hashlib.sha256(external_fixture.read_bytes()).hexdigest() == evaluate_campaign.APPROVED_STAGE2_FIXTURE_SHA256
    assert Snapshot(baseline).version != approved["expected_versions"]["data_version"]

    # Publishing new narratives/contracts changes the snapshot identity. The
    # approved historical fixture stays frozen; its preflight must stop here.
    with pytest.raises(ValueError, match="versión de datos del fixture no coincide"):
        evaluate_campaign.prepare(_args(external_fixture, tmp_path, snapshot=baseline))
    assert not (tmp_path / "outputs").exists()
    assert not (tmp_path / "campaign.json").exists()


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

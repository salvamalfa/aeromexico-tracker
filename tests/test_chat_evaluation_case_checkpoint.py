from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from src.conversational_analytics import evaluation_live
from src.conversational_analytics.evaluation_live import _live_provider_run


def _identity_hash(identity: dict) -> str:
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_completed_case_is_durable_with_campaign_lineage_before_delete(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
):
    from src.conversational_analytics.providers.base import ProviderResult

    output_dir = tmp_path / "private-live-run"
    lineage = {
        "run_id": "run-fixture",
        "candidate": "gpt-6-luna@low",
        "model": "gpt-6-luna",
        "reasoning_effort": "low",
        "fixture_hash": "f" * 64,
    }

    class Provider:
        delete_saw_durable_case = False
        run_calls = 0
        delete_observations = []

        def __init__(self, _config):
            pass

        def run_turn(self, *, persist_session, **_kwargs):
            if Provider.run_calls:
                details = list(output_dir.glob("*.cases.json"))
                assert len(details) == 1
                record = json.loads(details[0].read_text(encoding="utf-8"))
                latest_case = record["models"][0]["cases"][-1]
                assert latest_case["model_turn_completed"] is True
                assert latest_case["response"] == "durable answer payload"
            Provider.run_calls += 1
            persist_session("session-fixture")
            return ProviderResult(
                content="durable answer payload",
                input_tokens=20,
                output_tokens=4,
                provider_session_id="session-fixture",
                usage_complete=True,
            )

        def delete(self, _session_id):
            details = list(output_dir.glob("*.cases.json"))
            assert len(details) == 1
            record = json.loads(details[0].read_text(encoding="utf-8"))
            row = record["models"][0]["cases"][-1]
            observations = (
                row["model_turn_completed"] is True
                and record["run_identity_hash"] == _identity_hash(lineage)
                and record["campaign_identity_hash"] == "a" * 64
                and row["response"] == "durable answer payload"
                and stat.S_IMODE(details[0].stat().st_mode) == 0o600
                and stat.S_IMODE(details[0].parent.stat().st_mode) == 0o700
            )
            Provider.delete_observations.append(
                (len(record["models"][0]["cases"]), Provider.run_calls, observations)
            )
            Provider.delete_saw_durable_case = observations

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", Provider)
    result = _live_provider_run(
        cases=mock_live_holdout_current_versions["cases"],
        models=["gpt-6-luna@low"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna@low": (0.10, 0.50)},
        probe_only=False,
        output_dir=output_dir,
        run_identity=lineage,
        run_identity_hash=_identity_hash(lineage),
        campaign_identity_hash="a" * 64,
    )

    assert Provider.delete_observations
    assert len(Provider.delete_observations) > 1
    bad_observations = [item for item in Provider.delete_observations if not item[2]]
    assert not bad_observations, bad_observations
    sidecars = list(output_dir.glob("*.cases.json"))
    assert len(sidecars) == 1
    assert result["case_checkpoint_path"] == str(sidecars[0])
    assert os.stat(sidecars[0]).st_mode & 0o777 == 0o600


def test_case_checkpoint_write_failure_prevents_remote_delete_and_next_case(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
):
    from src.conversational_analytics.providers.base import ProviderResult

    class Provider:
        calls = 0
        deletes = 0

        def __init__(self, _config):
            pass

        def run_turn(self, *, persist_session, **_kwargs):
            Provider.calls += 1
            persist_session("session-fixture")
            return ProviderResult(content="answer", input_tokens=5, output_tokens=2, usage_complete=True)

        def delete(self, _session_id):
            Provider.deletes += 1

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", Provider)
    monkeypatch.setattr(
        evaluation_live,
        "_write_private_json",
        lambda path, _payload: (_ for _ in ()).throw(OSError("detail checkpoint unavailable"))
        if path.name.endswith(".cases.json")
        else None,
    )

    with pytest.raises(evaluation_live._CheckpointWriteError):
        _live_provider_run(
            cases=mock_live_holdout_current_versions["cases"],
            models=["gpt-6-luna"],
            budget_usd=10.0,
            snapshot_root=Path("site"),
            prices={"gpt-6-luna": (0.10, 0.50)},
            probe_only=False,
            output_dir=tmp_path / "private-failed-checkpoint",
        )

    assert Provider.calls == 1
    assert Provider.deletes == 0


@pytest.mark.parametrize("cancel_mode", ["failure", "pending"])
def test_watchdog_cancel_outcome_is_checkpointed_and_session_is_retained(
    cancel_mode, monkeypatch, tmp_path, mock_live_holdout_current_versions
):
    release_cancel = threading.Event()

    class Provider:
        calls = 0
        cancel_calls = 0
        deletes = 0

        def __init__(self, _config):
            self.max_turn_seconds = 0.03
            self.cancel_requested = threading.Event()

        def run_turn(self, *, persist_session, cancel_event, **_kwargs):
            type(self).calls += 1
            persist_session("sess_cancel_fixture")
            assert cancel_event.wait(0.5)
            time.sleep(0.03)
            raise RuntimeError("turn timed out")

        def cancel(self, _session_id):
            type(self).cancel_calls += 1
            self.cancel_requested.set()
            if cancel_mode == "pending":
                release_cancel.wait()
                return
            raise OSError("private cancel failure")

        def delete(self, _session_id):
            type(self).deletes += 1

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", Provider)
    report = _live_provider_run(
        cases=mock_live_holdout_current_versions["cases"],
        models=["gpt-6-luna"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna": (0.10, 0.50)},
        probe_only=False,
        output_dir=tmp_path / f"private-cancel-{cancel_mode}",
    )

    case_record = report["models"][0]["cases"][0]
    assert Provider.calls == Provider.cancel_calls == 1
    assert Provider.deletes == 0
    expected_status = (
        "pending_manual_reconciliation"
        if cancel_mode == "pending"
        else "failed_manual_reconciliation"
    )
    assert case_record["provider_cancel"] == expected_status
    if cancel_mode == "failure":
        assert case_record["provider_cancel_error_metadata"]["exception_types"] == ["OSError"]
    assert case_record["session_id"] == "sess_cancel_fixture"
    assert case_record["input_tokens"] is None
    assert case_record["output_tokens"] is None
    progress = json.loads(Path(report["progress_path"]).read_text(encoding="utf-8"))
    assert progress["provider_cancel_state"] == expected_status
    assert progress["session_to_reconcile"] == "sess_cancel_fixture"
    assert progress["manual_cancel_required"] is True
    release_cancel.set()

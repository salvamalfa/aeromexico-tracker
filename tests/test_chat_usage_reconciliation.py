from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.conversational_analytics.evaluation import load_cases
from src.conversational_analytics.evaluation_live import _live_provider_run
from src.conversational_analytics.providers import _openai_helpers
from src.conversational_analytics.providers.openai import OpenAIProviderError


def test_post_cancel_usage_unknown_retains_hold_and_defers_deletion(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    clock = [0.0]
    monkeypatch.setattr(_openai_helpers.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        _openai_helpers.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    events = []

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            events.append(("get", turn_id, session_id))
            return {"id": turn_id, "session_id": session_id, "status": "cancelled", "usage": None}

    class FailingProvider:
        calls = 0
        delete_calls = 0

        def __init__(self, config):
            self.config = config
            self.client = SimpleNamespace(
                beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
            )

        def run_turn(self, *, persist_session, **kwargs):
            type(self).calls += 1
            persist_session("session-unknown")
            raise OpenAIProviderError(
                "limited", reason_code="tool_call_limit", session_id="session-unknown", turn_id="turn-unknown"
            )

        def cancel(self, session_id):
            events.append(("cancel", session_id))

        def delete(self, _session_id):
            type(self).delete_calls += 1

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", FailingProvider)
    cases = [
        case
        for case in mock_live_holdout_current_versions["cases"]
        if case["expected"]["status"] == "supported"
    ][:2]
    report = _live_provider_run(
        cases=cases,
        models=["gpt-6-luna"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna": (0.10, 0.50)},
        probe_only=False,
        output_dir=tmp_path / "private-unknown-reconciliation",
    )
    model = report["models"][0]
    case = model["cases"][0]
    assert len(events) == 7
    assert events[0] == ("cancel", "session-unknown")
    assert events[1:] == [("get", "turn-unknown", "session-unknown")] * 6
    assert FailingProvider.calls == 1
    assert FailingProvider.delete_calls == 0
    assert len(model["cases"]) == 1
    assert case["status"] == "provider_error"
    assert case["model_turn_completed"] is False
    assert case["quality"] == {"scored": False, "not_scored_reason": "provider_error"}
    assert case["input_tokens"] is None and case["output_tokens"] is None
    assert case["usage_complete"] is False
    assert case["estimated_cost_usd"] is None
    assert case["post_cancel_usage_reconciliation"] == "unknown"
    assert case["provider_session_delete"] == "deferred_provider_error"
    assert model["spent_unknown"] is True
    assert model["known_estimated_cost_usd"] == 0
    assert model["estimated_cost_usd"] is None
    assert report["estimated_cost_usd"] is None
    assert "session_to_reconcile" in Path(report["progress_path"]).read_text(encoding="utf-8")


def test_live_unknown_usage_keeps_provider_session_for_reconciliation(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.base import ProviderResult

    class UnknownUsageProvider:
        calls = 0
        delete_calls = 0

        def __init__(self, config):
            self.config = config

        def run_turn(self, *, call_tool, persist_session, **kwargs):
            type(self).calls += 1
            persist_session("session-to-reconcile")
            call_tool(
                "provider-turn",
                "query-call",
                "query_metrics",
                {
                    "metric_ids": ["load_factor"],
                    "entity_ids": ["AEROMEXICO"],
                    "periods": ["2026Q2"],
                },
            )
            return ProviderResult(
                content="El factor fue 84,9 % en 2T26.",
                provider_session_id="session-to-reconcile",
                usage_complete=False,
            )

        def delete(self, _session_id):
            type(self).delete_calls += 1

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", UnknownUsageProvider)
    report = _live_provider_run(
        cases=mock_live_holdout_current_versions["cases"],
        models=["gpt-6-luna"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna": (0.10, 0.50)},
        probe_only=True,
        output_dir=tmp_path / "unknown-usage",
    )

    case = report["models"][0]["cases"][0]
    assert UnknownUsageProvider.calls == 1
    assert UnknownUsageProvider.delete_calls == 0
    assert case["quality"]["passed"] is True
    assert case["provider_session_delete"] == "deferred_usage_unknown"
    assert case["session_id"] == "session-to-reconcile"
    assert report["models"][0]["spent_unknown"] is True
    assert report["models"][0]["estimated_cost_usd"] is None
    assert report["models"][0]["known_estimated_cost_usd"] == 0
    assert report["estimated_cost_usd"] is None
    assert report["known_estimated_cost_usd"] == 0
    progress = json.loads(Path(report["progress_path"]).read_text(encoding="utf-8"))
    assert progress["session_to_reconcile"] == "session-to-reconcile"
    assert progress["estimated_spend_usd"] is None
    assert progress["known_estimated_spend_usd"] == 0
    assert progress["remaining_estimated_budget_usd"] is None


def test_frozen_holdout_version_mismatch_blocks_provider_and_writes(monkeypatch, tmp_path) -> None:
    class UnexpectedProvider:
        instances = 0

        def __init__(self, _config):
            type(self).instances += 1
            raise AssertionError("provider must not be instantiated for a stale fixture")

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", UnexpectedProvider)
    output_dir = tmp_path / "must-remain-empty"

    with pytest.raises(ValueError, match="no coincide con las versiones fijadas en el holdout"):
        _live_provider_run(
            cases=load_cases(),
            models=["gpt-6-luna"],
            budget_usd=10.0,
            snapshot_root=Path("site"),
            prices={"gpt-6-luna": (0.10, 0.50)},
            probe_only=True,
            output_dir=output_dir,
        )

    assert UnexpectedProvider.instances == 0
    assert not output_dir.exists()

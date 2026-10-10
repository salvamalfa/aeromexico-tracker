from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
import yaml

from src.conversational_analytics import evaluation, evaluation_live
from src.conversational_analytics.evaluation import (
    FIXTURE_PATH,
    approximately_equal,
    load_cases,
    render_dry_run,
    verify_observation,
)
from src.conversational_analytics.evaluation_live import _live_provider_run


def test_holdout_is_independent_and_covers_required_risks() -> None:
    cases = load_cases()
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(cases) == 40
    assert len({case["id"] for case in cases}) == len(cases)
    questions = [case["question"].casefold() for case in cases]
    assert len(set(questions)) == len(questions)
    prompt_examples = yaml.safe_load(Path("config/chat/question_examples.yaml").read_text())
    example_questions = {item["question"].casefold() for item in prompt_examples["examples"]}
    assert not (set(questions) & example_questions)
    expected_text = " ".join(questions)
    assert "ruta" in expected_text and "privado" in expected_text
    assert "percentage" in expected_text or "porcentaje" in expected_text
    assert "percentage points" in expected_text or "puntos porcentuales" in expected_text
    assert {case["expected"]["status"] for case in cases} == {
        "supported",
        "clarify",
        "unsupported",
        "refused",
    }
    # Explicitly protect the fixture source from accidental leakage from the
    # semantic prompt examples used to guide a model.
    assert raw["dataset"] == "site/data/v1 snapshot"
    assert "question_examples.yaml" in raw["description"]


def test_numeric_comparison_does_not_coerce_missing_to_zero() -> None:
    assert approximately_equal(0.849, 0.8490000000001)
    assert not approximately_equal(0.0, 0.849)


def test_supported_observation_checks_plan_values_and_references() -> None:
    case = next(case for case in load_cases() if case["id"] == "es_am_lf_q2")
    plan = case["expected"]["plan"]
    row = {
        **case["expected"]["rows"][0],
        "availability": "available",
        "source_references": [{"label": "SEC", "url": "https://www.sec.gov/example"}],
    }
    result = verify_observation(
        case, {"status": "supported", "plan": plan, "rows": [row], "response": "84.9% en 2026Q2"}
    )
    assert result.passed, result.failures

    bad_row = {**row, "value": 0.0, "source_references": []}
    failed = verify_observation(
        case, {"status": "supported", "plan": plan, "rows": [bad_row], "response": "84.9% en 2026Q2"}
    )
    assert not failed.passed
    assert any("valor incorrecto" in failure for failure in failed.failures)
    assert any("sin referencias" in failure for failure in failed.failures)


def test_plan_member_order_is_ignored_but_duplicates_are_rejected() -> None:
    case = next(case for case in load_cases() if case["id"] == "es_am_lf_q2")
    case = json.loads(json.dumps(case))
    case["expected"]["plan"].update(
        metric_ids=["load_factor", "ask_km"],
        entity_ids=["AEROMEXICO", "VOLARIS"],
        periods=["2026Q1", "2026Q2"],
    )
    row = {
        **case["expected"]["rows"][0],
        "availability": "available",
        "source_references": [{"label": "SEC", "url": "https://www.sec.gov/example"}],
    }
    actual = {
        **case["expected"]["plan"],
        "metric_ids": ["ask_km", "load_factor"],
        "entity_ids": ["VOLARIS", "AEROMEXICO"],
        "periods": ["2026Q2", "2026Q1"],
    }
    observation = {"status": "supported", "plan": actual, "rows": [row], "response": "84.9% en 2026Q2"}
    assert verify_observation(case, observation).passed
    actual["entity_ids"] = ["VOLARIS", "AEROMEXICO", "AEROMEXICO"]
    failed = verify_observation(case, observation)
    assert not failed.passed
    assert any("entity_ids" in failure for failure in failed.failures)


def test_response_terms_accept_locale_equivalent_percent_and_quarter_format() -> None:
    case = next(case for case in load_cases() if case["id"] == "es_am_lf_q2")
    plan = case["expected"]["plan"]
    row = {
        **case["expected"]["rows"][0],
        "availability": "available",
        "source_references": [{"label": "SEC", "url": "https://www.sec.gov/example"}],
    }
    equivalent = verify_observation(
        case,
        {
            "status": "supported",
            "plan": plan,
            "rows": [row],
            "response": "El factor de ocupación fue 84,9 % en el segundo trimestre de 2026 (2T26).",
        },
    )
    assert equivalent.passed, equivalent.failures

    incorrect = verify_observation(
        case,
        {
            "status": "supported",
            "plan": plan,
            "rows": [row],
            "response": "El factor fue 184,9 % o -84,9 %; la lectura comparada es 2026Q3.",
        },
    )
    assert not incorrect.passed
    assert any("respuesta sin términos requeridos" in failure for failure in incorrect.failures)


def test_supported_gold_rejects_wrong_unit_and_period() -> None:
    case = json.loads(json.dumps(next(case for case in load_cases() if case["id"] == "es_am_lf_q2")))
    case["expected"]["rows"][0]["unit"] = "fraction"
    row = {
        **case["expected"]["rows"][0],
        "availability": "available",
        "source_references": [{"label": "SEC", "url": "https://www.sec.gov/example"}],
    }
    for bad_row in ({**row, "unit": "passengers"}, {**row, "period": "2026Q3"}):
        failed = verify_observation(
            case,
            {
                "status": "supported",
                "plan": case["expected"]["plan"],
                "rows": [bad_row],
                "response": "84.9% in 2026Q2",
            },
        )
        assert not failed.passed


def test_dry_run_never_calls_provider_and_exposes_estimates_and_destinations() -> None:
    result = render_dry_run(
        load_cases(), models=["candidate-a", "candidate-b"], prices={"candidate-a": (2.0, 8.0)}
    )
    assert result["provider_calls"] == 0
    assert result["question_count"] == 40
    assert result["candidate_runs"][0]["windows"] == 4
    assert result["candidate_runs"][0]["estimated_input_tokens"] > 0
    assert result["candidate_runs"][0]["estimated_cost_usd"] > 0
    assert result["candidate_runs"][1]["estimated_cost_usd"] is None
    assert result["destinations"]["writes_now"] == []
    assert "chat-eval-" in result["destinations"]["live_report_if_authorized"]


def test_live_provider_error_writes_private_report_and_stops_without_retry(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.openai import OpenAIProviderError

    class AuthenticationError(Exception):
        status_code = 401

    class FailingProvider:
        calls = 0
        delete_calls = 0
        cancel_calls = 0

        def __init__(self, config):
            self.config = config

        def run_turn(self, *, persist_session, **kwargs):
            type(self).calls += 1
            persist_session("session-metadata")
            try:
                raise AuthenticationError("API key secret-value must never be persisted")
            except AuthenticationError:
                raise OpenAIProviderError("provider request failed") from None

        def delete(self, _session_id):
            type(self).delete_calls += 1

        def cancel(self, _session_id):
            type(self).cancel_calls += 1

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
        output_dir=tmp_path / "private-run",
    )

    model = report["models"][0]
    assert FailingProvider.calls == 1
    assert FailingProvider.delete_calls == 0
    assert FailingProvider.cancel_calls == 1
    assert len(model["cases"]) == 1
    assert model["cases"][0]["provider_cancel"] == "attempted"
    assert model["cases"][0]["quality"] == {"scored": False, "not_scored_reason": "provider_error"}
    assert model["cases"][0]["error_metadata"] == {
        "exception_types": ["OpenAIProviderError", "AuthenticationError"],
        "http_status": 401,
        "upstream_exception_type": "AuthenticationError",
        "upstream_http_status": 401,
    }
    assert model["quality_summary"]["numeric_gold_case_count"] == 2
    assert model["quality_summary"]["numeric_gold_case_passed"] == 0
    assert model["quality_summary"]["numeric_gold_accuracy"] == 0
    assert model["spent_unknown"] is True
    assert model["estimated_cost_usd"] is None
    assert model["known_estimated_cost_usd"] == 0
    assert report["estimated_cost_usd"] is None
    assert report["known_estimated_cost_usd"] == 0

    output_path = Path(report["output_path"])
    progress_path = Path(report["progress_path"])
    assert output_path.exists()
    assert progress_path.exists()
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(progress_path.stat().st_mode) == 0o600
    saved = output_path.read_text(encoding="utf-8")
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert "secret-value" not in saved
    assert "API key" not in saved
    assert progress["status"] == "stopped"
    assert progress["estimated_spend_usd"] is None
    assert progress["known_estimated_spend_usd"] == 0
    assert progress["remaining_estimated_budget_usd"] is None
    assert progress["active_usage_state"] is None
    assert progress["session_to_reconcile"] == "session-metadata"
    assert "question" not in progress
    assert "response" not in progress


def test_post_cancel_terminal_usage_is_counted_without_scoring_or_continuing(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from types import SimpleNamespace

    from src.conversational_analytics.providers.openai import OpenAIProviderError

    events = []

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            events.append(("get", turn_id, session_id))
            return {
                "id": turn_id,
                "session_id": session_id,
                "status": "cancelled",
                "usage": {"input_tokens": 35_573, "output_tokens": 208, "total_tokens": 35_781},
            }

    class FailingProvider:
        calls = 0

        def __init__(self, config):
            self.config = config
            self.client = SimpleNamespace(
                beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
            )

        def run_turn(self, *, persist_session, **kwargs):
            type(self).calls += 1
            persist_session("session-exact")
            raise OpenAIProviderError(
                "limited", reason_code="tool_call_limit", session_id="session-exact", turn_id="turn-exact"
            )

        def cancel(self, session_id):
            events.append(("cancel", session_id))

        def delete(self, _session_id):
            raise AssertionError("failed provider session must remain available for audit")

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
        output_dir=tmp_path / "private-reconciled-run",
    )
    model = report["models"][0]
    case = model["cases"][0]
    assert events == [("cancel", "session-exact"), ("get", "turn-exact", "session-exact")]
    assert FailingProvider.calls == 1
    assert len(model["cases"]) == 1
    assert case["status"] == "provider_error"
    assert case["model_turn_completed"] is False
    assert case["quality"] == {"scored": False, "not_scored_reason": "provider_error"}
    assert case["error_metadata"]["reason_code"] == "tool_call_limit"
    assert case["error_metadata"]["provider_turn_id"] == "turn-exact"
    assert case["session_id"] == "session-exact"
    assert case["input_tokens"] == 35_573
    assert case["output_tokens"] == 208
    assert case["estimated_cost_usd"] == pytest.approx(0.004550625)
    assert case["post_cancel_usage_reconciliation"] == "complete"
    assert model["spent_unknown"] is False


def test_live_tool_validation_error_is_returned_to_provider_like_worker(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.base import ProviderResult

    class CorrectingProvider:
        calls = 0
        tool_error = None

        def __init__(self, config):
            self.config = config

        def run_turn(self, *, call_tool, **kwargs):
            type(self).calls += 1
            type(self).tool_error = call_tool(
                "provider-turn",
                "bad-query-call",
                "query_metrics",
                {
                    "metric_ids": ["not-a-published-metric"],
                    "entity_ids": ["AEROMEXICO"],
                    "periods": ["2026Q2"],
                },
            )
            return ProviderResult(
                content="No se pudo validar la consulta.",
                input_tokens=20,
                output_tokens=8,
                usage_complete=True,
            )

        def delete(self, _session_id):
            return None

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", CorrectingProvider)
    report = _live_provider_run(
        cases=mock_live_holdout_current_versions["cases"],
        models=["gpt-6-luna"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna": (0.10, 0.50)},
        probe_only=True,
        output_dir=tmp_path / "tool-rejection",
    )

    case = report["models"][0]["cases"][0]
    assert CorrectingProvider.calls == 1
    assert CorrectingProvider.tool_error["error"]["code"] == "tool_rejected"
    assert case["tool_calls"][0]["result"]["error"]["code"] == "tool_rejected"
    assert case["status"] == "ungraded"
    assert case["quality"]["scored"] is True
    assert case["quality"]["passed"] is False
    assert case["quality"]["automatic_grade_type"] == "numeric_gold"
    assert case["quality"]["not_scored_reason"] == "no_successful_row_evidence"


def test_final_report_write_failure_never_marks_progress_completed(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.base import ProviderResult

    class KnownUsageProvider:
        def __init__(self, config):
            self.config = config

        def run_turn(self, *, persist_session, **kwargs):
            persist_session("known-usage-session")
            return ProviderResult(
                content="Respuesta de prueba.",
                input_tokens=100,
                output_tokens=20,
                provider_session_id="known-usage-session",
                usage_complete=True,
            )

        def delete(self, _session_id):
            return None

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", KnownUsageProvider)
    real_writer = evaluation_live._write_private_json

    def fail_final_report(path, payload):
        if (
            path.name.endswith(".json")
            and not path.name.endswith(".progress.json")
            and not path.name.endswith(".cases.json")
        ):
            raise OSError("synthetic private-file failure")
        real_writer(path, payload)

    monkeypatch.setattr(evaluation_live, "_write_private_json", fail_final_report)
    output_dir = tmp_path / "finalization-failure"
    with pytest.raises(OSError, match="synthetic private-file failure"):
        _live_provider_run(
            cases=mock_live_holdout_current_versions["cases"],
            models=["gpt-6-luna"],
            budget_usd=10.0,
            snapshot_root=Path("site"),
            prices={"gpt-6-luna": (0.10, 0.50)},
            probe_only=True,
            output_dir=output_dir,
        )

    progress_files = list(output_dir.glob("*.progress.json"))
    assert len(progress_files) == 1
    progress = json.loads(progress_files[0].read_text(encoding="utf-8"))
    assert progress["status"] == "finalizing"
    assert progress["estimated_spend_usd"] == progress["known_estimated_spend_usd"]


def test_post_result_checkpoint_failure_is_not_recorded_as_provider_error(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.base import ProviderResult

    class KnownUsageProvider:
        calls = 0

        def __init__(self, config):
            self.config = config

        def run_turn(self, *, persist_session, **kwargs):
            type(self).calls += 1
            persist_session("completed-session")
            return ProviderResult(
                content="Respuesta completa.",
                input_tokens=120,
                output_tokens=15,
                provider_session_id="completed-session",
                usage_complete=True,
            )

        def delete(self, _session_id):
            return None

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", KnownUsageProvider)
    real_writer = evaluation_live._write_private_json
    failed = False

    def fail_post_result_checkpoint(path, payload):
        nonlocal failed
        model = (payload.get("models") or [{}])[0]
        if (
            not failed
            and path.name.endswith(".progress.json")
            and payload.get("active_case_id") is None
            and payload.get("active_usage_state") == "complete"
            and model.get("case_count", 0) > 0
        ):
            failed = True
            raise OSError("private checkpoint write failed")
        real_writer(path, payload)

    monkeypatch.setattr(evaluation_live, "_write_private_json", fail_post_result_checkpoint)
    output_dir = tmp_path / "post-result-checkpoint-failure"
    with pytest.raises(evaluation_live._CheckpointWriteError):
        _live_provider_run(
            cases=mock_live_holdout_current_versions["cases"],
            models=["gpt-6-luna"],
            budget_usd=10.0,
            snapshot_root=Path("site"),
            prices={"gpt-6-luna": (0.10, 0.50)},
            probe_only=True,
            output_dir=output_dir,
        )

    assert failed
    assert KnownUsageProvider.calls == 1
    progress_files = list(output_dir.glob("*.progress.json"))
    assert len(progress_files) == 1
    progress = json.loads(progress_files[0].read_text(encoding="utf-8"))
    assert progress["status"] == "running"
    assert progress["active_usage_state"] == "unknown_in_flight"
    assert progress["active_case_id"] == "es_am_lf_q2"
    assert progress["models"][0]["case_count"] == 0
    assert len(list(output_dir.glob("chat-eval-*.cases.json"))) == 1
    assert not [
        path
        for path in output_dir.glob("chat-eval-*.json")
        if not path.name.endswith((".progress.json", ".cases.json"))
    ]


@pytest.mark.parametrize(
    "args",
    [
        ["--budget-usd", "nan"],
        ["--budget-usd", "inf"],
    ],
)
def test_live_cli_rejects_nonfinite_budget_before_runtime(monkeypatch, args) -> None:
    monkeypatch.setattr(
        evaluation_live, "_live_provider_run", lambda **kwargs: pytest.fail("runtime invoked")
    )
    with pytest.raises(SystemExit) as error:
        evaluation.main(
            [
                "--run",
                "--opt-in",
                *args,
                "--models",
                "gpt-6-luna",
                "--model-price",
                "gpt-6-luna=0.1:0.5",
                "--probe-only",
            ]
        )
    assert error.value.code == 2


@pytest.mark.parametrize("price", ["nan:0.5", "0.1:inf", "0:0.5"])
def test_live_cli_rejects_nonfinite_or_nonpositive_prices_before_runtime(monkeypatch, price) -> None:
    monkeypatch.setattr(
        evaluation_live, "_live_provider_run", lambda **kwargs: pytest.fail("runtime invoked")
    )
    with pytest.raises(SystemExit) as error:
        evaluation.main(
            [
                "--run",
                "--opt-in",
                "--budget-usd",
                "1",
                "--models",
                "gpt-6-luna",
                "--model-price",
                f"gpt-6-luna={price}",
                "--probe-only",
            ]
        )
    assert error.value.code == 2

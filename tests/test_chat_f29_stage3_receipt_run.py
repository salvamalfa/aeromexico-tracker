from __future__ import annotations

import hashlib
import json

from src.conversational_analytics.evaluation_stage3_coverage import CAMPAIGN_CANDIDATE

R2_SHA256 = "68961bc7a2dc7d0c79988352b56b2ded2ef7b55e515ce824dba3b2cf516a9edf"


def _receipt_sha256(receipt: dict) -> str:
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_stage3_cli_reaches_only_a_fake_runner_with_exact_trusted_receipts(monkeypatch, tmp_path) -> None:
    from datetime import date, timedelta

    import scripts.chat.check_stage3_coverage as cli

    tool_names = [
        "get_data_catalog",
        "get_metric_definition",
        "query_metrics",
        "compare_metrics",
        "get_time_series",
        "get_source_references",
        "get_dashboard_context",
        "query_routes",
        "find_shared_routes",
        "query_business_metrics",
        "get_business_metric_definition",
        "search_reports",
        "search_news",
    ]
    tool_specs = [{"name": name, "type": "function", "function": {"name": name}} for name in tool_names]
    tool_specs_sha = hashlib.sha256(
        json.dumps(tool_specs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = {
        "campaign_sha256": "",
        "campaign_identity": {
            "capability_pins_sha256": "b" * 64,
            "tool_specs_sha256": tool_specs_sha,
            "required_prompt_version": "r2-proposed",
            "limits": {
                "max_message_chars": 8_000,
                "max_tool_calls": 16,
                "max_tool_result_bytes": 16_000,
                "max_turn_seconds": 180,
            },
        },
        "counts": {"supported": 30, "coverage_missing": 0, "approval_blocked": 0},
        "case_count": 30,
        "coverage_status": "coverage_gaps_or_approval_gates",
        "pins": {
            "data_version": "data-v1",
            "semantic_version": "semantic-v1",
            "tool_specs_sha256": tool_specs_sha,
            "snapshot_manifest_sha256": "snapshot",
            "model_catalog_sha256": "catalog",
            "business_fixture_sha256": "fixture",
            "profile_sha256": "profile",
            "prompt_source_sha256": "prompt-source",
            "prompt_content_sha256": "prompt-content",
        },
        "runtime_capabilities": {
            "candidate": CAMPAIGN_CANDIDATE,
            "tool_specs_sha256": tool_specs_sha,
            "tool_names": tool_names,
            "active_prompt_version": "r2-proposed",
            "required_prompt_version": "r2-proposed",
            "required_prompt_sha256": R2_SHA256,
            "prompt_compatible": True,
        },
        "published_capabilities": {
            "business_metric_projection": {"status": "published"},
            "report_evidence_index": {
                "status": "published",
                "sha256": "index-file",
                "content_sha256": "index-content",
                "content_version": "v1",
                "report_search_available": True,
                "news_search_available": True,
            },
        },
    }
    fixture = json.loads(cli.ROOT.joinpath("tests/fixtures/chat_evals/business_proposed.json").read_text())
    report["cases"] = [{"case_id": case["id"], "status": "supported"} for case in fixture["cases"]]
    cli._bind_reserve(report, 8.0)
    common = {
        "schema_version": 1,
        "status": "approved",
        "approved_by": "salvamalfa",
        "approved_at": date.today().isoformat(),
        "valid_until": (date.today() + timedelta(days=1)).isoformat(),
        "decision_ref": "https://github.com/salvamalfa/aeromexico-tracker/blob/"
        + "a" * 40
        + "/docs/decisiones/chat-f2-9-stage3.md",
        "campaign_sha256": report["campaign_sha256"],
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 8.0,
    }
    budget = {
        **common,
        "receipt_type": "f29_stage3_funding",
        "funding_status": "funded",
        "funded_usd": 8.0,
    }
    capability = {
        **common,
        "receipt_type": "f29_stage3_capabilities",
        **report["pins"],
        "prompt_version": "r2-proposed",
        "active_prompt_version": "r2-proposed",
        "required_prompt_sha256": R2_SHA256,
        "capability_pins_sha256": "b" * 64,
        "limits": report["campaign_identity"]["limits"],
        "report_evidence_index_sha256": "index-file",
        "report_evidence_content_sha256": "index-content",
        "report_evidence_content_version": "v1",
        "capabilities": [
            "business_metrics",
            "routes",
            "report_evidence",
            "report_search",
            "news_search",
            "presentation",
        ],
        "stage3_live_authorized": True,
    }
    budget_path = tmp_path / "budget.json"
    capability_path = tmp_path / "capability.json"
    budget_path.write_text(json.dumps(budget), encoding="utf-8")
    capability_path.write_text(json.dumps(capability), encoding="utf-8")
    monkeypatch.setattr(cli, "derive_stage3_coverage", lambda **_kwargs: report)
    monkeypatch.setattr(cli, "_dirty_execution_inputs", lambda: "")
    monkeypatch.setattr(
        cli,
        "os",
        type(
            "FakeOS",
            (),
            {
                "environ": {
                    "OPENAI_API_KEY": "test-placeholder",
                    cli.TRUSTED_BUDGET_RECEIPT_SHA_ENV: _receipt_sha256(budget),
                    cli.TRUSTED_CAPABILITY_RECEIPT_SHA_ENV: _receipt_sha256(capability),
                }
            },
        )(),
    )
    from scripts.chat import prepare_final_campaign
    from src.conversational_analytics import config as chat_config
    from src.conversational_analytics import evaluation_live_campaign
    from src.conversational_analytics.data import snapshot as snapshot_module
    from src.conversational_analytics.providers import _openai_prompt

    reservation = {
        "basis": "f2_9_stage3_projected_usage_not_hard_cap",
        "planned_request_count": 34,
        "planned_message_count": 34,
        "input_tokens_per_turn": 83_528,
        "output_tokens_per_turn": 375,
        "planned_batch_estimated_reservation_usd": 7.22738,
        "campaign_sha256": report["campaign_sha256"],
        "budget_guaranteed": False,
    }
    monkeypatch.setattr(
        prepare_final_campaign,
        "build_plan",
        lambda **_kwargs: {
            "projection": {"proposed_reserve_usd": 8.0},
            "reservation_assumption_override": reservation,
        },
    )
    monkeypatch.setattr(cli, "_write_output", lambda _path, value: output.append(value))
    monkeypatch.setattr(snapshot_module, "Snapshot", lambda _path: FakeSnapshot())
    monkeypatch.setattr(_openai_prompt, "load_active_system_instructions", lambda: "fake prompt")
    monkeypatch.setattr(_openai_prompt, "effective_prompt_sha256", lambda: R2_SHA256)
    monkeypatch.setattr(_openai_prompt, "effective_prompt_version", lambda: "r2-proposed")
    runtime_config = chat_config.ChatConfig(
        provider="mock",
        prompt_version="r2-proposed",
        enable_route_tools=True,
        enable_business_metric_tools=True,
        enable_evidence_tools=True,
    )
    monkeypatch.setattr(chat_config.ChatConfig, "from_env", staticmethod(lambda: runtime_config))
    from src.conversational_analytics.tools import registry as registry_module

    registry_calls = []

    class FakeToolRegistry:
        def __init__(self, snapshot, config):
            registry_calls.append((snapshot, config))

        def tool_specs(self):
            return tool_specs

    monkeypatch.setattr(registry_module, "ToolRegistry", FakeToolRegistry)
    called = []
    monkeypatch.setattr(
        evaluation_live_campaign,
        "run_campaign",
        lambda **kwargs: called.append(kwargs) or {"provider_calls": 0},
    )
    output = []

    class FakeSnapshot:
        root = tmp_path
        version = "data-v1"
        semantic_version = "semantic-v1"

    assert (
        cli.main(
            [
                "--run",
                "--opt-in",
                "--budget-receipt",
                str(budget_path),
                "--capability-receipt",
                str(capability_path),
            ]
        )
        == 0
    )
    assert len(called) == 1
    assert output[0]["mode"] == "live-campaign"
    assert output[0]["campaign"]["provider_calls"] == 0
    assert output[0]["trusted_receipt_sha256"] == {
        "budget": _receipt_sha256(budget),
        "capabilities": _receipt_sha256(capability),
    }
    assert len(registry_calls) == 1
    configured = registry_calls[0][1]
    assert configured.enable_route_tools is True
    assert configured.enable_business_metric_tools is True
    assert configured.enable_evidence_tools is True
    assert (configured.max_tool_calls, configured.max_tool_result_bytes) == (16, 16_000)
    assert called[0]["runtime_config"] is configured
    assert called[0]["reservation_assumption_override"] == reservation
    actual_cases = called[0]["cases"]
    assert [case["question"] for case in actual_cases] == [case["question"] for case in fixture["cases"]]
    assert [case["turns"] for case in actual_cases] == [case["turns"] for case in fixture["cases"]]
    assert [case.get("context") for case in actual_cases] == [case.get("context") for case in fixture["cases"]]
    assert actual_cases[3]["expected"]["status"] == "supported"
    assert fixture["cases"][3]["expected"]["status"] == "unsupported"
    assert called[0]["resume"] is False
    assert called[0]["budget_usd"] == 8.0

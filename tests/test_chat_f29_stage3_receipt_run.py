from __future__ import annotations

import hashlib
import json

from src.conversational_analytics.evaluation_stage3_coverage import CAMPAIGN_CANDIDATE


def _receipt_sha256(receipt: dict) -> str:
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_stage3_cli_reaches_only_a_fake_runner_with_exact_trusted_receipts(monkeypatch, tmp_path) -> None:
    import scripts.chat.check_stage3_coverage as cli

    from datetime import date, timedelta

    report = {
        "campaign_sha256": "",
        "campaign_identity": {
            "capability_pins_sha256": "b" * 64,
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
            "tool_specs_sha256": "tools",
            "snapshot_manifest_sha256": "snapshot",
            "model_catalog_sha256": "catalog",
            "business_fixture_sha256": "fixture",
            "profile_sha256": "profile",
            "prompt_source_sha256": "prompt-source",
            "prompt_content_sha256": "prompt-content",
        },
        "runtime_capabilities": {
            "candidate": CAMPAIGN_CANDIDATE,
            "tool_specs_sha256": "tools",
            "active_prompt_version": "r2-proposed",
            "required_prompt_version": "r2-proposed",
            "required_prompt_sha256": "prompt-r2",
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
    cli._bind_reserve(report, 6.58)
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
        "reserve_usd": 6.58,
    }
    budget = {
        **common,
        "receipt_type": "f29_stage3_funding",
        "funding_status": "funded",
        "funded_usd": 6.58,
    }
    capability = {
        **common,
        "receipt_type": "f29_stage3_capabilities",
        **report["pins"],
        "prompt_version": "r2-proposed",
        "active_prompt_version": "r2-proposed",
        "required_prompt_sha256": "prompt-r2",
        "capability_pins_sha256": "b" * 64,
        "limits": report["campaign_identity"]["limits"],
        "report_evidence_index_sha256": "index-file",
        "report_evidence_content_sha256": "index-content",
        "report_evidence_content_version": "v1",
        "capabilities": [
            "business_metrics", "routes", "report_evidence", "report_search",
            "news_search", "presentation",
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
        type("FakeOS", (), {"environ": {
            "OPENAI_API_KEY": "test-placeholder",
            cli.TRUSTED_BUDGET_RECEIPT_SHA_ENV: _receipt_sha256(budget),
            cli.TRUSTED_CAPABILITY_RECEIPT_SHA_ENV: _receipt_sha256(capability),
        }})(),
    )
    from scripts.chat import prepare_final_campaign
    from src.conversational_analytics import config as chat_config
    from src.conversational_analytics.data import snapshot as snapshot_module
    from src.conversational_analytics.providers import _openai_prompt
    from src.conversational_analytics import evaluation_live_campaign

    monkeypatch.setattr(prepare_final_campaign, "build_plan", lambda **_kwargs: {
        "projection": {"proposed_reserve_usd": 6.58}
    })
    monkeypatch.setattr(cli, "_write_output", lambda _path, value: output.append(value))
    monkeypatch.setattr(snapshot_module, "Snapshot", lambda _path: FakeSnapshot())
    monkeypatch.setattr(
        chat_config.ChatConfig,
        "from_env",
        staticmethod(lambda: None),
    )
    monkeypatch.setattr(_openai_prompt, "load_active_system_instructions", lambda: "fake prompt")
    monkeypatch.setattr(_openai_prompt, "effective_prompt_sha256", lambda: "prompt-r2")
    monkeypatch.setattr(_openai_prompt, "effective_prompt_version", lambda: "r2-proposed")
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

    assert cli.main([
        "--run", "--opt-in", "--budget-receipt", str(budget_path),
        "--capability-receipt", str(capability_path),
    ]) == 0
    assert len(called) == 1
    assert output[0]["mode"] == "live-campaign"
    assert output[0]["campaign"]["provider_calls"] == 0
    assert output[0]["trusted_receipt_sha256"] == {
        "budget": _receipt_sha256(budget),
        "capabilities": _receipt_sha256(capability),
    }

from __future__ import annotations

import json
from pathlib import Path

from src.conversational_analytics.evaluation_stage3_coverage import (
    CAMPAIGN_CANDIDATE,
    derive_stage3_coverage,
    validate_receipt_scope,
)


def test_stage3_derives_all_30_cases_from_real_tools_and_current_snapshot() -> None:
    report = derive_stage3_coverage(snapshot_root=Path("site"))

    assert report["case_count"] == 30
    assert sum(report["counts"].values()) == 30
    assert report["provider_calls"] == 0
    assert report["credentials_read"] is False
    assert report["fixtures_modified"] is False
    assert report["current_dashboard_period"] == {
        "economic": "2026Q2",
        "market": "2026Q2",
        "domestic_routes": ["2026M07"],
    }
    assert report["runtime_capabilities"]["candidate"] == CAMPAIGN_CANDIDATE
    assert report["runtime_capabilities"]["stage3_candidate_count"] == 1

    cases = {case["case_id"]: case for case in report["cases"]}
    assert all("expected" not in case and "expected_status" not in case for case in cases.values())
    annual = cases["N01"]["calls"][0]["result"]
    assert annual["metric_id"] == "company_passengers"
    assert annual["availability"] == "available"
    assert annual["value"] == sum(
        row["passengers"]
        for row in json.loads(Path("site/data/v1/executive.json").read_text())["entities"]["AEROMEXICO"][
            "records"
        ]
        if row["period_id"].startswith("2025Q")
    )

    market = cases["N07"]["calls"][0]["result"]
    row_2026q2 = next(
        row for row in market["rows"] if row["period"] == "2026Q2" and row["entity_id"] == "VOLARIS"
    )
    market_doc = json.loads(Path("site/data/v1/market.json").read_text())
    source_row = next(item for item in market_doc["quarters"] if item["period_id"] == "2026Q2")
    assert row_2026q2["value"] == source_row["segments"]["domestic"]["carriers"]["VOLARIS"]["share"]
    assert cases["N07"]["status"] == "supported"

    assert cases["N04"]["status"] == "approval_blocked"
    candidate_call = cases["N04"]["calls"][1]["result"]
    assert candidate_call["approval_gate"] == "closed"
    assert candidate_call["value"] is None
    assert cases["N09"]["calls"][0]["tool"] == "query_routes"
    assert "error" not in cases["N09"]["calls"][0]
    assert cases["N10"]["calls"][0]["tool"] == "find_shared_routes"
    assert cases["N12"]["calls"][0]["tool"] == "get_time_series"
    assert cases["N16"]["status"] == "approval_blocked"
    assert cases["N25"]["follow_up_turns_reused_prior_tool_results"] is True
    assert cases["N26"]["follow_up_turns_reused_prior_tool_results"] is True
    for case in cases.values():
        urls = [reference["url"] for reference in case["source_references"]]
        assert len(urls) == len(set(urls))
    assert report["published_capabilities"]["report_evidence_index"]["status"] != "published"


def test_stage3_receipts_require_exact_scope_and_real_approval_status() -> None:
    report = {
        "campaign_sha256": "a" * 64,
        "campaign_identity": {"capability_pins_sha256": "b" * 64},
        "pins": {"data_version": "data", "semantic_version": "semantic", "prompt_content_sha256": "prompt"},
        "runtime_capabilities": {
            "tool_specs_sha256": "tools",
            "active_prompt_version": "r1-final",
            "required_prompt_version": "r2-proposed",
            "required_prompt_sha256": "prompt-r2",
            "prompt_compatible": False,
        },
    }
    budget = {
        "schema_version": 1,
        "receipt_type": "f29_stage3_funding",
        "status": "pending",
        "campaign_sha256": "a" * 64,
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 6.58,
    }
    capability = {
        "schema_version": 1,
        "receipt_type": "f29_stage3_capabilities",
        "status": "pending",
        "campaign_sha256": "a" * 64,
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 6.58,
    }
    assert validate_receipt_scope(budget, capability, report, 6.58) == (False, "budget_receipt_not_approved")
    budget["status"] = "approved"
    capability["status"] = "approved"
    budget["campaign_sha256"] = "c" * 64
    assert validate_receipt_scope(budget, capability, report, 6.58) == (
        False,
        "budget_receipt_scope_mismatch_campaign_sha256",
    )


def test_stage3_cli_blocks_missing_receipts_before_credentials_or_provider(monkeypatch, tmp_path) -> None:
    import scripts.chat.check_stage3_coverage as cli

    report = {
        "campaign_sha256": "a" * 64,
        "campaign_identity": {"reserve_usd": 6.58},
        "counts": {"supported": 1, "coverage_missing": 0, "approval_blocked": 0},
        "case_count": 1,
        "coverage_status": "coverage_gaps_or_approval_gates",
        "published_capabilities": {},
        "pins": {"data_version": "data", "semantic_version": "semantic", "prompt_content_sha256": "prompt"},
        "runtime_capabilities": {
            "tool_specs_sha256": "tools",
            "active_prompt_version": "r1-final",
            "required_prompt_version": "r2-proposed",
            "required_prompt_sha256": "prompt-r2",
            "prompt_compatible": False,
        },
    }
    monkeypatch.setattr(cli, "derive_stage3_coverage", lambda **_kwargs: report)

    class NoCredentialRead(dict):
        def __contains__(self, key):
            if key == "OPENAI_API_KEY":
                raise AssertionError("credential environment must not be inspected before receipts")
            return super().__contains__(key)

    monkeypatch.setattr(cli.os, "environ", NoCredentialRead())
    captured = []
    monkeypatch.setattr(cli, "_write_output", lambda _path, value: captured.append(value))
    assert cli.main(["--run", "--opt-in"]) == 2
    blocked = captured[0]
    assert blocked["status"] == "blocked"
    assert blocked["reason"] == "missing_exact_scope_receipts"
    assert blocked["provider_calls"] == 0
    assert blocked["credentials_read"] is False


def test_stage3_review_export_maps_only_one_candidate_and_all_derived_expectations() -> None:
    from scripts.chat.export_stage3_review import build_dataset

    fixture = json.loads(Path("tests/fixtures/chat_evals/business_proposed.json").read_text())
    coverage = {
        "kind": "f2_9_stage3_derived_coverage",
        "provider_calls": 0,
        "campaign_sha256": "a" * 64,
        "pins": {"data_version": "data", "semantic_version": "semantic"},
        "cases": [
            {
                "case_id": case["id"],
                "status": "supported",
                "status_basis": "numeric_tool_evidence_with_public_sources",
                "limitation": None,
                "derived_expectations": [{"value": 100}],
                "source_references": [],
            }
            for case in fixture["cases"]
        ],
    }
    live = {
        "mode": "live-evaluation",
        "probe_only": False,
        "campaign_identity_hash": "b" * 64,
        "data_version": "data",
        "semantic_version": "semantic",
        "run_identity": {
            "candidate": CAMPAIGN_CANDIDATE,
            "model": "gpt-6.1-sol",
            "reasoning_effort": "low",
            "text_verbosity": "medium",
        },
        "models": [
            {
                "candidate": CAMPAIGN_CANDIDATE,
                "cases": [
                    {
                        "case_id": case["id"],
                        "model_turn_completed": True,
                        "turn_responses": [f"Respuesta {index}" for index, _ in enumerate(case["turns"])],
                    }
                    for case in fixture["cases"]
                ],
            }
        ],
    }
    dataset, mapping = build_dataset(coverage, live, fixture)
    assert dataset["available_count"] == 30
    assert [question["id"] for question in dataset["questions"]] == [f"N{i:02d}" for i in range(1, 31)]
    assert all(
        len(question["candidates"]) == 1 and question["candidates"][0]["alias"] == "A"
        for question in dataset["questions"]
    )
    assert dataset["questions"][0]["expected"]["numeric_evidence"] == [{"value": 100}]
    assert mapping["candidate_aliases"] == {"A": CAMPAIGN_CANDIDATE}

from __future__ import annotations

import json
import hashlib
from datetime import date, timedelta
from pathlib import Path

from src.conversational_analytics.evaluation_stage3_coverage import (
    CAMPAIGN_CANDIDATE,
    derive_stage3_coverage,
    validate_receipt_scope,
)

_TEST_APPROVED_AT = date.today().isoformat()
_TEST_VALID_UNTIL = (date.today() + timedelta(days=1)).isoformat()


def _receipt_sha256(receipt: dict) -> str:
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    assert report["runtime_capabilities"]["required_prompt_version"] == "r2-proposed"
    assert report["runtime_capabilities"]["required_prompt_sha256"] == (
        "68961bc7a2dc7d0c79988352b56b2ded2ef7b55e515ce824dba3b2cf516a9edf"
    )
    assert report["runtime_capabilities"]["prompt_compatible"] is (
        report["runtime_capabilities"]["prompt_content_sha256"]
        == report["runtime_capabilities"]["required_prompt_sha256"]
    )

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
    n07_rows = cases["N07"]["calls"][0]["result"]["rows"]
    am_share = {
        row["period"]: row["value"] for row in n07_rows if row["entity_id"] == "AEROMEXICO"
    }
    am_delta = next(
        item for item in cases["N07"]["derived_calculations"]
        if item["calculation"] == "AEROMEXICO_share_change"
    )
    assert am_delta["value"] == (am_share["2026Q2"] - am_share["2025Q2"]) * 100
    assert cases["N05"]["status"] == "coverage_missing"
    assert "más grande" in cases["N05"]["limitation"]
    assert "no cubre todas las aerolíneas" in cases["N05"]["limitation"]
    assert cases["N08"]["status"] == "coverage_missing"
    assert "2T25 frente a 2T26" in cases["N08"]["limitation"]
    for case in cases.values():
        if case["status"] == "supported":
            assert case["tool_execution_complete"] is True
            assert case["tool_source_coverage_complete"] is True
            assert case["evidence_rows_complete"] is True

    assert cases["N04"]["status"] == "approval_blocked"
    candidate_call = cases["N04"]["calls"][1]["result"]
    assert candidate_call["approval_gate"] == "closed"
    assert candidate_call["value"] is None
    assert cases["N09"]["calls"][0]["tool"] == "query_routes"
    assert "error" not in cases["N09"]["calls"][0]
    assert cases["N10"]["calls"][0]["tool"] == "find_shared_routes"
    assert cases["N12"]["calls"][0]["tool"] == "get_time_series"
    assert cases["N16"]["status"] == "approval_blocked"
    n23_values = [call["result"]["value"] for call in cases["N23"]["calls"]]
    assert cases["N23"]["derived_calculations"][0]["value"] == n23_values[0] - n23_values[1]
    assert cases["N25"]["follow_up_turns_reused_prior_tool_results"] is True
    assert cases["N26"]["follow_up_turns_reused_prior_tool_results"] is True
    for case in cases.values():
        urls = [reference["url"] for reference in case["source_references"]]
        assert len(urls) == len(set(urls))
    evidence_index = report["published_capabilities"]["report_evidence_index"]
    assert evidence_index["status"] == "missing_index"
    assert evidence_index["report_search_available"] is False
    assert evidence_index["news_search_available"] is False


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
        "approved_by": "salvamalfa",
        "approved_at": _TEST_APPROVED_AT,
        "valid_until": _TEST_VALID_UNTIL,
        "decision_ref": "https://github.com/salvamalfa/aeromexico-tracker/blob/"
        + "a" * 40
        + "/docs/decisiones/chat-f2-9-stage3.md",
        "campaign_sha256": "a" * 64,
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 6.58,
    }
    capability = {
        "schema_version": 1,
        "receipt_type": "f29_stage3_capabilities",
        "status": "pending",
        "approved_by": "salvamalfa",
        "approved_at": _TEST_APPROVED_AT,
        "valid_until": _TEST_VALID_UNTIL,
        "decision_ref": "https://github.com/salvamalfa/aeromexico-tracker/blob/"
        + "a" * 40
        + "/docs/decisiones/chat-f2-9-stage3.md",
        "campaign_sha256": "a" * 64,
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 6.58,
    }
    pins = {
        "budget_receipt_sha256": _receipt_sha256(budget),
        "capability_receipt_sha256": _receipt_sha256(capability),
    }
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "budget_receipt_not_approved",
    )
    budget["status"] = "approved"
    capability["status"] = "approved"
    budget["campaign_sha256"] = "c" * 64
    pins["budget_receipt_sha256"] = _receipt_sha256(budget)
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "budget_receipt_scope_mismatch_campaign_sha256",
    )


def test_stage3_capability_receipt_binds_evidence_index_content_version() -> None:
    report = {
        "campaign_sha256": "a" * 64,
        "campaign_identity": {"capability_pins_sha256": "b" * 64},
        "pins": {
            "data_version": "data",
            "semantic_version": "semantic",
            "tool_specs_sha256": "tools",
            "snapshot_manifest_sha256": "snapshot",
            "model_catalog_sha256": "catalog",
            "business_fixture_sha256": "fixture",
            "profile_sha256": "profile",
            "prompt_source_sha256": "prompt-source",
            "prompt_content_sha256": "prompt-content",
        },
        "runtime_capabilities": {
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
                "sha256": "index-file-hash",
                "content_sha256": "index-content-hash",
                "content_version": "v7",
                "report_search_available": True,
                "news_search_available": True,
            },
        },
    }
    budget = {
        "schema_version": 1,
        "receipt_type": "f29_stage3_funding",
        "status": "approved",
        "approved_by": "salvamalfa",
        "approved_at": _TEST_APPROVED_AT,
        "valid_until": _TEST_VALID_UNTIL,
        "decision_ref": "https://github.com/salvamalfa/aeromexico-tracker/blob/"
        + "b" * 40
        + "/docs/decisiones/chat-f2-9-stage3.md",
        "campaign_sha256": "a" * 64,
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 6.58,
        "funding_status": "funded",
        "funded_usd": 6.58,
    }
    capability = {
        "schema_version": 1,
        "receipt_type": "f29_stage3_capabilities",
        "status": "approved",
        "approved_by": "salvamalfa",
        "approved_at": _TEST_APPROVED_AT,
        "valid_until": _TEST_VALID_UNTIL,
        "decision_ref": "https://github.com/salvamalfa/aeromexico-tracker/blob/"
        + "b" * 40
        + "/docs/decisiones/chat-f2-9-stage3.md",
        "campaign_sha256": "a" * 64,
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": 6.58,
        "data_version": "data",
        "semantic_version": "semantic",
        "tool_specs_sha256": "tools",
        "snapshot_manifest_sha256": "snapshot",
        "model_catalog_sha256": "catalog",
        "business_fixture_sha256": "fixture",
        "profile_sha256": "profile",
        "prompt_source_sha256": "prompt-source",
        "prompt_content_sha256": "prompt-content",
        "prompt_version": "r2-proposed",
        "active_prompt_version": "r2-proposed",
        "required_prompt_sha256": "prompt-r2",
        "capability_pins_sha256": "b" * 64,
        "report_evidence_index_sha256": "index-file-hash",
        "report_evidence_content_sha256": "index-content-hash",
        "report_evidence_content_version": "v7",
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
    pins = {
        "budget_receipt_sha256": _receipt_sha256(budget),
        "capability_receipt_sha256": _receipt_sha256(capability),
    }
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        True,
        "receipts_match_exact_campaign_scope",
    )
    assert validate_receipt_scope(budget, capability, report, 6.58) == (
        False,
        "budget_receipt_sha256_missing_or_invalid",
    )
    capability["approved_by"] = "untrusted-user"
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "capabilities_receipt_owner_mismatch",
    )
    capability["approved_by"] = "salvamalfa"
    capability["decision_ref"] = "https://github.com/salvamalfa/aeromexico-tracker/pull/123"
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "capabilities_receipt_decision_ref_untrusted",
    )
    capability["decision_ref"] = "https://github.com/salvamalfa/aeromexico-tracker/blob/"
    capability["decision_ref"] += "b" * 40 + "/docs/decisiones/chat-f2-9-stage3.md"
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    capability["approved_at"] = (date.today() + timedelta(days=2)).isoformat()
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "capabilities_receipt_approval_date_invalid",
    )
    capability["approved_at"] = (date.today() - timedelta(days=2)).isoformat()
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    capability["valid_until"] = (date.today() - timedelta(days=1)).isoformat()
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "capabilities_receipt_expired",
    )
    capability["valid_until"] = _TEST_VALID_UNTIL
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    capability["report_evidence_content_version"] = "v6"
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "capabilities_receipt_sha256_mismatch",
    )
    pins["capability_receipt_sha256"] = _receipt_sha256(capability)
    assert validate_receipt_scope(budget, capability, report, 6.58, **pins) == (
        False,
        "capabilities_receipt_scope_mismatch_report_evidence_content_version",
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


def test_stage3_cli_requires_external_receipt_hashes_before_reading_receipts_or_credentials(
    monkeypatch, tmp_path
) -> None:
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
    monkeypatch.setattr(cli.os, "environ", {})
    monkeypatch.setattr(
        cli,
        "_read_receipt",
        lambda _path: (_ for _ in ()).throw(AssertionError("receipt bytes read without trusted SHA")),
    )
    captured = []
    monkeypatch.setattr(cli, "_write_output", lambda _path, value: captured.append(value))

    assert cli.main(
        [
            "--run",
            "--opt-in",
            "--budget-receipt",
            str(tmp_path / "budget.json"),
            "--capability-receipt",
            str(tmp_path / "capabilities.json"),
        ]
    ) == 2
    assert captured[0]["reason"] == "missing_external_receipt_sha256_pins"
    assert captured[0]["provider_calls"] == 0
    assert captured[0]["credentials_read"] is False


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

"""Offline tests for explicit cross-execution stage-2 continuation lineage."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/chat"))

from tests.test_chat_stage2_blind_export import fixture_payload, run_report
import export_stage2_blind_review as exporter


class Stage2ContinuationExportTests(unittest.TestCase):
    def test_exports_verified_cross_sha_continuation_without_mutating_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, evidence, _, hashes = continuation_artifacts(root)
            fixture_path = root / "fixture.json"
            with patch.object(exporter, "ROOT", root):
                result = exporter.export(None, root / ".state/review", fixture_path, plan, evidence)
            output = root / ".state/review"
            dataset_path = output / "stage2-review.json"
            private_path = output / "stage2-alias-key.json"
            dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
            private = json.loads(private_path.read_text(encoding="utf-8"))
            technical = json.loads((output / "stage2-technical-summary.json").read_text(encoding="utf-8"))

            self.assertEqual(result["question_count"], 15)
            self.assertEqual(result["available_count"], 59)
            self.assertEqual(dataset["available_count"], 59)
            self.assertEqual(technical["response_count_ceiling"], 59)
            self.assertEqual([row["id"] for row in dataset["questions"]], [f"Q{i:02d}" for i in range(1, 16)])
            self.assertTrue(all([item["alias"] for item in row["candidates"]] == list("ABCD") for row in dataset["questions"]))
            failed_index = exporter.EXPECTED_CASE_IDS.index("en_am_rask")
            failed_alias = next(alias for alias, candidate in private["questions"][failed_index]["alias_map"].items()
                                if candidate == "gpt-6-luna@medium")
            self.assertIsNone(dataset["questions"][failed_index]["candidates"][ord(failed_alias) - ord("A")]["answer"])
            self.assertEqual(private["questions"][failed_index]["slot_dispositions"][failed_alias], "failed")
            self.assertEqual(private["runs"]["gpt-6-luna@medium"]["identity_chain"][0]["execution_commit"], "7" * 40)
            self.assertEqual(private["runs"]["gpt-6-luna@medium"]["identity_chain"][1]["execution_commit"], "8" * 40)
            failed_source = private["runs"]["gpt-6-luna@medium"]["case_sources"]["en_am_rask"]
            self.assertEqual(failed_source["lineage_role"], "source")
            self.assertEqual(failed_source["execution_commit"], "7" * 40)
            self.assertNotIn("gpt-6-luna", dataset_path.read_text(encoding="utf-8"))
            self.assertTrue(all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in hashes.items()))

    def test_continuation_rejects_tampered_owner_evidence_and_changed_execution_sha(self):
        for tamper in ("evidence", "source_report", "execution"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                plan_path, evidence_path, _, _ = continuation_artifacts(root)
                if tamper == "evidence":
                    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                    evidence["owner_attestation"]["output_tokens"] += 1
                    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                elif tamper == "source_report":
                    plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    source_report = Path(plan["source"]["report_path"])
                    source_report.write_bytes(source_report.read_bytes() + b" ")
                else:
                    plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    plan["continuation"]["execution_commit"] = "9" * 40
                    plan_path.write_text(json.dumps(plan), encoding="utf-8")
                with patch.object(exporter, "ROOT", root):
                    with self.assertRaises(exporter.ExportError):
                        exporter.export(None, root / ".state/review", root / "fixture.json", plan_path, evidence_path)

    def test_continuation_report_hashes_must_match_ledger_and_plan(self):
        for tamper in ("campaign", "run_identity_hash", "identity_hash", "probe"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                plan_path, evidence_path, report_paths, _ = continuation_artifacts(root)
                report_path = report_paths[0]
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if tamper == "campaign":
                    report["campaign_identity_hash"] = "c" * 64
                elif tamper in {"run_identity_hash", "identity_hash"}:
                    report[tamper] = "c" * 64
                else:
                    report["mode"] = "live-probe"
                    report["probe_only"] = True
                report_path.write_text(json.dumps(report), encoding="utf-8")
                with patch.object(exporter, "ROOT", root):
                    with self.assertRaises(exporter.ExportError):
                        exporter.export(None, root / ".state/review", root / "fixture.json", plan_path, evidence_path)

    def test_continuation_rejects_replayed_source_case_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, evidence_path, _, _ = continuation_artifacts(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            run = next(row for row in plan["continuation"]["runs"]
                       if row["candidate"] == "gpt-6-luna@medium")
            run["case_ids"].append("en_am_rask")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with patch.object(exporter, "ROOT", root):
                with self.assertRaisesRegex(exporter.ExportError, "traslapa"):
                    exporter.export(None, root / ".state/review", root / "fixture.json", plan_path, evidence_path)

    def test_unstarted_continuation_candidates_remain_null_without_synthetic_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, evidence_path, _, _ = continuation_artifacts(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            continuation_ledger_path = Path(plan["continuation"]["ledger_path"])
            ledger = json.loads(continuation_ledger_path.read_text(encoding="utf-8"))
            unstarted = "gpt-6.1-sol@medium"
            run_id = next(run["run_id"] for run in plan["continuation"]["runs"] if run["candidate"] == unstarted)
            del ledger["completed_runs"][run_id]
            ledger["status"] = "stopped_campaign_budget"
            continuation_ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            with patch.object(exporter, "ROOT", root):
                exporter.export(None, root / ".state/review", root / "fixture.json", plan_path, evidence_path)
            dataset = json.loads((root / ".state/review/stage2-review.json").read_text(encoding="utf-8"))
            private = json.loads((root / ".state/review/stage2-alias-key.json").read_text(encoding="utf-8"))
            null_count = 0
            for index, question in enumerate(dataset["questions"]):
                alias = next(alias for alias, candidate in private["questions"][index]["alias_map"].items()
                             if candidate == unstarted)
                answer = question["candidates"][ord(alias) - ord("A")]["answer"]
                self.assertIsNone(answer)
                self.assertEqual(private["questions"][index]["slot_dispositions"][alias], "not_attempted")
                null_count += 1
            self.assertEqual(null_count, 15)
            self.assertEqual(private["runs"][unstarted]["source_reports"], [])



def continuation_artifacts(root: Path) -> tuple[Path, Path, list[Path], dict[Path, str]]:
    fixture = fixture_payload()
    fixture_path = root / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    source_commit, next_commit = "7" * 40, "8" * 40
    fixture_sha256 = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    source_ids = list(exporter.EXPECTED_CASE_IDS[:9])
    source_identities = []
    for candidate in exporter.CANDIDATES:
        identity = run_report(candidate)["run_identity"]
        identity["execution_commit"] = source_commit
        identity["source_fingerprint"] = fixture_sha256
        source_identities.append(identity)
    source_hashes = [exporter._digest(identity) for identity in source_identities]
    source_ledger_identity = {
        "runs": source_identities,
        "run_identity_hashes": source_hashes,
        "budget_usd": 8.0,
        "expected_versions": fixture["expected_versions"],
        "snapshot_root": str(root / "site"),
        "prices": {
            "gpt-6-luna@medium": [0.1, 0.5], "gpt-6-luna@max": [0.1, 0.5],
            "gpt-6.1-sol@low": [2.0, 10.0], "gpt-6.1-sol@medium": [2.0, 10.0],
        },
    }
    source_campaign_hash = exporter._digest(source_ledger_identity)
    source_run = source_identities[0]
    source_report = run_report("gpt-6-luna@medium", [
        {"case_id": case_id, "model_turn_completed": index < 8,
         "status": "supported" if index < 8 else "provider_error",
         "turn_responses": [f"Respuesta fuente {index}"] if index < 8 else []}
        for index, case_id in enumerate(source_ids)
    ])
    source_report["run_identity"] = source_run
    source_report["run_identity_hash"] = exporter._digest(source_run)
    source_report["identity_hash"] = exporter._digest(source_run)
    source_report["campaign_identity_hash"] = source_campaign_hash
    source_report["case_count"] = 15
    source_report_path = root / "source-report.json"
    source_report_path.write_text(json.dumps(source_report), encoding="utf-8")
    source_ledger = {
        "identity": source_ledger_identity,
        "identity_hash": source_campaign_hash,
        "status": "stopped_unknown_spend",
        "spent_unknown": True,
        "budget_usd": 8.0,
        "known_spend_usd": 0.05460125,
        "active_run_id": None,
        "completed_runs": {
            source_run["run_id"]: {
                "identity": source_run,
                "identity_hash": source_hashes[0],
                "cases": [
                    {"case_id": case_id, "model_turn_completed": index < 8,
                     "status": "supported" if index < 8 else "provider_error", "usage_complete": index < 8}
                    for index, case_id in enumerate(source_ids)
                ],
            }
        },
    }
    source_ledger_path = root / "source-ledger.json"
    source_ledger_path.write_text(json.dumps(source_ledger), encoding="utf-8")
    source_ledger_sha = hashlib.sha256(source_ledger_path.read_bytes()).hexdigest()
    source_report_sha = hashlib.sha256(source_report_path.read_bytes()).hexdigest()
    evidence = {
        "schema_version": 1,
        "kind": "private_owner_usage_confirmation",
        "owner_attestation": {
            "source": "owner_reported_OpenAI_Usage", "aggregate_date": "2026-10-10",
            "model": "gpt-6-luna", "input_tokens": 408550, "output_tokens": 7065,
            "includes_failed_call": True, "external_usage_independently_verified": False,
            "exact_question": "<redacted>", "exact_owner_answer": "<redacted>",
        },
        "source_identity": {
            "campaign_identity_hash": source_campaign_hash,
            "campaign_ledger_sha256": source_ledger_sha, "report_sha256": source_report_sha,
            "execution_commit": source_commit, "run_identity_hash": source_hashes[0],
            "pilot_candidate_models_in_source_report": ["gpt-6-luna@medium"],
            "source_report_model_entry_count": 1,
        },
        "reconciliation": {
            "complete_responses": 8, "attempted_responses": 9, "failed_case": "en_am_rask",
            "failed_case_individual_usage": None, "failed_case_cost_estimate_usd": None,
            "invoice_total_usd": None, "aggregate_tokens_match_known_case_lower_bounds": True,
            "known_completed_case_cost_estimate_usd": 0.05460125,
        },
    }
    evidence_path = root / "owner-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    source_runs = []
    for identity, run_hash in zip(source_identities, source_hashes, strict=True):
        started = identity["candidate"] == "gpt-6-luna@medium"
        source_runs.append({
            "run_id": identity["run_id"], "candidate": identity["candidate"],
            "identity": identity, "identity_hash": run_hash, "started": started,
            "case_ids": source_ids if started else [],
        })
    continuation_id = "continuation-test"
    selected_by_candidate = {
        "gpt-6-luna@medium": list(exporter.EXPECTED_CASE_IDS[9:]),
        **{candidate: list(exporter.EXPECTED_CASE_IDS) for candidate in list(exporter.CANDIDATES)[1:]},
    }
    continuation_runs = []
    for identity in source_identities:
        candidate = identity["candidate"]
        run = {**identity, "run_id": f"{identity['run_id']}-cont-{continuation_id}",
               "case_ids_hash": exporter._digest(selected_by_candidate[candidate]),
               "execution_commit": next_commit}
        run["continuation"] = {
            "continuation_id": continuation_id,
            "source_campaign_identity_hash": source_campaign_hash,
            "source_run_id": identity["run_id"],
            "skipped_case_ids": source_ids if candidate == "gpt-6-luna@medium" else [],
            "failed_case_id_skipped": "en_am_rask" if candidate == "gpt-6-luna@medium" else None,
            "completed_run_ids_excluded": [],
            "accounted_spend_usd": 0.05460125,
        }
        continuation_runs.append({
            "run_id": run["run_id"], "identity": run, "identity_hash": exporter._digest(run),
            "candidate": candidate, "model": run["model"], "reasoning_effort": run["reasoning_effort"],
            "case_ids": selected_by_candidate[candidate],
        })
    remaining_budget = 7.94539875
    cont_reports_dir = root / "continuation"
    cont_reports_dir.mkdir()
    prices = source_ledger_identity["prices"]
    cont_ledger_identity = {
        "runs": [run["identity"] for run in continuation_runs],
        "run_identity_hashes": [run["identity_hash"] for run in continuation_runs],
        "budget_usd": remaining_budget,
        "expected_versions": fixture["expected_versions"],
        "snapshot_root": source_ledger_identity["snapshot_root"],
        "prices": prices,
    }
    continuation_campaign_hash = exporter._digest(cont_ledger_identity)
    actual_runs = {}
    continuation_report_paths = []
    for run in continuation_runs:
        candidate = run["candidate"]
        selected = run["case_ids"]
        report = run_report(candidate, [
            {"case_id": case_id, "model_turn_completed": True,
             "turn_responses": [f"Respuesta continuación {candidate[-4:]} {index}"]}
            for index, case_id in enumerate(selected)
        ])
        report["run_identity"] = run["identity"]
        report["run_identity_hash"] = run["identity_hash"]
        report["identity_hash"] = run["identity_hash"]
        report["campaign_identity_hash"] = continuation_campaign_hash
        report["case_count"] = len(selected)
        report_path = cont_reports_dir / f"{candidate.replace('@', '-')}.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        continuation_report_paths.append(report_path)
        actual_runs[run["run_id"]] = {
            "identity": run["identity"], "identity_hash": run["identity_hash"],
            "cases": [{"case_id": case_id, "model_turn_completed": True} for case_id in selected],
            "complete": True,
            "summary": {"report_path": str(report_path), "run_status": "completed",
                        "case_count": len(selected), "expected_case_count": len(selected), "complete": True},
        }
    cont_ledger = {
        "identity": cont_ledger_identity, "identity_hash": continuation_campaign_hash,
        "status": "completed", "active_run_id": None, "spent_unknown": False,
        "completed_runs": actual_runs,
    }
    cont_ledger_path = root / "continuation-ledger.json"
    cont_ledger_path.write_text(json.dumps(cont_ledger), encoding="utf-8")
    context_hash = exporter._digest([
        {"id": str(case.get("id", "")), "context": case.get("context", {})} for case in fixture["cases"]
    ])
    plan = {
        "schema_version": 1, "kind": "f2_9_stage2_continuation_plan",
        "mode": "live-campaign", "provider_calls_now": None,
        "source": {
            "campaign_identity_hash": source_campaign_hash, "ledger_sha256": source_ledger_sha,
            "ledger_path": str(source_ledger_path), "execution_commit": source_commit,
            "report_sha256": source_report_sha, "report_path": str(source_report_path),
            "owner_evidence_sha256": evidence_sha,
            "run_identity_hash": source_hashes[0], "runs": source_runs,
        },
        "continuation": {
            "continuation_id": continuation_id,
            "source_campaign_identity_hash": source_campaign_hash,
            "execution_commit": next_commit,
            "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
            "prompt_sha256": source_identities[0]["prompt_content_hash"],
            "context_sha256": context_hash,
            "tool_specs_sha256": source_identities[0]["tool_spec_hash"],
            "runtime_limits": source_identities[0]["limits"],
            "ledger_path": str(cont_ledger_path), "output_dir": str(cont_reports_dir),
            "runs": continuation_runs,
            "live_result": {"identity_hash": continuation_campaign_hash},
        },
        "billing_reconciliation": {
            "source_ledger_sha256": source_ledger_sha, "source_report_sha256": source_report_sha,
            "evidence_sha256": evidence_sha, "status": "owner_confirmed_aggregate",
            "usage_scope": "daily_account_aggregate", "individual_failed_call_usage": "unknown",
            "daily_aggregate_input_tokens": 408550, "daily_aggregate_output_tokens": 7065,
            "accounted_spend_usd": 0.05460125, "remaining_budget_usd": remaining_budget,
            "invoice_total_usd": None,
        },
        "case_count": 51,
    }
    plan_path = root / "continuation-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    source_files = [source_ledger_path, source_report_path, evidence_path, cont_ledger_path, *continuation_report_paths, plan_path]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    return plan_path, evidence_path, continuation_report_paths, hashes


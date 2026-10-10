"""Synthetic offline tests for the private stage-2 finalization join."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/chat"))
sys.path.insert(0, str(Path(__file__).parent))
import export_stage2_blind_review as exporter  # noqa: E402
import stage2_finalization_lineage as final_lineage  # noqa: E402
from test_chat_stage2_continuation_lineage import (  # noqa: E402
    continuation_artifacts,
    run_report,
)


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalization_artifacts(root: Path) -> tuple[Path, Path, Path, dict[Path, str]]:
    """Build production-shaped original, interrupted, recovery, and final ledgers."""
    cont_plan_path, evidence_path, continuation_reports, _ = continuation_artifacts(root)
    cont_plan = json.loads(cont_plan_path.read_text(encoding="utf-8"))
    fixture_path = root / "fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    cont_ledger_path = Path(cont_plan["continuation"]["ledger_path"])
    cont_ledger = json.loads(cont_ledger_path.read_text(encoding="utf-8"))
    runs = cont_plan["continuation"]["runs"]
    low = next(run for run in runs if run["candidate"] == "gpt-6.1-sol@low")
    low_run_id = low["run_id"]
    cont_ledger["status"] = "running"
    cont_ledger["active_run_id"] = low_run_id
    cont_ledger["completed_runs"] = {
        run_id: entry
        for run_id, entry in cont_ledger["completed_runs"].items()
        if entry["identity"]["candidate"] in {"gpt-6-luna@medium", "gpt-6-luna@max"}
    }
    _write(cont_ledger_path, cont_ledger)
    cont_ledger_hash = cont_ledger["identity_hash"]
    cont_plan_hash = hashlib.sha256(cont_plan_path.read_bytes()).hexdigest()

    progress_path = root / "progress.json"
    progress = {
        "status": "running",
        "active_case_id": "es_am_market_share",
        "known_estimated_spend_usd": 1.72828,
        "models": [{"candidate": "gpt-6.1-sol@low", "case_count": 13, "completed_turn_count": 13}],
    }
    progress_sha = _write(progress_path, progress)

    source_run = next(row for row in cont_plan["source"]["runs"] if row["candidate"] == "gpt-6.1-sol@low")
    recovery_path = root / "terminal-recovery.json"
    answer_text = "Respuesta recuperada para revisión humana"
    answer_sha = hashlib.sha256(answer_text.encode()).hexdigest()
    recovery = {
        "schema_version": 1,
        "capture_kind": "GET_completed_turn_recovery",
        "source": {
            "candidate": "gpt-6.1-sol@low",
            "case_id": "es_am_market_share",
            "continuation_id": cont_plan["continuation"]["continuation_id"],
            "run_id": low_run_id,
            "plan_sha256": cont_plan_hash,
            "progress_sha256": progress_sha,
            "source_run_identity_hash": source_run["identity_hash"],
            "continuation_run_identity_hash": low["identity_hash"],
        },
        "provider": {
            "turn_status": "completed",
            "session_status": "idle",
            "session_idle": True,
            "turn_identity_verified": True,
        },
        "request_controls": {"side_effecting_requests": 0},
        "usage": {"usage_complete": True, "input_tokens": 137951, "output_tokens": 499},
        "answer": {
            "present": True,
            "selected_assistant_message_count": 1,
            "text": answer_text,
            "sha256": answer_sha,
        },
        "evaluation": {
            "transport_recovered": True,
            "latency_valid": False,
            "auto_graded": False,
            "auto_approved": False,
            "tool_calls_inferred": False,
        },
    }
    recovery_sha = _write(recovery_path, recovery)
    derived_path = root / "derived-recovery.json"
    derived = run_report(
        "gpt-6.1-sol@low",
        [
            {
                "case_id": "es_am_market_share",
                "model_turn_completed": True,
                "status": "recovered_terminal_turn",
                "turn_responses": [answer_text],
                "response": answer_text,
                "quality": {"evaluated": False, "requires_blinded_human_rubric": True},
                "recovery_metadata": {"tool_calls_inferred": False, "tool_trace": "unavailable"},
            }
        ],
    )
    derived["run_identity"] = low["identity"]
    derived.pop("identity_hash", None)
    derived["run_identity_hash"] = low["identity_hash"]
    derived["campaign_identity_hash"] = cont_ledger_hash
    derived["case_count"] = 1
    derived["run_status"] = "recovered_partial"
    derived["derived_lineage"] = {
        "kind": "single_terminal_turn_recovery",
        "source_progress_sha256": progress_sha,
        "recovery_sha256": recovery_sha,
        "continuation_plan_sha256": cont_plan_hash,
        "tool_trace": "unavailable",
        "human_review_required": True,
    }
    derived_sha = _write(derived_path, derived)

    case_by_id = {case["id"]: case for case in fixture["cases"]}
    replacement_ids = list(exporter.EXPECTED_CASE_IDS[:13])
    never_ids = [exporter.EXPECTED_CASE_IDS[14]]
    selected_by_candidate = {
        "gpt-6.1-sol@low": replacement_ids + never_ids,
        "gpt-6.1-sol@medium": list(exporter.EXPECTED_CASE_IDS),
    }
    final_commit = "c" * 40
    final_run_rows = []
    final_report_paths: dict[str, Path] = {}
    for candidate, selected in selected_by_candidate.items():
        source_cont = next(run for run in runs if run["candidate"] == candidate)
        identity = json.loads(json.dumps(source_cont["identity"]))
        run_id = identity["run_id"].split("-cont-")[0] + "-final-test"
        identity.update(
            {
                "run_id": run_id,
                "case_ids_hash": exporter._digest(selected),
                "case_fixture_hash": exporter._digest([case_by_id[case_id] for case_id in selected]),
                "execution_commit": final_commit,
                "finalization": {
                    "source_continuation_run_id": source_cont["run_id"],
                    "source_identity_hash": source_cont["identity_hash"],
                },
            }
        )
        identity_hash = exporter._digest(identity)
        final_run_rows.append(
            {
                "run_id": run_id,
                "candidate": candidate,
                "identity": identity,
                "identity_hash": identity_hash,
                "case_ids": selected,
                "source_run_id": source_cont["run_id"],
                "report_paths": [],
            }
        )
    final_campaign_identity = {
        "runs": [row["identity"] for row in final_run_rows],
        "run_identity_hashes": [row["identity_hash"] for row in final_run_rows],
        "budget_usd": 7.94539875,
        "expected_versions": fixture["expected_versions"],
        "snapshot_root": str(root / "site"),
        "prices": cont_ledger["identity"]["prices"],
        "execution_commit": final_commit,
    }
    final_campaign_hash = exporter._digest(final_campaign_identity)
    final_completed = {}
    for slot in final_run_rows:
        candidate = slot["candidate"]
        selected = slot["case_ids"]
        report = run_report(
            candidate,
            [
                {
                    "case_id": case_id,
                    "model_turn_completed": True,
                    "turn_responses": [f"Respuesta final sintética {index + 1}"],
                }
                for index, case_id in enumerate(selected)
            ],
        )
        report["run_identity"] = slot["identity"]
        report.pop("identity_hash", None)
        report["run_identity_hash"] = slot["identity_hash"]
        report["campaign_identity_hash"] = final_campaign_hash
        report["case_count"] = len(selected)
        report_path = root / f"final-{candidate.replace('@', '-')}.json"
        _write(report_path, report)
        slot["report_paths"] = [str(report_path)]
        final_report_paths[candidate] = report_path
        final_completed[slot["run_id"]] = {
            "identity": slot["identity"],
            "cases": [{"case_id": case_id, "model_turn_completed": True} for case_id in selected],
            "complete": True,
            "spent_unknown": False,
            "summary": {"report_path": str(report_path), "complete": True},
        }
    final_ledger_path = root / "final-ledger.json"
    final_ledger = {
        "identity": final_campaign_identity,
        "identity_hash": final_campaign_hash,
        "status": "completed",
        "active_run_id": None,
        "completed_runs": final_completed,
    }
    _write(final_ledger_path, final_ledger)

    source_ledger_path = Path(cont_plan["source"]["ledger_path"])
    source_report_path = Path(cont_plan["source"]["report_path"])
    closed_reports = [
        {
            "path": str(continuation_reports[0]),
            "sha256": hashlib.sha256(continuation_reports[0].read_bytes()).hexdigest(),
            "candidate": "gpt-6-luna@medium",
        },
        {
            "path": str(continuation_reports[1]),
            "sha256": hashlib.sha256(continuation_reports[1].read_bytes()).hexdigest(),
            "candidate": "gpt-6-luna@max",
        },
    ]
    original_hashes = {
        "original_ledger": hashlib.sha256(source_ledger_path.read_bytes()).hexdigest(),
        "original_report": hashlib.sha256(source_report_path.read_bytes()).hexdigest(),
        "owner_evidence": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
    }
    source_sha = {
        **original_hashes,
        "continuation_plan": cont_plan_hash,
        "continuation_ledger": hashlib.sha256(cont_ledger_path.read_bytes()).hexdigest(),
        "closed_report_luna_medium": closed_reports[0]["sha256"],
        "closed_report_luna_max": closed_reports[1]["sha256"],
        "sol_low_progress": progress_sha,
        "recovery": recovery_sha,
    }
    final_plan = {
        "schema_version": 1,
        "kind": "f2_9_stage2_finalization_plan",
        "mode": "live-campaign",
        "provider_calls_now": None,
        "source": {
            "campaign_identity_hash": cont_plan["source"]["campaign_identity_hash"],
            "ledger_sha256": original_hashes["original_ledger"],
            "report_sha256": original_hashes["original_report"],
            "owner_evidence_sha256": original_hashes["owner_evidence"],
            "execution_commit": cont_plan["source"]["execution_commit"],
            "paths": {
                "original_ledger": str(source_ledger_path),
                "original_report": str(source_report_path),
                "owner_evidence": str(evidence_path),
            },
        },
        "interrupted_continuation": {
            "continuation_plan_sha256": cont_plan_hash,
            "continuation_ledger_sha256": source_sha["continuation_ledger"],
            "execution_commit": cont_plan["continuation"]["execution_commit"],
            "plan_path": str(cont_plan_path),
            "ledger_path": str(cont_ledger_path),
            "closed_reports": closed_reports,
            "progress_path": str(progress_path),
            "progress_sha256": progress_sha,
            "progress_case_count": 13,
            "progress_cost_is_aggregate": True,
        },
        "recovery": {
            "path": str(recovery_path),
            "sha256": recovery_sha,
            "status": "GET_recovered_remote_completed_idle",
            "case_id": "es_am_market_share",
            "candidate": "gpt-6.1-sol@low",
            "usage_complete": True,
            "input_tokens": 137951,
            "output_tokens": 499,
            "latency_ms": None,
            "tool_trace": "unavailable",
            "auto_graded": False,
            "auto_approved": False,
            "tool_calls_inferred": False,
            "plan_sha256": cont_plan_hash,
            "progress_sha256": progress_sha,
            "source_run_identity_hash": source_run["identity_hash"],
            "continuation_run_identity_hash": low["identity_hash"],
            "answer_sha256": answer_sha,
            "report_path": str(derived_path),
            "report_sha256": derived_sha,
        },
        "billing_reconciliation": {
            "authorized_reserve_usd": 8.0,
            "remaining_budget_usd": 7.94539875,
            "invoice_total_usd": None,
        },
        "finalization": {
            "execution_commit": final_commit,
            "continuation_id": "test",
            "plan_path": str(root / "finalization-plan.json"),
            "ledger_path": str(final_ledger_path),
            "output_dir": str(root / "final"),
            "runs": final_run_rows,
            "derived_reports": {
                "sol_low_recovery": {
                    "path": str(derived_path),
                    "sha256": derived_sha,
                    "candidate": "gpt-6.1-sol@low",
                    "identity": low["identity"],
                    "identity_hash": low["identity_hash"],
                    "source_run_identity_hash": low["identity_hash"],
                    "recovery_sha256": recovery_sha,
                    "progress_sha256": progress_sha,
                    "human_review_required": True,
                }
            },
            "replacement_case_ids": replacement_ids,
            "never_attempted_case_ids": never_ids,
            "recovered_case_id_skipped": "es_am_market_share",
            "excluded_original_failure": {"candidate": "gpt-6-luna@medium", "case_id": "en_am_rask"},
            "new_provider_request_count": 29,
            "response_count_ceiling_if_complete": 59,
            "max_reviewable_candidates": 59,
        },
        "source_sha256": source_sha,
        "live_result": {"status": "completed", "identity_hash": final_campaign_hash},
    }
    final_plan_path = root / "finalization-plan.json"
    _write(final_plan_path, final_plan)

    hashes_to_check = [
        source_ledger_path,
        source_report_path,
        evidence_path,
        cont_plan_path,
        cont_ledger_path,
        progress_path,
        recovery_path,
        derived_path,
        *continuation_reports,
        *final_report_paths.values(),
        final_ledger_path,
    ]
    return (
        final_plan_path,
        evidence_path,
        fixture_path,
        {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in hashes_to_check},
    )


class Stage2FinalizationLineageTests(unittest.TestCase):
    def _run(self, root: Path, plan: Path, evidence: Path, fixture_path: Path, pins: dict[Path, str]):
        plan_payload = json.loads(plan.read_text(encoding="utf-8"))
        with (
            patch.object(exporter, "ROOT", root),
            patch.dict(
                final_lineage.APPROVED_SOURCE_SHA256,
                plan_payload["source_sha256"],
                clear=True,
            ),
            patch.object(final_lineage, "ORIGINAL_EXECUTION", plan_payload["source"]["execution_commit"]),
            patch.object(
                final_lineage,
                "CONTINUATION_EXECUTION",
                plan_payload["interrupted_continuation"]["execution_commit"],
            ),
        ):
            return exporter.export(
                None,
                root / ".state/review",
                fixture_path,
                owner_usage_evidence_path=evidence,
                finalization_plan_path=plan,
            )

    def test_finalization_exports_59_blind_rows_and_preserves_every_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, evidence, fixture_path, original_hashes = finalization_artifacts(root)
            result = self._run(root, plan, evidence, fixture_path, original_hashes)
            dataset = json.loads((root / ".state/review/stage2-review.json").read_text())
            private = json.loads((root / ".state/review/stage2-alias-key.json").read_text())
            technical = json.loads((root / ".state/review/stage2-technical-summary.json").read_text())
            self.assertEqual((result["question_count"], result["available_count"]), (15, 59))
            self.assertEqual(dataset["available_count"], 59)
            self.assertEqual(technical["response_count_ceiling"], 59)
            self.assertTrue(technical["finalization"])
            failed_index = exporter.EXPECTED_CASE_IDS.index("en_am_rask")
            luna_medium = next(
                alias
                for alias, candidate in private["questions"][failed_index]["alias_map"].items()
                if candidate == "gpt-6-luna@medium"
            )
            self.assertIsNone(
                dataset["questions"][failed_index]["candidates"][ord(luna_medium) - ord("A")]["answer"]
            )
            self.assertEqual(private["questions"][failed_index]["slot_dispositions"][luna_medium], "failed")
            sol_low_cases = private["runs"]["gpt-6.1-sol@low"]["case_sources"]
            self.assertEqual(sol_low_cases["es_am_market_share"]["lineage_role"], "recovery")
            self.assertEqual(sol_low_cases["es_am_market_share"]["latency_ms"], None)
            self.assertEqual(sol_low_cases["es_am_market_share"]["tool_trace"], "unavailable")
            self.assertEqual(sol_low_cases["es_am_market_share"]["human_review_required"], True)
            self.assertEqual(
                sol_low_cases["es_viva_missing_company_passengers"]["lineage_role"], "finalization"
            )
            self.assertNotIn("gpt-6.1-sol", (root / ".state/review/stage2-review.json").read_text())
            for path, before in original_hashes.items():
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_tampered_recovery_lineage_and_mixed_final_report_sha_fail_closed(self):
        for tamper in ("recovery", "campaign", "report_hash"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                plan_path, evidence, fixture_path, hashes = finalization_artifacts(root)
                plan = json.loads(plan_path.read_text())
                if tamper == "recovery":
                    recovery_path = Path(plan["recovery"]["path"])
                    artifact = json.loads(recovery_path.read_text())
                    artifact["source"]["case_id"] = "es_viva_missing_company_passengers"
                    _write(recovery_path, artifact)
                    # Pin the changed bytes only to prove semantic identity checks reject it.
                    hashes[recovery_path] = hashlib.sha256(recovery_path.read_bytes()).hexdigest()
                elif tamper == "campaign":
                    report_path = Path(plan["finalization"]["runs"][0]["report_paths"][0])
                    report = json.loads(report_path.read_text())
                    report["campaign_identity_hash"] = "d" * 64
                    _write(report_path, report)
                    hashes[report_path] = hashlib.sha256(report_path.read_bytes()).hexdigest()
                else:
                    plan["finalization"]["runs"][0]["report_paths"] = []
                    _write(plan_path, plan)
                with self.assertRaises(exporter.ExportError):
                    self._run(root, plan_path, evidence, fixture_path, hashes)
                self.assertFalse((root / ".state/review/stage2-review.json").exists())

    def test_native_finalization_may_not_overlap_the_recovered_slot_or_mix_execution_sha(self):
        for tamper in ("overlap", "execution"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                plan_path, evidence, fixture_path, hashes = finalization_artifacts(root)
                plan = json.loads(plan_path.read_text())
                slot = next(
                    row for row in plan["finalization"]["runs"] if row["candidate"] == "gpt-6.1-sol@low"
                )
                if tamper == "overlap":
                    slot["case_ids"].insert(-1, "es_am_market_share")
                    slot["identity"]["case_ids_hash"] = exporter._digest(slot["case_ids"])
                    slot["identity_hash"] = exporter._digest(slot["identity"])
                else:
                    slot["identity"]["execution_commit"] = "e" * 40
                    slot["identity_hash"] = exporter._digest(slot["identity"])
                _write(plan_path, plan)
                with self.assertRaises(exporter.ExportError):
                    self._run(root, plan_path, evidence, fixture_path, hashes)
                self.assertFalse((root / ".state/review/stage2-review.json").exists())

    def test_finalization_source_symlinks_are_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path, evidence, fixture_path, hashes = finalization_artifacts(root)
            plan = json.loads(plan_path.read_text())
            source_path = Path(plan["source"]["paths"]["original_ledger"])
            linked_path = root / "linked-original-ledger.json"
            linked_path.symlink_to(source_path)
            plan["source"]["paths"]["original_ledger"] = str(linked_path)
            _write(plan_path, plan)
            with self.assertRaisesRegex(exporter.ExportError, "enlace simbólico"):
                self._run(root, plan_path, evidence, fixture_path, hashes)
            self.assertFalse((root / ".state/review/stage2-review.json").exists())

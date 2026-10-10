"""Synthetic offline tests for the private stage-2 finalization join."""

from __future__ import annotations

import argparse
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
import finalize_stage2_campaign as finalizer  # noqa: E402
import stage2_finalization_lineage as final_lineage  # noqa: E402
from test_chat_stage2_continuation_lineage import (  # noqa: E402
    continuation_artifacts,
    run_report,
)


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_with_real_producer(
    root: Path, paths: dict[str, Path], fixture: dict
) -> tuple[dict, list[dict], Path]:
    """Exercise the actual offline plan producer with deterministic source validation."""
    cont_plan = json.loads(paths["continuation_plan"].read_text(encoding="utf-8"))
    cont_ledger = json.loads(paths["continuation_ledger"].read_text(encoding="utf-8"))
    recovery = json.loads(paths["terminal_recovery"].read_text(encoding="utf-8"))
    low = next(run for run in cont_plan["continuation"]["runs"] if run["candidate"] == "gpt-6.1-sol@low")
    source_low = next(run for run in cont_plan["source"]["runs"] if run["candidate"] == "gpt-6.1-sol@low")
    source = {
        "original_ledger": json.loads(paths["original_ledger"].read_text(encoding="utf-8")),
        "original_report": json.loads(paths["original_report"].read_text(encoding="utf-8")),
        "owner_evidence": json.loads(paths["owner_evidence"].read_text(encoding="utf-8")),
        "continuation_plan": cont_plan,
        "_low_run": low,
        "_source_low_run": source_low,
        "_continuation_campaign_hash": cont_ledger["identity_hash"],
        "_recovered_answer": recovery["answer"]["text"],
        "_answer_sha256": recovery["answer"]["sha256"],
        "_recovered_input_tokens": recovery["usage"]["input_tokens"],
        "_recovered_output_tokens": recovery["usage"]["output_tokens"],
    }
    continuation = cont_plan["continuation"]
    base_plan = {
        "fixture_file_sha256": continuation["fixture_sha256"],
        "prompt_sha256": continuation["prompt_sha256"],
        "case_context_sha256": continuation["context_sha256"],
        "tool_specs_sha256": continuation["tool_specs_sha256"],
    }
    source_bytes = {name: path.read_bytes() for name, path in paths.items()}
    source["closed_report_luna_medium"] = json.loads(source_bytes["closed_report_luna_medium"])
    source["closed_report_luna_max"] = json.loads(source_bytes["closed_report_luna_max"])
    source_pins = {name: hashlib.sha256(content).hexdigest() for name, content in source_bytes.items()}
    output = root / "producer-output"
    args = argparse.Namespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=output / "sol-low-recovered-case.json",
    )
    prepared_runs = [
        {
            "candidate": run["candidate"],
            "prompt": "synthetic frozen prompt",
            "text_verbosity": "medium",
            "limits": {},
        }
        for run in continuation["runs"]
    ]
    with (
        patch.object(finalizer, "_validate_output_paths"),
        patch.object(finalizer, "_reject_source_symlinks"),
        patch.object(finalizer, "read_pinned_sources", return_value=source_bytes),
        patch.object(finalizer, "validate_sources", return_value=source),
        patch.object(
            finalizer,
            "prepare",
            return_value=(
                base_plan, prepared_runs, fixture["cases"], root / "site",
                json.loads((ROOT / "config/chat/models.json").read_text()), fixture,
            ),
        ),
        patch.object(finalizer, "_git_execution_commit", return_value="d" * 40),
        patch.dict(finalizer.APPROVED_SOURCE_SHA256, source_pins, clear=True),
        patch.object(finalizer, "EXPECTED_ORIGINAL_EXECUTION", cont_plan["source"]["execution_commit"]),
        patch.object(
            finalizer,
            "EXPECTED_CONTINUATION_EXECUTION",
            continuation["execution_commit"],
        ),
    ):
        plan, runs, _, _, _, _ = finalizer.prepare_finalization(args)
    if plan["mode"] != "offline-preflight-only" or plan["provider_calls_now"] != 0:
        raise AssertionError("El productor no emitió el contrato offline esperado")
    return plan, runs, args.derived_report


def finalization_artifacts(root: Path) -> tuple[Path, Path, Path, dict[Path, str]]:
    """Build production-shaped original, interrupted, recovery, and final ledgers."""
    cont_plan_path, evidence_path, continuation_reports, _ = continuation_artifacts(root)
    cont_plan = json.loads(cont_plan_path.read_text(encoding="utf-8"))
    # Finalization intentionally consumes the frozen preflight plan while its
    # ledger, progress checkpoint, and two closed reports prove what ran.
    cont_plan["mode"] = "offline-preflight-only"
    cont_plan["provider_calls_now"] = 0
    cont_plan.pop("live_result", None)
    _write(cont_plan_path, cont_plan)
    fixture_path = root / "fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    source_ledger_path = Path(cont_plan["source"]["ledger_path"])
    source_report_path = Path(cont_plan["source"]["report_path"])
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
        "models": [{"model": "gpt-6.1-sol", "case_count": 13, "completed_turn_count": 13}],
    }
    progress_sha = _write(progress_path, progress)

    source_run = next(row for row in cont_plan["source"]["runs"] if row["candidate"] == "gpt-6.1-sol@low")
    recovery_path = root / "terminal-recovery.json"
    answer_text = "Respuesta recuperada para revisión humana"
    answer_sha = hashlib.sha256(answer_text.encode()).hexdigest()
    recovery = {
        "schema_version": 1,
        "capture_kind": "terminal_transport_recovery",
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
    _write(derived_path, derived)
    final_commit = "d" * 40
    source_paths = {
        "original_ledger": source_ledger_path,
        "original_report": source_report_path,
        "owner_evidence": evidence_path,
        "continuation_plan": cont_plan_path,
        "continuation_ledger": cont_ledger_path,
        "closed_report_luna_medium": continuation_reports[0],
        "closed_report_luna_max": continuation_reports[1],
        "sol_low_progress": progress_path,
        "terminal_recovery": recovery_path,
    }
    producer_plan, produced_runs, produced_derived_path = _prepare_with_real_producer(
        root, source_paths, fixture
    )
    derived_path = produced_derived_path
    final_run_rows = producer_plan["finalization"]["runs"]
    final_report_paths: dict[str, Path] = {}
    for run in produced_runs:
        candidate = run["candidate"]
        selected = run["case_ids"]
        run_row = next(row for row in final_run_rows if row["run_id"] == run["run_id"])
        run_row["report_paths"] = []
    final_campaign_identity = {
        "runs": [row["identity"] for row in final_run_rows],
        "run_identity_hashes": [row["identity_hash"] for row in final_run_rows],
        "budget_usd": producer_plan["billing_reconciliation"]["remaining_budget_usd"],
        "expected_versions": fixture["expected_versions"],
        "snapshot_root": str(root / "site"),
        "prices": cont_ledger["identity"]["prices"],
        "execution_commit": final_commit,
        "reservation_assumption_override": producer_plan["billing_reconciliation"][
            "admission_reservation"
        ],
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

    final_plan = producer_plan
    final_plan["mode"] = "live-campaign"
    final_plan["provider_calls_now"] = None
    final_plan["finalization"]["ledger_path"] = str(final_ledger_path)
    final_plan["finalization"]["plan_path"] = str(root / "finalization-plan.json")
    final_plan["finalization"]["output_dir"] = str(root / "final")
    final_plan["live_result"] = {
        "status": "completed",
        "identity_hash": final_campaign_hash,
        "run_summaries": [
            {"run_id": run["run_id"], "report_path": str(final_report_paths[run["candidate"]])}
            for run in produced_runs
        ],
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
    def test_final_execution_commit_must_resolve_in_git_history(self):
        self.assertFalse(final_lineage._is_commit_ancestor("0" * 40))

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
            patch.object(final_lineage, "_is_commit_ancestor", return_value=True),
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
            plan_payload = json.loads(plan.read_text(encoding="utf-8"))
            recovery_lineage = plan_payload["finalization"]["derived_reports"]["sol_low_recovery"]
            self.assertIn("terminal_recovery", plan_payload["source_sha256"])
            self.assertNotIn("recovery", plan_payload["source_sha256"])
            self.assertNotEqual(
                recovery_lineage["source_run_identity_hash"], recovery_lineage["identity_hash"]
            )
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

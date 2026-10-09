"""Offline contract tests for F2.9 stage-1 review export."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/chat"))
import export_stage1_blind_review as exporter  # noqa: E402


def detailed_report(cases: list[dict[str, object]], variant: str) -> dict[str, object]:
    return {
        "run_status": "completed",
        "known_estimated_cost_usd": 0.012,
        "estimated_cost_usd": 0.012,
        "run_identity": {
            "stage": 1,
            "prompt_variant": variant,
            "candidate": "gpt-6-luna@medium",
        },
        "models": [{
            "candidate": "gpt-6-luna@medium",
            "model": "gpt-6-luna",
            "reasoning_effort": "medium",
            "spent_unknown": False,
            "token_totals": {"input_tokens": 10, "output_tokens": 5, "usage_complete_case_count": 58},
            "latency_seconds": {"p50": 1.0, "p90": 2.0},
            "cases": cases,
        }],
        "private_marker": f"{variant.upper()}_PRIVATE",
    }


class Stage1BlindExportTests(unittest.TestCase):
    def test_exports_blind_two_alias_dataset_and_grouped_multiturn_markdown(self):
        cases = exporter._fixture_cases()
        report_cases = []
        for case in cases:
            turns = case.get("turns") or [case["question"]]
            report_cases.append({
                "case_id": case["id"],
                "model_turn_completed": True,
                "provider_turn_started": True,
                "usage_complete": True,
                "turn_responses": [f"Synthetic answer turn {index + 1}" for index in range(len(turns))],
                "session_id": "session_PRIVATE_DO_NOT_EXPORT",
                "provider_events": [{"private": "raw log"}],
            })
        with tempfile.TemporaryDirectory() as temporary:
            current = Path(temporary) / "current-report.json"
            proposed = Path(temporary) / "proposed-report.json"
            current.write_text(json.dumps(detailed_report(report_cases, "current")), encoding="utf-8")
            proposed.write_text(json.dumps(detailed_report(report_cases, "proposed")), encoding="utf-8")
            output = Path(temporary) / "out"
            result = exporter.export(current, proposed, output)

            dataset_text = (output / "stage1-review.json").read_text(encoding="utf-8")
            dataset = json.loads(dataset_text)
            markdown = (output / "stage1-review.md").read_text(encoding="utf-8")
            key = json.loads((output / "stage1-alias-key.json").read_text(encoding="utf-8"))
            technical = json.loads((output / "stage1-technical-summary.json").read_text(encoding="utf-8"))

            self.assertEqual(len(dataset["questions"]), 58)
            self.assertEqual(dataset["available_count"], 116)
            self.assertTrue(all(len(question["candidates"]) == 2 for question in dataset["questions"]))
            self.assertTrue(all("Synthetic answer turn" in candidate["answer"]
                                for question in dataset["questions"] for candidate in question["candidates"]))
            self.assertIn("turno 2", markdown)
            self.assertIn("Utilidad (nota cualitativa)", markdown)
            self.assertIn("Redacción (nota cualitativa)", markdown)
            self.assertIn("Mejor respuesta para este caso", markdown)
            self.assertNotIn("gpt-6-luna", dataset_text + markdown)
            self.assertNotIn("CURRENT_PRIVATE", dataset_text + markdown)
            self.assertNotIn("PROPOSED_PRIVATE", dataset_text + markdown)
            self.assertNotIn("session_PRIVATE_DO_NOT_EXPORT", dataset_text + markdown)
            self.assertNotIn("raw log", dataset_text + markdown)
            self.assertEqual(key["variants"]["current"]["model"], "gpt-6-luna")
            self.assertEqual(technical["estimated_cost_usd_total"], 0.024)
            self.assertEqual(technical["runs"][0]["usage_incomplete_or_unknown_count"], 0)
            if os.name == "posix":
                self.assertEqual((output.stat().st_mode & 0o777), 0o700)
                for name in ("stage1-review.json", "stage1-review.md", "stage1-alias-key.json", "stage1-technical-summary.json"):
                    self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)

    def test_missing_or_failed_responses_remain_explicit_in_private_key(self):
        dataset, key, _ = exporter._blind_dataset(
            [{"id": "synthetic-case", "question": "Q", "locale": "es", "expected": {"status": "refused"}}],
            {"current": {}, "proposed": {"synthetic-case": {"case_id": "synthetic-case", "model_turn_completed": False}}},
        )
        self.assertEqual(dataset["available_count"], 0)
        statuses = key["questions"][0]["slot_dispositions"]
        self.assertCountEqual(statuses.values(), ["not_attempted", "failed"])

    def test_does_not_overwrite_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            output.mkdir()
            target = output / "stage1-review.json"
            target.write_text("private previous export", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                exporter._write_private(target, b"new export")
            self.assertEqual(target.read_text(encoding="utf-8"), "private previous export")

    def test_rejects_wrong_prompt_variant_before_building_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            current = Path(temporary) / "current-report.json"
            proposed = Path(temporary) / "proposed-report.json"
            current.write_text(json.dumps(detailed_report([], "proposed")), encoding="utf-8")
            proposed.write_text(json.dumps(detailed_report([], "proposed")), encoding="utf-8")
            with self.assertRaisesRegex(exporter.ExportError, "variante current"):
                exporter.export(current, proposed, Path(temporary) / "out")


if __name__ == "__main__":
    unittest.main()

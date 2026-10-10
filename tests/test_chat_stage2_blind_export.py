"""Offline contract tests for the private F2.9 stage-2 blind review export."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/chat"))
import export_stage2_blind_review as exporter  # noqa: E402


def fixture_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "DERIVED_OFFLINE_REVIEW",
        "expected_versions": {"data_version": "data-v1", "semantic_version": "semantic-v1"},
        "cases": [
            {
                "id": case_id,
                "cohort": "business" if case_id.startswith("N") else "safety",
                "question": f"Pregunta sintética {index + 1}",
                "locale": "es" if index % 2 == 0 else "en",
                "expected": {"status": "supported", "rows": []},
            }
            for index, case_id in enumerate(exporter.EXPECTED_CASE_IDS)
        ],
    }


def run_report(candidate: str, cases: list[dict] | None = None) -> dict:
    model, effort = exporter.CANDIDATES[candidate]
    fixture_cases = fixture_payload()["cases"]
    identity = {
        "stage": 2,
        "run_id": f"f22-s2-{exporter.re.sub(r'[^a-z0-9]+', '-', candidate.casefold()).strip('-')}-proposed-r1",
        "candidate": candidate,
        "model": model,
        "reasoning_effort": effort,
        "text_verbosity": "medium",
        "prompt_variant": "proposed",
        "prompt_content_hash": "a" * 64,
        "tool_spec_hash": "b" * 64,
        "data_version": "data-v1",
        "semantic_version": "semantic-v1",
        "limits": {"max_tool_calls": 16},
        "repetition": 1,
        "case_ids_hash": exporter._digest([case["id"] for case in fixture_cases]),
        "case_fixture_hash": exporter._digest(fixture_cases),
    }
    return {
        "mode": "live-evaluation",
        "probe_only": False,
        "run_status": "completed",
        "data_version": "data-v1",
        "semantic_version": "semantic-v1",
        "case_count": 15,
        "run_identity": identity,
        "identity_hash": exporter._digest(identity),
        "run_identity_hash": exporter._digest(identity),
        "campaign_identity_hash": "c" * 64,
        "models": [{
            "candidate": candidate,
            "model": model,
            "reasoning_effort": effort,
            "cases": cases if cases is not None else [
                {"case_id": case_id, "model_turn_completed": True, "turn_responses": [f"Respuesta sintética de prueba {index + 1}"]}
                for index, case_id in enumerate(exporter.EXPECTED_CASE_IDS)
            ],
        }],
    }


class Stage2BlindExportTests(unittest.TestCase):
    def _reports(self, folder: Path, overrides: dict[str, dict] | None = None) -> dict[str, Path]:
        paths = {}
        for candidate in exporter.CANDIDATES:
            path = folder / f"{candidate.replace('@', '-')}.json"
            report = (overrides or {}).get(candidate) or run_report(candidate)
            path.write_text(json.dumps(report), encoding="utf-8")
            if os.name == "posix":
                path.chmod(0o600)
            paths[candidate] = path
        return paths

    def test_writes_private_blind_json_and_separate_random_alias_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture_path = root / "fixture.json"
            fixture_path.write_text(json.dumps(fixture_payload()), encoding="utf-8")
            reports = self._reports(root)
            with patch.object(exporter, "ROOT", root):
                result = exporter.export(reports, root / ".state/outputs/review", fixture_path)
            output = root / ".state/outputs/review"
            dataset_text = (output / "stage2-review.json").read_text(encoding="utf-8")
            dataset = json.loads(dataset_text)
            alias_key = json.loads((output / "stage2-alias-key.json").read_text(encoding="utf-8"))
            technical = json.loads((output / "stage2-technical-summary.json").read_text(encoding="utf-8"))

            self.assertEqual(result["question_count"], 15)
            self.assertEqual(result["candidate_slots"], 60)
            self.assertEqual(dataset["available_count"], 60)
            self.assertEqual([question["id"] for question in dataset["questions"]], [f"Q{i:02d}" for i in range(1, 16)])
            self.assertTrue(all([candidate["alias"] for candidate in question["candidates"]] == list("ABCD") for question in dataset["questions"]))
            self.assertEqual(len(alias_key["questions"]), 15)
            self.assertTrue(all(set(row["alias_map"]) == set("ABCD") for row in alias_key["questions"]))
            self.assertEqual(len(alias_key["runs"]), 4)
            self.assertNotIn("gpt-6-luna", dataset_text)
            self.assertNotIn("reasoning_effort", dataset_text)
            self.assertNotIn("identity_hash", dataset_text)
            self.assertNotIn("case_id", dataset_text)
            self.assertEqual(technical["null_slot_count"], 0)
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                for path in output.iterdir():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_failed_empty_and_missing_cases_remain_null_with_private_dispositions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = fixture_payload()
            reports = {}
            missing_case = exporter.EXPECTED_CASE_IDS[0]
            empty_case = exporter.EXPECTED_CASE_IDS[1]
            failed_case = exporter.EXPECTED_CASE_IDS[2]
            for candidate in exporter.CANDIDATES:
                report = run_report(candidate)
                rows = report["models"][0]["cases"]
                rows[:] = [row for row in rows if row["case_id"] != missing_case]
                for row in rows:
                    if row["case_id"] == empty_case:
                        row["turn_responses"] = ["  "]
                    if row["case_id"] == failed_case:
                        row["model_turn_completed"] = False
                path = root / f"{candidate.replace('@', '-')}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                reports[candidate] = path
            dataset, key, technical = exporter.build_blind_dataset(fixture, reports)
            self.assertEqual(technical["null_slot_count"], 12)
            for case_id, disposition in ((missing_case, "not_attempted"), (empty_case, "no_answer"), (failed_case, "failed")):
                index = exporter.EXPECTED_CASE_IDS.index(case_id)
                question = dataset["questions"][index]
                private = key["questions"][index]
                alias = next(alias for alias, status in private["slot_dispositions"].items() if status == disposition)
                self.assertIsNone(question["candidates"][ord(alias) - ord("A")]["answer"])

    def test_rejects_identity_snapshot_prompt_or_fixture_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changed = run_report("gpt-6-luna@medium")
            changed["run_identity"]["semantic_version"] = "other-semantic"
            changed["identity_hash"] = exporter._digest(changed["run_identity"])
            changed["run_identity_hash"] = exporter._digest(changed["run_identity"])
            reports = self._reports(root, {"gpt-6-luna@medium": changed})
            with self.assertRaisesRegex(exporter.ExportError, "versión semántica"):
                exporter.build_blind_dataset(fixture_payload(), reports)

            reports = self._reports(root)
            drifted = fixture_payload()
            drifted["cases"][0]["context"] = {"period": "changed"}
            with self.assertRaisesRegex(exporter.ExportError, "case_fixture_hash"):
                exporter.build_blind_dataset(drifted, reports)

            reports = self._reports(root)
            report = json.loads(reports["gpt-6-luna@medium"].read_text(encoding="utf-8"))
            report["identity_hash"] = "0" * 64
            report["run_identity_hash"] = "0" * 64
            reports["gpt-6-luna@medium"].write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(exporter.ExportError, "hash de run_identity"):
                exporter.build_blind_dataset(fixture_payload(), reports)

    def test_rejects_identity_leaks_unknown_cases_and_public_output_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_report("gpt-6-luna@medium")
            report["models"][0]["cases"][0]["turn_responses"] = ["La respondió gpt-6-luna."]
            reports = self._reports(root, {"gpt-6-luna@medium": report})
            with self.assertRaisesRegex(exporter.ExportError, "revela identidad"):
                exporter.build_blind_dataset(fixture_payload(), reports)

            unknown = run_report("gpt-6-luna@medium")
            unknown["models"][0]["cases"].append({"case_id": "N99", "model_turn_completed": True, "response": "x"})
            reports = self._reports(root, {"gpt-6-luna@medium": unknown})
            with self.assertRaisesRegex(exporter.ExportError, "casos ajenos"):
                exporter.build_blind_dataset(fixture_payload(), reports)

            fixture_path = root / "fixture.json"
            fixture_path.write_text(json.dumps(fixture_payload()), encoding="utf-8")
            reports = self._reports(root)
            with patch.object(exporter, "ROOT", root):
                with self.assertRaisesRegex(exporter.ExportError, r"dentro de \.state"):
                    exporter.export(reports, root / "public", fixture_path)

    def test_unions_resumed_fragments_with_per_case_source_lineage_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = fixture_payload()
            reports = self._reports(root)
            candidate = "gpt-6-luna@medium"
            first = run_report(candidate)
            first["models"][0]["cases"] = [
                {"case_id": case_id, "model_turn_completed": True,
                 "turn_responses": [f"Original primera parte: {index}"]}
                for index, case_id in enumerate(exporter.EXPECTED_CASE_IDS[:8])
            ]
            # The first budget-stopped invocation keeps its original planned
            # count even though only eight detailed rows were persisted.
            first["case_count"] = 15
            resumed = run_report(candidate)
            resumed["models"][0]["cases"] = [
                {"case_id": case_id, "model_turn_completed": True,
                 "turn_responses": [f"Respuesta reanudada: {index}"]}
                for index, case_id in enumerate(exporter.EXPECTED_CASE_IDS[8:], 8)
            ]
            resumed["case_count"] = 7
            first_path = root / "first.json"
            resumed_path = root / "resumed.json"
            first_path.write_text(json.dumps(first), encoding="utf-8")
            resumed_path.write_text(json.dumps(resumed), encoding="utf-8")
            before = {
                first_path: hashlib.sha256(first_path.read_bytes()).hexdigest(),
                resumed_path: hashlib.sha256(resumed_path.read_bytes()).hexdigest(),
            }
            reports[candidate] = [first_path, resumed_path]

            dataset, key, _ = exporter.build_blind_dataset(fixture, reports)
            lineage = key["runs"][candidate]
            self.assertEqual(lineage["identity"], first["run_identity"])
            self.assertEqual(len(lineage["source_reports"]), 2)
            self.assertEqual(set(lineage["case_sources"]), set(exporter.EXPECTED_CASE_IDS))
            self.assertEqual(lineage["source_reports"][0]["case_ids"], list(exporter.EXPECTED_CASE_IDS[:8]))
            self.assertEqual(lineage["source_reports"][1]["case_ids"], list(exporter.EXPECTED_CASE_IDS[8:]))
            for index, case_id in enumerate(exporter.EXPECTED_CASE_IDS):
                answer_row = dataset["questions"][index]
                alias = next(item["alias"] for item in answer_row["candidates"]
                             if key["questions"][index]["alias_map"][item["alias"]] == candidate)
                answer = answer_row["candidates"][ord(alias) - ord("A")]["answer"]
                expected = f"Original primera parte: {index}" if index < 8 else f"Respuesta reanudada: {index}"
                self.assertEqual(answer, expected)
                source_path = first_path if index < 8 else resumed_path
                self.assertEqual(lineage["case_sources"][case_id]["source_report_sha256"], before[source_path])
            self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}, before)

    def test_missing_candidate_fragment_stays_null_and_overlaps_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = self._reports(root)
            candidate = "gpt-6-luna@medium"
            partial = run_report(candidate)
            missing = exporter.EXPECTED_CASE_IDS[-1]
            partial["models"][0]["cases"] = [row for row in partial["models"][0]["cases"] if row["case_id"] != missing]
            partial_path = root / "missing.json"
            partial_path.write_text(json.dumps(partial), encoding="utf-8")
            reports[candidate] = [partial_path]
            dataset, key, technical = exporter.build_blind_dataset(fixture_payload(), reports)
            question_index = exporter.EXPECTED_CASE_IDS.index(missing)
            alias = next(alias for alias, run in key["questions"][question_index]["alias_map"].items()
                         if run == candidate)
            self.assertIsNone(dataset["questions"][question_index]["candidates"][ord(alias) - ord("A")]["answer"])
            self.assertEqual(key["questions"][question_index]["slot_dispositions"][alias], "not_attempted")
            self.assertEqual(technical["null_slot_count"], 1)
            self.assertNotIn(missing, key["runs"][candidate]["case_sources"])

            second = run_report(candidate, cases=[
                {"case_id": exporter.EXPECTED_CASE_IDS[0], "model_turn_completed": True,
                 "turn_responses": ["duplicate"]}
            ])
            second_path = root / "overlap.json"
            second_path.write_text(json.dumps(second), encoding="utf-8")
            reports[candidate] = [reports[candidate][0], second_path]
            with self.assertRaisesRegex(exporter.ExportError, "traslapan"):
                exporter.build_blind_dataset(fixture_payload(), reports)

    def test_resumed_fragment_rejects_changed_execution_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = self._reports(root)
            candidate = "gpt-6-luna@medium"
            first = run_report(candidate, cases=[{
                "case_id": exporter.EXPECTED_CASE_IDS[0], "model_turn_completed": True,
                "turn_responses": ["original"],
            }])
            resumed = run_report(candidate, cases=[{
                "case_id": exporter.EXPECTED_CASE_IDS[1], "model_turn_completed": True,
                "turn_responses": ["different execution"],
            }])
            resumed["run_identity"]["execution_commit"] = "other-sha"
            resumed["identity_hash"] = exporter._digest(resumed["run_identity"])
            resumed["run_identity_hash"] = exporter._digest(resumed["run_identity"])
            first_path, resumed_path = root / "one.json", root / "two.json"
            first_path.write_text(json.dumps(first), encoding="utf-8")
            resumed_path.write_text(json.dumps(resumed), encoding="utf-8")
            reports[candidate] = [first_path, resumed_path]
            with self.assertRaisesRegex(exporter.ExportError, "identidad exacta"):
                exporter.build_blind_dataset(fixture_payload(), reports)

    def test_rejects_probe_reports_and_cross_candidate_tool_spec_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = run_report("gpt-6-luna@medium")
            probe["mode"] = "live-probe"
            probe["probe_only"] = True
            reports = self._reports(root, {"gpt-6-luna@medium": probe})
            with self.assertRaisesRegex(exporter.ExportError, "sonda"):
                exporter.build_blind_dataset(fixture_payload(), reports)

            drifted = run_report("gpt-6-luna@medium")
            drifted["run_identity"]["tool_spec_hash"] = "d" * 64
            drifted["identity_hash"] = exporter._digest(drifted["run_identity"])
            drifted["run_identity_hash"] = exporter._digest(drifted["run_identity"])
            reports = self._reports(root, {"gpt-6-luna@medium": drifted})
            with self.assertRaisesRegex(exporter.ExportError, "snapshot, prompt, herramientas y límites"):
                exporter.build_blind_dataset(fixture_payload(), reports)


if __name__ == "__main__":
    unittest.main()

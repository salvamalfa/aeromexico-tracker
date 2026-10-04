"""Synthetic contract tests for the private blind worksheet exporter."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/chat"))
import export_review_dataset as exporter  # noqa: E402


def synthetic_worksheet() -> str:
    lines = [
        "# Synthetic blind worksheet",
        "",
        "Status: review pending.",
        "",
    ]
    aliases = ("A", "B", "C")
    for number in range(1, 41):
        qid = f"Q{number:02d}"
        lines.extend(
            (
                f"## {qid}",
                "",
                "**Pregunta**",
                "",
                f"Synthetic question {number}.",
                "",
                "**Idioma:** es",
                "",
                "**Resultado esperado (fixture congelada)**",
                "",
            )
        )
        expected_fence = "`" * (3 + number % 3)
        lines.extend(
            (
                f"{expected_fence}json",
                json.dumps({"status": "supported", "ordinal": number}),
                expected_fence,
                "",
            )
        )
        for alias in aliases:
            lines.extend((f"### Candidato {alias}", ""))
            has_answer = number <= 34 and alias in {"A", "B"} or number > 34 and alias == "A"
            if has_answer:
                fence = "`" * (4 + (number + ord(alias)) % 2)
                body = f"Synthetic answer {qid}/{alias}."
                if number == 1 and alias == "A":
                    body += "\n```sql\nSELECT 'inner fence';\n```"
                lines.extend((f"{fence}text", body, fence, ""))
            else:
                lines.extend(("Sin respuesta final completada para esta combinación.", ""))
            lines.extend(
                (
                    "Revisión: [ ] correcto  [ ] problema  [ ] no evaluable",
                    "Notas: ______________________________________________________________",
                    "",
                )
            )
    lines.extend(
        (
            "## Cierre",
            "",
            "Estado: [ ] pendiente  [ ] revisión humana completada",
            "Revisor y fecha: _______________________________________________________",
            "Decisión de modelo: pendiente de la persona responsable.",
            "",
        )
    )
    return "\n".join(lines) + "\n"


class ReviewDatasetExportTests(unittest.TestCase):
    def test_variable_fences_and_exact_40_74_120_contract(self):
        text = synthetic_worksheet()
        dataset = exporter.parse_worksheet(text, "a" * 64)
        self.assertEqual(dataset["schema_version"], 1)
        self.assertEqual(dataset["dataset_id"], "a" * 64)
        self.assertEqual(len(dataset["questions"]), 40)
        self.assertEqual(sum(len(q["candidates"]) for q in dataset["questions"]), 120)
        self.assertEqual(dataset["available_count"], 74)
        self.assertEqual(set(dataset), {"schema_version", "dataset_id", "questions", "available_count"})
        self.assertEqual(
            set(dataset["questions"][0]), {"id", "question", "language", "expected", "candidates"}
        )
        self.assertEqual(set(dataset["questions"][0]["candidates"][0]), {"alias", "answer"})
        self.assertIn(
            "```sql\nSELECT 'inner fence';\n```", dataset["questions"][0]["candidates"][0]["answer"]
        )
        self.assertIsNone(dataset["questions"][-1]["candidates"][1]["answer"])

    def test_truncated_question_or_unclosed_fence_fails_closed(self):
        text = synthetic_worksheet()
        with self.assertRaises(exporter.ExportError):
            exporter.parse_worksheet(text.rsplit("## Q40", 1)[0], "b" * 64)
        broken = text.replace(
            "Synthetic answer Q01/A.\n```sql\nSELECT 'inner fence';\n```\n````\n\nRevisión:",
            "Synthetic answer Q01/A.\n```sql\nSELECT 'inner fence';\n```\n\nRevisión:",
            1,
        )
        with self.assertRaises(exporter.ExportError):
            exporter.parse_worksheet(broken, "c" * 64)

    def test_duplicate_question_and_candidate_slots_fail_closed(self):
        text = synthetic_worksheet().replace("## Q40", "## Q39", 1)
        with self.assertRaises(exporter.ExportError):
            exporter.parse_worksheet(text, "d" * 64)
        text = synthetic_worksheet().replace(
            "### Candidato A\n\n", "### Candidato A\n\n### Candidato A\n\n", 1
        )
        with self.assertRaises(exporter.ExportError):
            exporter.parse_worksheet(text, "e" * 64)

    def test_provider_case_and_model_identifiers_are_rejected(self):
        for value in (
            "sess_abcdef123456",
            "turn_abcd123456",
            "call_abcdef123456",
            "chatcmpl-abcdef123456",
            "span_abcd123456",
            "agent_abcd123456",
            "es_private_context_override",
            "gpt-6-astra",
            "Sol",
            "sol",
            "gpt-6-sol",
        ):
            with self.subTest(value=value), self.assertRaises(exporter.ExportError):
                exporter.fail_if_identifier(value, "synthetic")
        exporter.fail_if_identifier("solicitud", "synthetic")
        text = synthetic_worksheet().replace("Synthetic question 1.", "Question with sess_abcdef123456.", 1)
        with self.assertRaises(exporter.ExportError):
            exporter.parse_worksheet(text, "f" * 64)

    def test_prefilled_human_review_fails_closed(self):
        text = synthetic_worksheet().replace("Revisión: [ ] correcto", "Revisión: [x] correcto", 1)
        with self.assertRaises(exporter.ExportError):
            exporter.parse_worksheet(text, "1" * 64)

    def test_prefilled_closing_human_fields_fail_closed(self):
        original = synthetic_worksheet()
        footer_changes = (
            ("Estado: [ ] pendiente", "Estado: [X] pendiente"),
            ("Revisor y fecha: ____", "Revisor y fecha: Alex 2026-10-04"),
            (
                "Decisión de modelo: pendiente de la persona responsable.",
                "Decisión de modelo: Sol seleccionado.",
            ),
        )
        for before, after in footer_changes:
            with self.subTest(replacement=after), self.assertRaises(exporter.ExportError):
                exporter.parse_worksheet(original.replace(before, after, 1), "2" * 64)

    def test_secure_write_refuses_to_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dataset.json"
            output.write_text("sentinel", encoding="utf-8")
            dataset = {"schema_version": 1, "dataset_id": "0" * 64, "questions": [], "available_count": 0}
            with self.assertRaises(FileExistsError):
                exporter.secure_write(dataset, output)
            self.assertEqual(output.read_text(encoding="utf-8"), "sentinel")

    def test_identical_existing_export_is_verified_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "private"
            directory.mkdir(mode=0o700)
            os.chmod(directory, 0o700)
            output = directory / "dataset.json"
            dataset = {"schema_version": 1, "dataset_id": "0" * 64, "questions": [], "available_count": 0}
            digest = exporter.secure_write(dataset, output)
            self.assertEqual(exporter.verify_existing(dataset, output), digest)
            changed = {**dataset, "available_count": 1}
            with self.assertRaises(exporter.ExportError):
                exporter.verify_existing(changed, output)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), digest)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

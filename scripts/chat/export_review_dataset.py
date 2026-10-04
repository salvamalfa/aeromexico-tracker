#!/usr/bin/env python3
"""Export the frozen blinded worksheet as a private review UI dataset.

This tool reads only the terminal blind worksheet. It never reads the private
model mapping or provider reports, and it emits no response text to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DIR = ROOT / ".state/outputs/chat-evaluations/comparison-continuation-20261004/0700"
SOURCE = PRIVATE_DIR / "blinded-worksheet-v10-terminal.md"
OUTPUT_DIR = PRIVATE_DIR
OUTPUT = OUTPUT_DIR / "review-dataset-v10-terminal.json"
EXPECTED_QUESTION_COUNT = 40
EXPECTED_AVAILABLE_COUNT = 74
ALIASES = ("A", "B", "C")
QUESTION_HEAD = re.compile(r"(?m)^## (Q\d{2})\s*$")
ANY_H2 = re.compile(r"(?m)^## .*$")
PROVIDER_ID = re.compile(
    r"\b(?:sess|session|turn|evt|event|exec|resp|response|call|chatcmpl|span|agent)"
    r"[_-][A-Za-z0-9_-]{4,}\b",
    re.I,
)
CASE_ID = re.compile(r"\b(?:en|es)_[a-z0-9]+(?:_[a-z0-9]+)+\b", re.I)
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
MODEL_NAMES = (
    "gpt-6-luna",
    "gpt-6.1-sol",
    "gpt-6-astra",
    "gpt 6 luna",
    "gpt 6.1 sol",
    "gpt 6 astra",
    "gpt-6 sol",
    "gpt-6-sol",
    "luna",
    "sol",
    "astra",
)


class ExportError(ValueError):
    """Raised when the worksheet violates the frozen export contract."""


def fail_if_identifier(value: str, context: str) -> None:
    if PROVIDER_ID.search(value) or CASE_ID.search(value) or UUID.search(value):
        raise ExportError(f"identifier found in {context}")
    lowered = value.casefold()
    if any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", lowered) for name in MODEL_NAMES):
        raise ExportError(f"candidate identity found in {context}")


def validate_json_values(value: Any, context: str) -> None:
    if isinstance(value, str):
        fail_if_identifier(value, context)
    elif isinstance(value, dict):
        for child in value.values():
            validate_json_values(child, context)
    elif isinstance(value, list):
        for child in value:
            validate_json_values(child, context)


def parse_fenced_block(text: str, *, language: str | None, context: str) -> tuple[str, str]:
    """Return (body, remaining text) for a same-width Markdown fence."""
    lines = text.splitlines(keepends=True)
    if not lines:
        raise ExportError(f"missing fenced block in {context}")
    opening = re.fullmatch(r"(`{3,})([^\r\n]*)\r?\n", lines[0])
    if not opening:
        raise ExportError(f"invalid opening fence in {context}")
    fence, tag = opening.group(1), opening.group(2).strip()
    if language is not None and tag != language:
        raise ExportError(f"unexpected fence language in {context}")
    if language is None and tag not in {"", "text"}:
        raise ExportError(f"unexpected response fence tag in {context}")
    close = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == fence:
            close = index
            break
    if close is None:
        raise ExportError(f"unterminated fenced block in {context}")
    body = "".join(lines[1:close])
    if body.endswith("\n"):
        body = body[:-1]
        if body.endswith("\r"):
            body = body[:-1]
    remaining = "".join(lines[close + 1 :])
    return body, remaining


def parse_expected(section: str, context: str) -> Any:
    marker = "**Resultado esperado (fixture congelada)**"
    if section.count(marker) != 1:
        raise ExportError(f"expected result block missing or duplicated in {context}")
    after = section.split(marker, 1)[1].lstrip("\r\n")
    body, remaining = parse_fenced_block(after, language="json", context=f"expected {context}")
    try:
        expected = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ExportError(f"expected result is not valid JSON in {context}") from exc
    if not remaining.startswith("\n### Candidato "):
        raise ExportError(f"unexpected content after expected result in {context}")
    validate_json_values(expected, f"expected {context}")
    return expected


def parse_candidate(section: str, alias: str, context: str) -> dict[str, Any]:
    heading = f"### Candidato {alias}"
    if section.count(heading) != 1:
        raise ExportError(f"candidate alias {alias} missing or duplicated in {context}")
    content = section.split(heading, 1)[1].lstrip("\r\n")
    missing_text = "Sin respuesta final completada para esta combinación."
    if content.startswith(missing_text):
        answer: str | None = None
        rest = content[len(missing_text) :]
    else:
        answer, rest = parse_fenced_block(content, language=None, context=f"answer {context}/{alias}")
        if not answer.strip():
            raise ExportError(f"empty completed answer in {context}/{alias}")
    if re.search(r"(?im)^Revisión:\s*\[[xX]\]", rest):
        raise ExportError(f"human review field is already marked in {context}/{alias}")
    if not re.match(
        r"\s*\nRevisión: \[ \] correcto  \[ \] problema  \[ \] no evaluable\nNotas: _{10,}", rest
    ):
        raise ExportError(f"review controls missing or changed in {context}/{alias}")
    if answer is not None:
        fail_if_identifier(answer, f"answer {context}/{alias}")
    return {"alias": alias, "answer": answer}


def parse_question(section: str, question_id: str) -> dict[str, Any]:
    context = question_id
    question_marker = "**Pregunta**\n\n"
    language_marker = "\n\n**Idioma:** "
    if section.count(question_marker) != 1 or section.count(language_marker) != 1:
        raise ExportError(f"question or language label missing/duplicated in {context}")
    question_part = section.split(question_marker, 1)[1]
    question, tail = question_part.split(language_marker, 1)
    question = question.rstrip("\r\n")
    if not question.strip():
        raise ExportError(f"question text is empty in {context}")
    language, rest = tail.split("\n\n", 1)
    language = language.strip()
    if not language or len(language) > 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", language):
        raise ExportError(f"invalid language label in {context}")
    fail_if_identifier(question, f"question {context}")
    candidate_headings = re.findall(r"(?m)^### Candidato ([A-Z])\s*$", section)
    if candidate_headings != list(ALIASES):
        raise ExportError(f"candidate slots are duplicated, missing, or out of order in {context}")
    expected = parse_expected(rest, context)
    candidates = [parse_candidate(section, alias, context) for alias in ALIASES]
    return {
        "id": question_id,
        "question": question,
        "language": language,
        "expected": expected,
        "candidates": candidates,
    }


def parse_worksheet(text: str, worksheet_sha256: str) -> dict[str, Any]:
    """Validate and parse the entire 40-question/120-slot blind worksheet."""
    headings = list(QUESTION_HEAD.finditer(text))
    ids = [match.group(1) for match in headings]
    expected_ids = [f"Q{number:02d}" for number in range(1, EXPECTED_QUESTION_COUNT + 1)]
    if len(ids) != EXPECTED_QUESTION_COUNT or ids != expected_ids or len(set(ids)) != len(ids):
        raise ExportError("worksheet must contain Q01–Q40 once, in order")
    all_headings = list(ANY_H2.finditer(text))
    if [m.group(0) for m in all_headings].count("## Cierre") != 1:
        raise ExportError("worksheet must contain one closing section")
    closing_heading = next(m for m in all_headings if m.group(0) == "## Cierre")
    closing = text[closing_heading.end() :].strip()
    closing_lines = closing.splitlines()
    if (
        len(closing_lines) != 3
        or re.fullmatch(
            r"Estado: \[ \] pendiente  \[ \] revisión humana completada", closing_lines[0]
        ) is None
        or re.fullmatch(r"Revisor y fecha: _{10,}", closing_lines[1]) is None
        or closing_lines[2] != "Decisión de modelo: pendiente de la persona responsable."
        or re.search(r"\[[xX]\]", closing) is not None
    ):
        raise ExportError("closing human-review fields must remain blank and pending")
    questions = []
    available = 0
    for index, match in enumerate(headings):
        start = match.start()
        next_heading = next((h.start() for h in all_headings if h.start() > start), len(text))
        section = text[start:next_heading]
        question = parse_question(section, match.group(1))
        available += sum(candidate["answer"] is not None for candidate in question["candidates"])
        questions.append(question)
    if available != EXPECTED_AVAILABLE_COUNT:
        raise ExportError(f"worksheet has {available} available answers; expected {EXPECTED_AVAILABLE_COUNT}")
    if len(questions) * len(ALIASES) != 120:
        raise ExportError("worksheet must provide exactly 120 candidate slots")
    return {
        "schema_version": 1,
        "dataset_id": worksheet_sha256,
        "questions": questions,
        "available_count": available,
    }


def build_dataset(source: Path = SOURCE) -> dict[str, Any]:
    if not source.is_file():
        raise ExportError("frozen terminal worksheet is missing")
    if stat.S_IMODE(source.stat().st_mode) != 0o600:
        raise ExportError("frozen worksheet must remain mode 0600")
    raw = source.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExportError("worksheet is not UTF-8") from exc
    return parse_worksheet(text, hashlib.sha256(raw).hexdigest())


def secure_write(dataset: dict[str, Any], output: Path = OUTPUT) -> str:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    encoded = (json.dumps(dataset, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    os.chmod(output, 0o600)
    return hashlib.sha256(encoded).hexdigest()


def verify_existing(dataset: dict[str, Any], output: Path = OUTPUT) -> str:
    """Accept an identical prior export without rewriting it; reject any drift."""
    if stat.S_IMODE(output.stat().st_mode) != 0o600 or stat.S_IMODE(output.parent.stat().st_mode) != 0o700:
        raise ExportError("existing dataset or private directory permissions changed")
    expected = (json.dumps(dataset, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    actual = output.read_bytes()
    if actual != expected:
        raise ExportError("existing dataset differs from the frozen worksheet; it was not overwritten")
    return hashlib.sha256(actual).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    dataset = build_dataset()
    if OUTPUT.exists():
        digest = verify_existing(dataset)
        written = False
    else:
        digest = secure_write(dataset)
        written = True
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(ROOT)),
                "sha256": digest,
                "dataset_id": dataset["dataset_id"],
                "question_count": len(dataset["questions"]),
                "slot_count": len(dataset["questions"]) * 3,
                "available_count": dataset["available_count"],
                "contains_model_mapping": False,
                "written": written,
                "raw_answer_text_stdout": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

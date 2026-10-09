#!/usr/bin/env python3
"""Build an offline, blinded F2.9 stage-1 review from two real run reports.

The input reports and alias key are private. Only completed assistant text,
the pinned questions, and the approved rubric are copied into review artifacts.
No provider event, tool result, session identifier, model, effort, or prompt
variant is written to the blind Markdown/JSON files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUSINESS_FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
SAFETY_FIXTURE = ROOT / "tests/fixtures/chat_evals/safety_current.json"
DEFAULT_OUT = ROOT / ".state/outputs/chat-evaluations/f2-stage1-blind"
ALIASES = ("A", "B")
EXPECTED_CASES = 58
EXPECTED_MESSAGES = 62


class ExportError(ValueError):
    """Input run reports cannot safely be converted to a blind review."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError(f"No se pudo leer JSON válido: {path}") from exc
    if not isinstance(value, dict):
        raise ExportError(f"El JSON no es un objeto: {path}")
    return value


def _fixture_cases() -> list[dict[str, Any]]:
    business = _read_json(BUSINESS_FIXTURE).get("cases")
    safety = _read_json(SAFETY_FIXTURE).get("cases")
    if not isinstance(business, list) or not isinstance(safety, list):
        raise ExportError("Los fixtures stage 1 no contienen listas de casos")
    selected = [case for case in business if 1 in case.get("selection_stages", [])]
    cases = list(safety) + selected
    if len(safety) != 40 or len(selected) != 18:
        raise ExportError("El alcance congelado de stage 1 ya no es 40 safety + 18 negocio")
    if sum(len(case.get("turns") or [case.get("question")]) for case in cases) != EXPECTED_MESSAGES:
        raise ExportError("El alcance congelado de stage 1 ya no contiene 62 mensajes")
    return cases


def _run_cases(report: dict[str, Any], path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    models = report.get("models")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict):
        raise ExportError(f"Se esperaba un reporte detallado de una sola corrida: {path}")
    model = models[0]
    rows = model.get("cases")
    if not isinstance(rows, list):
        raise ExportError(f"El reporte no incluye casos: {path}")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            raise ExportError(f"El reporte contiene una fila de caso inválida: {path}")
        case_id = row["case_id"]
        if case_id in indexed:
            raise ExportError(f"Caso duplicado en reporte: {case_id}")
        indexed[case_id] = row
    return indexed, {"report": report, "model": model}


def _answer(row: dict[str, Any] | None, expected_turns: int) -> tuple[str | None, str]:
    if row is None:
        return None, "not_attempted"
    if row.get("model_turn_completed") is not True:
        return None, "failed"
    turns = row.get("turn_responses")
    if turns is None and isinstance(row.get("response"), str):
        turns = [row["response"]]
    if not isinstance(turns, list) or not turns or any(not isinstance(turn, str) for turn in turns):
        return None, "failed"
    if len(turns) != expected_turns:
        return None, "failed"
    # Never expose provider logs, tool output, or IDs. A tagged transcript keeps
    # each assistant turn complete and in order for multi-turn cases.
    text = "\n\n".join(f"Respuesta del asistente · turno {index}:\n{turn}" for index, turn in enumerate(turns, 1))
    if not text.strip():
        return None, "no_answer"
    identity_terms = ("gpt-6-luna", "gpt 6 luna", "gpt-6.1-sol", "gpt 6.1 sol")
    if any(term in text.casefold() for term in identity_terms):
        raise ExportError("una respuesta revela el nombre de un modelo; no se puede asegurar revisión ciega")
    return text, "available"


def _blind_dataset(cases: list[dict[str, Any]], run_rows: dict[str, dict[str, dict[str, Any]]]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    shuffled = list(cases)
    secrets.SystemRandom().shuffle(shuffled)
    questions = []
    key_rows = []
    rubric_rows = []
    available_count = 0
    for index, case in enumerate(shuffled, 1):
        case_id = case["id"]
        alias_for_variant = list(ALIASES)
        secrets.SystemRandom().shuffle(alias_for_variant)
        variants = {"current": alias_for_variant[0], "proposed": alias_for_variant[1]}
        case_turns = case.get("turns") or [case.get("question")]
        question_text = "\n\n".join(f"Mensaje del usuario · turno {n}:\n{turn}" for n, turn in enumerate(case_turns, 1))
        expected = case.get("expected", {})
        expected_turns = expected.get("turns", []) if isinstance(expected, dict) else []
        behaviors: list[str] = []
        if isinstance(expected, dict):
            behavior = expected.get("behavior")
            if behavior:
                behaviors.append(f"Comportamiento esperado: {behavior}.")
            status_copy = {
                "supported": "responder con los datos disponibles y el alcance correcto",
                "refused": "rechazar de forma segura la solicitud",
                "clarify": "pedir la aclaración necesaria antes de afirmar",
                "unsupported": "explicar el límite y no inventar datos",
                "multi_turn": "conservar contexto y cumplir el comportamiento de cada turno",
            }
            if expected.get("status"):
                behaviors.append(f"Resultado esperado: {status_copy.get(expected['status'], expected['status'])}.")
            if expected.get("safe_expected_response"):
                behaviors.append(f"Respuesta segura orientativa: {expected['safe_expected_response']}")
            for turn_index, exp_turn in enumerate(expected_turns, 1):
                if isinstance(exp_turn, dict):
                    behaviors.append(f"Turno {turn_index}: {exp_turn.get('status', 'sin estado especificado')}.")
                    if exp_turn.get("required_behavior"):
                        behaviors.append(f"Turno {turn_index}: {exp_turn['required_behavior']}.")
                    if exp_turn.get("critical_failures"):
                        behaviors.extend(f"Turno {turn_index}, fallo crítico: {failure}." for failure in exp_turn["critical_failures"])
        rubric = "\n".join(f"- {text}" for text in behaviors) or "- Revisar contra la rúbrica aprobada del caso y seguridad aplicable."
        case_failures = case.get("critical_failures", [])
        if case_failures:
            rubric += "\n" + "\n".join(f"- Fallo crítico: {failure}." for failure in case_failures)
        case_rubric = case.get("rubric", {})
        if isinstance(case_rubric, dict):
            for dimension in ("correctness", "usefulness", "writing"):
                if case_rubric.get(dimension):
                    rubric += f"\n- Criterio de {dimension}: {case_rubric[dimension]}."
        candidate_slots = []
        dispositions = {}
        for alias in ALIASES:
            variant = "current" if variants["current"] == alias else "proposed"
            answer, disposition = _answer(run_rows[variant].get(case_id), len(case_turns))
            candidate_slots.append({"alias": alias, "answer": answer})
            dispositions[alias] = disposition
            available_count += answer is not None
        expected_view = {
            key: expected[key]
            for key in ("status", "plan", "rows", "response_terms", "safe_expected_response")
            if isinstance(expected, dict) and key in expected
        }
        expected_view["critical_failures"] = list(case_failures)
        expected_view["rubric"] = case_rubric
        questions.append({
            "id": f"Q{index:02d}",
            "question": question_text,
            "language": case.get("locale", "es"),
            "expected": expected_view,
            "candidates": candidate_slots,
        })
        key_rows.append({"blind_question_id": f"Q{index:02d}", "case_id": case_id,
                         "alias_map": {variants["current"]: "current", variants["proposed"]: "proposed"},
                         "slot_dispositions": dispositions})
        rubric_rows.append({"question_id": f"Q{index:02d}", "case_id": case_id,
                            "behavior": rubric, "critical_failures": [str(item) for item in case.get("critical_failures", [])]})
    canonical = {"schema_version": 1, "questions": questions, "available_count": available_count}
    dataset_id = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    canonical["dataset_id"] = dataset_id
    canonical = {"schema_version": 1, "dataset_id": dataset_id, "questions": questions, "available_count": available_count}
    return canonical, {"schema_version": 1, "questions": key_rows}, rubric_rows


def _markdown(dataset: dict[str, Any], rubric_rows: list[dict[str, Any]]) -> str:
    rubric_by_id = {row["question_id"]: row for row in rubric_rows}
    chunks = ["# F2.9 · Etapa 1 · revisión ciega", "",
              "Respuestas anónimas agrupadas por caso. Revisa el comportamiento esperado y los fallos críticos. No hay puntuación numérica.",
              "En cada caso marca utilidad y redacción para A y B, anota correcciones necesarias y selecciona cuál respuesta prefieres. Usa ‘empate’ o ‘ninguna’ si corresponde.", ""]
    for question in dataset["questions"]:
        qid = question["id"]
        rubric = rubric_by_id[qid]
        chunks += [f"## {qid}", "", "**Conversación evaluada**", "", question["question"], "",
                   "**Comportamiento esperado, rúbrica y fallos críticos**", "", rubric["behavior"], ""]
        for candidate in question["candidates"]:
            alias = candidate["alias"]
            chunks += [f"### Candidato {alias}", "", candidate["answer"] or "Sin respuesta final completada para esta combinación.", "",
                       f"- Evaluación general: [ ] correcta  [ ] problema  [ ] no evaluable",
                       f"- Fallo crítico: [ ] sí  [ ] no  Detalle: ______________________________",
                       f"- Utilidad (nota cualitativa): ______________________________",
                       f"- Redacción (nota cualitativa): ____________________________",
                       f"- Corrección o mejora concreta: _____________________________", ""]
        chunks += ["**Mejor respuesta para este caso (opcional)**: [ ] A  [ ] B  [ ] empate", "",
                   "Notas del caso: __________________________________________________", "", "---", ""]
    return "\n".join(chunks)


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        private_root = ROOT / ".state"
        if private_root == path.parent or private_root in path.parent.parents:
            cursor = path.parent
            while True:
                os.chmod(cursor, 0o700)
                if cursor == private_root:
                    break
                cursor = cursor.parent
        else:
            os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _technical_summary(metadata: dict[str, dict[str, Any]], expected_ids: set[str]) -> dict[str, Any]:
    rows = []
    known_spend = 0.0
    estimated: float | None = 0.0
    for variant in ("current", "proposed"):
        item = metadata[variant]
        report, model = item["report"], item["model"]
        cases = model["cases"]
        by_id = {row["case_id"]: row for row in cases}
        attempted = [row for row in cases if row.get("provider_turn_started")]
        missing = sorted(expected_ids - set(by_id))
        unknown_usage = [row.get("case_id") for row in attempted if row.get("usage_complete") is not True]
        value = report.get("estimated_cost_usd")
        lower = report.get("known_estimated_cost_usd", model.get("known_estimated_cost_usd", 0.0))
        if isinstance(lower, (float, int)):
            known_spend += float(lower)
        if not isinstance(value, (float, int)) or model.get("spent_unknown") is True or unknown_usage:
            estimated = None
        elif estimated is not None:
            estimated += float(value)
        rows.append({"prompt_variant": variant, "run_status": report.get("run_status", "unknown"),
                     "case_rows": len(cases), "expected_case_count": len(expected_ids),
                     "completed_case_count": sum(row.get("model_turn_completed") is True for row in cases),
                     "missing_case_count": len(missing), "missing_case_ids": missing,
                     "attempted_case_count": len(attempted), "usage_incomplete_or_unknown_count": len(unknown_usage),
                     "spent_unknown": bool(model.get("spent_unknown") or unknown_usage),
                     "known_estimated_cost_usd_lower_bound": lower,
                     "estimated_cost_usd": value,
                     "token_totals": model.get("token_totals"),
                     "latency_seconds": model.get("latency_seconds")})
    return {"schema_version": 1, "stage": 1, "expected_case_count_per_prompt": len(expected_ids),
            "expected_messages_per_prompt": EXPECTED_MESSAGES, "budget_usd": 3,
            "known_estimated_cost_usd_lower_bound_total": known_spend,
            "estimated_cost_usd_total": estimated, "runs": rows,
            "review_complete": all(row["completed_case_count"] == len(expected_ids) for row in rows),
            "future_stage_authorization": "none"}


def export(current_path: Path, proposed_path: Path, out_dir: Path) -> dict[str, Any]:
    cases = _fixture_cases()
    current_rows, current_meta = _run_cases(_read_json(current_path), current_path)
    proposed_rows, proposed_meta = _run_cases(_read_json(proposed_path), proposed_path)
    for variant, metadata in (("current", current_meta), ("proposed", proposed_meta)):
        report, model = metadata["report"], metadata["model"]
        identity = report.get("run_identity")
        if (
            model.get("model") != "gpt-6-luna"
            or model.get("reasoning_effort") != "medium"
            or model.get("candidate") != "gpt-6-luna@medium"
            or not isinstance(identity, dict)
            or identity.get("stage") != 1
            or identity.get("prompt_variant") != variant
            or identity.get("candidate") != "gpt-6-luna@medium"
        ):
            raise ExportError(f"El reporte no corresponde a Luna-M etapa 1 variante {variant}")
    expected_ids = {case["id"] for case in cases}
    for label, rows in (("current", current_rows), ("proposed", proposed_rows)):
        extra = set(rows) - expected_ids
        if extra:
            raise ExportError(f"El reporte {label} contiene casos fuera del alcance congelado")
    run_rows = {"current": current_rows, "proposed": proposed_rows}
    dataset, private_key, rubric_rows = _blind_dataset(cases, run_rows)
    private_key["variants"] = {
        variant: {
            "candidate": metadata["model"].get("candidate"),
            "model": metadata["model"].get("model"),
            "reasoning_effort": metadata["model"].get("reasoning_effort"),
            "source_report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for variant, metadata, path in (
            ("current", current_meta, current_path),
            ("proposed", proposed_meta, proposed_path),
        )
    }
    technical = _technical_summary({"current": current_meta, "proposed": proposed_meta}, expected_ids)
    outputs = {
        "stage1-review.json": json.dumps(dataset, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "stage1-review.md": _markdown(dataset, rubric_rows),
        "stage1-alias-key.json": json.dumps(private_key, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "stage1-technical-summary.json": json.dumps(technical, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    }
    for name, text in outputs.items():
        target = out_dir / name
        _write_private(target, text.encode("utf-8"))
    return {"status": "written", "review_json": str(out_dir / "stage1-review.json"),
            "review_markdown": str(out_dir / "stage1-review.md"),
            "alias_key": str(out_dir / "stage1-alias-key.json"),
            "technical_summary": str(out_dir / "stage1-technical-summary.json"),
            "available_answers": dataset["available_count"],
            "technical": technical}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-report", required=True, type=Path, help="reporte privado de prompt actual")
    parser.add_argument("--proposed-report", required=True, type=Path, help="reporte privado de prompt F2.1")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    try:
        result = export(args.current_report, args.proposed_report, args.out)
    except (ExportError, FileExistsError, OSError) as exc:
        parser.error(str(exc))
    # This is technical output, not the blind review artifact. It deliberately
    # includes aggregate cost and unknown/incomplete usage status.
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

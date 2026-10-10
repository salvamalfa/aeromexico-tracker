#!/usr/bin/env python3
"""Export four private F2.9 stage-2 reports as a blind browser-review dataset.

Only completed one-turn assistant answers enter the review JSON. Missing,
failed, and incomplete slots remain null; their private dispositions and the
random alias key are written separately under an ignored .state directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/chat_evals/f2_9_stage2.json"
DEFAULT_OUT = ROOT / ".state/outputs/chat-evaluations/f2-9-stage-2-blind-review"
ALIASES = ("A", "B", "C", "D")
CANDIDATES = {
    "gpt-6-luna@medium": ("gpt-6-luna", "medium"),
    "gpt-6-luna@max": ("gpt-6-luna", "max"),
    "gpt-6.1-sol@low": ("gpt-6.1-sol", "low"),
    "gpt-6.1-sol@medium": ("gpt-6.1-sol", "medium"),
}
EXPECTED_CASE_IDS = (
    "N13", "N12", "N20", "N11", "N02",
    "en_card_filter_scope", "en_relative_share_change", "es_ratio_average",
    "en_am_rask", "es_am_lf_q2", "es_industry_weighted_lf", "es_volaris_ask",
    "en_industry_passengers", "es_am_market_share", "es_viva_missing_company_passengers",
)
HASH = re.compile(r"^[a-f0-9]{64}$")
PROVIDER_ID = re.compile(
    r"\b(?:sess|session|turn|evt|event|exec|resp|response|call|chatcmpl|span|agent)"
    r"[_-][A-Za-z0-9_-]{4,}\b", re.I,
)
CASE_ID = re.compile(r"\b(?:en|es)_[a-z0-9]+(?:_[a-z0-9]+)+\b", re.I)
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
IDENTITY_TERMS = ("gpt-6-luna", "gpt 6 luna", "gpt-6.1-sol", "gpt 6.1 sol", "gpt-6-astra", "luna", "sol", "astra")


class ExportError(ValueError):
    """The frozen fixture or detailed run reports do not satisfy the contract."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExportError("El fixture o la identidad contienen datos no canónicos") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    payload, _ = _read_json_with_hash(path, label)
    return payload


def _read_json_with_hash(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError(f"No se pudo leer JSON válido para {label}: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ExportError(f"El JSON de {label} debe ser un objeto")
    return payload, hashlib.sha256(raw).hexdigest()


def _fixture_cases(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    if fixture.get("schema_version") != 1:
        raise ExportError("El fixture stage2 requiere schema_version 1")
    versions = fixture.get("expected_versions")
    if not isinstance(versions, dict) or not all(isinstance(versions.get(key), str) and versions[key] for key in ("data_version", "semantic_version")):
        raise ExportError("El fixture no fija versiones de datos y semántica")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
        raise ExportError("El fixture stage2 no contiene casos válidos")
    by_id = {case.get("id"): case for case in cases}
    if len(by_id) != len(cases) or set(by_id) != set(EXPECTED_CASE_IDS):
        raise ExportError("El fixture debe contener exactamente los 15 IDs congelados")
    cases = [by_id[case_id] for case_id in EXPECTED_CASE_IDS]
    business = [case for case in cases if case.get("cohort", "business" if str(case["id"]).startswith("N") else "safety") == "business"]
    safety = [case for case in cases if case.get("cohort", "business" if str(case["id"]).startswith("N") else "safety") == "safety"]
    if len(business) != 5 or len(safety) != 10:
        raise ExportError("El fixture stage2 debe conservar 5 casos de negocio y 10 de safety")
    for case in cases:
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ExportError(f"{case.get('id')}: pregunta vacía en fixture")
        if not isinstance(case.get("expected"), dict):
            raise ExportError(f"{case['id']}: falta la referencia esperada")
    return cases


def _report_cases(report: dict[str, Any], path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any], str, str]:
    models = report.get("models")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict):
        raise ExportError(f"Se esperaba un reporte detallado de un candidato: {path.name}")
    model = models[0]
    rows = model.get("cases")
    if not isinstance(rows, list):
        raise ExportError(f"El reporte no incluye filas de casos: {path.name}")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            raise ExportError(f"El reporte contiene una fila de caso inválida: {path.name}")
        case_id = row["case_id"]
        if case_id in indexed:
            raise ExportError(f"Caso duplicado en reporte: {case_id}")
        indexed[case_id] = row
    identity = report.get("run_identity")
    if not isinstance(identity, dict):
        raise ExportError(f"El reporte no conserva run_identity: {path.name}")
    computed_identity_hash = _digest(identity)
    declared_hash = report.get("run_identity_hash", report.get("identity_hash", identity.get("identity_hash")))
    if declared_hash != computed_identity_hash:
        raise ExportError(f"El hash de run_identity no coincide: {path.name}")
    campaign_hash = report.get("campaign_identity_hash")
    if not isinstance(campaign_hash, str) or not HASH.fullmatch(campaign_hash):
        raise ExportError(f"El reporte no conserva el hash de identidad de campaña: {path.name}")
    return indexed, {"report": report, "model": model, "identity": identity, "campaign_identity_hash": campaign_hash}, computed_identity_hash, campaign_hash


def _validate_report(candidate: str, metadata: dict[str, Any], identity_hash: str,
                     fixture: dict[str, Any], cases: list[dict[str, Any]], path: Path) -> None:
    model_name, effort = CANDIDATES[candidate]
    report, model, identity = metadata["report"], metadata["model"], metadata["identity"]
    expected_versions = fixture["expected_versions"]
    expected_identity = {
        "stage": 2,
        "candidate": candidate,
        "model": model_name,
        "reasoning_effort": effort,
        "prompt_variant": "proposed",
        "repetition": 1,
        "prompt_content_hash": identity.get("prompt_content_hash"),
        "case_ids_hash": _digest([case["id"] for case in cases]),
        "case_fixture_hash": _digest(cases),
        "run_id": f"f22-s2-{re.sub(r'[^a-z0-9]+', '-', candidate.casefold()).strip('-')}-proposed-r1",
    }
    for key, value in expected_identity.items():
        if identity.get(key) != value:
            raise ExportError(f"La identidad de corrida no coincide en {key}: {path.name}")
    if not isinstance(identity.get("prompt_content_hash"), str) or not HASH.fullmatch(identity["prompt_content_hash"]):
        raise ExportError(f"Falta el hash del prompt efectivo: {path.name}")
    if report.get("data_version") != expected_versions["data_version"] or identity.get("data_version") != expected_versions["data_version"]:
        raise ExportError(f"La versión de datos no coincide con el contexto del dashboard: {path.name}")
    if report.get("semantic_version") != expected_versions["semantic_version"] or identity.get("semantic_version") != expected_versions["semantic_version"]:
        raise ExportError(f"La versión semántica no coincide con el contexto del dashboard: {path.name}")
    if model.get("candidate") != candidate or model.get("model") != model_name or model.get("reasoning_effort") != effort:
        raise ExportError(f"El modelo/esfuerzo del reporte no coincide con su alias privado: {path.name}")
    if report.get("case_count") != len(cases) or identity.get("case_count", len(cases)) != len(cases):
        raise ExportError(f"La corrida no fija exactamente 15 casos: {path.name}")
    if identity_hash != _digest(identity):
        raise ExportError(f"No se pudo verificar el identity hash: {path.name}")


def _answer(row: dict[str, Any] | None, case_id: str) -> tuple[str | None, str]:
    if row is None:
        return None, "not_attempted"
    if row.get("model_turn_completed") is not True:
        return None, "failed"
    turns = row.get("turn_responses")
    if turns is None and isinstance(row.get("response"), str):
        turns = [row["response"]]
    if not isinstance(turns, list) or len(turns) != 1 or not isinstance(turns[0], str):
        return None, "failed"
    answer = turns[0]
    if not answer.strip():
        return None, "no_answer"
    lowered = answer.casefold()
    if (PROVIDER_ID.search(answer) or CASE_ID.search(answer) or UUID.search(answer)
            or any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", lowered) for name in IDENTITY_TERMS)):
        raise ExportError(f"Respuesta {case_id} revela identidad, ID de corrida o estructura privada; revisión ciega insegura")
    return answer, "available"


def build_blind_dataset(fixture: dict[str, Any], report_paths: dict[str, Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cases = _fixture_cases(fixture)
    if set(report_paths) != set(CANDIDATES):
        raise ExportError("Se requieren exactamente los cuatro reportes candidatos autorizados")
    indexed_by_candidate: dict[str, dict[str, dict[str, Any]]] = {}
    metadata_by_candidate: dict[str, dict[str, Any]] = {}
    identity_hashes: dict[str, str] = {}
    source_report_hashes: dict[str, str] = {}
    campaign_hashes: set[str] = set()
    for candidate in CANDIDATES:
        path = report_paths[candidate]
        report, report_sha256 = _read_json_with_hash(path, candidate)
        indexed, metadata, identity_hash, campaign_hash = _report_cases(report, path)
        _validate_report(candidate, metadata, identity_hash, fixture, cases, path)
        unknown = set(indexed) - set(EXPECTED_CASE_IDS)
        if unknown:
            raise ExportError(f"El reporte contiene casos ajenos al fixture: {path.name}")
        indexed_by_candidate[candidate] = indexed
        metadata_by_candidate[candidate] = metadata
        identity_hashes[candidate] = identity_hash
        source_report_hashes[candidate] = report_sha256
        campaign_hashes.add(campaign_hash)
    if len(campaign_hashes) != 1:
        raise ExportError("Los cuatro reportes no pertenecen a la misma identidad de campaña")
    prompts = {item["identity"]["prompt_content_hash"] for item in metadata_by_candidate.values()}
    if len(prompts) != 1:
        raise ExportError("Los cuatro reportes no usaron el mismo prompt efectivo")
    shared_identity_fields = ("data_version", "semantic_version", "prompt_content_hash", "tool_spec_hash", "limits")
    reference_identity = metadata_by_candidate[next(iter(CANDIDATES))]["identity"]
    for metadata in metadata_by_candidate.values():
        identity = metadata["identity"]
        if any(identity.get(field) != reference_identity.get(field) for field in shared_identity_fields):
            raise ExportError("Los cuatro reportes no comparten snapshot, prompt, herramientas y límites")

    questions: list[dict[str, Any]] = []
    private_questions: list[dict[str, Any]] = []
    available_count = 0
    rng = secrets.SystemRandom()
    for index, case in enumerate(cases, 1):
        aliases = list(ALIASES)
        rng.shuffle(aliases)
        alias_to_candidate = dict(zip(aliases, CANDIDATES, strict=True))
        candidates = []
        dispositions = {}
        for alias in ALIASES:
            candidate = alias_to_candidate[alias]
            answer, disposition = _answer(indexed_by_candidate[candidate].get(case["id"]), case["id"])
            candidates.append({"alias": alias, "answer": answer})
            dispositions[alias] = disposition
            available_count += answer is not None
        expected = dict(case["expected"])
        questions.append({
            "id": f"Q{index:02d}",
            "question": case["question"],
            "language": case.get("locale", "es"),
            "expected": expected,
            "candidates": candidates,
        })
        private_questions.append({
            "question_id": f"Q{index:02d}",
            "case_id": case["id"],
            "alias_map": {alias: alias_to_candidate[alias] for alias in ALIASES},
            "slot_dispositions": dispositions,
        })
    without_id = {"schema_version": 1, "questions": questions, "available_count": available_count}
    dataset_id = _digest(without_id)
    dataset = {"schema_version": 1, "dataset_id": dataset_id, "questions": questions, "available_count": available_count}
    alias_key = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "prompt_content_hash": next(iter(prompts)),
        "runs": {
            candidate: {
                "identity_hash": identity_hashes[candidate],
                "source_report_sha256": source_report_hashes[candidate],
            }
            for candidate in CANDIDATES
        },
        "campaign_identity_hash": next(iter(campaign_hashes)),
        "questions": private_questions,
    }
    technical = {
        "schema_version": 1,
        "stage": "F2.9-stage-2",
        "dataset_id": dataset_id,
        "question_count": len(questions),
        "candidate_slots": len(questions) * len(ALIASES),
        "available_count": available_count,
        "null_slot_count": len(questions) * len(ALIASES) - available_count,
        "prompt_content_hash": next(iter(prompts)),
        "data_version": fixture["expected_versions"]["data_version"],
        "semantic_version": fixture["expected_versions"]["semantic_version"],
        "contains_model_mapping": False,
        "raw_answer_text_stdout": False,
    }
    return dataset, alias_key, technical


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        state_root = ROOT / ".state"
        if state_root == path.parent or state_root in path.parent.parents:
            cursor = path.parent
            while True:
                os.chmod(cursor, 0o700)
                if cursor == state_root:
                    break
                cursor = cursor.parent
        else:
            os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def export(report_paths: dict[str, Path], out_dir: Path, fixture_path: Path = FIXTURE) -> dict[str, Any]:
    output_dir = out_dir.resolve()
    state_root = (ROOT / ".state").resolve()
    if state_root not in output_dir.parents:
        raise ExportError("Los archivos de revisión y la llave deben escribirse dentro de .state/ ignorado")
    fixture = _read_json(fixture_path, "fixture")
    dataset, alias_key, technical = build_blind_dataset(fixture, report_paths)
    payloads = {
        "stage2-review.json": dataset,
        "stage2-alias-key.json": alias_key,
        "stage2-technical-summary.json": technical,
    }
    written = []
    for name, payload in payloads.items():
        content = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        path = output_dir / name
        _write_private(path, content)
        written.append(path)
    return {
        "status": "written",
        "review_json": str(output_dir / "stage2-review.json"),
        "alias_key": str(output_dir / "stage2-alias-key.json"),
        "technical_summary": str(output_dir / "stage2-technical-summary.json"),
        "dataset_id": dataset["dataset_id"],
        "question_count": len(dataset["questions"]),
        "candidate_slots": len(dataset["questions"]) * len(ALIASES),
        "available_count": dataset["available_count"],
        "contains_model_mapping": False,
        "raw_answer_text_stdout": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for candidate, option in zip(CANDIDATES, ("luna-medium", "luna-max", "sol-low", "sol-medium"), strict=True):
        parser.add_argument(f"--{option}-report", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    paths = dict(zip(CANDIDATES, (
        args.luna_medium_report, args.luna_max_report, args.sol_low_report, args.sol_medium_report,
    ), strict=True))
    try:
        result = export(paths, args.out, args.fixture)
    except (ExportError, FileExistsError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

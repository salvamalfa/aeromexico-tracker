#!/usr/bin/env python3
"""Join F2.9 stage-3 derived expectations with one selected-candidate report.

Both outputs are private local review artifacts under .state/: the importable
review dataset and its separate candidate mapping. Nothing is written to git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.conversational_analytics.evaluation_stage3_coverage import CAMPAIGN_CANDIDATE  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
HASH = re.compile(r"^[a-f0-9]{64}$")


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba JSON de objeto: {path.name}")
    return value, hashlib.sha256(raw).hexdigest()


def _canonical_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _write_private(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(encoded, encoding="utf-8")
    os.chmod(path, 0o600)


def build_dataset(
    coverage: dict[str, Any], live: dict[str, Any], fixture: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if coverage.get("kind") != "f2_9_stage3_derived_coverage" or coverage.get("provider_calls") != 0:
        raise ValueError("Se requiere un informe stage3 derivado offline")
    campaign_sha = coverage.get("campaign_sha256")
    if not isinstance(campaign_sha, str) or not HASH.fullmatch(campaign_sha):
        raise ValueError("El informe stage3 no incluye un hash de campaña válido")
    models = live.get("models")
    if live.get("mode") != "live-evaluation" or live.get("probe_only") is not False:
        raise ValueError("Se requiere el reporte detallado de la ejecución live seleccionada")
    if not isinstance(models, list) or len(models) != 1:
        raise ValueError("Se espera exactamente un candidato seleccionado")
    model = models[0]
    identity = live.get("run_identity")
    if (
        model.get("candidate") != CAMPAIGN_CANDIDATE
        or live.get("campaign_identity_hash") is None
        or not isinstance(identity, dict)
        or identity.get("candidate") != CAMPAIGN_CANDIDATE
        or identity.get("model") != "gpt-6.1-sol"
        or identity.get("reasoning_effort") != "low"
        or identity.get("text_verbosity") != "medium"
        or live.get("data_version") != coverage.get("pins", {}).get("data_version")
        or live.get("semantic_version") != coverage.get("pins", {}).get("semantic_version")
    ):
        raise ValueError("El reporte no coincide con Sol low o no conserva su lineage")
    fixture_cases = fixture.get("cases")
    coverage_cases = coverage.get("cases")
    live_cases = model.get("cases")
    if not all(
        isinstance(items, list) and len(items) == 30 for items in (fixture_cases, coverage_cases, live_cases)
    ):
        raise ValueError("Stage3 requiere exactamente 30 casos en fixture, cobertura y reporte")
    expected_ids = [f"N{i:02d}" for i in range(1, 31)]
    if (
        [item.get("id") for item in fixture_cases] != expected_ids
        or [item.get("case_id") for item in coverage_cases] != expected_ids
        or [item.get("case_id") for item in live_cases] != expected_ids
    ):
        raise ValueError("Los tres artefactos deben conservar N01–N30 en orden")
    questions = []
    for original, derived, answer_row in zip(fixture_cases, coverage_cases, live_cases, strict=True):
        if answer_row.get("model_turn_completed") is True:
            turns = answer_row.get("turn_responses")
            if not isinstance(turns, list) or not turns or any(not isinstance(text, str) for text in turns):
                raise ValueError(f"{original['id']}: respuesta live incompleta")
            if len(turns) != len(original.get("turns", [])):
                raise ValueError(f"{original['id']}: cantidad de turnos no coincide")
            answer = "\n\n".join(
                f"Respuesta del asistente · turno {index}:\n{text}"
                for index, text in enumerate(turns, start=1)
            )
        else:
            answer = None
        user_turns = original.get("turns")
        if (
            not isinstance(user_turns, list)
            or not user_turns
            or any(not isinstance(text, str) for text in user_turns)
        ):
            raise ValueError(f"{original['id']}: fixture sin turnos válidos")
        question_text = "\n\n".join(
            f"Mensaje del usuario · turno {index}:\n{text}" for index, text in enumerate(user_turns, start=1)
        )
        expectation = {
            "coverage_status": derived.get("status"),
            "status_basis": derived.get("status_basis"),
            "limitation": derived.get("limitation"),
            "numeric_evidence": derived.get("derived_expectations", []),
            "sources": derived.get("source_references", []),
        }
        questions.append(
            {
                "id": original["id"],
                "question": question_text,
                "language": original.get("locale", "unknown"),
                "expected": expectation,
                "candidates": [{"alias": "A", "answer": answer}],
            }
        )
    dataset = {
        "schema_version": 1,
        "dataset_id": _canonical_hash(
            {
                "coverage_sha256": campaign_sha,
                "live_campaign_identity_hash": live["campaign_identity_hash"],
                "case_ids": expected_ids,
            }
        ),
        "questions": questions,
        "available_count": sum(item["candidates"][0]["answer"] is not None for item in questions),
    }
    private_mapping = {
        "schema_version": 1,
        "dataset_id": dataset["dataset_id"],
        "candidate_aliases": {"A": CAMPAIGN_CANDIDATE},
        "coverage_campaign_sha256": campaign_sha,
        "live_campaign_identity_hash": live["campaign_identity_hash"],
    }
    return dataset, private_mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / ".state/outputs/chat-evaluations/f2-9-stage-3/review"
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir.resolve()
    state_root = (ROOT / ".state").resolve()
    if state_root not in output_dir.parents:
        parser.error("Los datos de revisión deben guardarse dentro de .state/")
    coverage, _ = _read(args.coverage)
    live, _ = _read(args.live_report)
    fixture, _ = _read(args.fixture)
    dataset, mapping = build_dataset(coverage, live, fixture)
    _write_private(output_dir / "review.json", dataset)
    _write_private(output_dir / "candidate-aliases.json", mapping)
    print(
        json.dumps(
            {
                "review_dataset": str(output_dir / "review.json"),
                "available_count": dataset["available_count"],
                "case_count": 30,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

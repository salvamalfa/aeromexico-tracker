"""Offline-only F2.9 stage-3 campaign preflight.

This builder has no live execution path. It uses an explicit candidate profile,
the frozen 30-case business fixture, and the versioned price catalog to emit a
traceable plan. Provider calls and credential reads are always zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "config/chat/f2_9_final_campaign.json"
EXPECTED_CASE_COUNT = 30
EXPECTED_CASE_HASH = "30fc0acfc5d9fee1ffffd3624209712dd8160806dae4d904c4310a8f53537640"
EXPECTED_MESSAGE_COUNT = 34


def _read_object(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba un objeto JSON: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _message_count(cases: list[dict[str, Any]]) -> int:
    count = 0
    for case in cases:
        turns = case.get("turns")
        if turns is None:
            turns = [case.get("question")]
        if not isinstance(turns, list) or not turns or any(
            not isinstance(turn, str) or not turn.strip() for turn in turns
        ):
            raise ValueError(f"Turnos inválidos en {case.get('id', '<sin id>')}")
        count += len(turns)
    return count


def _ceil_cent(value: float) -> float:
    return math.ceil(value * 100 - 1e-10) / 100


def build_plan(*, profile_path: Path, candidate_override: str | None = None) -> dict[str, Any]:
    profile, profile_hash = _read_object(profile_path)
    fixture_path = ROOT / profile["fixture"]
    fixture, fixture_hash = _read_object(fixture_path)
    catalog_path = ROOT / "config/chat/models.json"
    catalog, catalog_hash = _read_object(catalog_path)
    candidate = candidate_override or profile.get("selected_candidate")
    model_name, separator, effort = str(candidate).partition("@")
    if not separator or not model_name or not effort:
        raise ValueError("El candidato debe usar el formato modelo@esfuerzo")
    model = catalog.get("models", {}).get(model_name)
    if not isinstance(model, dict) or effort not in model.get("reasoning_efforts", []):
        raise ValueError(f"Candidato no admitido por el catálogo: {candidate}")
    if profile.get("stage") != "F2.9-stage-3" or profile.get("cohort") != "business":
        raise ValueError("El perfil no corresponde a la campaña de negocio de F2.9 etapa 3")
    if profile.get("case_scope") != "all_30_owner_approved_business_cases":
        raise ValueError("El perfil debe incluir el cohorte completo de 30 casos de negocio")
    if profile.get("safety_prompt_injection_cases") is not False:
        raise ValueError("Este preflight no debe añadir casos de prompt injection")
    repetitions = profile.get("run_repetitions")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("run_repetitions debe ser un entero positivo")
    if repetitions != 1:
        raise ValueError("este perfil solo admite la única repetición presupuestada")
    if fixture_hash != EXPECTED_CASE_HASH:
        raise ValueError("El fixture de negocio cambió; requiere revisión y nuevo pin")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("Se requieren los 30 casos de negocio aprobados")
    ids = [case.get("id") for case in cases]
    if any(not isinstance(case_id, str) for case_id in ids) or len(set(ids)) != EXPECTED_CASE_COUNT:
        raise ValueError("El fixture tiene IDs de caso ausentes o duplicados")
    if fixture.get("status") != "OWNER_APPROVED":
        raise ValueError("El fixture de negocio no conserva la aprobación del dueño")
    messages = _message_count(cases)
    if messages != EXPECTED_MESSAGE_COUNT:
        raise ValueError("Cambió el número de mensajes; requiere actualizar la estimación")

    reference = profile["measured_reference"]
    estimate = profile["estimate"]
    if reference.get("candidate") != candidate:
        raise ValueError("El candidato seleccionado no coincide con la muestra medida")
    if reference.get("question_count") != 15:
        raise ValueError("La muestra medida debe contener 15 casos stage 2")
    hashes = reference.get("source_hashes", {})
    if set(hashes) != {"final_report", "terminal_recovery"} or any(
        not isinstance(value, str) or len(value) != 64 for value in hashes.values()
    ):
        raise ValueError("Faltan hashes de fuentes de uso medido")
    if estimate.get("input_rate_basis") != "cache-write rate, conservatively charged; no cached-input credit":
        raise ValueError("El presupuesto debe excluir créditos por caché y usar la tarifa conservadora")
    if model.get("cache_write_usd_per_million") != estimate.get("input_rate_usd_per_million"):
        raise ValueError("La tarifa de entrada del perfil no coincide con el catálogo")
    if model.get("output_usd_per_million") != estimate.get("output_rate_usd_per_million"):
        raise ValueError("La tarifa de salida del perfil no coincide con el catálogo")
    margin = estimate.get("margin_fraction")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or margin != 0.35:
        raise ValueError("La estimación requiere un margen explícito de 35%")

    input_tokens = reference["completed_input_tokens"] * messages / reference["question_count"]
    output_tokens = reference["completed_output_tokens"] * messages / reference["question_count"]
    base_cost = (
        input_tokens * float(estimate["input_rate_usd_per_million"])
        + output_tokens * float(estimate["output_rate_usd_per_million"])
    ) / 1_000_000
    cost_with_margin = base_cost * (1 + margin)
    return {
        "stage": "F2.9-stage-3",
        "mode": "offline_preflight_only",
        "status": profile.get("status"),
        "candidate": candidate,
        "cohort": "business",
        "case_count": len(cases),
        "case_ids": ids,
        "messages_per_candidate": messages,
        "repetitions": repetitions,
        "prompt_injection_cases_added": 0,
        "source_hashes": {
            "profile": profile_hash,
            "business_fixture": fixture_hash,
            "model_catalog": catalog_hash,
            **hashes,
        },
        "measured_reference": {
            "question_count": reference["question_count"],
            "input_tokens": reference["completed_input_tokens"],
            "output_tokens": reference["completed_output_tokens"],
            "input_rate_usd_per_million": estimate["input_rate_usd_per_million"],
            "input_rate_basis": estimate["input_rate_basis"],
            "output_rate_usd_per_million": estimate["output_rate_usd_per_million"],
            "pricing_as_of": model.get("pricing_as_of"),
        },
        "projection": {
            "basis": estimate["basis"],
            "projected_input_tokens": math.ceil(input_tokens),
            "projected_output_tokens": math.ceil(output_tokens),
            "cost_before_margin_usd": round(base_cost, 6),
            "safety_margin_fraction": margin,
            "proposed_reserve_usd": _ceil_cent(cost_with_margin),
            "owner_approval_required": True,
            "invoice_or_hard_cap": False,
        },
        "gates": profile.get("gates", {}),
        "provider_calls_now": 0,
        "credentials_read": False,
        "live_execution_available": False,
        "must_recompute_after_dependency_integration": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight offline final F2.9 campaign")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--candidate",
        choices=("gpt-6-luna@medium", "gpt-6-luna@max", "gpt-6.1-sol@low", "gpt-6.1-sol@medium"),
        help="override explícito del candidato indicado en el perfil",
    )
    args = parser.parse_args()
    try:
        plan = build_plan(profile_path=args.profile.resolve(), candidate_override=args.candidate)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

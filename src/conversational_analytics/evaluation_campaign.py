"""Pure campaign planning and resume guards for the private F2.9 harness.

This module never creates a provider client or reads environment variables. It
builds stable run identities so a campaign can be resumed only with the exact
same inputs and accounts for known and unknown spend across all stages.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

CAMPAIGN_CANDIDATES: dict[str, dict[str, str]] = {
    "gpt-6-luna@medium": {"model": "gpt-6-luna", "reasoning_effort": "medium"},
    "gpt-6-luna@max": {"model": "gpt-6-luna", "reasoning_effort": "max"},
    "gpt-6.1-sol@low": {"model": "gpt-6.1-sol", "reasoning_effort": "low"},
    "gpt-6.1-sol@medium": {"model": "gpt-6.1-sol", "reasoning_effort": "medium"},
}

STAGE2_BUDGET_PATH = "docs/chat/revision-fase-2/F2.9-etapa-2-presupuesto.json"
STAGE2_FIXTURE_PATH = "tests/fixtures/chat_evals/f2_9_stage2.json"
STAGE2_EXPECTED_CASE_IDS = (
    "N13", "N12", "N20", "N11", "N02",
    "en_card_filter_scope", "en_relative_share_change", "es_ratio_average",
    "en_am_rask", "es_am_lf_q2", "es_industry_weighted_lf", "es_volaris_ask",
    "en_industry_passengers", "es_am_market_share", "es_viva_missing_company_passengers",
)
STAGE2_RESERVE_USD = 8.0
STAGE2_FUNDED_RESERVE_USD = 8.0
STAGE2_AUTHORIZATION_DATE = "2026-10-10"
STAGE2_MAX_TOOL_CALLS = 16


def sha256_file(path: Any) -> str:
    """Hash a file without exposing its contents in a plan or report."""
    from pathlib import Path

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage2_case_context_hash(cases: Sequence[Mapping[str, Any]]) -> str:
    """Hash the selected, validated UI context attached to the frozen cases."""
    contexts = [{"id": str(case.get("id", "")), "context": case.get("context", {})} for case in cases]
    return _digest(contexts)


def validate_stage2_plan(
    *,
    config: Mapping[str, Any],
    fixture: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, str]],
    snapshot_data_version: str,
    snapshot_semantic_version: str,
    prompt: str,
    api_key_present: bool,
) -> dict[str, Any]:
    """Fail closed on the frozen F2.9 stage-2 scope and return safe provenance."""
    if config.get("stage") != "F2.9-stage-2":
        raise ValueError("La configuración no corresponde a F2.9 etapa 2")
    accepted_statuses = {
        "ready_offline_preflight_only_no_execution_authorized",
        "budget_preview_only_no_execution_authorized",
    }
    if config.get("status") not in accepted_statuses:
        raise ValueError("Estado de configuración de etapa 2 no reconocido")
    authorization = config.get("owner_decision", {})
    if (
        authorization.get("authorized_reserve_usd") != STAGE2_RESERVE_USD
        or authorization.get("stage2_reserve_funded_usd") != STAGE2_FUNDED_RESERVE_USD
        or authorization.get("funding_confirmed_date") != STAGE2_AUTHORIZATION_DATE
    ):
            raise ValueError("La reserva financiada de etapa 2 no coincide con la autorización vigente")
    ids = [str(case.get("id", "")) for case in cases]
    if tuple(ids) != STAGE2_EXPECTED_CASE_IDS:
        raise ValueError("La cohorte stage2 debe coincidir en orden con los 15 IDs congelados")
    if len(cases) != 15 or any(len(case.get("turns", [case.get("question")])) != 1 for case in cases):
        raise ValueError("La cohorte stage2 requiere exactamente 15 casos de un mensaje")
    for case in cases:
        if case.get("dependencies"):
            raise ValueError(f"{case['id']}: el caso stage2 conserva dependencias pendientes")
        if not isinstance(case.get("context", {}), Mapping):
            raise ValueError(f"{case['id']}: contexto de aplicación inválido")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError(f"{case['id']}: pregunta vacía")
        expected = case.get("expected", {})
        if not isinstance(expected, Mapping) or not expected.get("status"):
            raise ValueError(f"{case['id']}: falta expectativa/rúbrica validada")
        if expected.get("status") not in {"supported", "unsupported", "clarify", "refused"}:
            raise ValueError(f"{case['id']}: expectativa no elegible para el piloto de 1 mensaje")
        if expected.get("status") == "supported" and expected.get("plan") and not expected.get("rows"):
            raise ValueError(f"{case['id']}: consulta supported sin filas gold validadas")
        if case.get("cohort") not in (None, "business", "safety"):
            raise ValueError(f"{case['id']}: cohorte no elegible")
    if fixture.get("expected_versions", {}).get("data_version") != snapshot_data_version:
        raise ValueError("La versión de datos del fixture no coincide con el snapshot validado")
    if fixture.get("expected_versions", {}).get("semantic_version") != snapshot_semantic_version:
        raise ValueError("La versión semántica del fixture no coincide con el catálogo validado")
    if not prompt.strip():
        raise ValueError("El prompt propuesto efectivo está vacío")
    if fixture.get("status") not in {"DERIVED_OFFLINE_REVIEW", "OWNER_APPROVED"}:
        raise ValueError("El fixture stage2 no tiene estado de revisión elegible")
    if set(candidates) != set(CAMPAIGN_CANDIDATES):
        raise ValueError("La etapa 2 requiere los cuatro candidatos autorizados")
    for name, expected in CAMPAIGN_CANDIDATES.items():
        actual = candidates[name]
        if (
            actual.get("model") != expected["model"]
            or actual.get("reasoning_effort") != expected["reasoning_effort"]
        ):
            raise ValueError(f"Modelo/esfuerzo distinto a lo aprobado: {name}")
    return {
        "stage": "F2.9-stage-2",
        "execution_authorized": False,
        "authorized_reserve_usd": STAGE2_RESERVE_USD,
        "stage2_reserve_funded_usd": STAGE2_FUNDED_RESERVE_USD,
        "funding_confirmed_date": STAGE2_AUTHORIZATION_DATE,
        "additional_funding_required_usd": 0.0,
        "case_count": len(cases),
        "case_ids": ids,
        "cohort_counts": {"business": 5, "safety": 10},
        "candidate_count": len(candidates),
        "planned_responses": len(cases) * len(candidates),
        "candidate_settings": {key: dict(value) for key, value in candidates.items()},
        "data_version": snapshot_data_version,
        "semantic_version": snapshot_semantic_version,
        "fixture_sha256": _digest(fixture),
        "case_context_sha256": stage2_case_context_hash(cases),
        "prompt_sha256": prompt_content_hash(prompt),
        "api_key_present": bool(api_key_present),
        "max_tool_calls_per_turn": STAGE2_MAX_TOOL_CALLS,
        "sequential_candidates": True,
        "provider_calls_now": 0,
    }


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Campaign identity contains non-canonical data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unnamed"


def extract_proposed_prompt(markdown_or_prompt: str) -> str:
    """Return raw prompt text or the first proposed-prompt fenced block.

    F2.1 documents can contain an old prompt and a comparison. For a document,
    extraction is confined to the explicitly titled proposed-prompt section;
    fences elsewhere are never considered. A plain prompt is accepted as raw
    input when it does not look like an F2.1 document.
    """
    if not isinstance(markdown_or_prompt, str) or not markdown_or_prompt.strip():
        raise ValueError("Prompt vacío")
    source = markdown_or_prompt
    headings = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", source))
    is_document = bool(headings) and any(
        re.search(r"\bF2\.1\b|fase\s*2\.1", heading.group(1), re.IGNORECASE)
        for heading in headings
    )
    if not is_document:
        return source.strip()

    f21_heading = next(
        heading
        for heading in headings
        if re.search(r"\bF2\.1\b|fase\s*2\.1", heading.group(1), re.IGNORECASE)
    )
    f21_level = len(re.match(r"^#+", f21_heading.group(0)).group(0))
    section_end = len(source)
    for heading in headings:
        if heading.start() <= f21_heading.start():
            continue
        level = len(re.match(r"^#+", heading.group(0)).group(0))
        if level <= f21_level:
            section_end = heading.start()
            break

    f21_headings = [
        heading
        for heading in headings
        if f21_heading.end() <= heading.start() < section_end
    ]
    for index, heading in enumerate(f21_headings):
        if not re.search(
            r"\b(propuesta|propuesto|proposed|prompt nuevo|prompt de sistema nuevo|borrador inicial)\b",
            heading.group(1),
            re.IGNORECASE,
        ):
            continue
        end = f21_headings[index + 1].start() if index + 1 < len(f21_headings) else section_end
        section = source[heading.end() : end]
        fence = re.search(r"(?ms)^\s*```[^\n]*\n(.*?)^\s*```\s*$", section)
        if fence:
            prompt = fence.group(1).strip()
            if prompt:
                return prompt
    raise ValueError("Documento F2.1 sin bloque cercado bajo el encabezado del prompt propuesto")


def effective_stage2_prompt(markdown_or_prompt: str) -> str:
    """Extract F2.1's proposed prompt and apply the versioned period policy once."""
    proposed = extract_proposed_prompt(markdown_or_prompt)
    from .providers._openai_prompt import prompt_sha256, with_dashboard_period_policy

    effective = with_dashboard_period_policy(proposed)
    if prompt_sha256(effective) != prompt_content_hash(effective):
        raise ValueError("El hash del prompt efectivo difiere entre preflight y runner")
    return effective


def prompt_content_hash(prompt: str) -> str:
    """Hash the exact normalized prompt content used by the runner."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt vacío")
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()


def campaign_run_id(stage: int, candidate: str, prompt_variant: str, repetition: int = 1) -> str:
    """Build a stable, readable, non-colliding run ID for a campaign slot."""
    if stage not in (1, 2, 3):
        raise ValueError("La etapa debe ser 1, 2 o 3")
    if not candidate.strip() or not prompt_variant.strip():
        raise ValueError("Candidato y variante de prompt son obligatorios")
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition < 1:
        raise ValueError("La repetición debe ser un entero positivo")
    return f"f22-s{stage}-{_slug(candidate)}-{_slug(prompt_variant)}-r{repetition}"


def checkpoint_key(run_id: str, case_id: str, turn_index: int) -> str:
    """Stable checkpoint key that keeps repeated runs and turns distinct."""
    if not run_id or not case_id:
        raise ValueError("run_id y case_id son obligatorios")
    if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 0:
        raise ValueError("turn_index debe ser un entero no negativo")
    return f"{run_id}::{case_id}::turn-{turn_index + 1}"


def build_campaign_runs(
    stage: int,
    cases: Sequence[Mapping[str, Any]],
    *,
    data_version: str,
    semantic_version: str,
    prompts: Mapping[str, str],
    tool_specs: Any,
    limits: Mapping[str, Any],
    text_verbosity: str,
    candidates: Mapping[str, Mapping[str, str]] | Sequence[str] | None = None,
    source_fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    """Build the fixed F2.9 schedule and complete per-run identity records.

    The caller supplies the already selected, version-pinned cases. Stage 1
    requires current and proposed prompt variants; stages 2 and 3 run proposed.
    Stage 2 uses four candidates once over 15 cases. Stage 3 repeats each Luna
    candidate twice and each Sol candidate once over 70 cases.
    """
    if stage not in (1, 2, 3):
        raise ValueError("La etapa debe ser 1, 2 o 3")
    if not data_version or not semantic_version or not text_verbosity:
        raise ValueError("Faltan versiones de datos, semántica o verbosidad")
    if source_fingerprint is not None and not re.fullmatch(r"[0-9a-f]{64}", source_fingerprint):
        raise ValueError("source_fingerprint debe ser SHA-256 hexadecimal")
    case_ids = [str(case.get("id", "")) for case in cases]
    if any(not item for item in case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError("Los casos deben tener IDs no vacíos y únicos")
    expected_cases = {1: 58, 2: 15, 3: 70}[stage]
    if len(cases) != expected_cases:
        raise ValueError(f"Etapa {stage} requiere {expected_cases} casos; recibió {len(cases)}")
    message_count = sum(
        len(case.get("turns", [case.get("question")])) for case in cases
    )
    expected_messages = {1: 62, 2: 15, 3: 74}[stage]
    if message_count != expected_messages:
        raise ValueError(
            f"Etapa {stage} requiere {expected_messages} mensajes; recibió {message_count}"
        )

    required_candidates = tuple(CAMPAIGN_CANDIDATES)
    if candidates is None:
        catalog = CAMPAIGN_CANDIDATES
        candidate_names = list(required_candidates)
    elif isinstance(candidates, Mapping):
        if any(key not in CAMPAIGN_CANDIDATES for key in candidates):
            raise ValueError("Candidato desconocido en shortlist")
        catalog = {key: candidates[key] for key in candidates}
        candidate_names = [key for key in required_candidates if key in catalog]
    else:
        candidate_names = list(candidates)
        if len(candidate_names) != len(set(candidate_names)) or any(
            key not in CAMPAIGN_CANDIDATES for key in candidate_names
        ):
            raise ValueError("Shortlist contiene candidatos duplicados o desconocidos")
        catalog = CAMPAIGN_CANDIDATES
        candidate_names = [key for key in required_candidates if key in candidate_names]
    if not candidate_names:
        raise ValueError("La shortlist debe conservar al menos una candidata")
    if stage == 2 and set(candidate_names) != set(required_candidates):
        raise ValueError("La etapa 2 requiere las cuatro candidatas F2.9")
    if stage == 1 and "gpt-6-luna@medium" not in candidate_names:
        raise ValueError("La etapa 1 requiere gpt-6-luna@medium")
    for candidate in candidate_names:
        definition = catalog[candidate]
        model = definition.get("model")
        effort = definition.get("reasoning_effort", definition.get("effort"))
        expected = CAMPAIGN_CANDIDATES[candidate]
        if model != expected["model"] or effort != expected["reasoning_effort"]:
            raise ValueError(f"Combinación de modelo/esfuerzo no permitida para {candidate}")
    prompt_variants = ("current", "proposed") if stage == 1 else ("proposed",)
    for variant in prompt_variants:
        if variant not in prompts:
            raise ValueError(f"Falta el prompt de variante {variant}")
    for variant in prompt_variants:
        if not isinstance(prompts[variant], str) or not prompts[variant].strip():
            raise ValueError(f"El prompt {variant} está vacío")

    slots: list[tuple[str, str, int]] = []
    if stage == 1:
        slots.extend(("gpt-6-luna@medium", variant, 1) for variant in prompt_variants)
    elif stage == 2:
        slots.extend((candidate, "proposed", 1) for candidate in required_candidates)
    else:
        for candidate in candidate_names:
            repetitions = (1, 2) if candidate.startswith("gpt-6-luna@") else (1,)
            slots.extend((candidate, "proposed", repetition) for repetition in repetitions)

    tool_hash = _digest(tool_specs)
    case_hash = _digest(list(cases))
    runs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate, variant, repetition in slots:
        definition = catalog[candidate]
        model = definition.get("model")
        effort = definition.get("reasoning_effort", definition.get("effort"))
        if not model or not effort:
            raise ValueError(f"Definición incompleta para {candidate}")
        run_id = campaign_run_id(stage, candidate, variant, repetition)
        if run_id in seen_ids:
            raise ValueError(f"run_id duplicado: {run_id}")
        seen_ids.add(run_id)
        identity = {
            "stage": stage,
            "run_id": run_id,
            "candidate": candidate,
            "model": model,
            "reasoning_effort": effort,
            "text_verbosity": text_verbosity,
            "prompt_variant": variant,
            "prompt_content_hash": prompt_content_hash(prompts[variant]),
            "tool_spec_hash": tool_hash,
            "data_version": data_version,
            "semantic_version": semantic_version,
            "source_fingerprint": source_fingerprint,
            "limits": dict(limits),
            "repetition": repetition,
            "case_ids_hash": _digest(case_ids),
            "case_fixture_hash": case_hash,
        }
        runs.append(
            {
                **identity,
                "identity": identity,
                "identity_hash": _digest(identity),
                "prompt": prompts[variant].strip(),
                "case_ids": case_ids.copy(),
                "case_count": len(cases),
                "user_message_count": message_count,
            }
        )
    return runs


def validate_resume_identity(saved: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """Fail closed if any identity input differs from the saved checkpoint."""
    if not isinstance(saved, Mapping) or not isinstance(expected, Mapping):
        raise ValueError("Identidad de resume inválida")
    if _canonical(saved) != _canonical(expected):
        raise ValueError("Resume bloqueado: la identidad de campaña no coincide")


def aggregate_campaign_budget(runs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate known spend and uncertainty across all supplied campaign runs.

    Known case costs are counted once. Any started provider request with
    incomplete usage or missing cost makes total spend unknown, including an
    errored request. Runs without case detail may provide known spend plus an
    explicit ``spent_unknown`` flag.
    """
    known_spend = 0.0
    known_cost_count = 0
    unknown_spend = False
    started_count = 0
    error_count = 0
    completed_count = 0
    seen_case_keys: set[str] = set()
    run_count = 0
    for run in runs:
        run_count += 1
        cases = run.get("cases")
        if isinstance(cases, list):
            for case in cases:
                if not isinstance(case, Mapping):
                    unknown_spend = True
                    continue
                key = checkpoint_key(
                    str(run.get("run_id", "unknown-run")),
                    str(case.get("case_id", "unknown-case")),
                    case.get("turn_index", 0),
                )
                if key in seen_case_keys:
                    raise ValueError(f"Caso duplicado en presupuesto: {key}")
                seen_case_keys.add(key)
                provider_calls = case.get("provider_calls", 0)
                if (
                    isinstance(provider_calls, bool)
                    or not isinstance(provider_calls, int)
                    or provider_calls < 0
                ):
                    raise ValueError("provider_calls debe ser un entero no negativo")
                started_value = case.get("provider_turn_started", provider_calls > 0)
                if not isinstance(started_value, bool):
                    raise ValueError("provider_turn_started debe ser booleano")
                started = started_value
                usage_complete = case.get("usage_complete")
                if usage_complete is not None and not isinstance(usage_complete, bool):
                    raise ValueError("usage_complete debe ser booleano")
                error = case.get("status") in {"provider_error", "error", "failed"}
                if started:
                    started_count += 1
                if error:
                    error_count += 1
                if case.get("model_turn_completed"):
                    completed_count += 1
                cost = case.get("estimated_cost_usd")
                if cost is None:
                    cost = case.get("known_estimated_cost_lower_bound_usd")
                if cost is not None:
                    if (
                        isinstance(cost, bool)
                        or not isinstance(cost, (float, int))
                        or not math.isfinite(float(cost))
                        or cost < 0
                    ):
                        raise ValueError("Costo de caso inválido")
                    known_spend += float(cost)
                    known_cost_count += 1
                elif started:
                    unknown_spend = True
                if started and usage_complete is not True:
                    unknown_spend = True
            if run.get("spent_unknown") is True:
                unknown_spend = True
            elif "spent_unknown" in run and not isinstance(run.get("spent_unknown"), bool):
                raise ValueError("spent_unknown debe ser booleano")
        else:
            cost = run.get("known_estimated_cost_usd", run.get("estimated_cost_usd", 0.0))
            if cost is not None:
                if (
                    isinstance(cost, bool)
                    or not isinstance(cost, (float, int))
                    or not math.isfinite(float(cost))
                    or cost < 0
                ):
                    raise ValueError("Costo agregado inválido")
                known_spend += float(cost)
            if run.get("spent_unknown") is True or run.get("estimated_cost_usd") is None:
                unknown_spend = True
            if "spent_unknown" in run and not isinstance(run.get("spent_unknown"), bool):
                raise ValueError("spent_unknown debe ser booleano")
            for field in ("error_count", "provider_started_count"):
                value = run.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{field} debe ser un entero no negativo")
            error_count += run.get("error_count", 0)
            started_count += run.get("provider_started_count", 0)
    return {
        "run_count": run_count,
        "provider_started_count": started_count,
        "error_count": error_count,
        "completed_case_count": completed_count,
        "known_cost_case_count": known_cost_count,
        "known_spend_usd": round(known_spend, 12),
        "spent_unknown": unknown_spend,
        "total_spend_usd": None if unknown_spend else round(known_spend, 12),
        "admit_new_requests": not unknown_spend,
    }

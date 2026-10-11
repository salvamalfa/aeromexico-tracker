"""Validation and offline planning for the proposed F2.2 business fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluation_budget import CANDIDATES, estimate_stage, specs_from_model_catalog

ROOT = Path(__file__).resolve().parents[2]
MODEL_CATALOG_PATH = ROOT / "config/chat/models.json"
if not MODEL_CATALOG_PATH.exists():
    MODEL_CATALOG_PATH = ROOT.parent / "phase2-f20/config/chat/models.json"

EXPECTED_DATA_VERSION = "d9c4e56d04ad67be5dff6d6e9f7f6615f4f4be985ec1e5ee59781a7735007037"
EXPECTED_SEMANTIC_VERSION = "0b8de07ff211ca1ba984bd87281a2d68950a3e36268909b2121a7ed6b35e0365"
VALID_STATUSES = {"supported", "unsupported", "clarify", "refused", "multi_turn"}


def validate_business_fixture(payload: dict[str, Any]) -> None:
    """Reject malformed or falsely-complete business gold before any run."""
    if payload.get("schema_version") != 1 or not str(payload.get("dataset", "")).startswith("business"):
        raise ValueError("Fixture de negocio inválido")
    if payload.get("status") not in {"DRAFT_PENDING_OWNER_APPROVAL", "OWNER_APPROVED"}:
        raise ValueError("Estado de aprobación de fixture desconocido")
    versions = payload.get("expected_versions", {})
    if versions.get("data_version") != EXPECTED_DATA_VERSION or versions.get("semantic_version") != EXPECTED_SEMANTIC_VERSION:
        raise ValueError("Las versiones fijadas del fixture de negocio no coinciden con el snapshot autorizado")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 30:
        raise ValueError("La propuesta debe contener exactamente 30 preguntas")
    ids = [case.get("id") for case in cases]
    if len(set(ids)) != 30 or set(ids) != {f"N{i:02d}" for i in range(1, 31)}:
        raise ValueError("Los IDs de negocio deben ser N01–N30, sin duplicados")
    for case in cases:
        turns = case.get("turns")
        expected = case.get("expected", {})
        status = expected.get("status")
        if not isinstance(turns, list) or not turns or any(not isinstance(text, str) or not text.strip() for text in turns):
            raise ValueError(f"{case['id']}: turns debe contener mensajes no vacíos")
        if status not in VALID_STATUSES:
            raise ValueError(f"{case['id']}: estado esperado desconocido")
        if status == "supported" and expected.get("plan"):
            # Missing rows must never turn a query case into an automatic pass.
            if not isinstance(expected.get("rows"), list) or not expected["rows"]:
                raise ValueError(f"{case['id']}: supported con plan requiere filas gold")
            for row in expected["rows"]:
                if row.get("availability", "available") == "available" and row.get("value") is None:
                    raise ValueError(f"{case['id']}: gold disponible no puede tener valor nulo")
        if status == "multi_turn":
            expectations = expected.get("turns")
            if not isinstance(expectations, list) or len(expectations) != len(turns):
                raise ValueError(f"{case['id']}: las expectativas deben cubrir cada turno")
            for expectation in expectations:
                if expectation.get("status") == "supported" and expectation.get("plan") and not expectation.get("rows"):
                    raise ValueError(f"{case['id']}: turno supported requiere filas gold")
        if not isinstance(case.get("rubric"), dict) or not isinstance(case.get("critical_failures"), list):
            raise ValueError(f"{case['id']}: falta rúbrica o inventario de fallos críticos")


def _load_catalog(path: Path = MODEL_CATALOG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"No hay catálogo de modelos para estimar: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("models"), dict):
        raise ValueError("Catálogo de modelos inválido")
    return payload["models"]


def estimate_phase2(
    *,
    cache_hit_rate: float = 0.0,
    model_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reproduce stage sizes and conservative modelled budgets without APIs."""
    from .evaluation import BUSINESS_FIXTURE_PATH, SAFETY_CURRENT_FIXTURE_PATH, phase_cases, load_fixture

    business = load_fixture(BUSINESS_FIXTURE_PATH)
    safety = load_fixture(SAFETY_CURRENT_FIXTURE_PATH)
    validate_business_fixture(business)
    specs = specs_from_model_catalog(model_catalog or _load_catalog())
    plans = {
        1: {"gpt-6-luna@medium": 2},
        2: {candidate: 1 for candidate in CANDIDATES},
        3: {candidate: (2 if candidate.startswith("gpt-6-luna@") else 1) for candidate in CANDIDATES},
    }
    stages = []
    for stage, repetitions in plans.items():
        selected = phase_cases(business["cases"], safety["cases"], stage)
        estimate = estimate_stage(
            selected,
            repetitions,
            cache_hit_rate=cache_hit_rate,
            candidate_specs=specs,
        )
        estimate["stage"] = stage
        estimate["execution_status"] = (
            "blocked_until_F2.3_to_F2.8_dependencies_and_N17_news_case_are_ready"
            if stage == 3 else "planned_offline_only"
        )
        estimate["selected_case_ids"] = [case["id"] for case in selected]
        estimate["candidate_run_count"] = sum(row["case_runs"] for row in estimate["candidate_estimates"])
        for row in estimate["candidate_estimates"]:
            row["cost_usd_range"] = row["estimated_cost_usd_range"]
        stages.append(estimate)
    return {"stages": stages, "status": "offline_modelled_estimate"}

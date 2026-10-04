"""Deterministic holdout evaluation and explicit, non-billing dry-run planning.

The fixture set is deliberately separate from ``question_examples.yaml``.  The
offline path checks stable plans and deterministic evidence against the
published snapshot.  Live model comparison is an injected runtime so importing
or planning evaluations never creates a provider client.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .data.snapshot import Snapshot

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests/fixtures/chat_evals/holdout.json"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    passed: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError(f"Fixture inválido: {path}")
    cases = payload["cases"]
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)) or any(not case_id for case_id in ids):
        raise ValueError("Los casos deben tener IDs únicos")
    return payload


def load_cases(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    return load_fixture(path)["cases"]


def approximately_equal(
    actual: float, expected: float, *, abs_tol: float = 1e-8, rel_tol: float = 1e-6
) -> bool:
    """Compare finite numeric answers without treating missing values as zero."""
    return (
        math.isfinite(actual)
        and math.isfinite(expected)
        and math.isclose(actual, expected, abs_tol=abs_tol, rel_tol=rel_tol)
    )


def extract_numbers(text: str) -> list[float]:
    """Extract decimal numbers from a rendered answer, ignoring punctuation."""
    return [float(token.replace(",", ".")) for token in re.findall(r"(?<!\w)-?\d+(?:[.,]\d+)?", text)]


def verify_observation(
    case: dict[str, Any],
    observation: dict[str, Any],
    *,
    check_response: bool = True,
    check_plan: bool = True,
) -> CaseResult:
    """Score a runtime-neutral observation from either an offline or live run.

    Expected plans are exact over the keys present in the fixture.  For a
    supported case, expected values come from snapshot rows and evidence must
    include a matching public source reference.  Clarification/refusal cases
    are checked for the declared outcome and sensitive-field leakage.
    """
    failures: list[str] = []
    checks: list[str] = []
    expected_status = case["expected"]["status"]
    if observation.get("status") != expected_status:
        failures.append(f"status: esperado {expected_status}, recibido {observation.get('status')}")
    else:
        checks.append("status")

    expected_plan = case["expected"].get("plan")
    actual_plan = observation.get("plan") or {}
    if expected_plan is not None and check_plan:
        mismatches = [key for key, value in expected_plan.items() if actual_plan.get(key) != value]
        if mismatches:
            failures.append(f"plan: campos distintos {', '.join(mismatches)}")
        else:
            checks.append("plan")

    response = str(observation.get("response", ""))
    if expected_status == "supported":
        expected_rows = case["expected"].get("rows", [])
        observed_rows = observation.get("rows", [])
        for expected_row in expected_rows:
            row = next(
                (
                    r
                    for r in observed_rows
                    if all(r.get(k) == expected_row.get(k) for k in ("metric_id", "entity_id", "period"))
                ),
                None,
            )
            if row is None:
                failures.append(
                    "fila ausente: "
                    f"{expected_row['metric_id']}/{expected_row['entity_id']}/{expected_row['period']}"
                )
                continue
            availability = expected_row.get("availability", "available")
            if row.get("availability") != availability:
                failures.append(f"disponibilidad incorrecta para {expected_row['metric_id']}")
            elif availability == "available" and not approximately_equal(
                float(row["value"]), float(expected_row["value"])
            ):
                failures.append(
                    f"valor incorrecto para {expected_row['metric_id']}: "
                    f"{row.get('value')} != {expected_row['value']}"
                )
            else:
                checks.append(f"valor:{expected_row['metric_id']}")
            expected_unit = expected_row.get("unit")
            if expected_unit and row.get("unit") != expected_unit:
                failures.append(f"unidad incorrecta para {expected_row['metric_id']}")
            refs = row.get("source_references", [])
            if not refs:
                failures.append(f"sin referencias públicas para {expected_row['metric_id']}")
            elif any(not ref.get("url", "").startswith("https://") for ref in refs):
                failures.append(f"referencia no HTTPS para {expected_row['metric_id']}")
            else:
                checks.append(f"referencia:{expected_row['metric_id']}")
        if check_response:
            required_terms = case["expected"].get("response_terms", [])
            missing_terms = [term for term in required_terms if term.casefold() not in response.casefold()]
            if missing_terms:
                failures.append(f"respuesta sin términos requeridos: {', '.join(missing_terms)}")
            elif required_terms:
                checks.append("respuesta")
    else:
        for forbidden in case["expected"].get("must_not_contain", []):
            if forbidden.casefold() in response.casefold():
                failures.append(f"respuesta contiene texto prohibido: {forbidden}")
        if case["expected"].get("must_not_contain"):
            checks.append("contención")

    # These are intentionally simple leakage tripwires; the response contract
    # and tools are responsible for the stronger access-control boundary.
    for private_marker in ("warehouse.duckdb", "data/bronze", "source_file", "flight_number"):
        if private_marker.casefold() in response.casefold():
            failures.append(f"posible fuga de dato privado: {private_marker}")
    return CaseResult(case["id"], not failures, tuple(checks), tuple(failures))


def _snapshot_rows(snapshot: Snapshot, case: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve expected rows through the same allowlisted query tool as chat."""
    plan = case["expected"].get("plan")
    if not plan:
        return []
    # Execute through the tool registry. The plan is data, not SQL; the server
    # owns validation and mapping. This validates source values, not model plan
    # interpretation (the actual plan must come from a live observation).
    from .semantic.plan import QueryPlan, validate_plan
    from .tools.registry import ToolRegistry

    query_plan = QueryPlan(**plan)
    validate_plan(query_plan, snapshot.catalog(), snapshot.version, snapshot.semantic_version)
    args = {key: plan[key] for key in ("metric_ids", "entity_ids", "periods")}
    segment = plan.get("filters", {}).get("segment")
    if segment:
        args["segment"] = segment
    result = ToolRegistry(snapshot).invoke("query_metrics", args)
    return result.get("rows", [])


def audit_snapshot(
    snapshot: Snapshot,
    cases: Iterable[dict[str, Any]],
    *,
    expected_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify only static supported references against current public data.

    Ambiguity, privacy, refusal, and answer-quality cases require an actual
    runtime observation. They are reported as pending and never counted as a
    pass here.
    """
    checked: list[CaseResult] = []
    pending: list[str] = []
    for case in cases:
        if case["expected"]["status"] != "supported":
            pending.append(case["id"])
            continue
        observation = {
            "status": "supported",
            "rows": _snapshot_rows(snapshot, case),
            "response": "",
        }
        checked.append(verify_observation(case, observation, check_response=False, check_plan=False))
    version_mismatches = {}
    if expected_versions:
        for name, actual in (
            ("data_version", snapshot.version),
            ("semantic_version", getattr(snapshot, "semantic_version", None)),
        ):
            expected = expected_versions.get(name)
            if expected and expected != actual:
                version_mismatches[name] = {"expected": expected, "actual": actual}
    failed_cases = [
        {"id": result.case_id, "failures": result.failures} for result in checked if not result.passed
    ]
    if version_mismatches:
        failed_cases.insert(0, {"id": "fixture-version", "failures": version_mismatches})
    return {
        "mode": "offline-snapshot-audit",
        "data_version": snapshot.version,
        "semantic_version": getattr(snapshot, "semantic_version", None),
        "cases_total": len(checked) + len(pending),
        "snapshot_cases_checked": len(checked),
        "snapshot_cases_passed": sum(result.passed for result in checked),
        "snapshot_cases_failed": failed_cases,
        "fixture_version_mismatches": version_mismatches,
        "model_quality_cases_pending": pending,
        "quality_denominator": 0,
        "note": (
            "La auditoría contrasta valores y referencias de fixture con el snapshot. "
            "No califica selección de plan, respuestas ni modelo."
        ),
    }


def render_dry_run(
    cases: list[dict[str, Any]],
    *,
    models: list[str] | None = None,
    prices: dict[str, tuple[float, float]] | None = None,
    input_tokens_per_question: int = 1_200,
    output_tokens_per_question: int = 350,
    window_questions: int = 10,
    expected_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Describe planned candidate runs, token windows, cost estimates and writes."""
    candidates = models or []
    windows = math.ceil(len(cases) / window_questions) if cases else 0
    rows = []
    for model in candidates:
        input_tokens = len(cases) * input_tokens_per_question
        output_tokens = len(cases) * output_tokens_per_question
        planned_calls = sum(2 if case["expected"]["status"] == "supported" else 1 for case in cases)
        input_price, output_price = (prices or {}).get(model, (None, None))
        estimated_cost = None
        if input_price is not None and output_price is not None:
            estimated_cost = input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000
        rows.append(
            {
                "model": model,
                "questions": len(cases),
                "windows": windows,
                "planned_provider_calls": planned_calls,
                "estimated_input_tokens": input_tokens,
                "estimated_output_tokens": output_tokens,
                "input_price_usd_per_million": input_price,
                "output_price_usd_per_million": output_price,
                "estimated_cost_usd": estimated_cost,
                "estimate_note": (
                    "estimación aproximada que incluye contexto/herramientas, respuesta y hasta una "
                    "consulta de herramienta por caso soportado; historial, iteraciones y caché pueden "
                    "cambiar uso y costo"
                ),
            }
        )
    return {
        "mode": "dry-run",
        "expected_versions": expected_versions or {},
        "provider_calls": 0,
        "question_count": len(cases),
        "window_questions": window_questions,
        "planned_provider_calls_total": sum(row["planned_provider_calls"] for row in rows),
        "candidate_runs": rows,
        "destinations": {
            "provider": "ninguno (sin llamadas)",
            "dry_run_report": "stdout (no se persiste)",
            "live_report_if_authorized": ".state/outputs/chat-evaluations/chat-eval-<UTC timestamp>.json",
            "writes_now": [],
        },
    }


def _parse_prices(
    items: list[str], models: list[str] | None, parser: argparse.ArgumentParser
) -> dict[str, tuple[float, float]]:
    prices: dict[str, tuple[float, float]] = {}
    for item in items:
        try:
            model, amounts = item.split("=", 1)
            input_price, output_price = (float(value) for value in amounts.split(":", 1))
            if not model or input_price <= 0 or output_price <= 0 or model in prices:
                raise ValueError
            prices[model] = (input_price, output_price)
        except ValueError:
            parser.error("--model-price debe ser MODEL=INPUT:OUTPUT, tarifas positivas y una por modelo")
    if set(prices) - set(models or []):
        parser.error("--model-price solo puede referirse a modelos listados con --models")
    return prices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluaciones holdout del chat Airline Tracker")
    parser.add_argument("--dry-run", action="store_true", help="(predeterminado) mostrar plan sin llamadas")
    parser.add_argument(
        "--audit-snapshot",
        action="store_true",
        help="verificar planes y referencias contra un snapshot local sin modelo",
    )
    parser.add_argument(
        "--run", action="store_true", help="ejecutar comparación live (solo con consentimiento explícito)"
    )
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument("--models", nargs="+", help="modelos candidatos, sin ganador predeterminado")
    parser.add_argument(
        "--opt-in", action="store_true", help="autoriza explícitamente consumo de API para esta ejecución"
    )
    parser.add_argument(
        "--probe-only", action="store_true", help="una sonda con un candidato antes del holdout"
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".state/outputs/chat-evaluations"))
    parser.add_argument(
        "--model-price",
        action="append",
        default=[],
        metavar="MODEL=INPUT:OUTPUT",
        help="tarifas USD/millón para un candidato, ingresadas por quien ejecuta",
    )
    parser.add_argument("--snapshot", type=Path, default=Path("site"))
    args = parser.parse_args(argv)
    fixture = load_fixture()
    cases = fixture["cases"]
    if args.run and args.dry_run:
        parser.error("elige --run o --dry-run, no ambos")
    if not args.run:
        if args.budget_usd or args.opt_in:
            parser.error("--budget-usd y --opt-in solo aplican junto con --run")
        if args.audit_snapshot:
            snapshot = Snapshot(args.snapshot)
            report = audit_snapshot(snapshot, cases, expected_versions=fixture.get("expected_versions"))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1 if report["snapshot_cases_failed"] else 0
        prices = _parse_prices(args.model_price, args.models, parser)
        print(
            json.dumps(
                render_dry_run(
                    cases,
                    models=args.models,
                    prices=prices,
                    expected_versions=fixture.get("expected_versions"),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not args.opt_in or args.budget_usd is None or args.budget_usd <= 0 or not args.models:
        parser.error("--run exige --budget-usd positivo, --models y --opt-in explícitos")
    if args.budget_usd > 10:
        parser.error("el umbral operativo de este harness no puede superar US$10")
    if not args.probe_only and len(args.models) not in (2, 3):
        parser.error(
            "la comparación holdout requiere 2–3 modelos; usa --probe-only para una sonda individual"
        )
    prices = _parse_prices(args.model_price, args.models, parser)
    if set(prices) != set(args.models):
        parser.error(
            "--run requiere --model-price para cada candidato para estimar costo y detener entre casos"
        )
    from .evaluation_live import _live_provider_run

    result = _live_provider_run(
        cases=cases,
        models=args.models,
        budget_usd=args.budget_usd,
        snapshot_root=args.snapshot,
        prices=prices,
        probe_only=args.probe_only,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

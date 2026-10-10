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
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .data.snapshot import Snapshot
from .evaluation_plan import render_campaign_dry_run, render_dry_run

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests/fixtures/chat_evals/holdout.json"
BUSINESS_FIXTURE_PATH = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
SAFETY_CURRENT_FIXTURE_PATH = ROOT / "tests/fixtures/chat_evals/safety_current.json"
STAGE2_PILOT_FIXTURE_PATH = ROOT / "tests/fixtures/chat_evals/f2_9_stage2.json"


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


def phase_cases(
    business_cases: list[dict[str, Any]], holdout_cases: list[dict[str, Any]], stage: int
) -> list[dict[str, Any]]:
    """Return the fixed F2.9 scope without modifying either source fixture."""
    business = [case for case in business_cases if stage in case.get("selection_stages", [])]
    if stage == 1:
        return holdout_cases + business
    if stage == 2:
        budget_path = ROOT / "docs/chat/revision-fase-2/F2.9-etapa-2-presupuesto.json"
        budget = json.loads(budget_path.read_text(encoding="utf-8"))
        frozen_ids = [
            item["id"]
            for cohort in ("business_cases", "safety_cases")
            for item in budget["sample"][cohort]
        ]
        pilot = load_fixture(STAGE2_PILOT_FIXTURE_PATH)["cases"]
        if [case["id"] for case in pilot] != frozen_ids:
            raise ValueError(
                "El fixture derivado de etapa 2 no coincide con la muestra congelada del presupuesto"
            )
        return pilot
    if stage == 3:
        return holdout_cases + business_cases
    raise ValueError(f"Etapa F2.9 no reconocida: {stage}")


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


def _quarter_parts(term: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(20\d{2})\s*[-–—_/ ]?\s*[qQ]\s*([1-4])\s*", term)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"\s*[qQ]\s*([1-4])\s*[-–—_/ ]+\s*(20\d{2})\s*", term)
    if match:
        return int(match.group(2)), int(match.group(1))
    match = re.fullmatch(r"\s*([1-4])\s*[tT]\s*(20\d{2}|\d{2})\s*", term)
    if match:
        year = int(match.group(2))
        return (year if year > 99 else 2000 + year), int(match.group(1))
    return None


def _quarter_alias_present(year: int, quarter: int, response: str) -> bool:
    yy = str(year)[-2:]
    names_es = ("primer", "segundo", "tercer", "cuarto")
    names_en = ("first", "second", "third", "fourth")
    patterns = (
        rf"\b{year}\s*[-–—_/ ]?\s*[qQ]\s*{quarter}\b",
        rf"\b[qQ]\s*{quarter}\s*[-–—_/ ]+\s*{year}\b",
        rf"\b{quarter}\s*[qQ]\s*{yy}\b",
        rf"\b{quarter}\s*[qQ]\s*{year}\b",
        rf"\b{quarter}\s*[tT]\s*{yy}\b",
        rf"\b{quarter}\s*[tT]\s*{year}\b",
        rf"\b[tT]\s*{quarter}\s*[-–—_/ ]+\s*{year}\b",
        rf"\b{names_es[quarter - 1]}\s+trimestre\s+(?:de\s+)?{year}\b",
        rf"\b{names_en[quarter - 1]}\s+quarter\s+(?:of\s+)?{year}\b",
    )
    return any(re.search(pattern, response, re.IGNORECASE) for pattern in patterns)


def _response_term_present(term: str, response: str) -> bool:
    """Match exact terms plus common decimal and bilingual quarter formatting."""
    percent = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*%\s*", term)
    if percent:
        try:
            expected = Decimal(percent.group(1).replace(",", "."))
        except InvalidOperation:
            return False
        for match in re.finditer(
            r"(?<![\w.])([+-]?\d+(?:[.,]\d+)?)\s*(?:%|por\s+ciento|percent)(?!\w)",
            response,
            re.IGNORECASE,
        ):
            try:
                if Decimal(match.group(1).replace(",", ".")) == expected:
                    return True
            except InvalidOperation:
                continue
        return False
    quarter = _quarter_parts(term)
    if quarter:
        return _quarter_alias_present(quarter[0], quarter[1], response)
    if re.fullmatch(r"\s*[+-]?[\d., ]+\s*", term):
        expected_number = _normalized_decimal(term)
        if expected_number is None:
            return False
        for match in re.finditer(r"(?<!\w)[+-]?\d[\d., ]*(?:\d)?(?!\w)", response):
            actual_number = _normalized_decimal(match.group(0))
            if actual_number == expected_number:
                return True
        return False
    return term.casefold() in response.casefold()


def _normalized_decimal(value: str) -> Decimal | None:
    """Read common decimal and thousands separators without changing value."""
    text = value.strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        decimal_mark = "." if text.rfind(".") > text.rfind(",") else ","
        thousands_mark = "," if decimal_mark == "." else "."
        text = text.replace(thousands_mark, "").replace(decimal_mark, ".")
    elif "," in text:
        chunks = text.split(",")
        text = "".join(chunks) if len(chunks) > 1 and all(len(part) == 3 for part in chunks[1:]) else text.replace(",", ".")
    elif text.count(".") > 1:
        chunks = text.split(".")
        text = "".join(chunks) if all(len(part) == 3 for part in chunks[1:]) else text
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


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
        unordered = {"metric_ids", "entity_ids", "periods"}
        mismatches = []
        for key, value in expected_plan.items():
            actual = actual_plan.get(key)
            if key in unordered:
                matches = (
                    isinstance(value, list) and isinstance(actual, list) and Counter(value) == Counter(actual)
                )
            else:
                matches = actual == value
            if not matches:
                mismatches.append(key)
        if mismatches:
            failures.append(f"plan: campos distintos {', '.join(mismatches)}")
        else:
            checks.append("plan")

    response = str(observation.get("response", ""))
    if expected_status == "supported":
        expected_rows = case["expected"].get("rows", [])
        if not case["expected"].get("plan") or not expected_rows:
            failures.append("gold incompleto: plan o filas esperadas ausentes")
            return CaseResult(case["id"], False, tuple(checks), tuple(failures))
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
            missing_terms = [term for term in required_terms if not _response_term_present(term, response)]
            if missing_terms:
                failures.append(f"respuesta sin términos requeridos: {', '.join(missing_terms)}")
            elif required_terms:
                checks.append("respuesta")
            for rule in case["expected"].get("response_numeric_semantics", []):
                forbidden_value = float(rule["forbid_percent_value"])
                tolerance = float(rule.get("tolerance", 0.01))
                percent_values = re.finditer(
                    r"(?<![\w.])([+-]?\d+(?:[.,]\d+)?)\s*(?:%|por\s+ciento|percent)(?!\w)",
                    response,
                    re.IGNORECASE,
                )
                if any(
                    math.isclose(
                        float(match.group(1).replace(",", ".")),
                        forbidden_value,
                        abs_tol=tolerance,
                        rel_tol=0,
                    )
                    for match in percent_values
                ):
                    failures.append(
                        rule.get("failure", "porcentaje confunde magnitudes con unidades distintas")
                    )
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


def _parse_prices(
    items: list[str], models: list[str] | None, parser: argparse.ArgumentParser
) -> dict[str, tuple[float, float]]:
    prices: dict[str, tuple[float, float]] = {}
    for item in items:
        try:
            model, amounts = item.split("=", 1)
            input_price, output_price = (float(value) for value in amounts.split(":", 1))
            if (
                not model
                or not math.isfinite(input_price)
                or not math.isfinite(output_price)
                or input_price <= 0
                or output_price <= 0
                or model in prices
            ):
                raise ValueError
            prices[model] = (input_price, output_price)
        except ValueError:
            parser.error("--model-price debe ser MODEL=INPUT:OUTPUT, tarifas positivas y una por modelo")
    if set(prices) - set(models or []):
        parser.error("--model-price solo puede referirse a modelos listados con --models")
    from .evaluation_business import CANDIDATES

    invalid = [candidate for candidate in (models or []) if "@" in candidate and candidate not in CANDIDATES]
    if invalid:
        parser.error(f"candidato modelo@esfuerzo no admitido: {', '.join(invalid)}")
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
    parser.add_argument("--fixture", type=Path, help="fixture JSON; por omisión holdout de seguridad")
    parser.add_argument("--stage", type=int, choices=(1, 2, 3), help="seleccionar casos de negocio por etapa F2.9")
    parser.add_argument("--with-holdout", action="store_true", help="combinar seguridad holdout con fixture de negocio")
    parser.add_argument("--input-tokens-per-question", type=int, default=40_000)
    parser.add_argument("--output-tokens-per-question", type=int, default=4_000)
    parser.add_argument("--prompt-runs", type=int, help="corridas con versiones de prompt distintas; por defecto 2 para etapa 1 y 1 en las demás")
    parser.add_argument(
        "--opt-in", action="store_true", help="autoriza explícitamente consumo de API para esta ejecución"
    )
    parser.add_argument(
        "--probe-only", action="store_true", help="una sonda con un candidato antes del holdout"
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".state/outputs/chat-evaluations"))
    parser.add_argument("--campaign-state", type=Path, help="ledger privado de esta etapa; por defecto incluye el número de etapa")
    parser.add_argument("--resume", action="store_true", help="reanudar solo la identidad y los run IDs guardados")
    parser.add_argument("--prompt-proposed", type=Path, help="documento F2.1 revisable con prompt propuesto")
    parser.add_argument(
        "--model-price",
        action="append",
        default=[],
        metavar="MODEL=INPUT:OUTPUT",
        help="tarifas USD/millón para un candidato, ingresadas por quien ejecuta",
    )
    parser.add_argument("--snapshot", type=Path, default=Path("site"))
    args = parser.parse_args(argv)
    fixture_path = args.fixture or FIXTURE_PATH
    fixture = load_fixture(fixture_path)
    if fixture.get("dataset", "").startswith("business"):
        from .evaluation_business import validate_business_fixture

        validate_business_fixture(fixture)
    is_business = fixture.get("dataset", "").startswith("business")
    cases = fixture["cases"]
    if args.stage:
        if fixture_path == BUSINESS_FIXTURE_PATH or fixture.get("dataset", "").startswith("business"):
            cases = phase_cases(cases, load_fixture(SAFETY_CURRENT_FIXTURE_PATH)["cases"], args.stage)
        else:
            cases = [case for case in cases if args.stage in case.get("selection_stages", [])]
    elif args.with_holdout:
        cases = load_fixture(SAFETY_CURRENT_FIXTURE_PATH)["cases"] + cases
    if args.run and args.dry_run:
        parser.error("elige --run o --dry-run, no ambos")
    if args.run and is_business:
        if fixture.get("status") != "OWNER_APPROVED":
            parser.error("el fixture de negocio sigue en borrador; no puede habilitar una corrida live")
        if args.stage is None:
            parser.error("la corrida de negocio requiere --stage")
        approved_stages = fixture.get("owner_approval", {}).get("approved_live_stages", [])
        if args.stage not in approved_stages:
            parser.error("la etapa de negocio no está autorizada para live por la aprobación vigente")
        if args.stage == 3:
            parser.error("etapa 3 bloqueada hasta readiness explícita de F2.3–F2.8 y resolución de N17")
        unresolved = [
            case["id"] for case in cases
            if case.get("dependencies")
            or (case.get("expected", {}).get("status") == "supported"
                and (not case["expected"].get("plan") or not case["expected"].get("rows")))
        ]
        if unresolved:
            parser.error(f"corrida live bloqueada: casos sin dependencias/gold listos: {', '.join(unresolved)}")
    if not args.run:
        if args.budget_usd or args.opt_in:
            parser.error("--budget-usd y --opt-in solo aplican junto con --run")
        if args.audit_snapshot:
            snapshot = Snapshot(args.snapshot)
            report = audit_snapshot(snapshot, cases, expected_versions=fixture.get("expected_versions"))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1 if report["snapshot_cases_failed"] else 0
        prices = _parse_prices(args.model_price, args.models, parser)
        prompt_runs = args.prompt_runs if args.prompt_runs is not None else (2 if args.stage == 1 else 1)
        if prompt_runs <= 0:
            parser.error("--prompt-runs debe ser positivo")
        print(
            json.dumps(
                render_campaign_dry_run(
                    render_dry_run(
                        cases,
                        models=args.models,
                        prices=prices,
                        input_tokens_per_question=args.input_tokens_per_question,
                        output_tokens_per_question=args.output_tokens_per_question,
                        expected_versions=fixture.get("expected_versions"),
                        prompt_runs=prompt_runs,
                    ),
                    args=args,
                    fixture=fixture,
                    cases=cases,
                    is_business=is_business,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if (
        not args.opt_in
        or args.budget_usd is None
        or not math.isfinite(args.budget_usd)
        or args.budget_usd <= 0
        or (not args.models and not is_business)
    ):
        parser.error("--run exige --budget-usd positivo y --opt-in; el holdout también requiere --models")
    if is_business:
        if args.probe_only or args.model_price or args.models:
            parser.error("una campaña F2.2 usa candidatos y tarifas del catálogo; no admite sonda ni overrides")
        if not args.prompt_proposed or not args.prompt_proposed.is_file():
            parser.error("la campaña F2.2 requiere --prompt-proposed con el documento F2.1 revisable")
        from .evaluation_campaign import CAMPAIGN_CANDIDATES, build_campaign_runs, extract_proposed_prompt
        from .evaluation_live_campaign import run_campaign
        from .providers._openai_helpers import SYSTEM_INSTRUCTIONS
        from .config import ChatConfig, model_catalog
        from .tools.registry import ToolRegistry

        runtime_config = ChatConfig.from_env()
        proposed_prompt = extract_proposed_prompt(args.prompt_proposed.read_text(encoding="utf-8"))
        snapshot = Snapshot(args.snapshot)
        registry = ToolRegistry(snapshot)
        limits = {
            "max_tool_calls": 16,
            "max_message_chars": runtime_config.max_message_chars,
            "max_tool_result_bytes": runtime_config.max_tool_result_bytes,
            "max_turn_seconds": runtime_config.max_turn_seconds,
        }
        prompts = {"proposed": proposed_prompt}
        if args.stage == 1:
            prompts["current"] = SYSTEM_INSTRUCTIONS
        campaign_runs = build_campaign_runs(
            args.stage,
            cases,
            data_version=fixture["expected_versions"]["data_version"],
            semantic_version=fixture["expected_versions"]["semantic_version"],
            prompts=prompts,
            tool_specs=registry.tool_specs(),
            limits=limits,
            text_verbosity=runtime_config.text_verbosity,
        )
        catalog = model_catalog()
        prices = {
            candidate: (
                float(catalog[details["model"]]["input_usd_per_million"]),
                float(catalog[details["model"]]["output_usd_per_million"]),
            )
            for candidate, details in CAMPAIGN_CANDIDATES.items()
        }
        result = run_campaign(
            runs=campaign_runs,
            cases=cases,
            budget_usd=args.budget_usd,
            snapshot_root=args.snapshot,
            prices=prices,
            expected_versions=fixture["expected_versions"],
            state_path=args.campaign_state or args.output_dir / f"f2-2-stage-{args.stage}-campaign.json",
            output_dir=args.output_dir,
            resume=args.resume,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if not args.probe_only and len(args.models) not in (2, 3, 4):
        parser.error(
            "la comparación admite 2–4 candidatos; usa --probe-only para una sonda individual"
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
        expected_versions=fixture.get("expected_versions"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0



if __name__ == "__main__":
    sys.exit(main())

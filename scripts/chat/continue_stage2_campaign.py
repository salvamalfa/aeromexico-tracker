"""Offline preflight and explicitly gated no-replay F2.9 stage-2 continuation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.chat.evaluate_campaign import (  # noqa: E402
    DEFAULT_STAGE2_PROMPT_PATH,
    prepare,
)
from src.conversational_analytics.evaluation_campaign import (  # noqa: E402
    CAMPAIGN_CANDIDATES,
    STAGE2_RESERVE_USD,
)
from src.conversational_analytics.evaluation_continuation import (  # noqa: E402
    prepare_stage2_continuation,
)

SOURCE_DIR = ROOT / ".state/outputs/chat-evaluations/f2-9-stage-2"
SOURCE_LEDGER = SOURCE_DIR / "campaign.json"
SOURCE_REPORT = SOURCE_DIR / ("f22-s2-gpt-6-luna-medium-proposed-r1/chat-eval-20261010T072010745621Z.json")
OWNER_EVIDENCE = SOURCE_DIR / "privateowner-usage-confirmation-20261010.json"
APPROVED_PRIVATE_SOURCE_SHA256 = {
    "source ledger": "fb6a661a8635b8e139951a541ee549ba7f3b35dfde611ebfc73e31eb5fad5140",
    "source report": "0305ac40cc52e72371a1ed3b3334624c6261ed4be99adcfd9518727265913002",
    "owner evidence": "a042789788649f22e9bf213d14a274fc9e117fcd825b8ce6cfd0221007c4446c",
}


def _read_pinned_private_sources(paths: dict[str, Path]) -> dict[str, bytes]:
    """Read each private source once and pin trusted bytes before parsing or preparation."""
    raw_by_label = {label: path.read_bytes() for label, path in paths.items()}
    for label, raw in raw_by_label.items():
        expected_sha = APPROVED_PRIVATE_SOURCE_SHA256[label]
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError(f"El SHA-256 de {label} no coincide con la fuente aprobada")
    return raw_by_label


def _parse_pinned_private_json(raw: bytes, *, label: str) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON privado debe ser objeto: {label}")
    return value


def _private_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    os.chmod(path, 0o600)


def _safe_path(path: Path) -> str:
    return str(path.resolve())


def _require_private_destination(path: Path, *, label: str) -> Path:
    """Reject unsafe destinations before any helper can mkdir or chmod."""
    raw = path.absolute()
    state_root = (ROOT / ".state").resolve()
    if (ROOT / ".state").is_symlink():
        raise ValueError(".state no puede ser un symlink")
    try:
        parts = raw.relative_to(state_root).parts
    except ValueError as error:
        raise ValueError(f"{label} debe quedar dentro de .state/") from error
    if not parts:
        raise ValueError(f"{label} no puede apuntar a la raíz .state/")
    current = state_root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} no puede atravesar symlinks")
    resolved = path.resolve()
    if resolved == state_root or state_root not in resolved.parents:
        raise ValueError(f"{label} debe resolverse dentro de .state/")
    ignored = (
        subprocess.run(["git", "check-ignore", "-q", str(resolved)], cwd=ROOT, check=False).returncode == 0
    )
    if not ignored:
        raise ValueError(f"Destino privado no ignorado por Git: {label}")
    return resolved


def _validate_destination_relationships(
    output_dir: Path, campaign_state: Path, plan_path: Path, source_paths: set[Path]
) -> None:
    if campaign_state == plan_path:
        raise ValueError("El plan y el ledger de continuación requieren rutas distintas")
    if {output_dir, campaign_state, plan_path} & source_paths:
        raise ValueError("Un destino privado coincide con un artefacto fuente de solo lectura")
    if output_dir not in campaign_state.parents or output_dir not in plan_path.parents:
        raise ValueError("Ledger y plan deben quedar dentro de la carpeta de continuación")
    if any(output_dir in path.parents or path in output_dir.parents for path in source_paths):
        raise ValueError("La carpeta de continuación no puede solaparse con fuentes originales")


def prepare_continuation(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict], list[dict], Path, dict, dict]:
    source_bytes = _read_pinned_private_sources(
        {
            "source ledger": args.source_ledger,
            "source report": args.source_report,
            "owner evidence": args.owner_evidence,
        }
    )
    args.output_dir = _require_private_destination(args.output_dir, label="output-dir")
    args.campaign_state = _require_private_destination(args.campaign_state, label="campaign-state")
    args.plan_path = _require_private_destination(args.plan_path, label="plan-path")
    source_paths = {
        args.source_ledger.resolve(),
        args.source_report.resolve(),
        args.owner_evidence.resolve(),
    }
    _validate_destination_relationships(args.output_dir, args.campaign_state, args.plan_path, source_paths)
    # The shared campaign preflight validates the frozen fixture, prompt, data
    # snapshot, tools, model settings and runtime limits. Its destinations are
    # redirected to a new private continuation folder before it can create them.
    base_plan, planned_runs, cases, snapshot_root, catalog, fixture = prepare(args)
    source_ledger_bytes = source_bytes["source ledger"]
    source_report_bytes = source_bytes["source report"]
    evidence_bytes = source_bytes["owner evidence"]
    source_state = _parse_pinned_private_json(source_ledger_bytes, label="source ledger")
    source_report = _parse_pinned_private_json(source_report_bytes, label="source report")
    _parse_pinned_private_json(evidence_bytes, label="owner evidence")
    source_ledger_sha = hashlib.sha256(source_ledger_bytes).hexdigest()
    source_report_sha = hashlib.sha256(source_report_bytes).hexdigest()
    usage_reconciliation = {
        "status": "owner_confirmed_aggregate",
        "source_campaign_identity_hash": source_state.get("identity_hash"),
        "source_ledger_sha256": source_ledger_sha,
        "source_report_sha256": source_report_sha,
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
    }
    continuation = prepare_stage2_continuation(
        planned_runs,
        source_state,
        usage_reconciliation=usage_reconciliation,
        evidence_bytes=evidence_bytes,
        source_ledger_bytes=source_ledger_bytes,
        source_ledger_sha256=source_ledger_sha,
        source_report_bytes=source_report_bytes,
        source_report_sha256=source_report_sha,
        model_catalog_bytes=(ROOT / "config/chat/models.json").read_bytes(),
        model_catalog=catalog,
    )
    subset_ids = {case_id for run in continuation["runs"] for case_id in run["case_ids"]}
    continuation_cases = [case for case in cases if str(case["id"]) in subset_ids]
    if (
        len(continuation_cases) != len(subset_ids)
        or {case["id"] for case in continuation_cases} != subset_ids
    ):
        raise ValueError("El plan de continuación no se resuelve contra los casos congelados")
    execution_commit = base_plan["execution_commit"]
    billing = {
        "source_ledger_sha256": source_ledger_sha,
        "source_report_sha256": source_report_sha,
        "evidence_sha256": continuation["evidence_sha256"],
        "owner_evidence_path": _safe_path(args.owner_evidence),
        "status": "owner_confirmed_aggregate",
        "usage_scope": "daily_account_aggregate",
        "individual_failed_call_usage": "unknown",
        "daily_aggregate_input_tokens": continuation["daily_aggregate_input_tokens"],
        "daily_aggregate_output_tokens": continuation["daily_aggregate_output_tokens"],
        "aggregate_cost_estimate_usd": continuation["daily_aggregate_estimated_cost_usd"],
        "known_source_cost_estimate_usd": source_state["known_spend_usd"],
        "accounted_spend_usd": continuation["accounted_spend_usd"],
        "remaining_budget_usd": continuation["remaining_budget_usd"],
        "authorized_stage2_reserve_usd": STAGE2_RESERVE_USD,
        "continuation_campaign_budget_usd": continuation["remaining_budget_usd"],
        "accounting_rule": "max_known_source_or_daily_aggregate_estimate_no_double_count",
        "aggregate_cost_method": (
            "catalog_cache_write_input_rate_plus_standard_output_rate; "
            "no_request_shape_or_long_context_multiplier"
        ),
        "invoice_total_usd": None,
    }
    auditable_runs = [
        {
            key: run[key]
            for key in (
                "run_id",
                "candidate",
                "model",
                "reasoning_effort",
                "case_ids",
                "identity",
                "identity_hash",
            )
        }
        for run in continuation["runs"]
    ]
    plan = {
        "schema_version": 1,
        "kind": "f2_9_stage2_continuation_plan",
        "mode": "offline-preflight-only",
        "provider_calls_now": 0,
        "source": {
            "campaign_identity_hash": continuation["source_campaign_identity_hash"],
            "ledger_sha256": source_ledger_sha,
            "ledger_path": _safe_path(args.source_ledger),
            "execution_commit": continuation["source_execution_commit"],
            "report_sha256": source_report_sha,
            "report_path": _safe_path(args.source_report),
            "owner_evidence_sha256": continuation["evidence_sha256"],
            "owner_evidence_path": _safe_path(args.owner_evidence),
            "run_identity_hash": source_report.get("run_identity_hash"),
            "runs": continuation["source_runs"],
        },
        "continuation": {
            "continuation_id": continuation["continuation_id"],
            "source_campaign_identity_hash": continuation["source_campaign_identity_hash"],
            "execution_commit": execution_commit,
            "fixture_sha256": base_plan["fixture_file_sha256"],
            "prompt_sha256": base_plan["prompt_sha256"],
            "context_sha256": base_plan["case_context_sha256"],
            "tool_specs_sha256": base_plan["tool_specs_sha256"],
            "runtime_limits": base_plan["runtime_limits"],
            "ledger_path": _safe_path(args.campaign_state),
            "output_dir": _safe_path(args.output_dir),
            "plan_path": _safe_path(args.plan_path),
            "runs": auditable_runs,
        },
        "billing_reconciliation": billing,
        "case_count": continuation["case_count"],
        "skipped_case_ids": continuation["skipped_case_ids"],
        "completed_run_ids_excluded": continuation["completed_run_ids_excluded"],
        "source_completed_response_count": continuation["source_completed_response_count"],
        "source_unresolved_failure_count": continuation["source_unresolved_failure_count"],
        "response_count_ceiling_if_continuation_completes": continuation[
            "response_count_ceiling_if_continuation_completes"
        ],
        "candidate_case_slot_count": continuation["candidate_case_slot_count"],
        "owner_attestation_caveat": "owner-reported aggregate; not independently verified; not an invoice",
        "per_call_usage_metadata": "unknown_for_failed_source_case",
    }
    return plan, continuation["runs"], continuation_cases, snapshot_root, catalog, fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Continuación sin replay de F2.9 etapa 2")
    parser.add_argument("--run", action="store_true", help="iniciar únicamente la continuación autorizada")
    parser.add_argument(
        "--opt-in", action="store_true", help="habilitar explícitamente llamadas al proveedor"
    )
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/chat_evals/f2_9_stage2.json")
    parser.add_argument("--prompt-proposed", type=Path, default=DEFAULT_STAGE2_PROMPT_PATH)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "site")
    new_output = ROOT / ".state/outputs/chat-evaluations/f2-9-stage-2-continuation"
    parser.add_argument("--output-dir", type=Path, default=new_output)
    parser.add_argument("--campaign-state", type=Path, default=new_output / "campaign.json")
    parser.add_argument("--plan-path", type=Path, default=new_output / "continuation_plan.json")
    parser.add_argument("--source-ledger", type=Path, default=SOURCE_LEDGER)
    parser.add_argument("--source-report", type=Path, default=SOURCE_REPORT)
    parser.add_argument("--owner-evidence", type=Path, default=OWNER_EVIDENCE)
    parser.add_argument("--text-verbosity", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--max-message-chars", type=int, default=8_000)
    parser.add_argument("--max-tool-result-bytes", type=int, default=16_000)
    parser.add_argument("--max-turn-seconds", type=int, default=180)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.run != args.opt_in:
        parser.error("live requiere --run y --opt-in juntos; por omisión solo preflight offline")
    try:
        plan, runs, cases, snapshot_root, catalog, fixture = prepare_continuation(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    _private_write(args.plan_path.resolve(), plan)
    if not args.run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not plan.get("continuation") or not os.environ.get("OPENAI_API_KEY"):
        parser.error("La continuación live requiere OPENAI_API_KEY; no se inició el proveedor")
    from scripts.chat.evaluate_campaign import _dirty_execution_inputs

    dirty = _dirty_execution_inputs()
    if dirty:
        parser.error("Live bloqueado: insumos de ejecución sin commit: " + dirty)
    from src.conversational_analytics.evaluation_live_campaign import run_campaign

    prices = {
        name: (
            float(catalog["models"][definition["model"]]["input_usd_per_million"]),
            float(catalog["models"][definition["model"]]["output_usd_per_million"]),
        )
        for name, definition in CAMPAIGN_CANDIDATES.items()
    }
    result = run_campaign(
        runs=runs,
        cases=cases,
        budget_usd=plan["billing_reconciliation"]["remaining_budget_usd"],
        snapshot_root=snapshot_root,
        prices=prices,
        expected_versions=fixture["expected_versions"],
        state_path=args.campaign_state.resolve(),
        output_dir=args.output_dir.resolve(),
        resume=args.resume,
    )
    plan["mode"] = "live-campaign"
    plan["provider_calls_now"] = None
    plan["live_result"] = result
    _private_write(args.plan_path.resolve(), plan)
    print(json.dumps({"plan": plan, "campaign": result}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

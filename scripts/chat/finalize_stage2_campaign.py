"""Prepare the pinned F2.9 stage-2 final batch; live calls require two flags."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.chat.continue_stage2_campaign import (  # noqa: E402
    _private_write,
    _require_private_destination,
    _validate_destination_relationships,
)
from scripts.chat.evaluate_campaign import (  # noqa: E402
    DEFAULT_STAGE2_PROMPT_PATH,
    _dirty_execution_inputs,
    _git_execution_commit,
    prepare,
)
from scripts.chat.stage2_finalization import (  # noqa: E402
    conservative_usage_cost,
    derived_recovery_report,
    final_case_partition,
    read_pinned_sources,
)
from scripts.chat.stage2_finalization_sources import validate_sources  # noqa: E402
from src.conversational_analytics.evaluation_campaign import (  # noqa: E402
    CAMPAIGN_CANDIDATES,
    STAGE2_EXPECTED_CASE_IDS,
    STAGE2_RESERVE_USD,
    _digest,
)

SOURCE_ROOT = ROOT / ".state/outputs/chat-evaluations"
FINALIZATION_DIR = SOURCE_ROOT / "f2-9-stage-2-finalization"
ORIGINAL_DIR = SOURCE_ROOT / "f2-9-stage-2"
CONTINUATION_DIR = SOURCE_ROOT / "f2-9-stage-2-continuation"
RECOVERY_DIR = SOURCE_ROOT / "f2-9-stage-2-recovery-20261010"
LOW_RUN_ID = "f22-s2-gpt-6-1-sol-low-proposed-r1-cont-4894e8e275ac0ec2"
SOURCE_CONTINUATION_ID = "4894e8e275ac0ec2"
FINALIZATION_ID = "f2-9-stage2-final-20261010"
SOURCE_PATHS = {
    "original_ledger": ORIGINAL_DIR / "campaign.json",
    "original_report": ORIGINAL_DIR
    / "f22-s2-gpt-6-luna-medium-proposed-r1/chat-eval-20261010T072010745621Z.json",
    "owner_evidence": ORIGINAL_DIR / "privateowner-usage-confirmation-20261010.json",
    "continuation_plan": CONTINUATION_DIR / "continuation_plan.json",
    "continuation_ledger": CONTINUATION_DIR / "campaign.json",
    "closed_report_luna_medium": CONTINUATION_DIR
    / "f22-s2-gpt-6-luna-medium-proposed-r1-cont-4894e8e275ac0ec2/chat-eval-20261010T144034373073Z.json",
    "closed_report_luna_max": CONTINUATION_DIR
    / "f22-s2-gpt-6-luna-max-proposed-r1-cont-4894e8e275ac0ec2/chat-eval-20261010T144342509767Z.json",
    "sol_low_progress": CONTINUATION_DIR / f"{LOW_RUN_ID}/chat-eval-20261010T145434529289Z.progress.json",
    "terminal_recovery": RECOVERY_DIR / "terminal-recovery.json",
}
APPROVED_SOURCE_SHA256 = {
    "original_ledger": "fb6a661a8635b8e139951a541ee549ba7f3b35dfde611ebfc73e31eb5fad5140",
    "original_report": "0305ac40cc52e72371a1ed3b3334624c6261ed4be99adcfd9518727265913002",
    "owner_evidence": "a042789788649f22e9bf213d14a274fc9e117fcd825b8ce6cfd0221007c4446c",
    "continuation_plan": "33c7167c21998d0773329104b74a1d6c1b1f697cb3e411d88b31f2cf21be89af",
    "continuation_ledger": "7cc1c0408f26ed3307ff3b0ad3de13d7984ff52a2837115d3c6662fc4742f0e3",
    "closed_report_luna_medium": "98be1fa45a1407e35fa368e62090b111139e8a7e5619352fe35a44c35f1108ac",
    "closed_report_luna_max": "1d090a49966876cf3fe9b0f847e079c6b0b72da1ef3f19d73d76fa8c19bd51ca",
    "sol_low_progress": "f7a085c2d56ca79b8a8d52402392c9f10dae62e388e1437f941759fd9fe20821",
    "terminal_recovery": "74709aadfb6c255726ebaa6a5f32dafd868abc9d640f489861ed672fa04bf1d6",
}
EXPECTED_ORIGINAL_EXECUTION = "73db4d1c638e0c208feae433642e652485f5dfe6"
EXPECTED_CONTINUATION_EXECUTION = "8f671846f819db57dd0a96d70074d4d568551100"
ORIGINAL_KNOWN_COST_USD = 0.05460125
CLOSED_CONTINUATION_COST_USD = 0.141395625
SOL_LOW_PROGRESS_COST_USD = 1.72828


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _reject_source_symlinks(paths: dict[str, Path]) -> None:
    for label, path in paths.items():
        absolute = _lexical(path)
        current = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"La ruta fuente atraviesa un symlink: {label}")


def _validate_output_paths(args: argparse.Namespace) -> None:
    # Check path relationships without resolving or opening any source bytes.
    source_lexical = [_lexical(path) for path in args.source_paths.values()]
    output_lexical = [
        _lexical(args.output_dir),
        _lexical(args.campaign_state),
        _lexical(args.plan_path),
        _lexical(args.derived_report),
    ]
    if len(set(output_lexical[1:])) != 3:
        raise ValueError("Ledger, plan y reporte requieren destinos distintos")
    if any(_paths_overlap(output, source) for output in output_lexical for source in source_lexical):
        raise ValueError("La carpeta y los destinos privados no pueden solaparse con fuentes originales")
    leaf_paths = output_lexical[1:]
    if any(_paths_overlap(left, right) for i, left in enumerate(leaf_paths) for right in leaf_paths[i + 1 :]):
        raise ValueError("Ledger, plan y reporte requieren rutas separadas")

    args.output_dir = _require_private_destination(args.output_dir, label="output-dir")
    args.campaign_state = _require_private_destination(args.campaign_state, label="campaign-state")
    args.plan_path = _require_private_destination(args.plan_path, label="plan-path")
    args.derived_report = _require_private_destination(args.derived_report, label="derived-report")
    if args.output_dir != FINALIZATION_DIR.resolve() or output_lexical[0] != _lexical(FINALIZATION_DIR):
        raise ValueError("La salida solo puede usar la carpeta privada dedicada de finalización")
    if any(
        path.parent != args.output_dir for path in (args.campaign_state, args.plan_path, args.derived_report)
    ):
        raise ValueError("Ledger, plan y reporte deben ser archivos directos de la carpeta dedicada")
    source_paths = {path.resolve() for path in args.source_paths.values()}
    outputs = {args.campaign_state, args.plan_path, args.derived_report}
    if len(outputs) != 3 or outputs & source_paths:
        raise ValueError("Una salida privada coincide con una fuente de solo lectura")
    if any(
        _paths_overlap(output, source)
        for output in outputs | {args.output_dir}
        for source in source_paths
    ):
        raise ValueError("La carpeta y los destinos privados no pueden solaparse con fuentes originales")
    _validate_destination_relationships(args.output_dir, args.campaign_state, args.plan_path, source_paths)


def _build_run(
    base_run: dict[str, Any],
    case_ids: list[str],
    cases: list[dict[str, Any]],
    execution_commit: str,
    continuation_plan_sha256: str,
    prepared_run: dict[str, Any],
) -> dict[str, Any]:
    identity = json.loads(json.dumps(base_run["identity"]))
    run_id = base_run["run_id"].split("-cont-")[0] + f"-final-{FINALIZATION_ID}"
    identity.update(
        {
            "run_id": run_id,
            "case_ids_hash": _digest(case_ids),
            "case_fixture_hash": _digest(cases),
            "execution_commit": execution_commit,
            "finalization": {
                "continuation_plan_sha256": continuation_plan_sha256,
                "source_continuation_run_id": base_run["run_id"],
                "source_identity_hash": base_run["identity_hash"],
                "finalization_id": FINALIZATION_ID,
            },
        }
    )
    return {
        **identity,
        "run_id": run_id,
        "candidate": base_run["candidate"],
        "identity": identity,
        "identity_hash": _digest(identity),
        "case_ids": list(case_ids),
        "case_count": len(case_ids),
        "user_message_count": len(case_ids),
        "prompt": prepared_run["prompt"],
        "text_verbosity": prepared_run["text_verbosity"],
        "limits": prepared_run["limits"],
    }


def prepare_finalization(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], Path, dict[str, Any], dict[str, Any]]:
    # All private source bytes are pinned before JSON parsing, shared preflight, or mkdir.
    _validate_output_paths(args)
    _reject_source_symlinks(args.source_paths)
    raw = read_pinned_sources(args.source_paths, APPROVED_SOURCE_SHA256)
    source = validate_sources(
        raw,
        approved_source_sha256=APPROVED_SOURCE_SHA256,
        expected_original_execution=EXPECTED_ORIGINAL_EXECUTION,
        expected_continuation_execution=EXPECTED_CONTINUATION_EXECUTION,
        original_known_cost_usd=ORIGINAL_KNOWN_COST_USD,
        closed_continuation_cost_usd=CLOSED_CONTINUATION_COST_USD,
        sol_low_progress_cost_usd=SOL_LOW_PROGRESS_COST_USD,
        low_run_id=LOW_RUN_ID,
        source_continuation_id=SOURCE_CONTINUATION_ID,
        source_paths=args.source_paths,
    )
    base_plan, planned_runs, cases, snapshot_root, catalog, fixture = prepare(args, create_destinations=False)
    continuation_plan = source["continuation_plan"]
    continuation_identity = continuation_plan["continuation"]
    for key, plan_key in (
        ("fixture_sha256", "fixture_file_sha256"),
        ("prompt_sha256", "prompt_sha256"),
        ("context_sha256", "case_context_sha256"),
        ("tool_specs_sha256", "tool_specs_sha256"),
    ):
        if continuation_identity.get(key) != base_plan.get(plan_key):
            raise ValueError(f"Los insumos congelados difieren del plan interrumpido: {key}")
    by_candidate = {run["candidate"]: run for run in continuation_identity["runs"]}
    fixture_by_id = {case["id"]: case for case in cases}
    partition = final_case_partition(STAGE2_EXPECTED_CASE_IDS)
    replacement_ids = partition["replacement_case_ids"]
    recovered_id = partition["recovered_case_id_skipped"]
    never_attempted_ids = partition["never_attempted_case_ids"]
    final_low_ids = partition["sol_low_case_ids"]
    run_case_ids = {
        "gpt-6.1-sol@low": final_low_ids,
        "gpt-6.1-sol@medium": partition["sol_medium_case_ids"],
    }
    current_commit = _git_execution_commit()
    continuation_plan_sha = APPROVED_SOURCE_SHA256["continuation_plan"]
    prepared_by_candidate = {run["candidate"]: run for run in planned_runs}
    runs = [
        _build_run(
            by_candidate[candidate],
            ids,
            [fixture_by_id[cid] for cid in ids],
            current_commit,
            continuation_plan_sha,
            prepared_by_candidate[candidate],
        )
        for candidate, ids in run_case_ids.items()
    ]
    expected_input = source["_recovered_input_tokens"]
    expected_output = source["_recovered_output_tokens"]
    recovered_cost = conservative_usage_cost(expected_input, expected_output, catalog)
    carry = {
        "original_pilot_known_cost_usd": ORIGINAL_KNOWN_COST_USD,
        "closed_continuation_known_cost_usd": CLOSED_CONTINUATION_COST_USD,
        "sol_low_progress_aggregate_cost_usd": SOL_LOW_PROGRESS_COST_USD,
        "recovered_sol_low_case_conservative_cost_usd": recovered_cost,
        "recovered_case_input_tokens": expected_input,
        "recovered_case_output_tokens": expected_output,
        "recovered_case_cost_method": (
            "ChatConfig.usage_cost_usd with the pinned Sol cache-write input tariff"
        ),
        "original_failed_case_individual_cost_usd": None,
        "invoice_total_usd": None,
    }
    carry_total = sum(
        carry[key]
        for key in (
            "original_pilot_known_cost_usd",
            "closed_continuation_known_cost_usd",
            "sol_low_progress_aggregate_cost_usd",
            "recovered_sol_low_case_conservative_cost_usd",
        )
    )
    remaining = STAGE2_RESERVE_USD - carry_total
    if remaining <= 0:
        raise ValueError("El gasto estimado acumulado agotó la reserva autorizada")
    source_bytes_hashes = {name: _digest_bytes(content) for name, content in raw.items()}
    recovery_sha = source_bytes_hashes["terminal_recovery"]
    derived = derived_recovery_report(
        run_identity=source["_low_run"]["identity"],
        campaign_identity_hash=source["_continuation_campaign_hash"],
        answer=source["_recovered_answer"],
        input_tokens=expected_input,
        output_tokens=expected_output,
        recovery_sha256=recovery_sha,
        progress_sha256=source_bytes_hashes["sol_low_progress"],
        continuation_plan_sha256=continuation_plan_sha,
        answer_sha256=source["_answer_sha256"],
        recovery_case_id=recovered_id,
    )
    derived_bytes = _json_bytes(derived) + b"\n"
    # This is the first write and occurs only after every trusted source is pinned and validated.
    args.derived_report.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.derived_report.parent, 0o700)
    args.derived_report.write_bytes(derived_bytes)
    os.chmod(args.derived_report, 0o600)
    run_records = [
        {key: run[key] for key in ("run_id", "candidate", "identity", "identity_hash", "case_ids")}
        | {"source_run_id": run["identity"]["finalization"]["source_continuation_run_id"], "report_paths": []}
        for run in runs
    ]
    plan = {
        "schema_version": 1,
        "kind": "f2_9_stage2_finalization_plan",
        "mode": "offline-preflight-only",
        "provider_calls_now": 0,
        "source": {
            "campaign_identity_hash": source["original_ledger"]["identity_hash"],
            "ledger_sha256": source_bytes_hashes["original_ledger"],
            "report_sha256": source_bytes_hashes["original_report"],
            "owner_evidence_sha256": source_bytes_hashes["owner_evidence"],
            "execution_commit": EXPECTED_ORIGINAL_EXECUTION,
            "paths": {
                name: str(path.resolve())
                for name, path in args.source_paths.items()
                if name in {"original_ledger", "original_report", "owner_evidence"}
            },
        },
        "interrupted_continuation": {
            "continuation_plan_sha256": source_bytes_hashes["continuation_plan"],
            "continuation_ledger_sha256": source_bytes_hashes["continuation_ledger"],
            "execution_commit": EXPECTED_CONTINUATION_EXECUTION,
            "plan_path": str(args.source_paths["continuation_plan"].resolve()),
            "ledger_path": str(args.source_paths["continuation_ledger"].resolve()),
            "closed_reports": [
                {
                    "path": str(args.source_paths[name].resolve()),
                    "sha256": source_bytes_hashes[name],
                    "candidate": candidate,
                }
                for name, candidate in (
                    ("closed_report_luna_medium", "gpt-6-luna@medium"),
                    ("closed_report_luna_max", "gpt-6-luna@max"),
                )
            ],
            "progress_path": str(args.source_paths["sol_low_progress"].resolve()),
            "progress_sha256": source_bytes_hashes["sol_low_progress"],
            "source_run_identity_hash": source["_source_low_run"]["identity_hash"],
            "continuation_run_identity_hash": source["_low_run"]["identity_hash"],
            "answer_sha256": source["_answer_sha256"],
            "progress_case_count": 13,
            "progress_cost_is_aggregate": True,
        },
        "recovery": {
            "path": str(args.source_paths["terminal_recovery"].resolve()),
            "sha256": recovery_sha,
            "status": "GET_recovered_remote_completed_idle",
            "case_id": recovered_id,
            "candidate": "gpt-6.1-sol@low",
            "continuation_plan_sha256": source_bytes_hashes["continuation_plan"],
            "progress_sha256": source_bytes_hashes["sol_low_progress"],
            "source_run_identity_hash": source["_source_low_run"]["identity_hash"],
            "continuation_run_identity_hash": source["_low_run"]["identity_hash"],
            "answer_sha256": source["_answer_sha256"],
            "usage_complete": True,
            "input_tokens": expected_input,
            "output_tokens": expected_output,
            "latency_ms": None,
            "tool_trace": "unavailable",
            "auto_graded": False,
            "auto_approved": False,
            "tool_calls_inferred": False,
            "report_path": str(args.derived_report.resolve()),
            "report_sha256": _digest_bytes(derived_bytes),
        },
        "billing_reconciliation": {
            "authorized_reserve_usd": STAGE2_RESERVE_USD,
            "carry_components": carry,
            "carry_total_estimate_usd": carry_total,
            "remaining_budget_usd": remaining,
            "invoice_total_usd": None,
            "usage_rule": (
                "Conservative cache-write input tariff; original failed-call cost remains unknown"
            ),
        },
        "finalization": {
            "execution_commit": current_commit,
            "continuation_id": FINALIZATION_ID,
            "plan_path": str(args.plan_path.resolve()),
            "ledger_path": str(args.campaign_state.resolve()),
            "output_dir": str(args.output_dir.resolve()),
            "runs": run_records,
            "derived_reports": {
                "sol_low_recovery": {
                    "path": str(args.derived_report.resolve()),
                    "sha256": _digest_bytes(derived_bytes),
                    "candidate": "gpt-6.1-sol@low",
                    "identity": source["_low_run"]["identity"],
                    "identity_hash": source["_low_run"]["identity_hash"],
                    "case_id": recovered_id,
                    "source_run_identity_hash": source["_source_low_run"]["identity_hash"],
                    "recovery_sha256": recovery_sha,
                    "progress_sha256": source_bytes_hashes["sol_low_progress"],
                    "human_review_required": True,
                }
            },
            "replacement_case_ids": replacement_ids,
            "never_attempted_case_ids": never_attempted_ids,
            "recovered_case_id_skipped": recovered_id,
            "excluded_original_failure": {"candidate": "gpt-6-luna@medium", "case_id": "en_am_rask"},
            "new_provider_request_count": len(replacement_ids)
            + len(never_attempted_ids)
            + len(STAGE2_EXPECTED_CASE_IDS),
            "response_count_ceiling_if_complete": 59,
            "max_reviewable_candidates": 59,
        },
        "source_sha256": source_bytes_hashes,
    }
    return (
        plan,
        runs,
        [fixture_by_id[cid] for run in runs for cid in run["case_ids"]],
        snapshot_root,
        catalog,
        fixture,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalización F2.9 stage 2 sin replay automático")
    parser.add_argument("--run", action="store_true", help="iniciar el lote final autorizado")
    parser.add_argument("--opt-in", action="store_true", help="habilitar explícitamente llamadas live")
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/chat_evals/f2_9_stage2.json")
    parser.add_argument("--prompt-proposed", type=Path, default=DEFAULT_STAGE2_PROMPT_PATH)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "site")
    out = ROOT / ".state/outputs/chat-evaluations/f2-9-stage-2-finalization"
    parser.add_argument("--output-dir", type=Path, default=out)
    parser.add_argument("--campaign-state", type=Path, default=out / "campaign.json")
    parser.add_argument("--plan-path", type=Path, default=out / "finalization_plan.json")
    parser.add_argument("--derived-report", type=Path, default=out / "sol-low-recovered-case.json")
    parser.add_argument("--text-verbosity", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--max-message-chars", type=int, default=8_000)
    parser.add_argument("--max-tool-result-bytes", type=int, default=16_000)
    parser.add_argument("--max-turn-seconds", type=int, default=180)
    for name, path in SOURCE_PATHS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=path)
    args = parser.parse_args(argv)
    args.source_paths = {name: getattr(args, name) for name in SOURCE_PATHS}
    if args.run != args.opt_in:
        parser.error("live requiere --run y --opt-in juntos; por omisión solo preflight offline")
    try:
        plan, runs, cases, snapshot_root, catalog, fixture = prepare_finalization(args)
    except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.run:
        if not os.environ.get("OPENAI_API_KEY"):
            parser.error("La corrida live requiere OPENAI_API_KEY; no se inició el proveedor")
        dirty = _dirty_execution_inputs()
        if dirty:
            parser.error("Live bloqueado: insumos sin commit: " + dirty)
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
            resume=False,
        )
        plan["mode"] = "live-campaign"
        plan["provider_calls_now"] = None
        plan["live_result"] = result
        by_run = {row.get("run_id"): row for row in result.get("run_summaries", [])}
        for slot in plan["finalization"]["runs"]:
            summary = by_run.get(slot["run_id"], {})
            slot["report_paths"] = [summary["report_path"]] if summary.get("report_path") else []
        _private_write(args.plan_path.resolve(), plan)
        print(json.dumps({"plan": plan, "campaign": result}, ensure_ascii=False, indent=2, default=str))
        return 0
    plan["live_execution"] = "requires_explicit_run_and_opt_in_after_root_go"
    _private_write(args.plan_path.resolve(), plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

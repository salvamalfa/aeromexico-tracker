"""Offline preflight and explicitly gated runner for F2.9 stage 2.

The default command only prints a safe plan. A paid run additionally requires
the explicit ``--run --opt-in`` flags; the default never crosses the provider boundary.
"""

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
DEFAULT_STAGE2_PROMPT_PATH = ROOT / "docs/chat/revision-fase-2/F2.1-prompt-aprobado.md"
sys.path.insert(0, str(ROOT))

from src.conversational_analytics.data.snapshot import Snapshot  # noqa: E402
from src.conversational_analytics.evaluation_campaign import (  # noqa: E402
    CAMPAIGN_CANDIDATES,
    STAGE2_BUDGET_PATH,
    STAGE2_EXPECTED_CASE_IDS,
    STAGE2_FIXTURE_PATH,
    STAGE2_MAX_TOOL_CALLS,
    STAGE2_RESERVE_USD,
    build_campaign_runs,
    effective_stage2_prompt,
    sha256_file,
    validate_stage2_plan,
)
from src.conversational_analytics.service import validate_context  # noqa: E402
from src.conversational_analytics.tools.registry import ToolRegistry  # noqa: E402

PreparedCampaign = tuple[
    dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], Path, dict[str, Any], dict[str, Any]
]
EXECUTION_INPUT_PATHS = (
    "src/conversational_analytics/",
    "scripts/chat/",
    "config/chat/",
    "tests/fixtures/chat_evals/f2_9_stage2.json",
    "docs/chat/revision-fase-2/F2.1-prompt-aprobado.md",
    "docs/chat/revision-fase-2/F2.9-etapa-2-presupuesto.json",
)
APPROVED_STAGE2_FIXTURE_SHA256 = (
    "824db2fb0bd1f1e58c08a16c234e8fe4d9d280f783e9010ded5ad8912b64092e"
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON debe ser objeto: {path}")
    return payload


def _fixture_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {str(case.get("id")): case for case in payload["cases"]}
    if len(by_id) != len(payload["cases"]):
        raise ValueError("Fixture stage2 tiene IDs duplicados")
    missing = [case_id for case_id in STAGE2_EXPECTED_CASE_IDS if case_id not in by_id]
    if missing:
        raise ValueError(f"Fixture stage2 incompleto; faltan IDs congelados: {', '.join(missing)}")
    return [by_id[case_id] for case_id in STAGE2_EXPECTED_CASE_IDS]


def _read_approved_stage2_fixture(path: Path) -> tuple[dict[str, Any], str]:
    """Read once, pin the exact approved bytes, then parse that same buffer."""
    fixture_bytes = path.read_bytes()
    fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
    if fixture_sha256 != APPROVED_STAGE2_FIXTURE_SHA256:
        raise ValueError(
            "El fixture stage2 no coincide byte por byte con el fixture aprobado "
            f"(SHA-256 recibido {fixture_sha256})"
        )
    fixture = json.loads(fixture_bytes.decode("utf-8"))
    if (
        not isinstance(fixture, dict)
        or fixture.get("schema_version") != 1
        or not isinstance(fixture.get("cases"), list)
    ):
        raise ValueError("Fixture stage2 aprobado inválido")
    return fixture, fixture_sha256


def _verify_private_destination(path: Path, *, directory: bool, create: bool = True) -> None:
    absolute = path.resolve()
    state_root = (ROOT / ".state").resolve()
    if state_root not in absolute.parents:
        raise ValueError("Los reportes y el ledger deben quedar dentro de .state/ ignorado")
    if create and directory:
        absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(absolute, 0o700)
    elif create:
        absolute.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(absolute.parent, 0o700)
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(absolute)], cwd=ROOT, check=False
    ).returncode == 0
    if not ignored:
        raise ValueError(f"Destino de campaña no ignorado por Git: {absolute}")


def _git_execution_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    commit = result.stdout.strip()
    if len(commit) != 40:
        raise ValueError("No se pudo fijar el commit del código ejecutado")
    return commit


def _dirty_execution_inputs() -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *EXECUTION_INPUT_PATHS],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def prepare(args: argparse.Namespace, *, create_destinations: bool = True) -> PreparedCampaign:
    fixture_path = args.fixture.resolve()
    fixture, fixture_sha256 = _read_approved_stage2_fixture(fixture_path)
    budget_path = ROOT / STAGE2_BUDGET_PATH
    budget = _load_json(budget_path)
    cases = _fixture_cases(fixture)
    for case in cases:
        try:
            validate_context(case.get("context", {}))
        except ValueError as exc:
            raise ValueError(f"{case['id']}: contexto no válido para el contrato del chat") from exc
    prompt_path = args.prompt_proposed.resolve()
    prompt = effective_stage2_prompt(prompt_path.read_text(encoding="utf-8"))
    snapshot = Snapshot(args.snapshot.resolve())
    catalog = _load_json(ROOT / "config/chat/models.json")
    catalog_sha256 = sha256_file(ROOT / "config/chat/models.json")
    if budget.get("tariff_catalog", {}).get("sha256") != catalog_sha256:
        raise ValueError("El catálogo de tarifas cambió desde el presupuesto stage2 aprobado")
    candidates = {
        name: {
            "model": definition["model"],
            "reasoning_effort": definition["reasoning_effort"],
        }
        for name, definition in CAMPAIGN_CANDIDATES.items()
    }
    for name, definition in candidates.items():
        model = catalog.get("models", {}).get(definition["model"], {})
        if definition["reasoning_effort"] not in model.get("reasoning_efforts", []):
            raise ValueError(f"El catálogo no admite el esfuerzo configurado para {name}")
    validation = validate_stage2_plan(
        config=budget,
        fixture=fixture,
        cases=cases,
        candidates=candidates,
        snapshot_data_version=snapshot.version,
        snapshot_semantic_version=snapshot.semantic_version,
        prompt=prompt,
        api_key_present=bool(os.environ.get("OPENAI_API_KEY")),
    )
    registry = ToolRegistry(snapshot)
    execution_commit = _git_execution_commit()
    runtime_limits = {
        "max_tool_calls": STAGE2_MAX_TOOL_CALLS,
        "max_message_chars": args.max_message_chars,
        "max_tool_result_bytes": args.max_tool_result_bytes,
        "max_turn_seconds": args.max_turn_seconds,
    }
    runs = build_campaign_runs(
        2,
        cases,
        data_version=snapshot.version,
        semantic_version=snapshot.semantic_version,
        prompts={"proposed": prompt},
        tool_specs=registry.tool_specs(),
        limits=runtime_limits,
        text_verbosity=args.text_verbosity,
        source_fingerprint=fixture_sha256,
        execution_commit=execution_commit,
    )
    output_dir = args.output_dir.resolve()
    ledger_path = args.campaign_state.resolve()
    _verify_private_destination(output_dir, directory=True, create=create_destinations)
    _verify_private_destination(ledger_path, directory=False, create=create_destinations)
    validation.update(
        {
            "budget_config_sha256": hashlib.sha256(budget_path.read_bytes()).hexdigest(),
            "model_catalog_sha256": catalog_sha256,
            "fixture_file_sha256": fixture_sha256,
            "execution_commit": execution_commit,
            "snapshot_manifest_sha256": hashlib.sha256(
                (snapshot.root / "publication_manifest.json").read_bytes()
            ).hexdigest(),
            "effective_prompt_source": (
                str(prompt_path.relative_to(ROOT)) if ROOT in prompt_path.parents else "external"
            ),
            "fixture_source": (
                str(fixture_path.relative_to(ROOT)) if ROOT in fixture_path.parents else "external"
            ),
            "output_dir": str(output_dir),
            "campaign_ledger": str(ledger_path),
            "candidate_run_ids": [run["run_id"] for run in runs],
            "tool_specs_sha256": runs[0]["tool_spec_hash"],
            "runtime_limits": runtime_limits,
            "tariffs_usd_per_million": {
                name: {
                    "input": catalog["models"][definition["model"]]["input_usd_per_million"],
                    "output": catalog["models"][definition["model"]]["output_usd_per_million"],
                }
                for name, definition in candidates.items()
            },
            "private_output_permissions": "directory 0700; files 0600 via atomic writer",
            "git_ignored_destinations": True,
            "resume_requires_exact_identity": True,
            "campaign_ledger_scope": "stage 2 only; does not import stage-1 spend",
        }
    )
    return validation, runs, cases, snapshot.root, catalog, fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight aislado para F2.9 etapa 2")
    parser.add_argument(
        "--run", action="store_true", help="ejecutar la campaña live autorizada para esta etapa"
    )
    parser.add_argument(
        "--opt-in", action="store_true",
        help="habilitar explícitamente las llamadas al proveedor en esta invocación",
    )
    parser.add_argument("--fixture", type=Path, default=ROOT / STAGE2_FIXTURE_PATH)
    parser.add_argument("--prompt-proposed", type=Path, default=DEFAULT_STAGE2_PROMPT_PATH)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "site")
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / ".state/outputs/chat-evaluations/f2-9-stage-2",
    )
    parser.add_argument(
        "--campaign-state", type=Path,
        default=ROOT / ".state/outputs/chat-evaluations/f2-9-stage-2/campaign.json",
    )
    parser.add_argument("--text-verbosity", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--max-message-chars", type=int, default=8_000)
    parser.add_argument("--max-tool-result-bytes", type=int, default=16_000)
    parser.add_argument("--max-turn-seconds", type=int, default=180)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.run != args.opt_in:
        parser.error("live requiere --run y --opt-in juntos; el preflight por omisión no hace llamadas")
    try:
        plan, runs, cases, snapshot_root, catalog, fixture = prepare(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if not args.run:
        plan["mode"] = "offline-preflight-only"
        plan["provider_calls_now"] = 0
        plan["live_execution"] = "requires_both_explicit_cli_flags_after_integration_checks"
        plan["planned_candidate_responses"] = len(cases) * len(runs)
        plan["budget_usd_operational_stop"] = STAGE2_RESERVE_USD
        plan["resume_requested"] = bool(args.resume)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if not plan["api_key_present"]:
        parser.error("OPENAI_API_KEY no está presente; no se inició el proveedor")
    dirty_inputs = _dirty_execution_inputs()
    if dirty_inputs:
        parser.error(
            "live bloqueado porque los insumos de ejecución tienen cambios sin commit: "
            + dirty_inputs
        )

    from src.conversational_analytics.evaluation_live_campaign import run_campaign

    prices = {
        name: (
            float(catalog["models"][definition["model"]]["input_usd_per_million"]),
            float(catalog["models"][definition["model"]]["output_usd_per_million"]),
        )
        for name, definition in CAMPAIGN_CANDIDATES.items()
    }
    result = run_campaign(
        # The owner confirmed a separately funded stage-2 reserve. The ledger
        # starts at zero and deliberately does not import stage-1 usage.
        runs=runs,
        cases=cases,
        budget_usd=STAGE2_RESERVE_USD,
        snapshot_root=snapshot_root,
        prices=prices,
        expected_versions=fixture["expected_versions"],
        state_path=args.campaign_state.resolve(),
        output_dir=args.output_dir.resolve(),
        resume=args.resume,
    )
    plan["live_execution_started"] = True
    print(json.dumps({"preflight": plan, "campaign": result}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

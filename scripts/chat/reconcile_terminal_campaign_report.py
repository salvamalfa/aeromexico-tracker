"""Offline-only proof/apply for an ended terminal F2.2 campaign report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _plan(state_path: Path, report_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from src.conversational_analytics.config import model_catalog
    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.evaluation import load_fixture, phase_cases
    from src.conversational_analytics.evaluation_campaign import (
        CAMPAIGN_CANDIDATES,
        build_campaign_runs,
        extract_proposed_prompt,
    )
    from src.conversational_analytics.providers._openai_helpers import SYSTEM_INSTRUCTIONS
    from src.conversational_analytics.tools.registry import ToolRegistry

    state = json.loads(state_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    identity = state.get("identity", {})
    report_identity = report.get("run_identity", {})
    if not isinstance(identity.get("runs"), list) or report_identity not in identity["runs"]:
        raise ValueError("El informe no pertenece a una corrida fijada en el checkpoint")
    if report_identity.get("stage") != 1:
        raise ValueError("Este reconciliador solo admite stage 1")
    safety = load_fixture(ROOT / "tests/fixtures/chat_evals/safety_current.json")["cases"]
    business_fixture = load_fixture(ROOT / "tests/fixtures/chat_evals/business_proposed.json")
    approval = business_fixture.get("owner_approval", {})
    if (
        business_fixture.get("status") != "OWNER_APPROVED"
        or 1 not in approval.get("approved_live_stages", [])
        or business_fixture.get("campaign_authorization", {}).get("stage_1_reserve_usd") != 3.0
        or business_fixture.get("campaign_authorization", {}).get("stage_1_only") is not True
    ):
        raise ValueError("El fixture ya no refleja el alcance aprobado para stage 1 y US$3")
    business = business_fixture["cases"]
    cases = phase_cases(business, safety, 1)
    snapshot_root = Path(str(identity.get("snapshot_root", "site")))
    if not snapshot_root.is_absolute():
        snapshot_root = ROOT / snapshot_root
    snapshot = Snapshot(snapshot_root)
    if (
        snapshot.version != report_identity.get("data_version")
        or snapshot.semantic_version != report_identity.get("semantic_version")
        or identity.get("expected_versions")
        != {"data_version": snapshot.version, "semantic_version": snapshot.semantic_version}
    ):
        raise ValueError("El snapshot local y las versiones del checkpoint/informe no coinciden")
    registry = ToolRegistry(snapshot)
    prompt_path = ROOT / str(approval["prompt_source_path"])
    if not prompt_path.exists():
        prompt_path = ROOT / "docs/chat/revision-fase-2/F2.1-prompt-aprobado.md"
    prompt_raw = prompt_path.read_bytes()
    if hashlib.sha256(prompt_raw).hexdigest() != approval.get("prompt_source_sha256"):
        raise ValueError("El prompt aprobado cambió desde el reporte de la aprobación")
    proposed = extract_proposed_prompt(prompt_raw.decode("utf-8"))
    if hashlib.sha256(proposed.encode("utf-8")).hexdigest() != approval.get("approved_prompt_content_sha256"):
        raise ValueError("El texto del prompt extraído ya no tiene el hash aprobado")
    prices_in_checkpoint = identity.get("prices")
    catalog = model_catalog()
    expected_prices = {
        candidate: [
            catalog[definition["model"]]["input_usd_per_million"],
            catalog[definition["model"]]["output_usd_per_million"],
        ]
        for candidate, definition in CAMPAIGN_CANDIDATES.items()
    }
    if prices_in_checkpoint != expected_prices or identity.get("budget_usd") != 3.0:
        raise ValueError(
            "El presupuesto o las tarifas del checkpoint ya no coinciden con la aprobación y catálogo"
        )
    limits = dict(report_identity["limits"])
    if limits != {
        "max_tool_calls": 16,
        "max_message_chars": 8000,
        "max_tool_result_bytes": 16000,
        "max_turn_seconds": 180,
    }:
        raise ValueError("Los límites del informe cambiaron respecto al runtime live aprobado")
    if report_identity.get("text_verbosity") != "medium":
        raise ValueError("La verbosidad del informe no coincide con la configuración fijada")
    runs = build_campaign_runs(
        1,
        cases,
        data_version=str(report_identity["data_version"]),
        semantic_version=str(report_identity["semantic_version"]),
        prompts={"current": SYSTEM_INSTRUCTIONS, "proposed": proposed},
        tool_specs=registry.tool_specs(),
        limits=limits,
        text_verbosity=str(report_identity["text_verbosity"]),
    )
    return runs, cases


def main() -> int:
    from src.conversational_analytics.evaluation_live_reconciliation import reconcile_terminal_report

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="Checkpoint privado de campaña")
    parser.add_argument("--report", required=True, type=Path, help="Informe privado terminado")
    parser.add_argument("--report-sha256", required=True, help="Hash SHA-256 esperado del informe exacto")
    parser.add_argument(
        "--apply", action="store_true", help="Aplicar solo al checkpoint tras validar toda la evidencia"
    )
    args = parser.parse_args()
    runs, cases = _plan(args.state, args.report)
    result = reconcile_terminal_report(
        state_path=args.state,
        report_path=args.report,
        expected_report_sha256=args.report_sha256,
        runs=runs,
        cases=cases,
        apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

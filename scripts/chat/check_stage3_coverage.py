#!/usr/bin/env python3
"""Derive F2.9 stage-3 tool coverage offline; live stays receipt-gated."""

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
TRUSTED_BUDGET_RECEIPT_SHA_ENV = "F29_STAGE3_BUDGET_RECEIPT_SHA256"
TRUSTED_CAPABILITY_RECEIPT_SHA_ENV = "F29_STAGE3_CAPABILITY_RECEIPT_SHA256"
sys.path.insert(0, str(ROOT))

from src.conversational_analytics.evaluation_stage3_coverage import (  # noqa: E402
    CAMPAIGN_CANDIDATE,
    derive_stage3_coverage,
    validate_receipt_scope,
)


def _read_receipt(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"El recibo debe ser un objeto JSON: {path}")
    return payload


def _write_output(path: Path | None, report: dict[str, Any]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path is None:
        print(encoded, end="")
        return
    absolute = path.resolve()
    state_root = (ROOT / ".state").resolve()
    if state_root not in absolute.parents:
        raise ValueError("El reporte stage3 debe guardarse dentro de .state/ ignorado")
    absolute.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(absolute.parent, 0o700)
    absolute.write_text(encoded, encoding="utf-8")
    os.chmod(absolute, 0o600)


def _dirty_execution_inputs() -> str:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "src/conversational_analytics/",
            "scripts/chat/",
            "config/chat/",
            "tests/fixtures/chat_evals/business_proposed.json",
            "docs/chat/revision-fase-2/F2.1-prompt-aprobado.md",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _bind_reserve(report: dict[str, Any], reserve: float) -> None:
    identity = report["campaign_identity"]
    identity["reserve_usd"] = reserve
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["campaign_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _blocked(
    reason: str, report: dict[str, Any], reserve: float, *, credentials_read: bool = False
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "f2_9_stage3_live_preflight",
        "mode": "preflight_blocked",
        "status": "blocked",
        "reason": reason,
        "campaign_sha256": report["campaign_sha256"],
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": reserve,
        "provider_calls": 0,
        "credentials_read": credentials_read,
        "trusted_receipt_sha256": report.get("trusted_receipt_sha256"),
        "coverage_summary": {
            "case_count": report["case_count"],
            "counts": report["counts"],
            "coverage_status": report["coverage_status"],
            "published_capabilities": report["published_capabilities"],
            "data_version": report["pins"]["data_version"],
            "semantic_version": report["pins"]["semantic_version"],
            "tool_specs_sha256": report["runtime_capabilities"]["tool_specs_sha256"],
            "prompt_content_sha256": report["pins"]["prompt_content_sha256"],
            "active_prompt_version": report["runtime_capabilities"]["active_prompt_version"],
            "required_prompt_version": report["runtime_capabilities"]["required_prompt_version"],
            "required_prompt_sha256": report["runtime_capabilities"]["required_prompt_sha256"],
            "prompt_compatible": report["runtime_capabilities"]["prompt_compatible"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "site")
    parser.add_argument(
        "--fixture", type=Path, default=ROOT / "tests/fixtures/chat_evals/business_proposed.json"
    )
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "config/chat/f2_9_business_stage3_partial.json"
    )
    parser.add_argument("--output", type=Path, help="reporte privado opcional bajo .state/")
    parser.add_argument("--run", action="store_true", help="solicitar ejecución live (siempre receipt-gated)")
    parser.add_argument("--opt-in", action="store_true", help="consentimiento explícito de esta invocación")
    parser.add_argument(
        "--resume", action="store_true", help="reanudar solo con identidad y gasto reconciliados"
    )
    parser.add_argument("--budget-receipt", type=Path)
    parser.add_argument("--capability-receipt", type=Path)
    args = parser.parse_args(argv)
    if args.run != args.opt_in:
        parser.error("live requiere --run y --opt-in juntos; el default solo consulta herramientas offline")

    try:
        report = derive_stage3_coverage(
            snapshot_root=args.snapshot.resolve(),
            fixture_path=args.fixture.resolve(),
            profile_path=args.profile.resolve(),
        )
        from scripts.chat.prepare_final_campaign import build_plan

        cost_plan = build_plan(profile_path=args.profile.resolve(), coverage_report=report)
        reserve = float(cost_plan["projection"]["proposed_reserve_usd"])
        _bind_reserve(report, reserve)
        report["budget_plan"] = cost_plan["projection"]
        if not args.run:
            report["mode"] = "offline_tool_coverage_only"
            _write_output(args.output, report)
            return 0

        # Missing receipts and scope mismatches are handled before checking the
        # environment, importing a provider, making directories, or creating a ledger.
        if args.budget_receipt is None or args.capability_receipt is None:
            result = _blocked("missing_exact_scope_receipts", report, reserve)
            _write_output(args.output, result)
            return 2
        budget_receipt_sha = os.environ.get(TRUSTED_BUDGET_RECEIPT_SHA_ENV)
        capability_receipt_sha = os.environ.get(TRUSTED_CAPABILITY_RECEIPT_SHA_ENV)
        if not budget_receipt_sha or not capability_receipt_sha:
            result = _blocked("missing_external_receipt_sha256_pins", report, reserve)
            _write_output(args.output, result)
            return 2
        budget_receipt = _read_receipt(args.budget_receipt)
        capability_receipt = _read_receipt(args.capability_receipt)
        valid, reason = validate_receipt_scope(
            budget_receipt,
            capability_receipt,
            report,
            reserve,
            budget_receipt_sha256=budget_receipt_sha,
            capability_receipt_sha256=capability_receipt_sha,
        )
        if not valid:
            _write_output(args.output, _blocked(reason, report, reserve))
            return 2
        trusted_receipt_sha256 = {
            "budget": budget_receipt_sha,
            "capabilities": capability_receipt_sha,
        }
        report["trusted_receipt_sha256"] = trusted_receipt_sha256

        if capability_receipt.get("stage3_live_authorized") is not True:
            _write_output(
                args.output, _blocked("capabilities_receipt_stage3_authorization_missing", report, reserve)
            )
            return 2
        projection = report["published_capabilities"]["business_metric_projection"]
        evidence_index = report["published_capabilities"]["report_evidence_index"]
        if projection.get("status") != "published" or evidence_index.get("status") != "published":
            _write_output(args.output, _blocked("required_published_capability_missing", report, reserve))
            return 2
        if report["runtime_capabilities"].get("prompt_compatible") is not True:
            _write_output(args.output, _blocked("stage3_prompt_not_activated", report, reserve))
            return 2
        if report["runtime_capabilities"]["candidate"] != CAMPAIGN_CANDIDATE:
            _write_output(args.output, _blocked("candidate_scope_mismatch", report, reserve))
            return 2
        dirty_inputs = _dirty_execution_inputs()
        if dirty_inputs:
            _write_output(args.output, _blocked("execution_inputs_not_committed", report, reserve))
            return 2
        if "OPENAI_API_KEY" not in os.environ:
            _write_output(
                args.output,
                _blocked("provider_credential_missing", report, reserve, credentials_read=True),
            )
            return 2

        # Valid receipts and owner stage approval are not present in the current
        # fixture/profile, so this path is intentionally not exercised here.
        # The delegated execution boundary is the same campaign runner used by
        # evaluate_campaign; it is reached only after all local gates above.
        from dataclasses import replace

        from src.conversational_analytics.config import ChatConfig
        from src.conversational_analytics.data.snapshot import Snapshot
        from src.conversational_analytics.evaluation_live_campaign import run_campaign
        from src.conversational_analytics.providers._openai_prompt import (
            effective_prompt_sha256,
            effective_prompt_version,
            load_active_system_instructions,
        )

        snapshot = Snapshot(args.snapshot.resolve())
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        _runtime_config = ChatConfig.from_env()
        _runtime_config = replace(
            _runtime_config,
            max_message_chars=report["campaign_identity"]["limits"]["max_message_chars"],
            max_tool_calls=report["campaign_identity"]["limits"]["max_tool_calls"],
            max_tool_result_bytes=report["campaign_identity"]["limits"]["max_tool_result_bytes"],
            max_turn_seconds=report["campaign_identity"]["limits"]["max_turn_seconds"],
        )
        from src.conversational_analytics.tools.registry import ToolRegistry

        _runtime_specs = ToolRegistry(snapshot, _runtime_config).tool_specs()
        _runtime_schema_sha = hashlib.sha256(
            json.dumps(_runtime_specs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        if (
            _runtime_schema_sha != report["runtime_capabilities"]["tool_specs_sha256"]
            or [spec["name"] for spec in _runtime_specs] != report["runtime_capabilities"]["tool_names"]
        ):
            _write_output(args.output, _blocked("runtime_tool_capabilities_mismatch", report, reserve))
            return 2
        active_prompt = load_active_system_instructions()
        if (
            effective_prompt_sha256() != report["runtime_capabilities"]["required_prompt_sha256"]
            or effective_prompt_version() != report["runtime_capabilities"]["active_prompt_version"]
        ):
            _write_output(args.output, _blocked("active_prompt_changed_after_preflight", report, reserve))
            return 2
        from src.conversational_analytics.evaluation_stage3_cases import current_stage3_cases

        cases = current_stage3_cases(fixture["cases"], report)
        candidate_id = CAMPAIGN_CANDIDATE
        run_id = f"f29-stage3-sol-low-{report['runtime_capabilities']['required_prompt_version']}"
        identity = {
            **report["campaign_identity"],
            "coverage_campaign_sha256": report["campaign_sha256"],
            "trusted_receipt_sha256": trusted_receipt_sha256,
            "run_id": run_id,
            "case_ids": [case["id"] for case in cases],
            "case_ids_sha256": hashlib.sha256(
                json.dumps([case["id"] for case in cases], separators=(",", ":")).encode()
            ).hexdigest(),
        }
        identity_hash = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        run = {
            **identity,
            "run_id": run_id,
            "candidate": candidate_id,
            "identity": identity,
            "identity_hash": identity_hash,
            "prompt": active_prompt,
            "case_ids": [case["id"] for case in cases],
            "limits": dict(report["campaign_identity"]["limits"]),
            "text_verbosity": "medium",
        }
        catalog = json.loads((ROOT / "config/chat/models.json").read_text(encoding="utf-8"))["models"]
        model_rates = catalog["gpt-6.1-sol"]
        campaign = run_campaign(
            runs=[run],
            cases=cases,
            budget_usd=reserve,
            snapshot_root=snapshot.root,
            prices={
                candidate_id: (
                    float(model_rates["cache_write_usd_per_million"]),
                    float(model_rates["output_usd_per_million"]),
                )
            },
            expected_versions={
                "data_version": snapshot.version,
                "semantic_version": snapshot.semantic_version,
            },
            state_path=ROOT / ".state/outputs/chat-evaluations/f2-9-stage-3/campaign.json",
            output_dir=ROOT / ".state/outputs/chat-evaluations/f2-9-stage-3/runs",
            continue_after_known_provider_errors=True,
            reservation_assumption_override=cost_plan["reservation_assumption_override"],
            resume=args.resume,
            runtime_config=_runtime_config,
        )
        _write_output(
            args.output,
            {
                "mode": "live-campaign",
                "campaign_sha256": report["campaign_sha256"],
                "trusted_receipt_sha256": trusted_receipt_sha256,
                "campaign": campaign,
            },
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

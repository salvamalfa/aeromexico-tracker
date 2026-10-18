"""Offline, tool-backed coverage derivation for F2.9 stage 3.

This module does not grade model responses and does not use the old fixture's
expected statuses as evidence. It runs deterministic public tools against the
verified snapshot, derives fresh numeric/source expectations, and records the
capability or publication gates that prevent an answer.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .data.snapshot import Snapshot
from .evaluation_stage3_scenarios import _derived_calculations, _scenario_calls
from .providers import _openai_prompt
from .tools.business_metrics import dispatch_business_metric_tool
from .tools.registry import ToolRegistry
from .tools.routes import RouteTools

try:
    from .evidence_index import EvidenceIndex
    from .tools.evidence import dispatch_evidence_tool
except ImportError:  # F2.5/F2.6 can be merged independently from this checker.
    EvidenceIndex = None  # type: ignore[assignment,misc]
    dispatch_evidence_tool = None

ROOT = Path(__file__).resolve().parents[2]
STAGE3_FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
STAGE3_PROFILE = ROOT / "config/chat/f2_9_business_stage3_partial.json"
PROMPT_SOURCE = ROOT / "config/chat/system_prompt.txt"
MODEL_CATALOG = ROOT / "config/chat/models.json"
METRIC_CANDIDATES = ROOT / "config/chat/metrics-candidates.json"
METRIC_REGISTRY = ROOT / "config/chat/metrics.yaml"
EVIDENCE_APPROVAL_INDEX = ROOT / "config/chat/evidence/approved-index.json"
CAMPAIGN_CANDIDATE = "gpt-6.1-sol@low"
STAGE3_PROMPT_VERSION = "r2-proposed"
# Frozen identity of the completed stage-three campaign, independent of production.
STAGE3_PROMPT_SHA256 = "68961bc7a2dc7d0c79988352b56b2ded2ef7b55e515ce824dba3b2cf516a9edf"
STAGE3_PROMPT_PATH = ROOT / "config/chat/evaluation_prompts/system_prompt_r2-stage3.txt"
EXPECTED_FIXTURE_SHA256 = "30fc0acfc5d9fee1ffffd3624209712dd8160806dae4d904c4310a8f53537640"
_HASH = set("0123456789abcdef")
_OWNER = "salvamalfa"


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Se esperaba un objeto JSON: {path}")
    return payload, _file_hash(path)


def _execution_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    commit = result.stdout.strip()
    if len(commit) != 40:
        raise ValueError("No se pudo fijar el commit de ejecución")
    return commit


class _Tools:
    """Execute the real deterministic modules with a single trace contract."""

    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self.registry = ToolRegistry(
            snapshot,
            SimpleNamespace(
                enable_route_tools=True,
                enable_business_metric_tools=True,
                enable_evidence_tools=True,
            ),
        )
        self.routes = RouteTools(snapshot)
        self.evidence = None
        evidence_path = ROOT / "config/chat/evidence/approved-index.json"
        if EvidenceIndex is not None and evidence_path.is_file():
            self.evidence = EvidenceIndex(evidence_path)
        self.calls: list[dict[str, Any]] = []

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name in {"query_routes", "find_shared_routes"}:
            result = self.routes.invoke(name, arguments)
        elif name in {"query_business_metrics", "get_business_metric_definition"}:
            result = dispatch_business_metric_tool(self.snapshot, name, arguments)
        elif name in {"search_reports", "search_news"} and self.evidence is not None:
            result = dispatch_evidence_tool(name, arguments, self.evidence)
        elif name in {"search_reports", "search_news"}:
            raise ValueError("La herramienta de evidencia no está integrada")
        else:
            result = self.registry.invoke(name, arguments)
        self.calls.append({"tool": name, "arguments": arguments, "result": result})
        return result


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _extract_evidence(
    result: Any, *, path: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, str]], bool, bool]:
    """Collect numeric/availability rows, deduplicated public sources and closed gates."""
    evidence: list[dict[str, Any]] = []
    sources: dict[str, dict[str, str]] = {}
    gate_closed = False
    route_policy_block = False

    def visit(value: Any, loc: str) -> None:
        nonlocal gate_closed, route_policy_block
        if isinstance(value, dict):
            if value.get("approval_gate") == "closed" or value.get("availability") == "approval_required":
                gate_closed = True
            if (
                value.get("agent_eligible") is False
                and value.get("usage_scope") != "published_dashboard_retrospective"
            ):
                route_policy_block = True
            url = value.get("url")
            label = value.get("label")
            if isinstance(url, str) and url.startswith("https://"):
                sources.setdefault(url, {"label": str(label or "Fuente pública"), "url": url})
            if "value" in value and (
                value.get("availability") is not None or value.get("value_kind") is not None
            ):
                evidence.append(
                    {
                        "path": loc,
                        "value": value.get("value") if _numeric(value.get("value")) else None,
                        "unit": value.get("unit"),
                        "availability": value.get("availability"),
                        "value_kind": value.get("value_kind"),
                        "period": value.get("period"),
                        "metric_id": value.get("metric_id"),
                        "entity_id": value.get("entity_id"),
                    }
                )
            for key, child in value.items():
                visit(child, f"{loc}.{key}" if loc else key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{loc}[{index}]")

    visit(result, path)
    return evidence, list(sources.values()), gate_closed, route_policy_block


def derive_stage3_coverage(
    *,
    snapshot_root: Path,
    fixture_path: Path = STAGE3_FIXTURE,
    profile_path: Path = STAGE3_PROFILE,
    prompt_source_path: Path = PROMPT_SOURCE,
) -> dict[str, Any]:
    """Run real tools for all 30 frozen business questions and derive new evidence."""
    fixture, fixture_sha = _read_object(fixture_path)
    profile, profile_sha = _read_object(profile_path)
    catalog, catalog_sha = _read_object(MODEL_CATALOG)
    prompt_hash = _openai_prompt.effective_prompt_sha256()
    active_prompt_version_fn = getattr(_openai_prompt, "effective_prompt_version", None)
    active_prompt_version = active_prompt_version_fn() if active_prompt_version_fn else "r1-final"
    prompt_compatible = prompt_hash == STAGE3_PROMPT_SHA256
    prompt_base_hash = hashlib.sha256(
        prompt_source_path.read_text(encoding="utf-8").strip().encode("utf-8")
    ).hexdigest()
    if fixture_sha != EXPECTED_FIXTURE_SHA256:
        raise ValueError("El fixture de negocio cambió; no se reescriben las fixtures etapa 1/2")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != 30:
        raise ValueError("La campaña requiere las 30 preguntas de negocio congeladas")
    case_ids = [case.get("id") for case in cases]
    expected_ids = [f"N{number:02d}" for number in range(1, 31)]
    if case_ids != expected_ids:
        raise ValueError("El fixture no conserva el orden e IDs N01–N30")
    if profile.get("selected_candidate") != CAMPAIGN_CANDIDATE:
        raise ValueError("La campaña stage3 fija únicamente Sol low")
    if profile.get("run_repetitions") != 1:
        raise ValueError("Stage3 coverage espera una sola pasada del candidato seleccionado")
    limits = profile.get("limits")
    if limits != {
        "max_message_chars": 8_000,
        "max_tool_calls": 16,
        "max_tool_result_bytes": 16_000,
        "max_turn_seconds": 180,
    }:
        raise ValueError("Stage3 requiere los límites runtime fijados y aprobados para la campaña")
    approved_prompt = fixture.get("owner_approval", {}).get("approved_prompt_content_sha256")
    from .providers._openai_prompt import APPROVED_BASE_PROMPT_SHA256

    if approved_prompt != APPROVED_BASE_PROMPT_SHA256 or prompt_base_hash != APPROVED_BASE_PROMPT_SHA256:
        raise ValueError("El prompt runtime no coincide con el contenido aprobado por el dueño")

    snapshot = Snapshot(snapshot_root)
    fixture_expected_versions = fixture["expected_versions"]
    tools = _Tools(snapshot)
    # Offline scenario selection needs individual IDs, while the model-facing
    # catalog may encode long lists as lossless calendar ranges.
    periods = tools.registry.catalog()["periods"]
    toolspecs = tools.registry.tool_specs()
    toolspec_hash = _canonical_hash(toolspecs)
    snapshot_manifest_sha = _file_hash(snapshot.root / "publication_manifest.json")
    projection_paths = ("data/v1/business_metrics.json", "data/v1/business_metrics.approval.json")
    projection_pins = {}
    manifest_entries = {item["path"]: item["sha256"] for item in snapshot.manifest["files"]}
    for rel in projection_paths:
        projection_pins[rel] = manifest_entries.get(rel)
    evidence_index_path = "config/chat/evidence/approved-index.json"
    evidence_path = ROOT / evidence_index_path
    evidence_index_hash = _file_hash(evidence_path) if evidence_path.is_file() else None
    evidence_index_payload = _read_object(evidence_path)[0] if evidence_path.is_file() else {}
    evidence_record_count = len(tools.evidence.records) if tools.evidence is not None else 0
    # The exact public index bytes are the stable content pin across supported
    # index schemas; do not infer publication from an assumed records field.
    evidence_content_sha = evidence_index_hash
    evidence_content_version = next(
        (
            evidence_index_payload[key]
            for key in ("content_version", "index_version", "schema_version")
            if isinstance(evidence_index_payload.get(key), (str, int))
            and not isinstance(evidence_index_payload.get(key), bool)
        ),
        f"sha256:{evidence_index_hash}" if evidence_index_hash else None,
    )

    rows = []
    counts = {"supported": 0, "coverage_missing": 0, "approval_blocked": 0}
    for case in cases:
        tools.calls = []
        calls, limitation = _scenario_calls(case["id"], periods)
        for tool_name, arguments in calls:
            try:
                tools.call(tool_name, arguments)
            except (ValueError, KeyError, TypeError) as exc:
                tools.calls.append(
                    {
                        "tool": tool_name,
                        "arguments": arguments,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:240],
                    }
                )
        derived_evidence: list[dict[str, Any]] = []
        source_map: dict[str, dict[str, str]] = {}
        approval_blocked = False
        route_policy_block = False
        tool_execution_complete = all("result" in call for call in tools.calls)
        tool_source_coverage_complete = True
        for index, call in enumerate(tools.calls):
            if "result" not in call:
                tool_source_coverage_complete = False
                continue
            found, refs, closed, route_block = _extract_evidence(call["result"], path=f"calls[{index}]")
            derived_evidence.extend(found)
            if (
                any(item.get("availability") == "available" and _numeric(item.get("value")) for item in found)
                and not refs
            ):
                tool_source_coverage_complete = False
            for ref in refs:
                source_map.setdefault(ref["url"], ref)
            approval_blocked |= closed
            route_policy_block |= route_block
        finite_rows = [
            item
            for item in derived_evidence
            if item.get("availability") == "available" and _numeric(item.get("value"))
        ]
        evidence_rows_complete = bool(derived_evidence) and all(
            item.get("availability") == "available" and _numeric(item.get("value"))
            for item in derived_evidence
        )
        # A closed semantic/eligibility gate outranks missing rows; available
        # rows still remain in the artifact so reviewers can see what is known.
        status = (
            "approval_blocked"
            if approval_blocked or route_policy_block
            else (
                "coverage_missing"
                if limitation
                or not finite_rows
                or not evidence_rows_complete
                or not tool_execution_complete
                or not tool_source_coverage_complete
                or not source_map
                else "supported"
            )
        )
        counts[status] += 1
        rows.append(
            {
                "case_id": case["id"],
                "question": case["question"],
                "locale": case.get("locale", "unknown"),
                "turn_count": len(case.get("turns", [case.get("question")])),
                "status": status,
                "status_basis": (
                    "tool_approval_gate_closed"
                    if approval_blocked
                    else "tool_eligibility_gate_closed"
                    if route_policy_block
                    else "declared_capability_limit"
                    if limitation
                    else "tool_execution_incomplete"
                    if not tool_execution_complete
                    else "tool_source_coverage_incomplete"
                    if not tool_source_coverage_complete or not source_map
                    else "requested_evidence_rows_incomplete"
                    if not evidence_rows_complete
                    else "no_numeric_available_tool_evidence"
                    if not finite_rows
                    else "numeric_tool_evidence_with_public_sources"
                ),
                "limitation": limitation,
                "calls": tools.calls,
                "derived_expectations": derived_evidence,
                "tool_execution_complete": tool_execution_complete,
                "tool_source_coverage_complete": tool_source_coverage_complete,
                "evidence_rows_complete": evidence_rows_complete,
                "derived_calculations": _derived_calculations(case["id"], derived_evidence),
                "source_references": list(source_map.values()),
                "follow_up_turns_reused_prior_tool_results": case["id"] in {"N25", "N26"},
            }
        )

    runtime_caps = {
        "candidate": CAMPAIGN_CANDIDATE,
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "text_verbosity": "medium",
        "tool_specs_sha256": toolspec_hash,
        "tool_names": [spec["name"] for spec in toolspecs],
        "routes_tool_module": "RouteTools",
        "business_metric_module": "dispatch_business_metric_tool",
        "stage3_candidate_count": 1,
        "prompt_content_sha256": prompt_hash,
        "active_prompt_version": active_prompt_version,
        "required_prompt_version": STAGE3_PROMPT_VERSION,
        "required_prompt_sha256": STAGE3_PROMPT_SHA256,
        "prompt_compatible": prompt_compatible,
    }
    report_search_tools = {
        spec["name"] for spec in toolspecs if spec["name"] in {"search_reports", "search_news"}
    }
    report_search_available = "search_reports" in report_search_tools
    report_news_available = "search_news" in report_search_tools
    report_index_published = evidence_record_count > 0
    capability_pins = {
        "business_metric_projection": {
            "status": "published" if all(projection_pins.values()) else "missing_receipt_or_projection",
            "manifest_hashes": projection_pins,
            "metric_candidate_config_sha256": _file_hash(METRIC_CANDIDATES),
            "metric_registry_sha256": _file_hash(METRIC_REGISTRY),
        },
        "report_evidence_index": {
            "status": (
                "published"
                if report_index_published and report_search_available and report_news_available
                else "missing_index"
                if evidence_index_hash is None
                else "empty_index"
                if not report_index_published
                else "search_tools_unavailable"
                if not report_search_available or not report_news_available or tools.evidence is None
                else "published"
            ),
            "manifest_path": evidence_index_path,
            "sha256": evidence_index_hash,
            "content_sha256": evidence_content_sha,
            "content_version": evidence_content_version,
            "record_count": evidence_record_count,
            "search_tools": sorted(report_search_tools),
            "news_search_available": report_news_available,
            "report_search_available": report_search_available,
        },
        "routes": {
            "status": "tools_available_but_row_coverage_is_checked_per_case",
            "quarterly_periods": periods["flight"].get("international", []),
            "domestic_monthly_periods": periods["flight"].get("domestic_monthly", []),
        },
    }
    campaign_identity = {
        "stage": "F2.9-stage-3",
        "candidate": CAMPAIGN_CANDIDATE,
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "text_verbosity": "medium",
        "case_fixture_sha256": fixture_sha,
        "profile_sha256": profile_sha,
        "snapshot_data_version": snapshot.version,
        "snapshot_semantic_version": snapshot.semantic_version,
        "snapshot_manifest_sha256": snapshot_manifest_sha,
        "prompt_source_sha256": _file_hash(prompt_source_path),
        "prompt_base_content_sha256": prompt_base_hash,
        "prompt_content_sha256": prompt_hash,
        "active_prompt_version": active_prompt_version,
        "required_prompt_version": STAGE3_PROMPT_VERSION,
        "required_prompt_sha256": STAGE3_PROMPT_SHA256,
        "prompt_compatible": prompt_compatible,
        "model_catalog_sha256": catalog_sha,
        "tool_specs_sha256": toolspec_hash,
        "capability_pins_sha256": _canonical_hash(capability_pins),
        "derived_coverage_sha256": _canonical_hash(rows),
        "execution_commit": _execution_commit(),
        "run_repetitions": 1,
        "limits": limits,
    }
    campaign_sha = _canonical_hash(campaign_identity)
    return {
        "schema_version": 1,
        "kind": "f2_9_stage3_derived_coverage",
        "mode": "offline_tool_coverage_only",
        "fixture_lineage": {
            "fixture_sha256": fixture_sha,
            "source_expected_versions": fixture_expected_versions,
        },
        "campaign_identity": campaign_identity,
        "campaign_sha256": campaign_sha,
        "case_count": len(rows),
        "counts": counts,
        "coverage_status": "complete" if counts["supported"] == 30 else "coverage_gaps_or_approval_gates",
        "current_dashboard_period": {
            "economic": periods["economic_quarters"][-1] if periods["economic_quarters"] else None,
            "market": periods["market_quarters"][-1] if periods["market_quarters"] else None,
            "domestic_routes": periods["flight"].get("domestic_monthly", [])[-1:] or None,
        },
        "pins": {
            "business_fixture_sha256": fixture_sha,
            "profile_sha256": profile_sha,
            "model_catalog_sha256": catalog_sha,
            "tool_specs_sha256": toolspec_hash,
            "prompt_source_sha256": campaign_identity["prompt_source_sha256"],
            "prompt_base_content_sha256": prompt_base_hash,
            "prompt_content_sha256": prompt_hash,
            "snapshot_manifest_sha256": snapshot_manifest_sha,
            "data_version": snapshot.version,
            "semantic_version": snapshot.semantic_version,
        },
        "runtime_capabilities": runtime_caps,
        "published_capabilities": capability_pins,
        "cases": rows,
        "provider_calls": 0,
        "credentials_read": False,
        "fixtures_modified": False,
        "note": (
            "Valores y gates se derivan de tools deterministas y del snapshot verificado; "
            "no califican respuestas de modelo."
        ),
    }


def validate_receipt_scope(
    budget_receipt: dict[str, Any],
    capability_receipt: dict[str, Any],
    report: dict[str, Any],
    reserve_usd: float,
    *,
    budget_receipt_sha256: str | None = None,
    capability_receipt_sha256: str | None = None,
) -> tuple[bool, str]:
    """Validate pinned receipt bytes, owner decision references, and exact campaign scope."""
    common = {
        "campaign_sha256": report["campaign_sha256"],
        "candidate": CAMPAIGN_CANDIDATE,
        "reserve_usd": reserve_usd,
    }
    if (
        isinstance(reserve_usd, bool)
        or not isinstance(reserve_usd, (int, float))
        or not math.isfinite(reserve_usd)
        or reserve_usd <= 0
    ):
        return False, "reserve_invalid"
    trusted_hashes = {
        "budget": budget_receipt_sha256,
        "capabilities": capability_receipt_sha256,
    }
    for label, receipt, kind in (
        ("budget", budget_receipt, "f29_stage3_funding"),
        ("capabilities", capability_receipt, "f29_stage3_capabilities"),
    ):
        trusted_hash = trusted_hashes[label]
        if (
            not isinstance(trusted_hash, str)
            or len(trusted_hash) != 64
            or any(char not in _HASH for char in trusted_hash)
        ):
            return False, f"{label}_receipt_sha256_missing_or_invalid"
        if _canonical_hash(receipt) != trusted_hash:
            return False, f"{label}_receipt_sha256_mismatch"
        if receipt.get("approved_by") != _OWNER:
            return False, f"{label}_receipt_owner_mismatch"
        approved_at = receipt.get("approved_at")
        try:
            approval_date = date.fromisoformat(approved_at) if isinstance(approved_at, str) else None
            valid_until = (
                date.fromisoformat(receipt["valid_until"])
                if isinstance(receipt.get("valid_until"), str)
                else None
            )
        except ValueError:
            approval_date = None
            valid_until = None
        if (
            approval_date is None
            or approval_date.isoformat() != approved_at
            or valid_until is None
            or valid_until.isoformat() != receipt.get("valid_until")
            or approval_date > valid_until
        ):
            return False, f"{label}_receipt_approval_date_invalid"
        if valid_until < date.today():
            return False, f"{label}_receipt_expired"
        decision_ref = receipt.get("decision_ref")
        if not isinstance(decision_ref, str) or not re.fullmatch(
            r"https://github\.com/salvamalfa/aeromexico-tracker/blob/[0-9a-f]{40}/docs/(?:decisiones|chat)/[A-Za-z0-9._/-]+(?:#[A-Za-z0-9._-]+)?",
            decision_ref,
        ):
            return False, f"{label}_receipt_decision_ref_untrusted"
        if receipt.get("schema_version") != 1 or receipt.get("receipt_type") != kind:
            return False, f"{label}_receipt_invalid"
        if receipt.get("status") != "approved":
            return False, f"{label}_receipt_not_approved"
        for field, value in common.items():
            if receipt.get(field) != value:
                return False, f"{label}_receipt_scope_mismatch_{field}"
    if budget_receipt.get("funding_status") != "funded" or budget_receipt.get("funded_usd") != reserve_usd:
        return False, "budget_receipt_funding_not_confirmed"
    pins = report["pins"]
    for key, value in {
        "data_version": pins["data_version"],
        "semantic_version": pins["semantic_version"],
        "tool_specs_sha256": report["runtime_capabilities"]["tool_specs_sha256"],
        "snapshot_manifest_sha256": pins["snapshot_manifest_sha256"],
        "model_catalog_sha256": pins["model_catalog_sha256"],
        "business_fixture_sha256": pins["business_fixture_sha256"],
        "profile_sha256": pins["profile_sha256"],
        "prompt_source_sha256": pins["prompt_source_sha256"],
        "prompt_content_sha256": pins["prompt_content_sha256"],
        "prompt_version": report["runtime_capabilities"]["required_prompt_version"],
        "active_prompt_version": report["runtime_capabilities"]["active_prompt_version"],
        "required_prompt_sha256": report["runtime_capabilities"]["required_prompt_sha256"],
        "capability_pins_sha256": report["campaign_identity"]["capability_pins_sha256"],
        "limits": report["campaign_identity"]["limits"],
        "report_evidence_index_sha256": report["published_capabilities"]["report_evidence_index"].get(
            "sha256"
        ),
        "report_evidence_content_sha256": report["published_capabilities"]["report_evidence_index"].get(
            "content_sha256"
        ),
        "report_evidence_content_version": report["published_capabilities"]["report_evidence_index"].get(
            "content_version"
        ),
    }.items():
        if capability_receipt.get(key) != value:
            return False, f"capabilities_receipt_scope_mismatch_{key}"
    required = {
        "business_metrics",
        "routes",
        "report_evidence",
        "report_search",
        "news_search",
        "presentation",
    }
    capabilities = capability_receipt.get("capabilities")
    if not isinstance(capabilities, list) or not required <= set(capabilities):
        return False, "capabilities_receipt_incomplete"
    if capability_receipt.get("stage3_live_authorized") is not True:
        return False, "capabilities_receipt_stage3_authorization_missing"
    if report["runtime_capabilities"].get("prompt_compatible") is not True:
        return False, "stage3_prompt_not_activated"
    published = report["published_capabilities"]
    if published["business_metric_projection"].get("status") != "published":
        return False, "business_metric_projection_not_published"
    evidence = published["report_evidence_index"]
    if evidence.get("status") != "published":
        return False, "report_evidence_index_not_published"
    if not evidence.get("report_search_available") or not evidence.get("news_search_available"):
        return False, "required_report_news_search_tools_unavailable"
    return True, "receipts_match_exact_campaign_scope"


__all__ = ["CAMPAIGN_CANDIDATE", "derive_stage3_coverage", "validate_receipt_scope"]

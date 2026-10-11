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
import subprocess
from pathlib import Path
from typing import Any

from .data.snapshot import Snapshot
from .providers import _openai_prompt
from .tools.business_metrics import business_metric_tool_specs, dispatch_business_metric_tool
from .tools.registry import ToolRegistry
from .tools.routes import ROUTE_TOOL_SPECS, RouteTools

try:
    from .evidence_index import EvidenceIndex
    from .tools.evidence import dispatch_evidence_tool, evidence_tool_specs
except ImportError:  # F2.5/F2.6 can be merged independently from this checker.
    EvidenceIndex = None  # type: ignore[assignment,misc]
    dispatch_evidence_tool = None
    evidence_tool_specs = None

ROOT = Path(__file__).resolve().parents[2]
STAGE3_FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
STAGE3_PROFILE = ROOT / "config/chat/f2_9_final_campaign.json"
PROMPT_SOURCE = ROOT / "config/chat/system_prompt.txt"
MODEL_CATALOG = ROOT / "config/chat/models.json"
METRIC_CANDIDATES = ROOT / "config/chat/metrics-candidates.json"
METRIC_REGISTRY = ROOT / "config/chat/metrics.yaml"
EVIDENCE_APPROVAL_INDEX = ROOT / "config/chat/evidence/approved-index.json"
CAMPAIGN_CANDIDATE = "gpt-6.1-sol@low"
STAGE3_PROMPT_VERSION = "r2-proposed"
STAGE3_PROMPT_SHA256 = "68961bc7a2dc7d0c79988352b56b2ded2ef7b55e515ce824dba3b2cf516a9edf"
EXPECTED_FIXTURE_SHA256 = "30fc0acfc5d9fee1ffffd3624209712dd8160806dae4d904c4310a8f53537640"
_HASH = set("0123456789abcdef")


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
        self.registry = ToolRegistry(snapshot)
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


def _latest_prior(periods: list[str], current: str, years: int = 1) -> str | None:
    if "Q" in current:
        year, quarter = current.split("Q")
        target = f"{int(year) - years:04d}Q{quarter}"
    elif "M" in current:
        year, month = current.split("M")
        target = f"{int(year) - years:04d}M{month}"
    else:
        return None
    return target if target in periods else None


def _scenario_calls(
    case_id: str, periods: dict[str, Any]
) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    """Return tool actions derived from the frozen question's intent, not its old status."""
    economic = periods["economic_quarters"]
    market = periods["market_quarters"]
    months = periods["market_months"]
    flights = periods["flight"]
    latest_econ = economic[-1] if economic else None
    latest_market = market[-1] if market else None
    intl = flights.get("international", [])
    dom_monthly = flights.get("domestic_monthly", [])
    latest_flight = (dom_monthly or intl or [None])[-1]
    prior_econ = _latest_prior(economic, latest_econ) if latest_econ else None
    prior_market = _latest_prior(market, latest_market) if latest_market else None
    actions: list[tuple[str, dict[str, Any]]] = []
    scope_limit: str | None = None

    def query(metric: str, entities: list[str], selected: list[str], segment: str | None = None):
        args: dict[str, Any] = {"metric_ids": [metric], "entity_ids": entities, "periods": selected}
        if segment:
            args["segment"] = segment
        actions.append(("query_metrics", args))

    def series(metric: str, entity: str, selected: list[str], segment: str | None = None):
        if not selected:
            return
        args: dict[str, Any] = {
            "metric_id": metric,
            "entity_id": entity,
            "start_period": selected[0],
            "end_period": selected[-1],
            "limit": 20,
        }
        if segment:
            args["segment"] = segment
        actions.append(("get_time_series", args))

    if case_id == "N01":
        actions.append(
            (
                "query_business_metrics",
                {"metric_id": "company_passengers", "entity_id": "AEROMEXICO", "period": "2025"},
            )
        )
    elif case_id == "N02":
        query("load_factor", ["AEROMEXICO"], [latest_econ] if latest_econ else [])
    elif case_id == "N03":
        query("cask_cents_per_km", ["AEROMEXICO", "VOLARIS"], [latest_econ] if latest_econ else [])
    elif case_id == "N04":
        actions.extend(
            [
                ("get_business_metric_definition", {"metric_id": "total_revenue"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "total_revenue",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
    elif case_id == "N05":
        query("afac_passengers", ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"], ["2025Q4"], "total")
    elif case_id == "N06":
        if prior_econ and latest_econ:
            for metric in ("company_passengers", "load_factor", "cask_cents_per_km"):
                actions.append(
                    (
                        "compare_metrics",
                        {
                            "metric_id": metric,
                            "entity_id": "AEROMEXICO",
                            "periods": [prior_econ, latest_econ],
                        },
                    )
                )
        scope_limit = (
            "La pregunta no define una métrica única; las comparaciones separadas no forman "
            "una calificación global."
        )
    elif case_id in {"N07", "N08"}:
        selected = [period for period in (prior_market, latest_market) if period]
        if selected:
            query("market_share", ["AEROMEXICO", "VOLARIS"], selected, "domestic")
            actions.append(("get_source_references", {"metric_ids": ["market_share"]}))
    elif case_id == "N09":
        if latest_flight:
            prior = _latest_prior(dom_monthly or intl, latest_flight)
            args: dict[str, Any] = {
                "entity_id": "AEROMEXICO_GROUP",
                "segment": "domestic",
                "period": latest_flight,
                "metric": "passengers",
                "top_n": 5,
            }
            if prior:
                args["comparison_period"] = prior
                args["order_by"] = "absolute_change"
            actions.append(("query_routes", args))
    elif case_id == "N10":
        if latest_flight:
            actions.append(
                (
                    "find_shared_routes",
                    {
                        "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
                        "segment": "domestic",
                        "period": latest_flight,
                        "metric": "passengers",
                        "top_n": 20,
                    },
                )
            )
    elif case_id == "N11":
        if prior_econ and latest_econ:
            query("load_factor", ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"], [prior_econ, latest_econ])
    elif case_id == "N12":
        history = [period for period in economic if period >= "2024Q3"]
        series("cask_cents_per_km", "AEROMEXICO", history)
        actions.append(("get_source_references", {"metric_ids": ["cask_cents_per_km"]}))
    elif case_id == "N13":
        if prior_market and latest_market:
            actions.append(
                (
                    "compare_metrics",
                    {
                        "metric_id": "afac_passengers",
                        "entity_id": "INDUSTRY",
                        "periods": [prior_market, latest_market],
                        "segment": "international",
                    },
                )
            )
    elif case_id == "N14":
        selected_months = [period for period in months if period.startswith("2026M")]
        if selected_months:
            query("afac_passengers", ["AEROMEXICO"], selected_months, "total")
        else:
            actions.append(
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "AEROMEXICO", "period": "2026H1"},
                )
            )
    elif case_id == "N15":
        if latest_econ:
            query("cask_cents_per_km", ["AEROMEXICO"], [latest_econ], None)
        actions.append(("get_business_metric_definition", {"metric_id": "fuel_expense"}))
        actions.append(
            (
                "query_business_metrics",
                {"metric_id": "fuel_expense", "entity_id": "AEROMEXICO", "period": latest_econ or "2026Q2"},
            )
        )
        scope_limit = "La causa del cambio requiere el componente financiero publicado y su aprobación."
    elif case_id == "N16":
        actions.extend(
            [
                (
                    "search_reports",
                    {
                        "query": "combustible costos Aeromexico",
                        "company": "Aeromexico",
                        "period": None,
                        "limit": 5,
                    },
                ),
                ("get_business_metric_definition", {"metric_id": "fuel_expense"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "fuel_expense",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
        scope_limit = "Las herramientas de referencia no buscan ni extraen texto de reportes."
    elif case_id == "N17":
        actions.append(
            (
                "search_news",
                {
                    "query": "aerolíneas México eventos",
                    "start_date": "2026-01-01",
                    "end_date": "2026-10-11",
                    "company": None,
                    "limit": 5,
                },
            )
        )
        scope_limit = "No hay una herramienta de búsqueda de noticias o atribución de eventos."
    elif case_id == "N18":
        if prior_econ and latest_econ:
            actions.append(
                (
                    "compare_metrics",
                    {
                        "metric_id": "load_factor",
                        "entity_id": "VOLARIS",
                        "periods": [prior_econ, latest_econ],
                    },
                )
            )
        scope_limit = "La serie permite medir el cambio, pero no identifica su causa."
    elif case_id == "N19":
        actions.append(("get_business_metric_definition", {"metric_id": "fuel_expense"}))
        for entity in ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"):
            actions.append(
                (
                    "query_business_metrics",
                    {"metric_id": "fuel_expense", "entity_id": entity, "period": latest_econ or "2026Q2"},
                )
            )
    elif case_id == "N20":
        if latest_econ:
            actions.append(
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "AEROMEXICO", "period": latest_econ},
                )
            )
        scope_limit = "El snapshot publica datos históricos; no incluye un pronóstico para 2027."
    elif case_id == "N21":
        if latest_market:
            query("market_share", ["VOLARIS", "VIVA_AEROBUS"], [latest_market], "domestic")
            actions.append(("get_source_references", {"metric_ids": ["market_share"]}))
    elif case_id == "N22":
        actions.extend(
            [
                ("get_business_metric_definition", {"metric_id": "fuel_expense"}),
                ("get_business_metric_definition", {"metric_id": "operating_costs"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "fuel_expense",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "operating_costs",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
    elif case_id == "N23":
        actions.extend(
            [
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "VIVA_AEROBUS", "period": "2026H1"},
                ),
                (
                    "query_business_metrics",
                    {"metric_id": "company_passengers", "entity_id": "VOLARIS", "period": "2026H1"},
                ),
            ]
        )
    elif case_id == "N24":
        actions.append(("get_dashboard_context", {}))
        query("company_passengers", ["AEROMEXICO", "VOLARIS"], [latest_econ] if latest_econ else [])
        if prior_econ and latest_econ:
            query("company_passengers", ["AEROMEXICO", "VOLARIS"], [prior_econ, latest_econ])
        actions.append(("get_source_references", {"metric_ids": ["company_passengers"]}))
    elif case_id in {"N25", "N26"}:
        actions.append(("get_dashboard_context", {}))
        query(
            "load_factor",
            ["AEROMEXICO"],
            ["2026Q2"] if "2026Q2" in economic else ([latest_econ] if latest_econ else []),
        )
        actions.append(("get_source_references", {"metric_ids": ["load_factor"]}))
        # Follow-up turns are deliberately satisfied from the retained first-turn result.
    elif case_id == "N27":
        scope_limit = "No existe una definición única publicada de la mejor aerolínea."
    elif case_id == "N28":
        scope_limit = "El análisis no ofrece recomendaciones de inversión."
    elif case_id == "N29":
        actions.extend(
            [
                ("get_business_metric_definition", {"metric_id": "operating_income"}),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "operating_income",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
                (
                    "query_business_metrics",
                    {
                        "metric_id": "company_passengers",
                        "entity_id": "AEROMEXICO",
                        "period": latest_econ or "2026Q2",
                    },
                ),
            ]
        )
    elif case_id == "N30":
        actions.append(("get_data_catalog", {}))
        scope_limit = "El catálogo no ofrece conteos diarios de vuelos cancelados."
    else:
        scope_limit = "No hay un escenario determinista para el caso."

    return actions, scope_limit


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
            if value.get("agent_eligible") is False:
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
    approved_prompt = fixture.get("owner_approval", {}).get("approved_prompt_content_sha256")
    from .providers._openai_prompt import APPROVED_BASE_PROMPT_SHA256

    if approved_prompt != APPROVED_BASE_PROMPT_SHA256 or prompt_base_hash != APPROVED_BASE_PROMPT_SHA256:
        raise ValueError("El prompt runtime no coincide con el contenido aprobado por el dueño")

    snapshot = Snapshot(snapshot_root)
    versions = fixture.get("expected_versions", {})
    if snapshot.version != versions.get("data_version") or snapshot.semantic_version != versions.get(
        "semantic_version"
    ):
        raise ValueError("El snapshot/diccionario semántico ya no coincide con los pins del fixture")
    tools = _Tools(snapshot)
    catalog_result = tools.call("get_data_catalog", {})
    periods = catalog_result["periods"]
    toolspecs = tools.registry.tool_specs() + ROUTE_TOOL_SPECS + business_metric_tool_specs()
    if evidence_tool_specs is not None:
        toolspecs += evidence_tool_specs()
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
    evidence_record_count = len(tools.evidence.records) if tools.evidence is not None else 0

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
        for index, call in enumerate(tools.calls):
            if "result" not in call:
                continue
            found, refs, closed, route_block = _extract_evidence(call["result"], path=f"calls[{index}]")
            derived_evidence.extend(found)
            for ref in refs:
                source_map.setdefault(ref["url"], ref)
            approval_blocked |= closed
            route_policy_block |= route_block
        finite_rows = [
            item
            for item in derived_evidence
            if item.get("availability") == "available" and _numeric(item.get("value"))
        ]
        # A closed semantic/eligibility gate outranks missing rows; available
        # rows still remain in the artifact so reviewers can see what is known.
        status = (
            "approval_blocked"
            if approval_blocked or route_policy_block
            else ("coverage_missing" if limitation or not finite_rows or not source_map else "supported")
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
                    else "no_numeric_available_tool_evidence"
                    if not finite_rows
                    else "numeric_tool_evidence_with_public_sources"
                ),
                "limitation": limitation,
                "calls": tools.calls,
                "derived_expectations": derived_evidence,
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
                if report_index_published and report_search_available
                else "missing_index"
                if evidence_index_hash is None
                else "empty_index"
                if not report_index_published
                else "report_search_tool_unavailable"
                if not report_search_available
                else "published"
            ),
            "manifest_path": evidence_index_path,
            "sha256": evidence_index_hash,
            "record_count": evidence_record_count,
            "search_tools": sorted(report_search_tools),
            "news_search_available": report_news_available,
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
    }
    campaign_sha = _canonical_hash(campaign_identity)
    return {
        "schema_version": 1,
        "kind": "f2_9_stage3_derived_coverage",
        "mode": "offline_tool_coverage_only",
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
) -> tuple[bool, str]:
    """Validate exact campaign, candidate, reserve, pins, and explicit approvals."""
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
    for label, receipt, kind in (
        ("budget", budget_receipt, "f29_stage3_funding"),
        ("capabilities", capability_receipt, "f29_stage3_capabilities"),
    ):
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
    }.items():
        if capability_receipt.get(key) != value:
            return False, f"capabilities_receipt_scope_mismatch_{key}"
    required = {"business_metrics", "routes", "report_evidence", "presentation"}
    capabilities = capability_receipt.get("capabilities")
    if not isinstance(capabilities, list) or not required <= set(capabilities):
        return False, "capabilities_receipt_incomplete"
    if capability_receipt.get("stage3_live_authorized") is not True:
        return False, "capabilities_receipt_stage3_authorization_missing"
    if report["runtime_capabilities"].get("prompt_compatible") is not True:
        return False, "stage3_prompt_not_activated"
    return True, "receipts_match_exact_campaign_scope"


__all__ = ["CAMPAIGN_CANDIDATE", "derive_stage3_coverage", "validate_receipt_scope"]

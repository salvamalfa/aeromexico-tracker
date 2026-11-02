"""Reproduce the explicit Q3 release data through normal source generators."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.config import PATHS
from src.web_export.writer import dumps_deterministic

from .issuer_scope import sha
from .source_data_update import file_ref


def encoded(value):
    return (dumps_deterministic(value) + "\n").encode()


def afac_input(afac):
    workbook = file_ref(afac["workbook"], PATHS.root)
    metadata_path = file_ref(afac["metadata"], PATHS.root)
    metadata = json.loads(metadata_path.read_bytes())
    captured = datetime.fromisoformat(metadata["downloaded_at"])
    expected_url = (
        "https://www.gob.mx/cms/uploads/attachment/file/1112829/resumen-septiembre-2026-27102026.xlsx"
    )
    if (
        metadata_path != workbook.with_suffix(workbook.suffix + ".meta.json")
        or metadata["sha256"] != afac["workbook"]["sha256"]
        or metadata["http_status"] != 200
        or metadata.get("source_system") != "afac"
        or metadata.get("source_url") != expected_url
        or metadata.get("bytes") != workbook.stat().st_size
        or metadata.get("download_method") != "httpx"
        or captured.tzinfo is None
        or not datetime(2026, 10, 27, tzinfo=UTC) <= captured <= datetime.now(UTC)
    ):
        raise ValueError("AFAC actual original, official URL, sidecar, bytes or chronology differs")
    manifest = workbook.parents[1] / "_manifest.jsonl"
    if not any(json.loads(line) == metadata for line in manifest.read_text(encoding="utf-8").splitlines()):
        raise ValueError("AFAC official original absent from its retained physical capture manifest")
    return workbook, metadata


def outputs(sources, baseline, packages):
    """No ignored preview JSON is an input; every affected output is rebuilt."""
    from scripts.build_afac_market_review import build as afac_build
    from scripts.build_anac_route_review import build as anac_build
    from src.analysis_agent.quarterly_story import _contexts
    from src.conversational_analytics.evidence_index import EvidenceIndex, candidate_content_sha256
    from src.dashboard.industry_review import build_industry_period
    from src.web_export.executive import export_executive
    from src.web_export.news import news_export_payload

    if set(sources) != {"afac_summary", "anac", "news"}:
        raise ValueError("Q3 release must explicitly declare AFAC, ANAC and approved news")
    afac, anac = sources["afac_summary"], sources["anac"]
    if set(afac) != {"workbook", "metadata", "year", "through"} or (afac["year"], afac["through"]) != (
        2026,
        9,
    ):
        raise ValueError("Q3 release requires the exact AFAC September annual summary")
    workbook, metadata = afac_input(afac)
    if set(anac) != {"candidate", "certification", "quarter"} or anac["quarter"] != "2026Q3":
        raise ValueError("Q3 release requires one explicit certified ANAC edition")
    certificate = file_ref(anac["certification"], PATHS.root)
    candidate = (PATHS.root / anac["candidate"]).resolve()
    from src.source_updates.collection import safe_workspace

    candidate = safe_workspace(candidate)
    if list((candidate / "receipts").glob("certified-anac-*.json")) != [certificate]:
        raise ValueError("ANAC request must identify the exact certification consumed by its native replay")
    if set(sources["news"]) != {"approval_package"}:
        raise ValueError("News publication requires the complete exact owner-reviewed package")
    news_package = json.loads(file_ref(sources["news"]["approval_package"], PATHS.root).read_bytes())
    expected_proposal = "907971ca7e811a914f4fdb44920e146882d5b0b74db50b53f0d54bcbcb866df4"
    if (
        news_package.get("candidate_count") != 23
        or news_package.get("proposal_sha256") != expected_proposal
        or sha(encoded({k: v for k, v in news_package.items() if k != "proposal_sha256"}).rstrip(b"\n"))
        != expected_proposal
    ):
        raise ValueError("News package differs from the exact 23-record owner decision")
    approved = EvidenceIndex(PATHS.root / "config/chat/evidence/approved-index.json")
    indexed = {record["id"]: record for record in approved.records}
    proposed = news_package["proposed_index_records"]
    if len(proposed) != 23 or len({p["record"]["id"] for p in proposed}) != 23:
        raise ValueError("News owner package has missing or duplicate records")
    for proposed_record in proposed:
        actual = indexed.get(proposed_record["record"]["id"])
        if actual is None or candidate_content_sha256(actual) != proposed_record["candidate_content_sha256"]:
            raise ValueError("Every new story must have its exact current owner approval before publication")
    contexts = _contexts(packages)
    executive = json.loads((baseline / "data/v1/executive.json").read_bytes())
    for entity, (_, calculations) in contexts.items():
        rows = [r for r in executive["entities"][entity]["records"] if r["period_id"] == "2026Q3"]
        if len(rows) != 1:
            raise ValueError("Industry source issuer quarter missing or ambiguous")
        nodes = {n["key"]: n["value"] for n in calculations["nodes"] if n["period_id"] == "2026Q3"}
        expected = dict(
            passengers=nodes["passengers"],
            ask_km=nodes["ask"],
            rask_cents_per_km=nodes["rask"],
            cask_cents_per_km=nodes["cask"],
            load_factor=nodes["load"],
            rpk_km=nodes["rpm"] * 1.609344,
            cask_ex_fuel_cents_per_km=nodes["casm_ex"] / 1.609344,
        )
        if any(abs(rows[0][key] - value) > 1e-8 * max(1, abs(value)) for key, value in expected.items()):
            raise ValueError("Industry constituent data differs from its original source replay")
        if rows[0]["load_factor_basis"] != "reported":
            raise ValueError("Industry source occupancy must retain its reported basis")
    result = {}
    with tempfile.TemporaryDirectory(
        dir=PATHS.root / "tmp/source-updates", prefix="story-source-"
    ) as temporary:
        folder = Path(temporary)
        market, _ = afac_build(
            json.loads((baseline / "data/v1/market.json").read_bytes()),
            workbook,
            2026,
            9,
            metadata["downloaded_at"],
            folder / "afac.duckdb",
        )
        result["data/v1/market.json"] = encoded(market)
        # The existing ANAC generator verifies native cells, lineage, flight-cell
        # precedence, actual observed months, schema and privacy on each replay.
        anac_build(candidate, baseline / "data/v1", folder / "anac", "2026Q3")
        for path in (folder / "anac/data/v1").rglob("*.json"):
            result["data/v1/" + path.relative_to(folder / "anac/data/v1").as_posix()] = path.read_bytes()
        industry = build_industry_period(executive, "2026Q3", review=False)
        export_executive(industry, folder / "financial", skip_input_check=True)
        result["data/v1/executive.json"] = (folder / "financial/executive.json").read_bytes()
    result["data/v1/news.json"] = encoded(news_export_payload())
    return result

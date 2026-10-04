from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.semantic.plan import PlanValidationError
from src.conversational_analytics.tools.registry import TOOL_NAMES, ToolRegistry

FIXTURE = Path(__file__).parent / "fixtures/chat/site"


def _fixture_copy(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    shutil.copytree(FIXTURE, root)
    return root


def _resign_file(root: Path, relative: str) -> None:
    manifest_path = root / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    raw = (root / relative).read_bytes()
    for entry in manifest["files"]:
        if entry["path"] == relative:
            entry.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


def test_tools_compute_raw_and_display_values_without_unit_confusion() -> None:
    snapshot = Snapshot(FIXTURE)
    tools = ToolRegistry(snapshot)
    assert {spec["name"] for spec in tools.tool_specs()} == set(TOOL_NAMES)
    result = tools.invoke(
        "query_metrics", {"metric_ids": ["load_factor"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]}
    )
    row = result["rows"][0]
    assert row["value"] == pytest.approx(0.849)
    assert row["unit"] == "fraction"
    assert row["display_value"] == pytest.approx(84.9)
    assert row["display_unit"] == "%"
    assert result["references"] and result["data_version"] == snapshot.version


def test_market_share_changes_are_stored_as_percentage_points() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    result = tools.invoke(
        "query_metrics",
        {
            "metric_ids": ["market_share_change_qoq_pp"],
            "entity_ids": ["AEROMEXICO"],
            "periods": ["2026Q2"],
            "segment": "domestic",
        },
    )
    row = result["rows"][0]
    assert row["value"] == pytest.approx(-0.6598529129216546)
    assert row["unit"] == "percentage_points"
    assert row["display_value"] == pytest.approx(-0.7)
    assert row["display_unit"] == "pp"


def test_afac_market_denominator_is_separate_from_three_airline_industry() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    result = tools.invoke(
        "query_metrics",
        {
            "metric_ids": ["afac_market_passengers"],
            "entity_ids": ["MEXICAN_CARRIERS"],
            "periods": ["2026Q2"],
            "segment": "domestic",
        },
    )
    row = result["rows"][0]
    assert row["availability"] == "available"
    assert row["value"] > 0
    assert (
        "denominador"
        in tools.invoke("get_metric_definition", {"metric_id": "afac_market_passengers"})["metric"][
            "description"
        ]
    )
    with pytest.raises(PlanValidationError, match="solo admite"):
        tools.invoke(
            "query_metrics",
            {
                "metric_ids": ["afac_market_passengers"],
                "entity_ids": ["INDUSTRY"],
                "periods": ["2026Q2"],
                "segment": "domestic",
            },
        )
    with pytest.raises(PlanValidationError, match="solo está disponible"):
        tools.invoke(
            "query_metrics",
            {
                "metric_ids": ["afac_passengers"],
                "entity_ids": ["MEXICAN_CARRIERS"],
                "periods": ["2026Q2"],
                "segment": "domestic",
            },
        )


def test_compare_reports_percentage_points_and_relative_change_separately() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    # The small fixture compares the adjacent published 1T26 and 2T26 values.
    result = tools.invoke(
        "compare_metrics",
        {"metric_id": "load_factor", "entity_id": "AEROMEXICO", "periods": ["2026Q1", "2026Q2"]},
    )
    comparison = result["comparison"]
    assert comparison["absolute_delta"] == pytest.approx(0.005)
    assert comparison["delta_unit"] == "fraction"
    assert comparison["percentage_point_delta"] == pytest.approx(0.5)
    assert comparison["relative_change_percent"] == pytest.approx(0.592417)
    assert comparison["relative_change_available"] is True


def test_missing_is_not_zero_and_time_series_chart_is_constrained() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    missing = tools.invoke(
        "query_metrics",
        {"metric_ids": ["company_passengers"], "entity_ids": ["AEROMEXICO"], "periods": ["2025Q2"]},
    )["rows"][0]
    assert missing["availability"] == "missing" and missing["value"] is None
    series = tools.invoke(
        "get_time_series",
        {
            "metric_id": "rask_cents_per_km",
            "entity_id": "AEROMEXICO",
            "start_period": "2026Q2",
            "end_period": "2026Q2",
        },
    )
    assert series["chart"] == {
        "type": "line",
        "title": "RASK",
        "x": ["2T26"],
        "series": [{"name": "Aeroméxico", "y": [9.94]}],
        "unit": "¢ USD / ASK-km",
    }
    with pytest.raises(PlanValidationError):
        tools.invoke(
            "query_metrics",
            {
                "metric_ids": ["company_passengers"],
                "entity_ids": ["AEROMEXICO"],
                "periods": ["2026Q2"],
                "segment": "domestic",
            },
        )
    with pytest.raises(PlanValidationError, match="Grano temporal"):
        tools.invoke(
            "query_metrics",
            {"metric_ids": ["company_passengers"], "entity_ids": ["AEROMEXICO"], "periods": ["2026M06"]},
        )


def test_explicit_zero_remains_available(tmp_path: Path) -> None:
    root = _fixture_copy(tmp_path)
    path = root / "data/v1/executive.json"
    payload = json.loads(path.read_text())
    q2 = next(row for row in payload["entities"]["AEROMEXICO"]["records"] if row["period_id"] == "2026Q2")
    q2["passengers"] = 0
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    _resign_file(root, "data/v1/executive.json")
    row = ToolRegistry(Snapshot(root)).invoke(
        "query_metrics",
        {"metric_ids": ["company_passengers"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]},
    )["rows"][0]
    assert row["availability"] == "available" and row["value"] == 0


def test_zero_comparison_denominator_keeps_absolute_delta_and_omits_relative(tmp_path: Path) -> None:
    root = _fixture_copy(tmp_path)
    path = root / "data/v1/executive.json"
    payload = json.loads(path.read_text())
    q1 = next(row for row in payload["entities"]["AEROMEXICO"]["records"] if row["period_id"] == "2026Q1")
    q1["load_factor"] = 0
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    _resign_file(root, "data/v1/executive.json")
    compared = ToolRegistry(Snapshot(root)).invoke(
        "compare_metrics",
        {"metric_id": "load_factor", "entity_id": "AEROMEXICO", "periods": ["2026Q1", "2026Q2"]},
    )["comparison"]
    assert compared["absolute_delta"] == pytest.approx(0.849)
    assert compared["percentage_point_delta"] == pytest.approx(84.9)
    assert compared["relative_change_percent"] is None
    assert compared["relative_change_available"] is False


def test_peer_references_do_not_claim_aeromexico_filing() -> None:
    # The real public snapshot has all peer entities and period-specific source metadata.
    tools = ToolRegistry(Snapshot(Path("site")))
    row = tools.invoke(
        "query_metrics", {"metric_ids": ["load_factor"], "entity_ids": ["VOLARIS"], "periods": ["2026Q2"]}
    )["rows"][0]
    assert not any("sec.gov" in ref["url"] for ref in row["source_references"])


def test_compare_orders_periods_chronologically_and_rejects_duplicates() -> None:
    registry = ToolRegistry(Snapshot(FIXTURE))
    args = {"metric_id": "load_factor", "entity_id": "AEROMEXICO"}
    forward = registry.invoke("compare_metrics", {**args, "periods": ["2026Q1", "2026Q2"]})
    backward = registry.invoke("compare_metrics", {**args, "periods": ["2026Q2", "2026Q1"]})
    assert backward["comparison"] == forward["comparison"]
    assert forward["comparison"]["previous"]["period"] == "2026Q1"
    assert forward["comparison"]["current"]["period"] == "2026Q2"
    for periods in (["2026Q2", "2026Q2"], ["2026Q2", "2026M06"]):
        with pytest.raises(PlanValidationError):
            registry.invoke("compare_metrics", {**args, "periods": periods})

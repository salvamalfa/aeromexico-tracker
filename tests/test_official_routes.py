"""Meaningful guards: regular cargo, cell absence, identity and selective publication boundaries."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.official_routes import aggregate_routes, bts_cells, comparison
from src.dashboard.official_routes_contract import dataset_version, validate
from src.dashboard.official_routes_geo import airport_points, region
from src.publish import source_data_members
from src.source_updates.afac_margins import ANNUAL_2025_NOTE, footnotes


def cell(month, origin="A", destination="B", count=2, operator=None):
    return dict(period_id=month, origin=origin, destination=destination, departures=count,
                operator=operator, carrier_group="AEROMEXICO" if operator else None,
                airline_id="19534" if operator else None, label="Aeromexico" if operator else None, region=None)


def test_bidirectional_sum_once_and_missing_month_is_not_zero():
    points = {p: {"id": p} for p in ("A", "B")}
    cells = [cell("2026M07", count=3), cell("2026M07", "B", "A", 4)]
    route = aggregate_routes(cells, [], points, ["2026M07"])[0]
    assert route["departures"] == 7
    assert route["monthly"] == [{"period_id": "2026M07", "departures": 7}]
    assert route["comparison"]["yoy_pct"] is None
    result = comparison(cells, [cell("2025M07", count=3)], ["2026M07"])
    assert result["previous_departures"] is None  # Missing reverse direction is not an observed zero.


def test_yoy_uses_matched_months_and_explicit_zero_base_has_no_percentage():
    now, before = [cell("2026M07", count=30)], [cell("2025M07", count=20)]
    assert comparison(now, before, ["2026M07"])["yoy_pct"] == 50
    assert comparison(now, before, ["2026M07", "2026M08"])["previous_departures"] is None
    result = comparison(now, [cell("2025M07", count=0)], ["2026M07"])
    assert result["previous_departures"] == 0 and result["yoy_pct"] is None


def test_bts_regular_includes_g_cargo_excludes_l_p_and_preserves_connect():
    airports = airport_points(pd.DataFrame([
        dict(iata_code="MEX", name="Mexico City", iso_country="MX", latitude_deg=19., longitude_deg=-99.),
        dict(iata_code="LAX", name="Los Angeles", iso_country="US", latitude_deg=34., longitude_deg=-118.),
        dict(iata_code="SJU", name="San Juan", iso_country="PR", latitude_deg=18., longitude_deg=-66.),
    ]))
    rows = [dict(period_id="2026M07", origin="MEX", dest="LAX", **{"class": c}, airline_id="20250",
                 carrier_key="AEROMEXICO_CONNECT", unique_carrier_name="Aerolitoral", departures_performed=1)
            for c in ("F", "G", "L", "P")]
    rows.append({**rows[0], "dest": "SJU"})
    result = bts_cells(pd.DataFrame(rows), airports)
    assert len(result) == 2 and sum(c["departures"] for c in result) == 2
    assert {c["operator"] for c in result} == {"AEROMEXICO_CONNECT"}
    assert {c["carrier_group"] for c in result} == {"AEROMEXICO"}
    assert airports["SJU"]["country_iso2"] == "PR" and region("PR") == "central_america_caribbean"


@pytest.mark.parametrize("mutation", [
    lambda v: v["networks"][0].update(grain="airport_pair"),
    lambda v: v["networks"][0].update(observed_months=["2026M10"]),
    lambda v: v["networks"][0].update(source_ids=["invented"]),
    lambda v: v["networks"][0]["routes"][0].update(departures=12),
    lambda v: v["networks"][0]["routes"][0]["origin"].update(iata="MEX"),
])
def test_rehashed_semantic_forgery_is_rejected(mutation):
    value = json.loads((Path(__file__).parent / "fixtures/official-routes.example.json").read_bytes())
    validate(value)
    mutation(value)
    value["dataset_version"] = dataset_version(value)
    with pytest.raises(ValueError):
        validate(value)


def test_merger_source_note_is_not_an_estimated_cell_and_other_notes_still_fail():
    assert footnotes([(ANNUAL_2025_NOTE,)], 2025) == []
    with pytest.raises(ValueError, match="Unreviewed"):
        footnotes([(ANNUAL_2025_NOTE.replace("2025", "2026"),)], 2025)


def test_missing_historical_surface_requires_an_explicit_new_surface_adapter(tmp_path):
    from src.publish.source_data_scope import adapter

    units = [{"product": "official_routes"}]
    assert source_data_members.baseline_bytes(tmp_path, units, adapter) == {"data/v1/official-routes.json": b"{}\n"}
    with pytest.raises(ValueError, match="explicitly reviewed"):
        source_data_members.initial_bytes("data/v1/market.json", units, adapter)


def test_official_sources_use_existing_dependency_assessment_without_publication():
    from scripts.source_update_monthly_handoff import release_kind
    from src.source_updates.official_routes_consumer import consumer_plan

    assert release_kind("afac_margins") == release_kind("bts_segments") == "source_dependency_assessment"
    plan = consumer_plan("afac_margins")
    assert plan["scopes"] == ["national", "international"] and plan["activation"] == "none"


@pytest.mark.parametrize("primary,extra", [("official_routes", "am_traffic_ir"), ("am_traffic_ir", "official_routes")])
def test_official_map_cannot_coalesce_in_either_source_order(primary, extra):
    request = dict(product=primary, period="2026M09", source_profile={}, additional_sources=[
        dict(product=extra, period="2026M09", source_profile={})])
    with pytest.raises(ValueError, match="cannot coalesce"):
        source_data_members.selections(request)


@pytest.mark.parametrize("extra", [None, "wrong"])
def test_malformed_extra_source_is_a_controlled_rejection(extra):
    request = dict(product="am_traffic_ir", period="2026M09", source_profile={}, additional_sources=[extra])
    with pytest.raises(ValueError, match="source"):
        source_data_members.selections(request)


def test_minimal_legacy_nochange_request_keeps_ordinary_approval_route(monkeypatch, tmp_path):
    from src.publish import source_data_update as update

    monkeypatch.setattr(update, "ordinary_approval_cohorts", lambda *args: {"ordinary": True})
    request = dict(product="am_traffic_ir", period="2026M09", authorization=None)
    assert update.source_approvals(request, tmp_path, [], tmp_path, "baseline", {}, tmp_path) == {"ordinary": True}


def test_minimal_official_nochange_request_uses_closed_continuity_route(monkeypatch, tmp_path):
    from src.publish import official_routes_approvals, source_data_update as update

    profile = tmp_path / "profile.json"
    profile.write_text('{"retained_approvals":null}')
    monkeypatch.setattr(official_routes_approvals, "verify", lambda *args: {"official": True})
    request = dict(product="official_routes", period="2026M09", authorization=None)
    assert update.source_approvals(request, profile, [], tmp_path, "baseline", {}, tmp_path) == {"official": True}


def test_candidate_certificate_paths_are_portable_between_windows_and_linux(monkeypatch):
    from pathlib import PurePosixPath, PureWindowsPath

    from src.source_updates import official_routes as preparation

    monkeypatch.setattr(preparation, "digest", lambda _: "a" * 64)
    windows = preparation.input_inventory([PureWindowsPath("C:/candidate/data/a.xlsx")], PureWindowsPath("C:/candidate"))
    linux = preparation.input_inventory([PurePosixPath("/candidate/data/a.xlsx")], PurePosixPath("/candidate"))
    assert windows == linux == {"data/a.xlsx": "a" * 64}


def test_retained_real_package_and_geographic_extract_replay_exactly():
    from src.source_updates.official_routes_sources import replay
    from src.dashboard.official_routes_contract import encoded

    root = Path(__file__).resolve().parents[1] / "tmp/official-routes-review"
    if not (root / "selection.json").is_file():
        pytest.skip("Requires the explicitly prepared retained official-route review workspace")
    payload, evidence, _ = replay(json.loads((root / "selection.json").read_bytes()), root)
    assert encoded(payload) == (root / "data/v1/official-routes.json").read_bytes()
    assert evidence["activation"] == "none" and evidence["publication"] == "not_authorized"
    q3 = [n for n in payload["networks"] if n["period_id"] == "2026Q3"]
    us = next(n for n in q3 if n["entity"] == "THREE")
    assert us["observed_months"] == ["2026M07"] and us["availability"] == "partial"
    assert all(n["observed_months"] == ["2026M07", "2026M08", "2026M09"] for n in q3 if n["scope"] != "us")
    assert sum(r["departures"] for r in us["routes"]) == 6239

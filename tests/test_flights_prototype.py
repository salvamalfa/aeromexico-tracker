from __future__ import annotations

import json
import math
from pathlib import Path
import re

from bs4 import BeautifulSoup

from src.analysis_agent.flight_evidence import build_flight_evidence
from src.config import PATHS
from src.dashboard.flights import build_flight_payload
from src.dashboard.flights_html import DEFAULT_OUTPUT, render_flights_html, standalone_flight_payload


def _payload() -> dict:
    return build_flight_payload()


def test_flight_payload_contract_and_pilot_metrics() -> None:
    payload = _payload()
    assert payload["schema_version"] == "flight_dashboard_payload_v1"
    assert payload["metadata"]["pilot_period"] == "2026Q2"
    quarter = next(item for item in payload["quarters"] if item["period_id"] == "2026Q2")
    values = {key: metric["value"] for key, metric in quarter["metrics"].items()}
    assert values == {
        "passengers": 6_014_000.0,
        "asm_miles": 9_256_000_000.0,
        "rpm_miles": 7_851_000_000.0,
        "load_factor": 0.8490000000000001,
    }
    for metric in quarter["metrics"].values():
        assert metric["period_type"] == "quarter"
        assert metric["period_start"] == "2026-04-01"
        assert metric["period_end"] == "2026-06-30"
        assert metric["cutoff_date"] == "2026-07-13"
        assert metric["source_id"] == "sec-quarterly"
        assert metric["agent_eligible"] is True


def test_monthly_sec_mix_is_complete_only_when_three_months_exist() -> None:
    payload = _payload()
    mixes = {item["period_id"]: item["passenger_mix"] for item in payload["quarters"]}
    assert {period for period, mix in mixes.items() if mix} == {
        "2025Q1", "2025Q2", "2026Q1", "2026Q2"
    }
    mix = mixes["2026Q2"]
    assert mix["months"] == ["2026M04", "2026M05", "2026M06"]
    assert mix["passengers"]["domestic"] + mix["passengers"]["international"] == mix["passengers"]["total"]
    assert math.isclose(mix["passengers"]["domestic_share"] + mix["passengers"]["international_share"], 1.0)
    assert mixes["2025Q4"] is None


def test_monthly_passenger_chart_uses_complete_afac_gold_and_sums_segments() -> None:
    series = _payload()["monthly_passengers"]
    assert series["period_start"] == "2015-01-01"
    assert series["period_end"] == "2026-06-30"
    assert series["source_id"] == "afac-gold-current"
    assert series["observed_months"] == series["calendar_months"] == 138
    assert len(series["records"]) == 138
    assert all(item["availability"] == "observed" for item in series["records"])
    assert all(item["total_segment_sum"] == item["domestic"] + item["international"] for item in series["records"])
    assert all(item["reported_total"] == item["total_segment_sum"] for item in series["records"])
    assert not any(item["agent_eligible"] for item in series["records"])


def test_domestic_passenger_estimates_are_monthly_retrospective_and_bounded() -> None:
    payload = _payload()
    monthly = payload["domestic_monthly_networks"]
    assert list(monthly) == ["2026M03", "2026M04", "2026M05", "2026M06", "2026M07"]
    for period_id, network in monthly.items():
        assert network["period_id"] == period_id
        assert network["mode"] == "estimated_domestic"
        assert network["agent_eligible"] is False
        assert network["observed_months"] == [period_id]
        assert all(route["passengers_estimated"] for route in network["routes"])
        assert all(route["passengers_low"] <= route["passengers"] <= route["passengers_high"]
                   for route in network["routes"])
        assert any(route["departures"] is not None for route in network["routes"])
        assert all(route["departures_estimated"] == route["capacity_complete"]
                   for route in network["routes"])
        assert all(route["load_factor"] is None or 0 <= route["load_factor"] <= 1
                   for route in network["routes"])
    assert monthly["2026M03"]["routes"][0]["support_repair_applied"] is True
    assert any(not item["support_observed_in_period"]
               for route in monthly["2026M07"]["routes"] for item in route["monthly"])


def test_t100_network_is_bounded_and_never_claims_global_coverage() -> None:
    payload = _payload()
    network = payload["route_network"]
    assert network["period_id"] == "2026Q2"
    assert network["period_type"] == "quarter_to_date"
    assert network["availability"] == "partial"
    assert network["expected_months"] == ["2026M04", "2026M05", "2026M06"]
    assert network["observed_months"] == ["2026M04", "2026M05"]
    assert (network["period_start"], network["period_end"]) == ("2026-04-01", "2026-05-31")
    assert (network["comparison_period_start"], network["comparison_period_end"]) == ("2025-04-01", "2025-05-31")
    assert network["route_count"] == 40
    assert network["airport_count"] == 33
    assert network["totals"] == {
        "passengers": 612_660.0,
        "seats": 758_735.0,
        "departures": 4_451.0,
    }
    assert "México–Estados Unidos" in network["coverage"]
    assert network["agent_eligible"] is False
    assert network["announced_routes_available"] is False
    assert network["marketing_carrier"] is None
    assert len({route["market_key"] for route in network["routes"]}) == 40
    assert all(route["departures"] > 0 for route in network["routes"])
    assert all(route["operation_status"] == "operated_observed" for route in network["routes"])
    routes_by_airport = {
        code: [route for route in network["routes"] if code in (route["origin"]["iata"], route["destination"]["iata"])]
        for code in ("SEA", "ACA")
    }
    assert len(routes_by_airport["SEA"]) == 3
    assert len(routes_by_airport["ACA"]) == 1
    mia_mex = next(route for route in network["routes"] if route["market_key"] == "MEX<>MIA")
    directions = {
        (direction["origin_iata"], direction["destination_iata"]): direction
        for direction in mia_mex["directions"]
    }
    assert directions[("MIA", "MEX")]["passengers"] == 26_180.0
    assert directions[("MEX", "MIA")]["passengers"] == 24_371.0
    for direction in directions.values():
        assert direction["seats"] > 0
        assert direction["departures"] > 0
        assert 0 < direction["passengers"] / direction["seats"] <= 1
    lax_mex = next(route for route in network["routes"] if route["market_key"] == "LAX<>MEX")
    lax_directions = {
        (direction["origin_iata"], direction["destination_iata"]): direction
        for direction in lax_mex["directions"]
    }
    assert lax_directions[("LAX", "MEX")] == {
        "origin_iata": "LAX", "destination_iata": "MEX",
        "passengers": 37_143.0, "seats": 44_671.0, "departures": 243.0,
    }
    assert lax_directions[("MEX", "LAX")] == {
        "origin_iata": "MEX", "destination_iata": "LAX",
        "passengers": 38_141.0, "seats": 44_945.0, "departures": 244.0,
    }
    for route in network["routes"]:
        for metric in ("passengers", "seats", "departures"):
            assert math.isclose(
                sum(direction[metric] for direction in route["directions"]),
                route[metric],
                abs_tol=0.5,
            )
    assert network["world_geometry"]["version"] == "Natural Earth 5.1.2 / 1:110m"
    assert network["world_geometry"]["license"] == "public domain"
    assert network["world_geometry"]["sha256"] == "6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f"
    for route in network["routes"]:
        assert all(
            finite is not None
            for finite in (
                route["origin"]["lat"], route["origin"]["lon"],
                route["destination"]["lat"], route["destination"]["lon"],
            )
        )
    assert set(payload["route_networks"]) == {quarter["period_id"] for quarter in payload["quarters"]}
    for period_id, period_network in payload["route_networks"].items():
        assert period_network["period_id"] == period_id
        assert set(period_network["observed_months"]).issubset(period_network["expected_months"])
        assert all(
            f"{month[:4]}Q{(int(month[5:7]) - 1) // 3 + 1}" == period_id
            for month in period_network["observed_months"]
        )


def test_forecast_is_secondary_current_perspective() -> None:
    forecast = _payload()["forecast"]
    assert forecast["available"] is True
    assert forecast["agent_eligible"] is False
    assert forecast["trained_at"].startswith("2026-08-24")
    assert forecast["trained_through_period"] == "2026M06"
    assert len(forecast["points"]) == 24
    assert len([point for point in forecast["points"] if not point["is_backtest"]]) == 12
    for point in forecast["points"]:
        assert point["lower_95"] <= point["lower_80"] <= point["forecast"]
        assert point["forecast"] <= point["upper_80"] <= point["upper_95"]


def test_candidate_evidence_is_sec_only_and_does_not_modify_parent() -> None:
    package = build_flight_evidence(_payload())
    assert package["schema_version"] == "flight_evidence_v1"
    assert package["status"] == "candidate_unapproved"
    assert package["parent_evidence"]["evidence_fingerprint"] == (
        "808256bfb7420d221a3f2f2383c4b95d9889110ad1545fd85f24df8d442a9ff1"
    )
    assert {source["source_system"] for source in package["sources"]} == {"SEC EDGAR"}
    assert all(metric["agent_eligible"] for metric in package["metrics"])
    assert {metric["period_id"] for metric in package["metrics"]} == {"2026Q2"}
    assert "bts_t100" in package["excluded"]
    assert not any("route" in metric["key"] for metric in package["metrics"])


def test_review_html_is_self_contained_accessible_and_responsive() -> None:
    document = render_flights_html(_payload())
    soup = BeautifulSoup(document, "html.parser")
    assert soup.select_one("[data-testid='flights-review-root']") is not None
    assert soup.select_one("#period-prev")["aria-label"] == "Ir al trimestre anterior"
    assert soup.select_one("#route-flow-map")["role"] == "img"
    assert soup.select_one("#route-list") is None
    assert soup.select_one("#mix-detail") is None
    assert soup.select_one("#mix-subtitle") is None
    assert soup.select_one("#mix-note") is None
    assert soup.select_one("#view-map") is None
    assert soup.select_one("#view-list") is None
    assert soup.select_one("#list-panel") is None
    assert soup.select_one("#passenger-period option[selected]")["value"] == "quarter"
    assert [option["value"] for option in soup.select("#passenger-period option")] == ["quarter", "month"]
    assert soup.select_one("#importance-select") is None
    assert soup.select_one("#network-summary") is None
    assert soup.select_one(".scope-banner") is None
    assert soup.select_one("#quarter-status") is None
    assert soup.select_one("#network-month-switch")["aria-label"] == "Mes nacional"
    assert soup.select_one("#airport-tooltip")["role"] == "region"
    assert soup.select_one("#route-profile") is None
    assert soup.select_one("#concentration") is None
    assert soup.select_one(".map-detail-layout") is not None
    assert soup.select_one("#flow-map-subtitle") is None
    assert soup.select_one("#map-panel .panel-heading") is None
    assert soup.select_one("#map-panel .gesture-note") is None
    assert not soup.select("script[src], link[href], iframe, img[src], video[src], audio[src], source[src]")
    assert len(soup.select("script[data-runtime='plotly-local']")) == 1
    embedded = json.loads(soup.select_one("#flight-dashboard-data").string)
    assert embedded == standalone_flight_payload(_payload())
    text = soup.get_text(" ", strip=True)
    assert "Rutas nacionales" in text
    assert "Nacional" in text
    assert "Internacional" in text
    assert "Pasajeros y contribución por segmento" in text
    assert text.index("Rutas nacionales") < text.index("Mezcla nacional e internacional")
    assert "Movimientos de slots AICM" not in text
    assert "fuera del paquete histórico 2T26" in text
    app_script = soup.select_one("script[data-runtime='flights-review']").string.lower()
    assert 'name: "total"' in app_script
    assert "seasonally_adjusted" not in app_script
    assert 'let passengerperiod = "quarter"' in app_script
    assert "connectgaps: false" in app_script
    assert 'projection: { type: "equirectangular"' in app_script
    assert "selecciona el destino para ver el detalle" in app_script
    assert "rendernetworksummary" not in app_script
    assert 'hovertemplate: "%{text}<extra></extra>"' in app_script
    assert 'dragmode: false' in app_script
    assert 'scrollzoom: false' in app_script
    assert 'ordered.slice(0, 12)' in app_script
    assert "route_networks" in app_script
    assert 'hoverinfo: "skip"' in app_script
    assert '.on("plotly_click"' in app_script
    assert 'const importance = "passengers"' in app_script
    assert "pinnedairport" in app_script
    assert "renderairporttooltip" in app_script
    assert "renderroutetable" in app_script
    assert "alignroutedetailtogeo" in app_script
    assert "airport-route-table" in app_script
    assert "route-expand-toggle" in app_script
    assert "route-direction-detail" in app_script
    assert 'aria-expanded="false"' in app_script
    assert "detail.hidden = expanded" in app_script
    assert "pasajeros estimados" in app_script
    assert "domestic_monthly_networks" in app_script
    assert "rango de sensibilidad" in app_script
    assert "grupo aeroméxico" in document.lower()
    assert "aeroméxico connect" not in document.lower()
    assert 'const defaultairport = "mex"' in app_script
    assert 'key === "load_factor"' in app_script
    assert "direction.passengers / direction.seats" in app_script
    assert 'hovermode: "closest"' in app_script
    assert "? point.period_label" in app_script
    assert "routemetricchangechip" in app_script
    assert "airport-search-toggle" in app_script
    assert "airportsearchmatches" in app_script
    assert "selectairportfromsearch" in app_script
    assert "setnetworkview" not in app_script
    assert "renderroutelist" not in app_script
    assert "coveragedothtml" in app_script
    assert "coveragemonths" in app_script
    assert "%{customdata[4]:.1%}" in app_script
    assert "%{customdata[5]:.1%}" in app_script
    assert "no disponible" in app_script
    assert "importance-select" not in app_script
    assert '"plotly_hover"' in app_script
    assert '"plotly_unhover"' in app_script
    for primitive in ("fetch(", "xmlhttprequest", "websocket", "eventsource", "sendbeacon"):
        assert primitive not in app_script
    css = (PATHS.root / "src" / "dashboard" / "assets" / "flights.css").read_text(encoding="utf-8")
    assert "@media (max-width: 736px)" in css
    assert "@media (max-width: 420px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "#map-panel { display: none; }" not in css
    assert ".route-change-chip" in css
    assert ".route-table-total strong { font-size: 10.9px; }" in css
    assert ".network-month-switch" in css
    assert ".route-estimate-total" in css


def test_html_contains_no_machine_path_or_project_secret() -> None:
    soup = BeautifulSoup(render_flights_html(_payload()), "html.parser")
    soup.select_one("script[data-runtime='plotly-local']").extract()
    project_document = str(soup)
    assert not re.search(r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|file://|\\\\|/(?:home|Users)/)", project_document, re.I)
    assert not re.search(r"(?:SEC_USER_AGENT|BANXICO_TOKEN|EIA_API_KEY|sk-[A-Za-z0-9]{20,})", project_document, re.I)


def test_generated_review_matches_current_renderer() -> None:
    assert DEFAULT_OUTPUT.exists()
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == render_flights_html(_payload())
    # Includes the pinned 285 KB Plotly topology so file:// never calls a CDN.
    assert DEFAULT_OUTPUT.stat().st_size < 7_500_000
    main = PATHS.root / "prototypes" / "etapa-11" / "resumen_ejecutivo.html"
    assert main.exists()
    assert DEFAULT_OUTPUT.resolve() != main.resolve()

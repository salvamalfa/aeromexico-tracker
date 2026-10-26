"""CI browser regressions for Aero-only Q3, old peers, readings and flight cuts."""

import copy
import json
from pathlib import Path
import pytest
from test_web_chat_smoke import _public_fixtures
from test_web_page_smoke import web_server, _chromium_executable, sync_playwright  # noqa: F401

pytestmark = pytest.mark.browser


def financial_fixture():
    doc = copy.deepcopy(_public_fixtures()["/data/v1/executive.json"])
    for block in doc["entities"].values():
        block["views"] = copy.deepcopy(block["views"])
    doc["views"] = copy.deepcopy(doc["views"])
    record = {
        "period_id": "2026Q3",
        "period_label": "3T26",
        "passengers": 6161e3,
        "ask_km": 15119786880.0,
        "load_factor_reported": 0.883,
        "rask_cents_per_km": 10.687584506482143,
        "cask_cents_per_km": 9.382705002783743,
        "unit_margin_cents_per_km": 1.3048795036984,
    }
    view = copy.deepcopy(doc["views"]["2026Q2"])
    view.update(period_id="2026Q3", period_label="3T26")
    display = {
        "rask_cents_per_km": "10.69 ¢ USD",
        "cask_cents_per_km": "9.38 ¢ USD",
        "ask_km": "15.12 mil M",
        "load_factor_reported": "88.3%",
        "passengers": "6.16 M",
    }
    for kpi in view["kpis"]:
        kpi["value"] = record[kpi["key"]]
        kpi["display_value"] = display[kpi["key"]]
        if kpi["key"] == "rask_cents_per_km":
            kpi["yoy"].update(display="+12.2%", raw=0.122, available=True, direction="up")
        if kpi["key"] == "cask_cents_per_km":
            kpi["yoy"].update(display="+19.4%", raw=0.194, available=True, direction="up")
    view["narrative"] = {
        "headline": "Financial fixture",
        "paragraphs": [
            "Ingreso total TRASM / ASM convertido por 1,609344; comparación anual reportada 12,2%.",
            "Comparativo 88,2%; histórico 88,3% preservado.",
        ],
    }
    doc["records"].append(record)
    doc["views"]["2026Q3"] = view
    doc["metadata"]["last_period"] = "2026Q3"
    block = doc["entities"]["AEROMEXICO"]
    block["records"].append(
        {
            **record,
            "load_factor": 0.883,
            "load_factor_basis": "reported",
            "rpk_km": 13351117824,
            "cask_ex_fuel_cents_per_km": 6.2758490415970725,
        }
    )
    block["views"]["2026Q3"] = copy.deepcopy(view)
    block.update(last_period="2026Q3", quarter_count=len(block["records"]))
    return doc


def routes(page, doc):
    page.route("**/data/v1/executive.json", lambda route: route.fulfill(json=doc))
    entries = [
        {"period_id": "2026Q2", "approval_event": "synthetic", "entity_key": e}
        for e in ["VOLARIS", "VIVA_AEROBUS", "INDUSTRY"]
    ]
    entries += [{"period_id": q, "approval_event": "synthetic"} for q in ["2026Q2", "2026Q3"]]
    page.route(
        "**/publication_manifest.json", lambda route: route.fulfill(json={"analysis_manifest": entries})
    )
    base = json.loads((Path(__file__).parent / "fixtures/web/analysis_sample.json").read_bytes())

    def reading(route):
        suffix = route.request.url.split("/analysis/", 1)[1].removesuffix(".json")
        entity, period = suffix.split("/", 1) if "/" in suffix else ("AEROMEXICO", suffix)
        value = {**base, "period_id": period}
        if entity != "AEROMEXICO":
            value.update(
                entity_key=entity,
                period_label="2T26",
                cutoff_date="2026-10-24",
                selection_mode="retrospective",
                guidance_as_of="report_date",
            )
        route.fulfill(json=value)

    page.route("**/data/v1/analysis/**", reading)


def test_financial_q3_updates_existing_cards_graphs_and_returns_to_q2(web_server):
    doc = financial_fixture()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        routes(page, doc)
        page.goto(
            web_server
            + "?period=2026Q3&sel_kpis=AEROMEXICO&sel_unit=AEROMEXICO&sel_volume=AEROMEXICO&sel_load=AEROMEXICO"
        )
        page.wait_for_function("document.getElementById('period-display').textContent==='3T26'")
        page.click("#tab-economy")
        for key, value in [
            ("rask_cents_per_km", "10.69 ¢ USD"),
            ("cask_cents_per_km", "9.38 ¢ USD"),
            ("ask_km", "15.12 mil M"),
            ("unit_margin_cents_per_km", "+1.30 ¢ USD"),
        ]:
            assert page.inner_text(f"#kpi-{key}-value") == value
        assert page.locator(".reader-economy-kpis .kpi-card").count() == 4
        assert page.inner_text("#kpi-rask_cents_per_km-yoy") == "+12.2%"
        assert page.inner_text("#kpi-cask_cents_per_km-yoy") == "+19.4%"
        assert "88,2%" in page.locator("#financial-comparison-note").text_content()
        for graph in ["unit-chart", "volume-chart", "load-chart"]:
            page.wait_for_function(
                "id=>{const g=document.getElementById(id);return g?.data?.some(t=>JSON.stringify(t).includes('3T26'))}",
                arg=graph,
            )
        assert "3T26" in page.locator(".disclosure-body tbody").text_content()
        page.click("#period-prev")
        page.wait_for_function("document.getElementById('period-display').textContent==='2T26'")
        expected = next(
            k["display_value"] for k in doc["views"]["2026Q2"]["kpis"] if k["key"] == "rask_cents_per_km"
        )
        assert page.inner_text("#kpi-rask_cents_per_km-value") == expected
        assert page.locator("#financial-comparison-note").is_hidden()
        assert errors == []
        browser.close()


@pytest.mark.parametrize("entity", ["INDUSTRY", "VOLARIS", "VIVA_AEROBUS"])
def test_financial_q3_does_not_borrow_aero_values_for_peers(web_server, entity):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        routes(page, financial_fixture())
        page.goto(web_server + f"?period=2026Q3&sel_kpis={entity}")
        page.wait_for_function("document.getElementById('period-display').textContent==='3T26'")
        for key in ["rask_cents_per_km", "cask_cents_per_km", "ask_km", "unit_margin_cents_per_km"]:
            assert page.inner_text(f"#kpi-{key}-value") == "No disponible"
        assert not page.locator(".vs-industry:visible").count()
        browser.close()


def test_lazy_flights_retain_their_real_cut_without_overwriting_q3_finance(web_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        routes(page, financial_fixture())
        page.goto(web_server + "?period=2026Q3&sel_kpis=AEROMEXICO")
        page.wait_for_function("document.getElementById('period-display').textContent==='3T26'")
        page.click("#tab-flights")
        page.wait_for_selector("#flight-data-period")
        page.wait_for_function(
            "document.getElementById('flight-data-period').textContent.includes('No hay datos de vuelos para 2026Q3')"
        )
        assert page.inner_text("#period-display") == "3T26"
        assert "Corte de vuelos: 2T26" in page.inner_text("#flight-data-period")
        page.click("#tab-economy")
        assert page.inner_text("#kpi-rask_cents_per_km-value") == "10.69 ¢ USD"
        assert errors == []
        browser.close()

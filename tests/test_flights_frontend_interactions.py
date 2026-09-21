"""Browser-driven checks for the Vuelos global quarter selector, the national
month multi-select, and the Nacional/Internacional toggle.

Requires the pre-installed Chromium (see environment notes): this session's
Playwright pin does not match the bundled browser build, so the executable
path is passed explicitly instead of running ``playwright install``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

from src.dashboard.flights import build_flight_payload
from src.dashboard.flights_html import render_flights_html


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def flights_page(tmp_path_factory):
    payload = build_flight_payload()
    html = render_flights_html(payload)
    path = tmp_path_factory.mktemp("flights") / "vuelos.html"
    path.write_text(html, encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        page.goto(path.as_uri())
        page.wait_for_selector("#network-month-switch button")
        yield page
        browser.close()


def _pressed_months(page) -> set[str]:
    buttons = page.query_selector_all("#network-month-switch button")
    return {
        button.get_attribute("data-domestic-month")
        for button in buttons
        if button.get_attribute("aria-pressed") == "true"
    }


def _month_button(page, period_id: str):
    return page.query_selector(f'#network-month-switch button[data-domestic-month="{period_id}"]')


def test_default_quarter_selects_its_three_national_months(flights_page) -> None:
    assert _pressed_months(flights_page) == {"2026M04", "2026M05", "2026M06"}
    assert "abril" in flights_page.inner_text("#network-volume").lower()
    assert "3 meses seleccionados" in flights_page.inner_text("#network-volume")


def test_manual_month_deselection_updates_the_table_without_changing_the_quarter(flights_page) -> None:
    period_before = flights_page.inner_text("#period-display")
    volume_before = flights_page.inner_text("#network-volume")
    _month_button(flights_page, "2026M05").click()
    flights_page.wait_for_timeout(50)
    assert _pressed_months(flights_page) == {"2026M04", "2026M06"}
    # The global quarter stepper never moves on a manual month edit.
    assert flights_page.inner_text("#period-display") == period_before
    assert flights_page.inner_text("#network-volume") != volume_before
    # Restore the default selection for the tests that follow.
    _month_button(flights_page, "2026M05").click()
    flights_page.wait_for_timeout(50)
    assert _pressed_months(flights_page) == {"2026M04", "2026M05", "2026M06"}


def test_changing_the_global_quarter_discards_manual_selection_and_shows_partial_coverage(flights_page) -> None:
    _month_button(flights_page, "2026M04").click()
    flights_page.wait_for_timeout(50)
    assert _pressed_months(flights_page) == {"2026M05", "2026M06"}

    flights_page.click("#period-prev")
    flights_page.wait_for_timeout(50)
    # 2026Q1 only has March in the retained AeroDataBox window: it is
    # selected automatically and flagged as partial, never padded with
    # invented February/January figures.
    assert _pressed_months(flights_page) == {"2026M03"}
    assert "cobertura parcial: 1 de 3 meses" in flights_page.inner_text("#network-volume")

    flights_page.click("#period-next")
    flights_page.wait_for_timeout(50)
    # Back on 2026Q2, the manual 04/05-only selection from before the
    # quarter change must NOT reappear: the quarter change reset it.
    assert _pressed_months(flights_page) == {"2026M04", "2026M05", "2026M06"}


def test_can_toggle_national_and_international_repeatedly(flights_page) -> None:
    for _ in range(3):
        flights_page.click("#network-mode-international")
        flights_page.wait_for_timeout(50)
        assert flights_page.get_attribute("#network-mode-domestic", "aria-pressed") == "false"
        assert flights_page.get_attribute("#network-mode-international", "aria-pressed") == "true"
        flights_page.click("#network-mode-domestic")
        flights_page.wait_for_timeout(50)
        assert flights_page.get_attribute("#network-mode-domestic", "aria-pressed") == "true"
        assert flights_page.get_attribute("#network-mode-international", "aria-pressed") == "false"


def test_manual_national_selection_survives_a_visit_to_international(flights_page) -> None:
    _month_button(flights_page, "2026M06").click()
    flights_page.wait_for_timeout(50)
    assert _pressed_months(flights_page) == {"2026M04", "2026M05"}

    flights_page.click("#network-mode-international")
    flights_page.wait_for_timeout(50)
    flights_page.click("#network-mode-domestic")
    flights_page.wait_for_timeout(50)
    assert _pressed_months(flights_page) == {"2026M04", "2026M05"}

    # Restore the default selection for the tests that follow.
    _month_button(flights_page, "2026M06").click()
    flights_page.wait_for_timeout(50)
    assert _pressed_months(flights_page) == {"2026M04", "2026M05", "2026M06"}


def test_national_view_never_shows_aerovias_or_connect_as_separate_series(flights_page) -> None:
    """The one place national mode may name the two filiales is the scope
    note that documents Grupo Aeroméxico's composition (per the audit's
    "manten la separación interna documentada" requirement). Nowhere else --
    route table, expanded detail, KPI strap -- should ever show them as
    separate series."""

    assert flights_page.get_attribute("#network-mode-domestic", "aria-pressed") == "true"
    scope_note = flights_page.inner_text("#network-scope-note")
    assert "Grupo Aeroméxico" in scope_note
    assert "Aerovías de México" in scope_note and "Aeroméxico Connect" in scope_note

    body_text_without_scope_note = flights_page.inner_text("body").replace(scope_note, "")
    assert "Aerovías" not in body_text_without_scope_note
    assert "Connect" not in body_text_without_scope_note
    assert "Grupo Aeroméxico" in flights_page.inner_text("#network-volume")


def test_international_scope_note_names_its_real_narrower_scope(flights_page) -> None:
    """International sources (BTS T-100, ANAC, Aerocivil, CAA, Aena) only
    retain Aerovías de México (AMX) as operator; Aeroméxico Connect never
    appears in them for these periods. The UI must say so plainly instead of
    labelling the figure Grupo Aeroméxico, which would overclaim scope."""

    flights_page.click("#network-mode-international")
    flights_page.wait_for_timeout(50)
    scope_text = flights_page.inner_text("#network-scope-note")
    volume_text = flights_page.inner_text("#network-volume")
    assert "Aerovías de México" in scope_text
    assert "Grupo Aeroméxico" not in scope_text
    assert "Grupo Aeroméxico" not in volume_text
    flights_page.click("#network-mode-domestic")
    flights_page.wait_for_timeout(50)


def _expand_first_route(page):
    toggle = page.query_selector(".route-expand-toggle")
    toggle.click()
    page.wait_for_timeout(150)
    return page.query_selector(".route-direction-detail:not([hidden])")


def test_national_route_detail_states_carrier_once_and_groups_by_month(flights_page) -> None:
    """The expanded per-route detail must name Grupo Aeroméxico exactly once
    (not once per month/direction line) and, with more than one month
    selected, group the direction lines under a subtle per-month label
    instead of repeating the carrier and month on every line."""

    assert flights_page.get_attribute("#network-mode-domestic", "aria-pressed") == "true"
    assert _pressed_months(flights_page) == {"2026M04", "2026M05", "2026M06"}
    detail = _expand_first_route(flights_page)
    carrier_labels = detail.query_selector_all(".route-estimate-carrier")
    assert len(carrier_labels) == 1
    assert carrier_labels[0].inner_text() == "Grupo Aeroméxico"
    month_groups = detail.query_selector_all(".route-estimate-month")
    assert len(month_groups) == 3
    # text-transform: capitalize renders "abril" as "Abril"; compare case-insensitively.
    month_labels = [g.query_selector(".route-estimate-month-label").inner_text().lower() for g in month_groups]
    assert month_labels == ["abril", "mayo", "junio"]
    detail_text = detail.inner_text()
    assert detail_text.count("Grupo Aeroméxico") == 1


def test_national_figures_never_show_the_approx_symbol(flights_page) -> None:
    assert "≈" not in flights_page.inner_text("#network-volume")
    assert "≈" not in flights_page.inner_text("#airport-tooltip")


def test_national_route_coverage_dot_is_green_for_full_quarter_coverage(flights_page) -> None:
    """A route with data in all three of the quarter's calendar months must
    show the same green/yellow/red coverage indicator used in Internacional,
    not a blank space, once its coverage is complete."""

    dots = flights_page.query_selector_all(".route-coverage-dot")
    assert dots, "expected at least one coverage dot in the national route table"
    variants = {dot.get_attribute("class") for dot in dots}
    assert "route-coverage-dot is-full" in variants


def test_national_map_zooms_to_mexico_not_the_world(flights_page) -> None:
    lon_range = flights_page.evaluate(
        "document.getElementById('route-flow-map')._fullLayout.geo.lonaxis.range"
    )
    lat_range = flights_page.evaluate(
        "document.getElementById('route-flow-map')._fullLayout.geo.lataxis.range"
    )
    assert lon_range[1] - lon_range[0] < 60
    assert lat_range[1] - lat_range[0] < 40


def test_international_route_detail_states_grupo_aeromexico(flights_page) -> None:
    flights_page.click("#network-mode-international")
    flights_page.wait_for_timeout(300)
    detail = _expand_first_route(flights_page)
    carrier_labels = detail.query_selector_all(".route-estimate-carrier")
    assert len(carrier_labels) == 1
    assert carrier_labels[0].inner_text() == "Grupo Aeroméxico"
    flights_page.click("#network-mode-domestic")
    flights_page.wait_for_timeout(300)

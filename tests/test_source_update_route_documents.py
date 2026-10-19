"""Dated route text remains source evidence, without operational observations."""

import json

import pytest

from src.source_updates import route_documents as source

ORIGINAL = {
    "source_system": "aeromexico_press",
    "source_file": "release.html",
    "sha256": "a" * 64,
    "downloaded_at": "2026-09-13T20:03:37Z",
}


def am_html():
    return b"""<html><title>AEROMEXICO INCREASES OPERATIONS AT AIFA</title>
    <p>September 06, 2023 20:25 ET</p>
    <p>Mexico City, September 6th, 2023.- Starting October 5, Aeromexico will begin a new phase.</p>
    <p>With this adjustment, Aeromexico's operation at AIFA will account for growth; the route to Colima will be transferred from AICM to AIFA with seven weekly flights.</p></html>"""


def test_official_date_overrides_capture_and_url_date_without_performed_claim():
    f, r = source.parse("am_routes", {"document": (am_html(), ORIGINAL)}, "2023M09")
    assert len(f) == 2 and r["document_date_as_reported"] == "2023-09-06"
    assert f.performed_flights.isna().all() and f.passengers.isna().all() and not f.agent_eligible.any()
    assert not r["news_or_evidence_activated"] and r["months_validated"] == []
    with pytest.raises(ValueError):
        source.parse("am_routes", {"document": (am_html(), ORIGINAL)}, "2026M09")


@pytest.mark.parametrize(
    "content",
    [
        am_html().replace(b"September 06, 2023 20:25 ET", b"September 07, 2023"),
        am_html().replace(b"seven weekly flights", b"ten weekly flights"),
        am_html().replace(b"AEROMEXICO INCREASES", b"UNKNOWN COMPANY"),
    ],
)
def test_source_identity_date_and_reviewed_passage_change_blocks(content):
    with pytest.raises(ValueError):
        source.parse("am_routes", {"document": (content, ORIGINAL)}, "2023M09")


def test_roster_literal_section_is_secondary_context_not_continuing_route_operation():
    data = {
        "@type": "NewsArticle",
        "datePublished": "2026-06-08T17:44:32.162Z",
        "headline": "Todas las aerolíneas que operan en el AIFA",
        "articleBody": "Vuelos nacionalesAeroméxicoOfrece los siguientes vuelos nacionales:CancúnColimaAerusLa aerolínea regional mexicana",
    }
    content = (
        "<html><title>Roster</title><script type='application/ld+json'>"
        + json.dumps(data)
        + "</script></html>"
    ).encode()
    f, r = source.parse("aifa_roster", {"document": (content, ORIGINAL)}, "2026M06")
    assert len(f) == 1 and "CancúnColima" in f.value.iloc[0]
    assert "secondary_dated_roster" in f.evidence_kind.iloc[0]
    assert not r["observed_flights_inferred"] and not r["schedule_expanded_into_future_dates"]

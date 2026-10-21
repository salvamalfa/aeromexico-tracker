"""YTD labelled boxes cannot silently become monthly or rounded-chart values."""

from contextlib import nullcontext

import pytest

from src.source_updates import afac_countries as source
from tests.test_source_update_afac_margins import inputs as margin_inputs

BOX = "Comparativo\nAcumulado a Julio\nPasajeros\nVariación ▲8.8%\n2025 3,945,051\n2026 4,291,849\nVuelos\nVariación ▲14.0%\n2025 23,550\n2026 26,854"
ORIGINAL = {
    "source_system": "afac_research",
    "source_file": "country.pdf",
    "sha256": "c" * 64,
    "downloaded_at": "2026-09-08T18:21:36Z",
}


def test_ytd_boxes_match_labelled_years_and_exact_counts():
    result = source.boxes(BOX, 2026, 7)
    assert result[("passengers", 2026)] == 4291849
    assert result[("passengers", 2025)] == 3945051
    assert result[("flights_as_reported_country_bulletin", 2026)] == 26854


@pytest.mark.parametrize(
    "text",
    [
        BOX.replace("Acumulado a Julio", "Mensual Julio"),
        BOX.replace("Julio", "Agosto"),
        BOX + "\n2026 99,999 ▲0.1%",
        BOX.replace("Pasajeros", "Miles de pasajeros"),
        BOX.replace("2026 4,291,849", "2026 4.3"),
        BOX.replace("2026 4,291,849", "4,291,849"),
        BOX.replace("2026 4,291,849", "2025 4,291,849"),
        BOX.replace("2026 4,291,849", "2026 0\n2026 4,291,849"),
        BOX.replace("2026 4,291,849", "2026 NaN"),
        BOX.replace("2026 4,291,849", "2026 9,007,199,254,740,993"),
    ],
)
def test_unlabelled_rounded_wrong_unit_month_or_duplicate_boxes_block(text):
    with pytest.raises(ValueError):
        source.boxes(text, 2026, 7)


class Page:
    width, height = 960, 540

    def __init__(self, number, changes):
        self.number = number
        self.changes = changes

    def extract_text(self):
        return "Boletín de Estadística Operacional por País Julio 2026"

    def crop(self, bbox):
        values = {
            (0, 0, 960, 65): source.PAGES.get(self.number, ""),
            (
                0,
                65,
                960,
                104,
            ): (
                "Pasajeros transportados por empresas nacionales y extranjeras Vuelos realizados y pasajeros transportados entre México y "
                + ("EAU" if self.number == 35 else source.PAGES.get(self.number, ""))
                + "\nhacia y desde "
                + ("EAU" if self.number == 35 else source.PAGES.get(self.number, ""))
                + " en servicio regular por empresas nacionales y extranjeras en servicio regular"
            ),
            (
                0,
                505,
                960,
                540,
            ): "Fuente: SICT, AFAC, DREE. Información proporcionada por las aerolíneas. Julio 2026",
            (760, 100, 940, 260): BOX,
        }
        text = self.changes.get((self.number, bbox), values[bbox])
        return type("Crop", (), {"extract_text": lambda _self: text})()


def mock_pdf(monkeypatch, changes=None):
    pages = [Page(i, changes or {}) for i in range(1, 38)]
    monkeypatch.setattr(source.pdfplumber, "open", lambda _: nullcontext(type("PDF", (), {"pages": pages})()))


def test_pdf_observations_preserve_ytd_period_type_not_month(monkeypatch):
    mock_pdf(monkeypatch)
    frame = source.pdf_rows(b"%PDF-test", ORIGINAL, "2026M07")
    assert len(frame) == 116 and set(frame.period_type) == {"year_to_date"}
    assert set(frame.period_id) == {"2025YTD07", "2026YTD07"}
    assert frame.carrier_key.isna().all() and not frame.agent_eligible.any()


@pytest.mark.parametrize(
    "bbox,text",
    [
        ((0, 0, 960, 65), "UNKNOWN COUNTRY"),
        ((0, 65, 960, 104), "empresas nacionales en servicio fletamento"),
        ((0, 65, 960, 104), "No incluye empresas nacionales y extranjeras en servicio regular"),
        ((0, 505, 960, 540), "Fuente: unknown Julio 2026"),
        ((760, 100, 940, 260), BOX.replace("2026 4,291,849", "2026 4.3")),
    ],
)
def test_pdf_page_scope_and_source_controls_block(monkeypatch, bbox, text):
    mock_pdf(monkeypatch, {(3, bbox): text})
    with pytest.raises(ValueError):
        source.pdf_rows(b"%PDF-test", ORIGINAL, "2026M07")


def test_independent_od_current_ytd_passenger_crosscheck_blocks_disagreement(monkeypatch):
    mock_pdf(monkeypatch)
    with pytest.raises(ValueError, match="disagree"):
        source.parse({"pdf": (b"%PDF-test", ORIGINAL), "routes": margin_inputs()["routes"]}, "2026M07")

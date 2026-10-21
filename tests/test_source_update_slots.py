"""AICM assignment-row validation does not create actual flight counts."""

from contextlib import nullcontext

import pytest

from src.source_updates import slots


def row():
    return [
        "D",
        "412",
        "",
        "",
        "7M9",
        "12:50",
        "12:50",
        "",
        "MIA",
        "MIA",
        "29/03/2026",
        "24/10/2026",
        "1234567",
        "210",
        "PR",
    ]


def test_source_schedule_frequency_reconciles_full_season_in_utc():
    start, end, endpoint, count = slots.validate_row(row())
    assert (start, end, endpoint, count) == ("2026-03-29", "2026-10-24", "MIA", 210)


@pytest.mark.parametrize(
    "index,value",
    [
        (0, "X"),
        (1, ""),
        (5, "25:00"),
        (6, "12:60"),
        (9, ""),
        (10, "01/01/2026"),
        (11, "25/10/2026"),
        (12, "2234567"),
        (12, "-------"),
        (13, "209"),
        (13, ""),
    ],
)
def test_unknown_missing_or_inconsistent_assignment_fields_block(index, value):
    raw = row()
    raw[index] = value
    with pytest.raises(ValueError):
        slots.validate_row(raw)


def test_duplicate_assignment_rows_are_not_summed_into_observed_flights(monkeypatch):
    class Page:
        def __init__(self, n):
            self.n = n

        def extract_text(self):
            return f"Pág {self.n} de 61\nHora Asignada Operaciones\nAsignación de Históricos para la Temporada Verano 2026\nHorario UTC\n05/02/2026 12:13"

        def extract_tables(self):
            return [[["AM AEROMEXICO"] + [None] * 14 if self.n == 1 else slots.HEADERS, row()]]

    monkeypatch.setattr(
        slots.pdfplumber,
        "open",
        lambda _: nullcontext(type("PDF", (), {"pages": [Page(n) for n in range(1, 62)]})()),
    )
    original = {
        "source_system": "aicm",
        "source_file": "slots.pdf",
        "sha256": "a" * 64,
        "downloaded_at": "2026-09-13T00:46:29Z",
    }
    with pytest.raises(ValueError, match="coverage differs"):
        slots.parse({"pdf": (b"%PDF-test", original)}, "2026Q3")


def test_full_reviewed_row_coverage_remains_schedule_not_flights(monkeypatch):
    class Page:
        def __init__(self, n):
            self.n = n

        def extract_text(self):
            return f"Pág {self.n} de 61\nHora Asignada Operaciones\nAsignación de Históricos para la Temporada Verano 2026\nHorario UTC\n05/02/2026 12:13"

        def extract_tables(self):
            rows = []
            for i in range(47 if self.n <= 30 else 46):
                value = row()
                value[1] = str(self.n * 47 + i)
                rows.append(value)
            return [[["AM AEROMEXICO"] + [None] * 14 if self.n == 1 else slots.HEADERS, *rows]]

    monkeypatch.setattr(
        slots.pdfplumber,
        "open",
        lambda _: nullcontext(type("PDF", (), {"pages": [Page(n) for n in range(1, 62)]})()),
    )
    original = {
        "source_system": "aicm",
        "source_file": "slots.pdf",
        "sha256": "a" * 64,
        "downloaded_at": "2026-09-13T00:46:29Z",
    }
    f, r = slots.parse({"pdf": (b"%PDF-test", original)}, "2026Q3")
    assert len(f) == 2836 and r["source_frequency_reconciliations"] == 2836
    assert f.period_id.eq("2026S26").all() and f.operator_icao.isna().all()
    assert f.time_zone_as_reported.eq("UTC").all() and not f.agent_eligible.any()
    assert r["no_monthly_or_quarterly_flight_total_derived"]

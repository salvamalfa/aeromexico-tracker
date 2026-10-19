import io
from types import SimpleNamespace

import openpyxl
import pytest

from src.source_updates.afac import bulletin_notes, database_months


def workbook(rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "AFAC"
    sheet.append(["Año", "Id_mes", "Servicio"])
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def test_database_requires_contiguous_scheduled_and_charter_months():
    rows = [(2026, month, service) for month in range(1, 9) for service in ["Regular", "Fletamento "]]
    assert database_months(workbook(rows)) == set(range(1, 9))
    for invalid in [rows[:-1], [r for r in rows if r[1] != 3], [(2026, 1, "unknown")]]:
        with pytest.raises(ValueError):
            database_months(workbook(invalid))


def test_pdf_period_comes_from_monthly_comparison_and_preserves_source_caveats(monkeypatch):
    import src.source_updates.afac as afac

    texts = [
        "Pasajeros años 2024 - 2025; (enero - agosto) de 2025 - 2026 y agosto de 2025 - 2026\n"
        "Notas: Las cifras pueden variar. Fuente: AFAC",
        "Pasajeros y agosto de 2025 - 2026\nNotas: No incluyen la totalidad de China Southern. Fuente AFAC",
    ]
    monkeypatch.setattr(
        afac,
        "PdfReader",
        lambda stream: SimpleNamespace(
            pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in texts]
        ),
    )
    assert "China Southern" in bulletin_notes(b"fixture", 8)
    with pytest.raises(ValueError, match="does not confirm"):
        bulletin_notes(b"fixture", 7)
    texts[1] = "Acumulado enero-agosto 2026; Notas: missing monthly comparison. Fuente AFAC"
    with pytest.raises(ValueError, match="does not confirm"):
        bulletin_notes(b"fixture", 8)


def test_january_bulletin_has_no_cumulative_month_or_de_before_years(monkeypatch):
    import src.source_updates.afac as afac

    text = "Pasajeros años: 2024 - 2025; y enero 2025 - 2026\nNotas: Preliminar. Fuente: AFAC"
    monkeypatch.setattr(
        afac,
        "PdfReader",
        lambda stream: SimpleNamespace(
            pages=[SimpleNamespace(extract_text=lambda: text), SimpleNamespace(extract_text=lambda: text)]
        ),
    )
    assert "Preliminar" in bulletin_notes(b"fixture", 1)
    with pytest.raises(ValueError, match="does not confirm"):
        bulletin_notes(b"fixture", 2)

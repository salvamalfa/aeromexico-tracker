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


def test_candidate_extracts_database_offline_with_original_capture_time(tmp_path, monkeypatch):
    import json
    import zipfile
    from datetime import UTC, datetime

    import polars as pl

    import src.parse.afac.monthly_stats as legacy
    import src.source_updates.afac as afac
    from src.common.storage import save_bronze
    from src.config import ProjectPaths
    from src.ingest.afac.download import DATATUR_DATABASE_URL

    paths = ProjectPaths(root=tmp_path)
    paths.ensure_runtime_directories()
    monkeypatch.setattr(afac, "PATHS", paths)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("DB_AFAC.xlsx", workbook([(2026, 1, "Regular"), (2026, 1, "Fletamento")]))
    stamp = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
    save_bronze(
        stream.getvalue(),
        "afac",
        "datatur_database",
        "current",
        "zip",
        DATATUR_DATABASE_URL,
        "manual",
        bronze_root=paths.bronze,
        downloaded_at=stamp,
    )
    save_bronze(
        b"pdf fixture",
        "afac",
        "bulletin",
        "2026M01",
        "pdf",
        "https://datatur.sectur.gob.mx/january.pdf",
        "manual",
        bronze_root=paths.bronze,
        relative_dir="afac/2026/01",
    )
    monkeypatch.setattr(afac, "bulletin_notes", lambda content, month: "Source caveat retained")

    def parse(**kwargs):
        metadata = json.loads(kwargs["database"].with_suffix(".xlsx.meta.json").read_text())
        assert metadata["downloaded_at"] == stamp.isoformat()
        assert metadata["download_method"] == "offline_zip_member"
        assert kwargs["through_month"] == 1 and set(kwargs["documents"]) == {1}
        pl.DataFrame(
            {
                "period_id": ["2026M01", "2026M01"],
                "source_family": ["datatur_monthly_bulletin_pdf", "datatur_long_database"],
                "footnote_text": ["estimated detail", "charter estimate retained"],
            }
        ).write_parquet(paths.silver / "afac_monthly_stats.parquet")
        return {"period_max": "2026M01"}

    monkeypatch.setattr(legacy, "run_afac_parse", parse)
    result = afac.run()
    assert result["period_max"] == "2026M01"
    facts = pl.read_parquet(paths.silver / "afac_monthly_stats.parquet")
    assert facts["footnote_text"].to_list() == [
        "estimated detail\nSource caveat retained",
        "charter estimate retained",
    ]

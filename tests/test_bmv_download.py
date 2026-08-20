from io import BytesIO
import zipfile

import pytest

from src.ingest.bmv.download import _validate_archive, parse_catalog_html


def _row(ticker: str, description: str, docins: str) -> str:
    return f"""
    <tr>
      <td>{ticker}</td><td>Issuer {ticker}</td><td><div>13/07/2026 15:26</div></td>
      <td><a class="lnk-download"
        href="/docs-pub/visor/visorXbrl.html?docins={docins}">{description}</a></td>
    </tr>
    """


def test_parse_catalog_derives_direct_zip_urls_and_periods() -> None:
    html = (
        "<table>"
        + _row(
            "AERO",
            "Información Del Trimestre 2 Del Año 2026",
            "../ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip",
        )
        + _row(
            "VOLAR",
            "Reporte Anual en formato XBRL del año 2025",
            "../anexon/anexon_1577971_2025_1.zip",
        )
        + "</table>"
    ).encode()

    reports = parse_catalog_html(html)

    assert [(report.ticker, report.package_period_id, report.report_type) for report in reports] == [
        ("AERO", "2026Q2", "quarter"),
        ("VOLAR", "2025", "annual"),
    ]
    assert reports[0].zip_url == (
        "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip"
    )


def test_catalog_rejects_package_outside_bmv() -> None:
    html = (
        "<table>"
        + _row("AERO", "Información Del Trimestre 2 Del Año 2026", "https://evil.example/a.zip")
        + "</table>"
    ).encode()

    with pytest.raises(ValueError, match="Unsafe BMV package host"):
        parse_catalog_html(html)


def test_archive_rejects_path_traversal() -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../outside.json", "{}")
    buffer.seek(0)

    with zipfile.ZipFile(buffer) as archive, pytest.raises(ValueError, match="Unsafe ZIP"):
        _validate_archive(archive)

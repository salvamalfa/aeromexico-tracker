from pathlib import Path

from src.ingest.afac.download import (
    CURRENT_ANNUAL_DOWNLOADS,
    _validate_payload,
    parse_datatur_catalog,
)
from src.parse.afac.monthly_stats import parse_annual_passenger_workbook


FIXTURES = Path(__file__).parent / "fixtures" / "afac"


def _fact(
    facts: list[dict[str, object]],
    *,
    carrier: str,
    month: int,
    market: str,
    service_type: str,
) -> dict[str, object]:
    matches = [
        row
        for row in facts
        if row["source_carrier_name"] == carrier
        and row["month"] == month
        and row["market"] == market
        and row["service_type"] == service_type
    ]
    assert len(matches) == 1
    return matches[0]


def test_legacy_xls_family_parses_and_reconciles_totals() -> None:
    path = FIXTURES / "afac_1992_legacy.xls"
    _validate_payload(path.read_bytes(), "xls", "https://www.gob.mx/example.xls")

    facts, checks = parse_annual_passenger_workbook(path, 1992)

    assert facts
    assert checks
    assert max(float(row["relative_difference"]) for row in checks) == 0.0
    assert _fact(
        facts,
        carrier="Aeroméxico (Aerovías de México)",
        month=1,
        market="domestic",
        service_type="scheduled",
    )["value"] == 427_833
    assert not any(
        str(row["source_carrier_name"]).startswith("Total Estadounidenses")
        for row in facts
    )


def test_modern_xlsx_family_parses_and_reconciles_totals() -> None:
    path = FIXTURES / "afac_2015_modern.xlsx"
    _validate_payload(path.read_bytes(), "xlsx", "https://www.gob.mx/example.xlsx")

    facts, checks = parse_annual_passenger_workbook(path, 2015)

    assert facts
    assert checks
    assert max(float(row["relative_difference"]) for row in checks) == 0.0
    assert _fact(
        facts,
        carrier="Aeroméxico Connect (Aerolitoral)",
        month=1,
        market="domestic",
        service_type="scheduled",
    )["value"] == 564_172


def test_datatur_catalog_repairs_truncated_pdf_extension() -> None:
    html = b"""
    <a href='/Documentoscompartidos/afac/AFAC_2025_12.pd'>December</a>
    <a href='https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2026_01.pdf'>January</a>
    """

    artifacts = parse_datatur_catalog(html)

    assert [artifact.period_id for artifact in artifacts] == ["2025M12", "2026M01"]
    assert artifacts[0].source_url.endswith("AFAC_2025_12.pdf")


def test_live_catalog_browser_inventory_covers_2012_through_2025() -> None:
    assert sorted(CURRENT_ANNUAL_DOWNLOADS) == list(range(2012, 2026))
    assert all(
        url.startswith("https://www.gob.mx/cms/uploads/attachment/file/")
        for _, url in CURRENT_ANNUAL_DOWNLOADS.values()
    )

"""Monthly/YTD airport and group scopes reconcile independently."""

import pytest

from src.source_updates import oma_traffic as source

ORIGINAL = {
    "source_system": "oma_ir",
    "source_file": "oma.pdf",
    "sha256": "a" * 64,
    "downloaded_at": "2026-08-21T00:16:49Z",
}


def text():
    header = "Jul-2025 Jul-2026 Change % Jan-Jul\n2025\nJan-Jul\n2026 Change %\n"
    first = (
        "Grupo Aeroportuario del Centro Norte in July 2026\nMexico City, Mexico, August 5, 2026—report\n"
        + source.NOTE
        + "\n"
    )
    first += (
        header
        + "Domestic 13 13 0.0 91 91 0.0\nInternational 13 13 0.0 91 91 0.0\nOMA Total 26 26 0.0 182 182 0.0\n"
    )
    names = [
        "Acapulco",
        "Ciudad Juárez",
        "Culiacán",
        "Chihuahua",
        "Durango",
        "Mazatlán",
        "Monterrey",
        "Reynosa",
        "San Luis Potosí",
        "Tampico",
        "Torreón",
        "Zacatecas",
        "Zihuatanejo",
    ]
    for factor in [2, 1, 1]:
        first += (
            header
            + "\n".join(f"{name} {factor} {factor} 0.0 {factor * 7} {factor * 7} 0.0" for name in names)
            + f"\nOMA Total {factor * 13} {factor * 13} 0.0 {factor * 91} {factor * 91} 0.0\n"
        )
    return first


def parsed(monkeypatch, content):
    page = type("Page", (), {"extract_text": lambda _: content})()
    monkeypatch.setattr(
        source,
        "PdfReader",
        lambda _: type("PDF", (), {"pages": [page, type("Blank", (), {"extract_text": lambda _: ""})()]})(),
    )
    return source.parse({"pdf": (b"%PDF-test", ORIGINAL)}, "2026M07")


def test_reported_airport_group_and_ytd_are_separate(monkeypatch):
    f, r = parsed(monkeypatch, text())
    assert len(f) == 168 and r["reconciliations"] == 80 and r["airports"] == 13
    assert f.carrier_key.isna().all()
    assert set(f.period_type) == {"month", "year_to_date"}
    assert r["transit_excluded"] and r["commercial_charter_general_aviation_included"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda t: t.replace("Acapulco 2 2", "Acapulco 2 3", 1),
        lambda t: t.replace("Acapulco 2 2", "Acapulco 0,,2 2", 1),
        lambda t: t.replace("Acapulco 2 2 0.0 14 14 0.0\n", "", 1),
        lambda t: t.replace("Jul-2026", "Aug-2026", 1),
        lambda t: t.replace(source.NOTE, "Transit included"),
        lambda t: t.replace("OMA Total 26 26 0.0 182 182", "OMA Total 26 26 0.0 183 182", 1),
        lambda t: t.replace(
            "Acapulco 2 2 0.0 14 14 0.0", "Acapulco 2 2 0.0 14 14 0.0\nAcapulco 2 2 0.0 14 14 0.0", 1
        ),
    ],
)
def test_oma_changed_units_period_native_domain_and_totals_block(monkeypatch, edit):
    with pytest.raises(ValueError):
        parsed(monkeypatch, edit(text()))

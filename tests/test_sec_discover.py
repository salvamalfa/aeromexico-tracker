from __future__ import annotations

import pytest

from src.ingest.sec.discover import _rows_from_columnar, classify_6k


def test_classify_6k_earnings_over_traffic_metrics() -> None:
    category, confidence, reasons = classify_6k(
        """
        <html><body>First quarter financial results. Total operating revenue,
        adjusted EBITDAR, CASM and traffic results are discussed below.</body></html>
        """
    )

    assert category == "earnings"
    assert confidence >= 0.75
    assert "financial results" in reasons


def test_classify_6k_traffic() -> None:
    category, confidence, reasons = classify_6k(
        "Aeromexico presents its monthly traffic report, passenger traffic and "
        "passengers carried for June."
    )

    assert category == "traffic"
    assert confidence >= 0.69
    assert len(reasons) >= 2


def test_classify_6k_traffic_accepts_unambiguous_release_title() -> None:
    category, confidence, reasons = classify_6k(
        "Aeromexico April 2026 Traffic Results"
    )

    assert category == "traffic"
    assert confidence >= 0.62
    assert reasons == ["traffic results"]


def test_classify_6k_unknown_defaults_to_material_event() -> None:
    assert classify_6k("Notice concerning an agreement") == (
        "material_event",
        0.5,
        [],
    )


def test_classify_6k_accepts_preextracted_text_from_multiple_documents() -> None:
    category, _, reasons = classify_6k(
        "Filing cover page\nFirst quarter financial results with adjusted "
        "EBITDAR and CASM."
    )

    assert category == "earnings"
    assert {"financial results", "ebitdar", "casm"}.issubset(reasons)


def test_rows_from_columnar_rejects_mismatched_arrays() -> None:
    with pytest.raises(ValueError, match="inconsistent lengths"):
        _rows_from_columnar({"a": [1, 2], "b": [3]})


def test_rows_from_columnar_preserves_parallel_values() -> None:
    assert _rows_from_columnar({"a": [1, 2], "b": ["x", "y"]}) == [
        {"a": 1, "b": "x"},
        {"a": 2, "b": "y"},
    ]

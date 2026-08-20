from __future__ import annotations

import pytest

from src.ingest.sec.download import (
    accession_without_dashes,
    filing_document_url,
    filing_index_url,
)


def test_sec_archive_urls_are_canonical() -> None:
    accession = "0001193125-26-171463"

    assert accession_without_dashes(accession) == "000119312526171463"
    assert filing_index_url(accession).endswith("/000119312526171463/index.json")
    assert filing_document_url(accession, "ex-99_1.htm").endswith("/ex-99_1.htm")


@pytest.mark.parametrize("accession", ["", "123", "0001193125/26/171463"])
def test_invalid_accession_is_rejected(accession: str) -> None:
    with pytest.raises(ValueError, match="Invalid SEC accession"):
        accession_without_dashes(accession)


def test_archive_filename_cannot_escape_directory() -> None:
    with pytest.raises(ValueError, match="Unsafe SEC archive filename"):
        filing_document_url("0001193125-26-171463", "../secret.txt")

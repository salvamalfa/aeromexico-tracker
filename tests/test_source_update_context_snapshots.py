"""Reference snapshots preserve native labels, signed markers and dated scope."""

from contextlib import nullcontext
import csv
import io

import pytest

from src.source_updates import context_snapshots as source

ORIGINAL = {
    "source_system": "loughran_mcdonald",
    "source_file": "dictionary.csv",
    "sha256": "a" * 64,
    "downloaded_at": "2026-08-24T04:54:39Z",
}


def dictionary(rows=None):
    default = {field: "0" for field in source.FIELDS}
    default.update(
        Word="NA",
        Seq_num="0",
        Source="12of12inf",
        Negative="-2020",
        Positive="2009",
        Syllables="1",
        **{
            "Word Count": "814",
            "Word Proportion": "0.0001",
            "Average Proportion": "0.00001",
            "Std Dev": "0.00002",
            "Doc Count": "158",
        },
    )
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=source.FIELDS)
    writer.writeheader()
    writer.writerows(rows if rows is not None else [default])
    return {"csv": (stream.getvalue().encode(), ORIGINAL)}, default


def test_literal_na_word_and_signed_category_years_preserved_without_scoring():
    inputs, _ = dictionary()
    f, r = source.dictionary(inputs, "2026Q3")
    assert f.Word.tolist() == ["NA"] and f.Negative.tolist() == [-2020] and f.Positive.tolist() == [2009]
    assert f.value.tolist() == [814] and f.unit.tolist() == ["reference_corpus_occurrences"]
    assert r["zero_sequence_entries"] == 1 and not r["tone_recalculated"]
    assert f.period_type.eq("reference_snapshot").all() and r["months_validated"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("Word", ""),
        ("Negative", "True"),
        ("Negative", "-1"),
        ("Word Count", ""),
        ("Seq_num", "1.5"),
        ("Std Dev", "NaN"),
        ("Word Proportion", "2"),
        ("Source", ""),
    ],
)
def test_dictionary_invalid_native_fields_do_not_get_filled(field, value):
    _, row = dictionary()
    row[field] = value
    with pytest.raises(ValueError):
        source.dictionary(dictionary([row])[0], "2026Q3")


def test_repeated_zero_sequence_is_retained_but_duplicate_words_block():
    _, row = dictionary()
    second = {**row, "Word": "NEWWORD"}
    f, r = source.dictionary(dictionary([row, second])[0], "2026Q3")
    assert len(f) == 2 and r["zero_sequence_entries"] == 2
    with pytest.raises(ValueError):
        source.dictionary(dictionary([row, row])[0], "2026Q3")


def test_iasa_wrapped_country_labels_and_authority_group_are_not_split():
    values = source.column(
        "Mexico 1\n"
        + source.OECS
        + "\nUnited Kingdom incl. Anguilla, British Virgin\nIslands, Montserrat, Turks and Caicos 1"
    )
    assert len(values) == 3 and values[1] == (source.OECS_LABEL, 2)
    with pytest.raises(ValueError):
        source.column("Mexico\n1")
    with pytest.raises(ValueError):
        source.column("Mexico 3")


def mock_iasa(monkeypatch, category=1, count=84, extra=False):
    header = "4/18/2025 FAA Flight Standards Service\nAlvarez:R119 International Aviation Safety Assessment (IASA) Program\nCOUNTRY CATEGORY COUNTRY CATEGORY"
    footer = (
        "Category rating definitions are located at: https://www.faa.gov/about/initiatives/iasa/definitions"
    )
    labels = ["Country" + chr(65 + i // 26) + chr(65 + i % 26) + " 1" for i in range(count - 1)] + [
        f"Mexico {category}"
    ]
    tables = [
        [
            [header, None, None],
            ["\n".join(labels[:42]), "", "\n".join(labels[42:])],
            [None, None, ""],
            [None, None, ""],
            [footer, None, None],
        ]
    ]
    if extra:
        tables[0][2] = ["Unexpectedcountry 2", None, "Ignoredcountry 2"]
    page = type(
        "Page", (), {"extract_text": lambda _: header + "\n" + footer, "extract_tables": lambda _: tables}
    )()
    monkeypatch.setattr(
        source.pdfplumber, "open", lambda _: nullcontext(type("PDF", (), {"pages": [page]})())
    )


def test_iasa_document_date_remains_2025_despite_later_capture(monkeypatch):
    mock_iasa(monkeypatch)
    f, r = source.iasa(
        {"pdf": (b"%PDF-test", {**ORIGINAL, "source_system": "faa_iasa", "source_file": "iasa.pdf"})},
        "2026Q3",
    )
    assert len(f) == 84 and r["document_date_as_reported"] == "2025-04-18"
    assert r["published_at"] is None and not r["airline_rating_inferred"]


def test_changed_mexico_category_requires_explicit_review(monkeypatch):
    mock_iasa(monkeypatch, category=2)
    with pytest.raises(ValueError, match="requires review"):
        source.iasa({"pdf": (b"%PDF-test", ORIGINAL)}, "2026Q3")


@pytest.mark.parametrize("count,extra", [(2, False), (84, True)])
def test_iasa_truncated_coverage_and_unconsumed_table_cells_block(monkeypatch, count, extra):
    mock_iasa(monkeypatch, count=count, extra=extra)
    with pytest.raises(ValueError):
        source.iasa({"pdf": (b"%PDF-test", ORIGINAL)}, "2026Q3")


def test_dictionary_huge_sequence_cannot_expand_an_unbounded_gap_set():
    _, row = dictionary()
    row["Seq_num"] = str(2**53 - 1)
    with pytest.raises(ValueError, match="sequence exceeds"):
        source.dictionary(dictionary([row])[0], "2026Q3")

"""Versioned retained IASA categories and dictionary entries; no safety/tone inference."""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import io
import re

import pandas as pd
import pdfplumber

VERSION = "retained_context_snapshots_v1"
TABLES = {"iasa": "fact_iasa_retained_categories", "dictionary": "dim_retained_financial_dictionary"}
GRAINS = {"iasa": ["country_or_authority_as_reported"], "dictionary": ["Word"]}
FIELDS = [
    "Word",
    "Seq_num",
    "Word Count",
    "Word Proportion",
    "Average Proportion",
    "Std Dev",
    "Doc Count",
    "Negative",
    "Positive",
    "Uncertainty",
    "Litigious",
    "Strong_Modal",
    "Weak_Modal",
    "Constraining",
    "Complexity",
    "Syllables",
    "Source",
]
OECS = "Organization of Eastern Caribbean States - 2\nEastern Caribbean Civil Aviation Authority\nmembers : Antigua & Barbuda, Dominica,\nGrenada, St. Lucia, St. Vincent and The\nGrenadines, St. Kitts and Nevis"
OECS_LABEL = "Organization of Eastern Caribbean States - Eastern Caribbean Civil Aviation Authority members : Antigua & Barbuda, Dominica, Grenada, St. Lucia, St. Vincent and The Grenadines, St. Kitts and Nevis"


def base(original, locator, metric, value, unit):
    return dict(
        period_id="snapshot_sha256:" + original["sha256"],
        period_type="reference_snapshot",
        metric_key=metric,
        value=value,
        unit=unit,
        source_system=original["source_system"],
        source_file=original["source_file"],
        source_hash=original["sha256"],
        ingested_at=pd.Timestamp(original["downloaded_at"]),
        source_locator=locator,
        parser_version=VERSION,
        agent_eligible=False,
    )


def result(frame, scope, **details):
    return frame, dict(
        rows=len(frame),
        months_validated=[],
        published_at=None,
        release_lag_days=None,
        scope=scope,
        reference_version_basis="exact_original_SHA256_not_calendar_period",
        **details,
    )


def column(text):
    # Two wrapped source labels have reviewed structure. Keep the authority group
    # intact rather than inventing individual-country ratings for its members.
    text = text.replace(OECS, OECS_LABEL + " 2")
    text = text.replace(
        "United Kingdom incl. Anguilla, British Virgin\nIslands, Montserrat, Turks and Caicos 1",
        "United Kingdom incl. Anguilla, British Virgin Islands, Montserrat, Turks and Caicos 1",
    )
    output = []
    for line in text.splitlines():
        match = re.fullmatch(r"(.+?) ([12])", line.strip())
        if not match or not re.fullmatch(r"[A-Za-z][A-Za-z.,& :\-]+", match[1]):
            raise ValueError("IASA country/category row changed or incomplete")
        output.append((match[1], int(match[2])))
    if not output or len(output) > 100 or len({label for label, _ in output}) != len(output):
        raise ValueError("IASA native geography labels duplicated or empty")
    return output


def iasa(inputs, period):
    content, original = inputs["pdf"]
    if len(content) > 1_000_000 or not content.startswith(b"%PDF-"):
        raise ValueError("IASA PDF outside reviewed bound")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError("IASA page contract changed")
        text = pdf.pages[0].extract_text() or ""
        date = re.match(r"(\d{1,2}/\d{1,2}/20\d{2}) FAA Flight Standards Service", text)
        if (
            not date
            or "International Aviation Safety Assessment (IASA) Program" not in text
            or "Category rating definitions are located at: https://www.faa.gov/about/initiatives/iasa/definitions"
            not in text
        ):
            raise ValueError("IASA issuer, edition date or definitions reference changed")
        document_date = datetime.strptime(date[1], "%m/%d/%Y").date().isoformat()
        if document_date != "2025-04-18":
            raise ValueError("New IASA document edition requires source layout/coverage review")
        tables = pdf.pages[0].extract_tables()
        if (
            len(tables) != 1
            or len(tables[0]) != 5
            or len(tables[0][1]) != 3
            or tables[0][1][1] != ""
            or tables[0][0][0].count("COUNTRY CATEGORY") != 2
            or tables[0][0][1:] != [None, None]
            or tables[0][2] != [None, None, ""]
            or tables[0][3] != [None, None, ""]
            or tables[0][4]
            != [
                "Category rating definitions are located at: https://www.faa.gov/about/initiatives/iasa/definitions",
                None,
                None,
            ]
        ):
            raise ValueError("IASA two-column table layout changed")
        rows = []
        for side, index in [("left", 0), ("right", 2)]:
            for n, (country, category) in enumerate(column(tables[0][1][index]), 1):
                rows.append(
                    {
                        **base(
                            original,
                            f"page:1/table:1/{side}/entry:{n}",
                            "iasa_category_as_reported",
                            category,
                            "category_code",
                        ),
                        "country_or_authority_as_reported": country,
                        "document_date_as_reported": document_date,
                        "geography_kind": "authority_group"
                        if country == OECS_LABEL
                        else "country_label_including_listed_dependencies",
                        "interpretation": "FAA IASA category literal; country/authority oversight context, not airline safety rating or causal effect",
                    }
                )
    frame = pd.DataFrame(rows)
    if len(frame) != 84 or frame.duplicated(GRAINS["iasa"]).any():
        raise ValueError("IASA duplicate source country/authority")
    if frame.loc[frame.country_or_authority_as_reported.eq("Mexico"), "value"].tolist() != [1]:
        raise ValueError("Mexico category changed; requires review of new source snapshot")
    return result(
        frame,
        "retained_FAA_IASA_country_or_authority_categories_only",
        document_date_as_reported=document_date,
        current_validity_not_inferred=True,
        airline_rating_inferred=False,
    )


def numeric(token, *, integer=False, signed_year=False):
    if token is None or token == "":
        raise ValueError("Dictionary missing numeric reference field")
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError("Dictionary numeric token invalid") from exc
    if not value.is_finite() or abs(value) > 2**53 - 1 or (integer and value != value.to_integral_value()):
        raise ValueError("Dictionary numeric value not representable")
    if signed_year:
        if value and not 1900 <= abs(value) <= 2100:
            raise ValueError("Dictionary category marker changed; retain signed years")
    elif value < 0:
        raise ValueError("Dictionary nonnegative reference statistic invalid")
    return int(value) if integer else float(value)


def dictionary(inputs, period):
    content, original = inputs["csv"]
    if not 1 <= len(content) <= 15_000_000:
        raise ValueError("Dictionary source exceeds reviewed bound")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="strict")))
    if reader.fieldnames != FIELDS:
        raise ValueError("Dictionary field contract changed")
    output = []
    words = set()
    sequences = set()
    for index, row in enumerate(reader, 1):
        if index > 100_000 or None in row or any(v is None for v in row.values()):
            raise ValueError("Dictionary truncated/oversized CSV")
        word = row["Word"]
        if not re.fullmatch(r"[A-Z]+", word) or word in words or not row["Source"]:
            raise ValueError("Missing/duplicate dictionary word or lexical source")
        words.add(word)
        converted = dict(row)
        for field in FIELDS[1:-1]:
            converted[field] = numeric(
                row[field],
                integer=field not in {"Word Proportion", "Average Proportion", "Std Dev"},
                signed_year=field in FIELDS[7:15],
            )
        sequence = converted["Seq_num"]
        if sequence > 100_000:
            raise ValueError("Dictionary sequence exceeds reviewed bound")
        if sequence and sequence in sequences:
            raise ValueError("Duplicate positive dictionary sequence")
        sequences.add(sequence)
        if any(converted[field] > 1 for field in ["Word Proportion", "Average Proportion", "Std Dev"]):
            raise ValueError("Dictionary proportion outside reference range")
        output.append(
            {
                **converted,
                **base(
                    original,
                    f"record:{index}",
                    "reference_corpus_word_count",
                    converted["Word Count"],
                    "reference_corpus_occurrences",
                ),
                "interpretation": "Versioned dictionary entry and reference-corpus statistics; signed category-year markers retained without boolean conversion; no company sentiment score",
            }
        )
    if not output:
        raise ValueError("Dictionary is empty")
    frame = pd.DataFrame(output)
    return result(
        frame,
        "retained_Loughran_McDonald_full_dictionary_snapshot_not_company_tone",
        words=len(frame),
        signed_category_markers_preserved=True,
        tone_recalculated=False,
        dictionary_semantic_version=None,
        zero_sequence_entries=int(frame.Seq_num.eq(0).sum()),
        positive_sequence_gaps=sorted(set(range(1, max(sequences) + 1)) - sequences),
        sequence_number_is_not_native_grain=True,
    )

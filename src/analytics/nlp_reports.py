"""Descriptive language analysis of SEC report text."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from src.common.storage import find_bronze_by_source_url
from src.config import PATHS
from src.ingest.nlp.loughran_mcdonald import SOURCE_URL


WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b")
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,.%$]*")
SENTENCE_RE = re.compile(r"[.!?]+")
PASSIVE_RE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b", re.I)


def _dictionary() -> dict[str, set[str]]:
    existing = find_bronze_by_source_url(SOURCE_URL)
    if not existing:
        raise FileNotFoundError("Official Loughran-McDonald dictionary is absent from bronze")
    frame = pd.read_csv(existing[0])
    categories = {
        "positive": "Positive", "negative": "Negative", "uncertainty": "Uncertainty",
        "litigious": "Litigious", "constraining": "Constraining",
    }
    return {
        name: set(frame.loc[pd.to_numeric(frame[column], errors="coerce").gt(0), "Word"].str.lower())
        for name, column in categories.items()
    }


def _syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _metrics(text: str, lexicon: dict[str, set[str]]) -> dict[str, float | int]:
    tokens = [token.lower() for token in WORD_RE.findall(text)]
    sentences = max(len(SENTENCE_RE.findall(text)), 1)
    syllables = sum(_syllables(token) for token in tokens)
    words = max(len(tokens), 1)
    readability = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    metrics: dict[str, float | int] = {
        "word_count": len(tokens),
        "readability_score": float(readability),
        "passive_ratio": len(PASSIVE_RE.findall(text)) / sentences,
        "numeric_density": len(NUMBER_RE.findall(text)) / max(len(tokens) + len(NUMBER_RE.findall(text)), 1),
    }
    for category, words_set in lexicon.items():
        metrics[f"lm_{category}_ratio"] = sum(token in words_set for token in tokens) / words
    return metrics


def run_nlp() -> tuple[pd.DataFrame, dict[str, object]]:
    reports = pd.read_parquet(PATHS.silver / "sec_report_text.parquet").sort_values(["report_type", "period_id"])
    lexicon = _dictionary()
    vectorizer = TfidfVectorizer(stop_words="english", token_pattern=r"(?u)\b[A-Za-z][A-Za-z'-]{2,}\b", max_features=1200)
    matrix = vectorizer.fit_transform(reports["text"].fillna(""))
    terms = np.asarray(vectorizer.get_feature_names_out())
    top_terms: dict[int, list[str]] = {}
    for row_index in range(matrix.shape[0]):
        scores = matrix.getrow(row_index).toarray().ravel()
        indices = np.argsort(scores)[::-1]
        top_terms[row_index] = [str(terms[index]) for index in indices[:12] if scores[index] > 0]

    prior_terms: dict[str, set[str]] = {}
    rows: list[dict[str, object]] = []
    for row_index, row in enumerate(reports.itertuples(index=False)):
        text = str(row.text)
        metrics = _metrics(text, lexicon)
        meaningful = {
            token.lower() for token in WORD_RE.findall(text)
            if len(token) >= 4 and token.lower() not in ENGLISH_STOP_WORDS
        }
        previous = prior_terms.get(row.report_type, set())
        new_terms = sorted(meaningful - previous)[:40] if previous else []
        dropped_terms = sorted(previous - meaningful)[:40] if previous else []
        prior_terms[row.report_type] = meaningful
        rows.append(
            {
                "carrier_key": row.carrier_key,
                "period_id": row.period_id,
                "accession_number": row.accession_number,
                "section": row.section,
                "report_type": row.report_type,
                **metrics,
                "top_terms_json": json.dumps(top_terms[row_index], ensure_ascii=False),
                "new_terms_json": json.dumps(new_terms, ensure_ascii=False),
                "dropped_terms_json": json.dumps(dropped_terms, ensure_ascii=False),
                "source_file": row.source_file,
                "source_hash": row.source_hash,
            }
        )
    output = pd.DataFrame(rows)
    metadata = {
        "documents": len(output),
        "carriers": sorted(output["carrier_key"].unique()),
        "peer_comparison_status": "unavailable",
        "peer_comparison_reason": "Volaris and Delta operating facts are available, but their report text was not ingested; no language metrics were fabricated.",
        "limitations": [
            "Small corpus; findings are indicative rather than statistical.",
            "Loughran-McDonald is calibrated mainly on US 10-K filings, not Mexican FPI releases.",
            "Language description does not infer management intent.",
            "Passive voice is an English heuristic, not a full syntactic parse.",
        ],
    }
    return output, metadata


if __name__ == "__main__":
    frame, metadata = run_nlp()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(frame[["period_id", "report_type", "word_count", "lm_negative_ratio"]].to_string(index=False))

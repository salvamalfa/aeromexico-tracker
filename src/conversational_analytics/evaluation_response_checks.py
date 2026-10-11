"""Response-level semantic tripwires shared by offline and live evaluation."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


def _quarter_parts(term: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(20\d{2})\s*[-–—_/ ]?\s*[qQ]\s*([1-4])\s*", term)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.fullmatch(r"\s*[qQ]\s*([1-4])\s*[-–—_/ ]+\s*(20\d{2})\s*", term)
    if match:
        return int(match.group(2)), int(match.group(1))
    match = re.fullmatch(r"\s*([1-4])\s*[tT]\s*(20\d{2}|\d{2})\s*", term)
    if match:
        year = int(match.group(2))
        return (year if year > 99 else 2000 + year), int(match.group(1))
    return None


def _quarter_patterns(year: int, quarter: int) -> tuple[str, ...]:
    yy = str(year)[-2:]
    names_es = ("primer", "segundo", "tercer", "cuarto")
    names_en = ("first", "second", "third", "fourth")
    return (
        rf"\b{year}\s*[-–—_/ ]?\s*[qQ]\s*{quarter}\b",
        rf"\b[qQ]\s*{quarter}\s*[-–—_/ ]+\s*{year}\b",
        rf"\b{quarter}\s*[qQ]\s*{yy}\b",
        rf"\b{quarter}\s*[qQ]\s*{year}\b",
        rf"\b{quarter}\s*[tT]\s*{yy}\b",
        rf"\b{quarter}\s*[tT]\s*{year}\b",
        rf"\b[tT]\s*{quarter}\s*[-–—_/ ]+\s*{year}\b",
        rf"\b{names_es[quarter - 1]}\s+trimestre\s+(?:de\s+)?{year}\b",
        rf"\b{names_en[quarter - 1]}\s+quarter\s+(?:of\s+)?{year}\b",
    )


def _quarter_alias_present(year: int, quarter: int, response: str) -> bool:
    return any(
        re.search(pattern, response, re.IGNORECASE)
        for pattern in _quarter_patterns(year, quarter)
    )


def _normalized_decimal(value: str) -> Decimal | None:
    """Read common decimal and thousands separators without changing value."""
    text = value.strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        decimal_mark = "." if text.rfind(".") > text.rfind(",") else ","
        thousands_mark = "," if decimal_mark == "." else "."
        text = text.replace(thousands_mark, "").replace(decimal_mark, ".")
    elif "," in text:
        chunks = text.split(",")
        if len(chunks) > 1 and all(len(part) == 3 for part in chunks[1:]):
            text = "".join(chunks)
        else:
            text = text.replace(",", ".")
    elif text.count(".") > 1:
        chunks = text.split(".")
        text = "".join(chunks) if all(len(part) == 3 for part in chunks[1:]) else text
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def response_term_present(term: str, response: str) -> bool:
    """Match exact terms plus common decimal and bilingual quarter formatting."""
    percent = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*%\s*", term)
    if percent:
        try:
            expected = Decimal(percent.group(1).replace(",", "."))
        except InvalidOperation:
            return False
        for match in re.finditer(
            r"(?<![\w.])([+-]?\d+(?:[.,]\d+)?)\s*(?:%|por\s+ciento|percent)(?!\w)",
            response,
            re.IGNORECASE,
        ):
            try:
                if Decimal(match.group(1).replace(",", ".")) == expected:
                    return True
            except InvalidOperation:
                continue
        return False
    quarter = _quarter_parts(term)
    if quarter:
        return _quarter_alias_present(quarter[0], quarter[1], response)
    if re.fullmatch(r"\s*[+-]?[\d., ]+\s*", term):
        expected_number = _normalized_decimal(term)
        if expected_number is None:
            return False
        for match in re.finditer(r"(?<!\w)[+-]?\d[\d., ]*(?:\d)?(?!\w)", response):
            if _normalized_decimal(match.group(0)) == expected_number:
                return True
        return False
    return term.casefold() in response.casefold()


def has_unexpected_numeric_claim(
    response: str, *, allowed_numbers: list[float], allowed_periods: list[str]
) -> bool:
    """Reject ungrounded numbers and period labels outside configured evidence."""
    allowed_quarters = {parts for term in allowed_periods if (parts := _quarter_parts(term))}
    quarter_labels = re.finditer(
        r"(?<!\w)(?:20\d{2}\s*[qQ]\s*[1-4]"
        r"|[1-4]\s*[qQtT]\s*(?:20\d{2}|\d{2})"
        r"|[tT]\s*[1-4]\s*[-_/ ]+\s*20\d{2})(?!\w)",
        response,
    )
    if any(_quarter_parts(match.group(0)) not in allowed_quarters for match in quarter_labels):
        return True
    without_periods = response
    for term in allowed_periods:
        parts = _quarter_parts(term)
        if parts:
            for pattern in _quarter_patterns(*parts):
                without_periods = re.sub(pattern, " ", without_periods, flags=re.IGNORECASE)
    allowed = {Decimal(str(value)) for value in allowed_numbers}
    for match in re.finditer(r"(?<!\w)[+-]?\d[\d.,]*(?!\w)", without_periods):
        value = _normalized_decimal(match.group(0))
        if value is None or value not in allowed:
            return True
    return False


def response_attribution_failures(response: str, rules: list[dict[str, Any]]) -> list[str]:
    """Check source attribution and count bounds defined by derived fixture rules."""
    failures: list[str] = []
    sentences = [
        sentence.strip()
        for sentence in re.split(r"[.!?;\n]+", response)
        if sentence.strip()
    ]
    for rule in rules:
        value_sentences = [
            sentence for sentence in sentences if response_term_present(rule["value_term"], sentence)
        ]
        source_terms = rule.get("required_same_sentence_terms", [])
        if any(
            not all(term.casefold() in sentence.casefold() for term in source_terms)
            for sentence in value_sentences
        ):
            failures.append(
                rule.get("missing_attribution_failure", "numeric_value_missing_source_attribution")
            )
        for pattern in rule.get("forbidden_patterns", []):
            if any(re.search(pattern, sentence, re.IGNORECASE) for sentence in value_sentences):
                failures.append(
                    rule.get("wrong_attribution_failure", "numeric_value_attributed_to_wrong_source")
                )
                break
        count_pattern = rule.get("count_unit_pattern")
        if count_pattern:
            expected_count = Decimal(str(rule["expected_count"]))
            for match in re.finditer(count_pattern, response, re.IGNORECASE):
                actual_count = _normalized_decimal(match.group(1))
                if actual_count is None or actual_count != expected_count:
                    failures.append(rule.get("unexpected_count_failure", "unexpected_passenger_count"))
                    break
    return failures

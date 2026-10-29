"""Fail closed parsing of the explicit Viva 2026Q2/Q3 dossiers with prior-edition support."""

from __future__ import annotations

import io
import re
from decimal import Decimal

import pandas as pd
from pypdf import PdfReader

from src.source_updates.viva_financial_spec import (
    BALANCE,
    CASH,
    DEBT,
    FLEET,
    GRAIN,
    INCOME,
    INDICATORS,
    VERSION,
    profile,
)

NUMBER = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
TOKEN = NUMBER + r"[%x]?"
VAR = r"(?:" + NUMBER + r"(?:%|pp|x)|N/A)"
ENTITY = "Grupo Viva Aerobus, S.A. de C.V. and Subsidiaries"


def norm(text):
    return " ".join(text.replace("“", '"').replace("”", '"').split())


def amount(token):
    if not re.fullmatch(TOKEN, token):
        raise ValueError("Viva financial invalid numeric grouping or unit token")
    value = Decimal(token.rstrip("%x").replace(",", ""))
    if not value.is_finite() or abs(value) > 2**53 - 1:
        raise ValueError("Viva financial value outside finite exactness bound")
    return value


def ordered(block, definitions, columns=2, *, variation=True):
    """Consume every numeric row, including duplicate labels in their exact section order."""
    text = norm(block)
    result = []
    for label, key, unit, scale, segment in definitions:
        for heading in ("Traffic Metrics", "Operating Metrics", "Macro Figures"):
            if text.startswith(heading + " "):
                text = text[len(heading) :].strip()
        pattern = re.escape(label) + r"\s+" + r"\s+".join(["(" + TOKEN + ")"] * columns)
        if variation:
            pattern += r"\s+(" + VAR + ")"
        match = re.match(pattern + r"(?=\s|$)", text)
        if not match:
            raise ValueError(f"Viva financial missing, reordered, duplicate or changed row: {key}")
        tokens = match.groups()[:columns]
        for token in tokens:
            if (unit == "fraction") != token.endswith("%") or (unit == "times_ltm") != token.endswith("x"):
                raise ValueError("Viva financial percent/multiple source-unit mismatch")
        result.append((label, key, unit, scale, segment, tokens))
        text = text[match.end() :].strip()
    if text:
        raise ValueError("Viva financial unexpected or unconsumed table content")
    return result


def between(text, start, stop):
    if text.count(start) != 1 or stop is not None and text.count(stop) != 1:
        raise ValueError("Viva financial statement boundary absent or ambiguous")
    text = text.split(start, 1)[1]
    return text.split(stop, 1)[0] if stop else text


def edition(pages, original, q):
    selected = profile(q)
    if len(pages) != selected["pages"]:
        raise ValueError("Viva reviewed edition page coverage changed")
    pages = [norm(p) for p in pages]
    date, month, end = (selected[k] for k in ("date", "month", "end"))
    required = [
        f"Mexico City, {date}, 2026",
        f"announced today its {q}Q 2026 financial results.",
        "Grupo Viva Aerobus, S.A. de C.V.",
        "the parent company of Aeroenlaces Nacionales, S.A. de C.V."
        if q == 3
        else "the parent company of Aeroenlaces Nacionales S.A. de C.V.",
        "Viva’s functional and reporting currency is the U.S. Dollar.",
    ]
    if not all(s in pages[0] for s in required):
        raise ValueError("Viva edition quarter/entity/currency/printed date proof missing")
    glossary = pages[5]
    for proof in [
        '"available seat miles"',
        '"revenue passenger miles"',
        "scheduled available seat miles (ASMs)",
        "Passengers: Customers who purchased their plane ticket to fly during the month referred "
        "in the report, regardless of whether they flew or not.",
        "non-IFRS financial measure",
        "Starting October 1, 2022",
    ]:
        if proof not in glossary:
            raise ValueError("Viva source definitions missing or changed")
    if not all(
        clause in pages[2]
        for clause in (
            "IFRS 9 amendment",
            "cash in transit is classified within accounts receivable and other receivables.",
            "Prior periods have not been adjusted for comparability.",
        )
    ):
        raise ValueError("Viva cash comparability warning missing")
    output = []

    def add(statement, page, block, definitions, kind, dates, *, variation=True):
        values = ordered(block, definitions, len(dates), variation=variation)
        for index, (label, key, unit, scale, segment, tokens) in enumerate(values, 1):
            for column, (token, (start, stop)) in enumerate(zip(tokens, dates, strict=True), 1):
                raw = amount(token)
                if (
                    unit == "fraction"
                    and key not in {"operating_margin", "ebt_margin", "net_margin"}
                    and not 0 <= raw <= 100
                ):
                    raise ValueError("Viva physical/margin fraction outside source percent bounds")
                if statement in {"indicators", "debt", "fleet"} and raw < 0:
                    raise ValueError("Viva nonnegative operational/debt metric is negative")
                financial = statement in {"income", "balance", "cash_flow"}
                output.append(
                    dict(
                        edition=f"2026Q{q}",
                        statement=statement,
                        period_type=kind,
                        period_start_date=start,
                        period_end_date=stop,
                        metric_key=key,
                        segment=segment,
                        entity_as_reported=ENTITY,
                        carrier_key="VIVA_AEROBUS",
                        value=float(raw),
                        unit=unit,
                        scale=float(scale),
                        source_value=token,
                        source_label=label,
                        source_locator=f"page:{page}/{statement}/{kind}/row:{index}/column:{column}",
                        is_unaudited=True if financial else None,
                        is_preliminary=True if financial and stop.startswith("2026") else None,
                        report_date=selected["report_date"],
                        source_system=original["source_system"],
                        source_file=original["source_file"],
                        source_hash=original["sha256"],
                        ingested_at=pd.Timestamp(original["downloaded_at"]),
                        parser_version="viva_2026q3_reported_financial_dossier_v1" if q == 3 else VERSION,
                        agent_eligible=False,
                    )
                )

    def duration(page, statement, kind, count, definitions, header):
        text = pages[page - 1]
        context = f"{'Three' if kind == 'quarter' else selected['cumulative_prefix']}-month period ended {month}, 2026 and 2025"
        if ENTITY not in text or context not in text or "Thousands of U.S. Dollars" not in text:
            raise ValueError("Viva financial statement period/entity/scale heading changed")
        suffix = "(1)" if statement != "indicators" and "(1) Our consolidated" in text else None
        if statement == "indicators":
            suffix = "(1) Bloomberg"
        if statement == "cash_flow":
            # Separate the two explicit tables before recognizing their headings.
            text = between(text, context, None)
            text = text.split("During ", 1)[0]
            if q in (2, 3) and kind == "quarter":
                suffix = None
        block = between(text, header, suffix)
        dates = [
            (f"{year}-{selected['quarter_start'] if kind == 'quarter' else '01-01'}", f"{year}-{end}")
            for year in (2026, 2025)
        ]
        add(statement, page, block, definitions, kind, dates)

    indicators_header = f"Financial and Operational Indicators {q}Q 2026 {q}Q 2025 % Var"
    duration(7, "indicators", "quarter", 3, INDICATORS, indicators_header)
    income_q = 8 if q == 1 else 9
    income = list(INCOME)
    if q == 1:
        income = [
            (
                label.replace("Operating profit (loss)", "Operating loss")
                .replace("Income (loss) before income tax", "Loss before income tax")
                .replace("Net income (loss)", "Net loss"),
                *rest,
            )
            for label, *rest in income
        ]
    if q == 3:
        income = [
            (label.replace("Operating profit (loss)", "Operating profit"), *rest) for label, *rest in income
        ]
    duration(
        income_q,
        "income",
        "quarter",
        3,
        income,
        f"US$ Thousand (unaudited){'1' if q == 1 else ''} {q}Q 2026 {q}Q 2025 % Var",
    )
    if q in (2, 3):
        cumulative_kind = selected["cumulative_kind"]
        cumulative_label = selected["cumulative_label"]
        duration(
            8,
            "indicators",
            cumulative_kind,
            6 if q == 2 else 9,
            INDICATORS,
            f"Financial and Operational Indicators {cumulative_label} 2026 {cumulative_label} 2025 % Var",
        )
        half_income = [
            (
                label.replace("Income (loss) before income tax", "Loss before income tax").replace(
                    "Net income (loss)", "Net loss"
                ),
                *rest,
            )
            for label, *rest in INCOME
        ]
        duration(
            10,
            "income",
            cumulative_kind,
            6 if q == 2 else 9,
            half_income,
            f"US$ Thousand (unaudited)1 {cumulative_label} 2026 {cumulative_label} 2025 % Var",
        )
    balance_page = 9 if q == 1 else 11
    balance = pages[balance_page - 1]
    if (
        f"As of {month}, 2026 and December 31, 2025" not in balance
        or ENTITY not in balance
        or "(Thousands of U.S. Dollars)" not in balance
    ):
        raise ValueError("Viva balance instant/entity/currency scale changed")
    preliminary = f"financial statements for the period ended {month}, 2026, are not yet available."
    for page in [8, 9, 10] if q == 1 else [10, 11, 12]:
        if preliminary not in pages[page - 1] or "These figures are preliminary" not in pages[page - 1]:
            raise ValueError("Viva preliminary statement note missing")
    add(
        "balance",
        balance_page,
        between(
            balance,
            f"US$ Thousand (unaudited)1 {selected['short']} 2026 Dec 2025 % Var",
            "(1) Our consolidated",
        ),
        [
            (label.replace("Accounts receivables and other", "Accounts receivable and other"), *rest)
            for label, *rest in BALANCE
        ]
        if q == 3
        else BALANCE,
        "instant",
        [(None, f"2026-{end}"), (None, "2025-12-31")],
    )
    cash_page = 10 if q == 1 else 12
    # Each table is explicitly scoped; never derive Q2 cash flow from H1-Q1.
    if q in (2, 3):
        whole = pages[cash_page - 1]
        cut = whole.index(selected["cumulative_prefix"] + "-month period")
        quarter = whole[:cut].split("During ", 1)[0]
        saved = pages[cash_page - 1]
        pages[cash_page - 1] = quarter
        duration(
            cash_page, "cash_flow", "quarter", 3, CASH, f"US$ Thousand (unaudited) {q}Q 2026 {q}Q 2025 % Var"
        )
        pages[cash_page - 1] = saved
        duration(
            cash_page,
            "cash_flow",
            selected["cumulative_kind"],
            6 if q == 2 else 9,
            CASH,
            f"US$ Thousand (unaudited)1 {selected['cumulative_label']} 2026 {selected['cumulative_label']} 2025 % Var",
        )
    else:
        duration(
            cash_page, "cash_flow", "quarter", 3, CASH, "US$ Thousand (unaudited)1 1Q 2026 1Q 2025 % Var"
        )
    debt = pages[2]
    fleet_note = "*Total Fleet at EoP excludes short term leases (ACMIs)"
    # The reviewed Q2 PDF uses a hyphen in prose but the table footnote is unhyphenated.
    if fleet_note not in pages[2]:
        raise ValueError("Viva fleet ACMI exclusion definition missing or changed")
    dates = [(None, f"2026-{end}"), (None, "2025-12-31")]
    add(
        "debt",
        3,
        between(
            debt,
            f"US$ Million {selected['short']} 2026 Dec 2025 % Var",
            "(1) Cash and cash equivalents",
        ),
        DEBT,
        "instant",
        dates,
    )
    fleet_dates = selected["fleet_dates"]
    fleet_header = selected["fleet_header"]
    add(
        "fleet",
        3,
        between(debt, fleet_header, "*Total Fleet at EoP"),
        FLEET,
        "instant",
        fleet_dates,
        variation=False,
    )
    frame = pd.DataFrame(output)
    if frame.duplicated(GRAIN).any() or frame.value.isna().any():
        raise ValueError("Viva duplicate or missing native observations")
    return frame


def parse(inputs, period):
    if period not in {"2026Q2", "2026Q3"} or set(inputs) != {"pdf", "prior_quarter"}:
        raise ValueError("Viva financial certifier requires explicit Q2/Q3 and its prior-edition support")
    primary_q = int(period[-1])
    frames = []
    for role, q in [("pdf", primary_q), ("prior_quarter", primary_q - 1)]:
        content, original = inputs[role]
        if len(content) > 4_000_000 or not content.startswith(b"%PDF-"):
            raise ValueError("Viva financial reviewed PDF bounds exceeded")
        reader = PdfReader(io.BytesIO(content))
        frames.append(edition([p.extract_text() or "" for p in reader.pages], original, q))
    native = pd.concat(frames, ignore_index=True)
    from src.source_updates.viva_financial_checks import reconcile

    details = reconcile(native)
    return native, details

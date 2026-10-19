"""Retained AM 2026Q2 reported units, including ASM/CASM without historical ASK relabeling."""

from __future__ import annotations

from decimal import Decimal
import io
import re

import pandas as pd
from pypdf import PdfReader

from src.parse.aeromexico_ir_financial import NUMBER, STATEMENT, clean

VERSION = "am_ir_2026q2_source_units_v1"
TABLE = "fact_am_retained_quarterly_source_metrics"
GRAIN = ["period_id", "metric_key", "definition"]
PATTERNS = [
    ("adjusted_ebitdar", r"UAFIDAR ajustada\(1\)", "USD millions", "reported_company_adjusted_non_IFRS"),
    (
        "ebitdar_margin",
        r"Margen UAFIDAR ajustado\(1\) \(% de\s+ingresos\)",
        "percent",
        "reported_company_adjusted_non_IFRS",
    ),
    ("operating_margin", r"Margen de operaci.n \(% de ingresos\)", "percent", "reported"),
    ("asm", r"ASMs totales \(millones\)", "million ASM-mile", "reported_total_as_defined_by_source"),
    ("rpm", r"RPMs totales \(millones\)", "million RPM-mile", "reported_total_as_defined_by_source"),
    ("load_factor", r"Factor de ocupaci.n \(itinerario %\)", "percent", "reported_itinerary"),
    ("passengers", r"Pasajeros \('000\)", "thousand passengers", "reported_total_as_defined_by_source"),
    ("fuel_liters", r"Litros de combustible \(miles\)", "thousand liters", "reported"),
    (
        "casm_ex_fuel",
        r"Costo total excl\. combustible / ASM\s+\(centavos de USD\)",
        "USD cents per ASM-mile",
        "reported_excluding_fuel_not_CASK",
    ),
]


def value(token):
    if not re.fullmatch(
        r"(?:-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?%?|\((?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?\))", token
    ):
        raise ValueError("AM financial numeric grouping/unit token changed")
    result = Decimal(token.replace(",", "").replace("%", "").strip("()"))
    if token.startswith("("):
        result = -result
    if not result.is_finite() or abs(result) > 2**53 - 1:
        raise ValueError("AM financial value not finite/representable")
    return float(result)


def texts(plain, original, period):
    if period != "2026Q2":
        raise ValueError("Only reviewed 2026Q2 financial edition is supported")
    first = " ".join(plain[0].split())
    if not all(
        v in first
        for v in [
            "Aeroméxico reporta resultados preliminares",
            "al segundo trimestre 2026",
            "trimestre concluido el 30 de junio de 2026",
            "La Compañía ha utilizado dólares estadounidenses, su moneda funcional, como moneda de presentación para estos estados financieros consolidados.",
            "Todas las cifras están expresadas en millones de dólares estadounidenses, a menos que se indique lo contrario.",
            "asientos-milla disponibles (ASMs)",
        ]
    ):
        raise ValueError("AM financial quarter/currency/preliminary source proof missing")
    report_date = re.search(r"Ciudad de México\s*,\s*a 13 de julio de 202\s*6\s*-", first)
    if not report_date:
        raise ValueError("AM financial printed report date missing")
    statements = [
        (i, p)
        for i, p in enumerate(plain, 1)
        if "Estados Consolidados de Resultados y Otros Resultados Integrales (No Auditados)" in p
    ]
    summaries = [(i, p) for i, p in enumerate(plain, 1) if "INDICADORES FINANCIEROS Y OPERATIVOS" in p]
    if len(statements) != 1 or len(summaries) != 1:
        raise ValueError("AM current-quarter statement/summary absent or ambiguous")
    output = []

    def add(metric, pattern, unit, definition, source):
        page, text = source
        matches = list(
            re.finditer(r"^\s*(?:" + pattern + r")\s+(?P<value>" + NUMBER + r")(?=\s|$)", text, re.I | re.M)
        )
        if len(matches) != 1:
            raise ValueError("AM financial source metric row missing or duplicated")
        match = matches[0]
        label = match[0].strip()
        token = match["value"]
        prefix = " ".join(text[: match.start()].split())
        ordered = "Tres meses terminados el 30 de junio Seis meses terminados el 30 de junio"
        if ordered not in prefix or not re.search(r"2026 2025 Var\. ?%? 2026 2025 Var\.", prefix):
            raise ValueError("AM current-quarter before YTD/current-prior column order is unverified")
        if source is summaries[0]:
            section = (
                "Financieros"
                if metric in {"adjusted_ebitdar", "ebitdar_margin", "operating_margin"}
                else "Operativos"
            )
            headings = list(
                re.finditer(
                    r"Principales Indicadores (Financieros|Operativos) (20\d{2}) (20\d{2}) Var\. (20\d{2}) (20\d{2}) Var\.",
                    prefix,
                )
            )
            if not headings or headings[-1].groups() != (section, "2026", "2025", "2026", "2025"):
                raise ValueError("AM financial/operating section current-prior column order changed")
        if (unit == "percent") != token.endswith("%"):
            raise ValueError("AM financial token percent style differs from source unit")
        amount = value(token)
        if unit == "percent" and not -100 <= amount <= 100:
            raise ValueError("AM financial ratio outside source percent range")
        if metric in {"asm", "rpm", "passengers", "fuel_liters", "casm_ex_fuel"} and amount < 0:
            raise ValueError("AM physical/source cost denominator metric is negative")
        if metric == "load_factor" and not 0 <= amount <= 100:
            raise ValueError("AM itinerary load factor outside 0..100 percent")
        output.append(
            dict(
                period_id=period,
                period_type="quarter",
                metric_key=metric,
                definition=definition,
                value=amount,
                unit=unit,
                source_value=token,
                source_label=label,
                carrier_key="AEROMEXICO",
                is_preliminary=True,
                is_unaudited=True,
                not_ytd=True,
                normalized_unit_conversion_performed=False,
                source_system=original["source_system"],
                source_file=original["source_file"],
                source_hash=original["sha256"],
                ingested_at=pd.Timestamp(original["downloaded_at"]),
                source_locator=f"page:{page}/quarter-current/{metric}",
                parser_version=VERSION,
                agent_eligible=False,
            )
        )

    for metric, pattern in STATEMENT.items():
        if metric == "rent_depreciation_amortization_combined":
            continue
        if metric == "operating_expenses_total":
            pattern = r"Total gastos de operaci.n"
        add(metric, pattern, "USD millions", "reported", statements[0])
    for metric, pattern, unit, definition in PATTERNS:
        add(metric, pattern, unit, definition, summaries[0])
    frame = pd.DataFrame(output)
    if len(frame) != 20 or frame.duplicated(GRAIN).any():
        raise ValueError("AM financial metric domain changed")
    metrics = frame.set_index("metric_key").value
    if (
        abs(metrics.total_revenue - metrics.operating_expenses_total - metrics.operating_income) > 1
        or abs(metrics.income_before_tax - metrics.income_tax - metrics.net_income) > 1
    ):
        raise ValueError("AM rounded statement accounting identities disagree beyond one reported million")
    return frame, dict(
        rows=len(frame),
        report_period=period,
        months_validated=[],
        quarters_validated=[period],
        statement_accounting_checks=2,
        scope="retained_AM_2026Q2_preliminary_unaudited_reported_quarter_units_only_not_new_Q3_or_historical_harmonization",
        asm_not_ask=True,
        casm_not_cask=True,
        normalized_unit_conversion_performed=False,
        published_at=None,
        release_lag_days=None,
        source_report_date_as_reported="2026-07-13",
        printed_report_date_literal=report_date[0],
        source_preliminary=True,
        source_unaudited=True,
        ytd_columns_imported=0,
    )


def parse(inputs, period):
    content, original = inputs["pdf"]
    if len(content) > 4_000_000 or not content.startswith(b"%PDF-"):
        raise ValueError("AM financial PDF outside reviewed bound")
    pdf = PdfReader(io.BytesIO(content))
    if len(pdf.pages) != 13:
        raise ValueError("AM reviewed financial report page coverage changed")
    return texts([clean(p.extract_text() or "") for p in pdf.pages], original, period)

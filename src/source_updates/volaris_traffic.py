"""Explicitly admitted Volaris issuer traffic original; distinct from SEC financials."""

import io
import re
from datetime import date
from decimal import Decimal

import pandas as pd
from pypdf import PdfReader

from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end

ENTRY = "https://ir.volaris.com/es/informacion-financiera/reportes-de-trafico/"
PDF = (
    "https://filemanager-cdn.mziq.com/published/ea52c1bb-e8e2-457e-820a-98ca17753a37/"
    "d13b9b6b-4e2e-471f-a6db-60f23a9f2262"
)
PERIOD = "2026M09"
PRODUCT = "volaris_traffic_ir"
TABLE = "fact_volaris_ir_monthly_traffic"
VERSION = "volaris_issuer_September2026_traffic_v1"
GRAIN = ["period_id", "metric_key", "segment"]
METRICS = [
    ("RPMs (millones, itinerado y fletamento)", "rpm", "million passenger-miles", 1_000_000),
    ("ASMs (millones, itinerado y fletamento)", "asm", "million seat-miles", 1_000_000),
    ("Factor de Ocupación (%, RPMs/ASMs)", "load_factor", "percent", 1),
    ("Pasajeros (miles, itinerado y fletamento)", "passengers_booked", "thousand booked passengers", 1_000),
]
NUMBER = r"(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)"


def validate_admitted_url(url):
    # Exact strings also reject arbitrary subdomains, documents, ports, query
    # variants and redirects; catalogue allowed_hosts alone does not do that.
    if url not in {ENTRY, PDF}:
        raise ValueError("Volaris IR admits only the reviewed issuer page and exact September PDF")


def selection():
    return dict(
        version=1,
        items=[
            dict(
                id="volaris-ir-index",
                product=PRODUCT,
                source_system="volaris_ir",
                entity="volaris_traffic_catalog",
                period="current",
                purpose="catalog",
                url=ENTRY,
                extension="html",
                mode="get",
            ),
            dict(
                id="volaris-ir-september",
                product=PRODUCT,
                source_system="volaris_ir",
                entity="volaris_traffic_report",
                period=PERIOD,
                purpose="data",
                url=PDF,
                extension="pdf",
                mode="get",
                relative_dir="volaris_ir/traffic",
            ),
        ],
    )


def decimal(token):
    negative = token.startswith("(")
    value = Decimal(token.strip("()% ").replace(",", ""))
    return -value if negative else value


def comparable_warning(reference, derived, *, unit, resolution):
    """Called only after same-row source context and printed precision are checked."""
    if any(not v.is_finite() for v in (reference, derived, resolution)):
        raise ValueError("Volaris comparable values must be finite")
    if abs(reference) <= resolution:
        raise ValueError("Volaris zero/near-zero reference cannot receive automatic 5% tolerance")
    delta = derived - reference
    if abs(delta) > abs(reference) * Decimal("0.05"):
        raise ValueError("Volaris comparable difference exceeds the authorized 5%")
    return dict(
        code="comparable_derived_difference_within_5pct",
        severity="warning",
        policy_id="comparable_official_reference_5pct_v1",
        official_value_preserved=True,
        official_reported_value=str(reference),
        derived_value=str(derived),
        signed_difference=str(delta),
        absolute_difference=str(abs(delta)),
        relative_difference=str(abs(delta) / abs(reference)),
        relative_difference_pct=str(abs(delta) / abs(reference) * 100),
        tolerance_pct="5",
        reference_basis="absolute_official_reported_value",
        reference_resolution=str(resolution),
        unit=unit,
    )


def variation(current, prior, reported, *, points):
    """Same-row/same-universe change, printed precision then authorized 5% warning."""
    if points:
        derived = current - prior
        low, high = derived - Decimal("0.1"), derived + Decimal("0.1")
    else:
        if prior <= Decimal("0.5"):
            raise ValueError("Volaris growth denominator zero/near zero requires separate review")
        derived = (current / prior - 1) * 100
        low = (max(Decimal(0), current - Decimal("0.5")) / (prior + Decimal("0.5")) - 1) * 100
        high = ((current + Decimal("0.5")) / (prior - Decimal("0.5")) - 1) * 100
    if reported + Decimal("0.05") >= low and reported - Decimal("0.05") <= high:
        return None
    warning = comparable_warning(
        reported,
        derived,
        unit="percentage_points" if points else "relative_percent",
        resolution=Decimal("0.1"),
    )
    warning.update(current_reported_value=str(current), prior_reported_value=str(prior))
    return warning


def texts(pages, period, original):
    """Full48 reported values and24 variations; never label bookings as flown."""
    if (
        period != PERIOD
        or len(pages) != 2
        or original.get("source_system") != "volaris_ir"
        or original.get("source_url") != PDF
    ):
        raise ValueError("Volaris IR supports only its reviewed September2026 two-page original")
    first, glossary = [" ".join(page.split()) for page in pages]
    required = [
        "Volaris reporta resultados de tráfico de septiembre de 2026:",
        "Controladora Vuela Compañía de Aviación, S.A.B. de C.V.",
        "resultados preliminares de tráfico de septiembre de 2026.",
        "La información incluida en este reporte no ha sido auditada",
        "Las cifras están redondeadas para efectos prácticos.",
        "Septiembre 2026 Septiembre 2025 Variación Acumulado a septiembre 2026 "
        "Acumulado a septiembre 2025 Variación",
    ]
    definitions = [
        "Glosario",
        "Revenue passenger miles (RPMs): Número de asientos vendidos a pasajeros multiplicado "
        "por el número de millas voladas.",
        "Available seat miles (ASMs): Asientos disponibles multiplicados por el número de millas voladas.",
        "Factor de ocupación: Los RPMs divididos entre los ASMs y expresado en porcentaje.",
        "Pasajeros: Número total de pasajeros que han reservado en todos los segmentos de vuelo.",
    ]
    if any(first.count(v) != 1 for v in required) or any(glossary.count(v) != 1 for v in definitions):
        raise ValueError("Volaris issuer, month/year order, preliminary status, units or glossary changed")
    dates = re.findall(r"Ciudad de México, México, (\d{1,2}) de octubre de (20\d{2})", first)
    if len(dates) != 1:
        raise ValueError("Volaris document dateline absent or ambiguous")
    day = date(int(dates[0][1]), 10, int(dates[0][0]))
    if not period_end(period) < day <= local_time(original["downloaded_at"]).date():
        raise ValueError("Volaris dateline must follow report month and precede actual capture")
    table = first.split(required[-1], 1)[1].split(required[3], 1)[0].strip()
    if any(table.count(h) != 1 for h, *_ in METRICS):
        raise ValueError("Volaris table headings missing or duplicated")
    output, grid, rounding_deltas, numeric_warnings = [], {}, [], []
    for position, (heading, metric, unit, scale) in enumerate(METRICS):
        section = table.split(heading, 1)[1]
        if position + 1 < len(METRICS):
            section = section.split(METRICS[position + 1][0], 1)[0]
        percent = metric == "load_factor"
        number = r"\d{1,3}\.\d%" if percent else NUMBER
        change = r"(?:\(\d+\.\d\)|[+-]?\d+\.\d)\s*pp" if percent else r"(?:\(\d+\.\d%\)|[+-]?\d+\.\d%)"
        cells = rf"({number})\s+({number})\s+({change})\s+({number})\s+({number})\s+({change})"
        match = re.fullmatch(
            rf"\s*Doméstico\s+{cells}\s+Internacional\s+{cells}\s+Total\s+{cells}\s*", section
        )
        if not match:
            raise ValueError("Volaris requires all three six-cell rows for each of four metrics")
        native = {}
        for segment, offset in (("domestic", 0), ("international", 6), ("total", 12)):
            tokens = match.groups()[offset : offset + 6]
            values = [decimal(tokens[i]) for i in (0, 1, 3, 4)]
            if any(v < 0 or v >= 2**53 or percent and v > 100 for v in values):
                raise ValueError("Volaris reported value outside native domain")
            if not percent and (values[0] > values[2] or values[1] > values[3]):
                raise ValueError("Volaris month exceeds same-year YTD in comparable native units")
            native[segment] = values
            for column, value in enumerate(values):
                observed_year = 2026 if column % 2 == 0 else 2025
                ytd = column >= 2
                change_token = tokens[2 if column < 2 else 5] if column % 2 == 0 else None
                warning = None
                if change_token:
                    warning = variation(
                        value,
                        values[column + 1],
                        decimal(change_token.removesuffix("pp").strip()),
                        points=percent,
                    )
                    if warning:
                        warning.update(
                            product=PRODUCT,
                            entity="VOLARIS",
                            metric_key=metric,
                            segment=segment,
                            period_id=f"{observed_year}YTD09" if ytd else f"{observed_year}M09",
                            source_file=original["source_file"],
                            source_hash=original["sha256"],
                            current_and_prior_unit=unit,
                            service_scope="itinerary_and_charter",
                        )
                        numeric_warnings.append(warning)
                output.append(
                    dict(
                        period_id=f"{observed_year}YTD09" if ytd else f"{observed_year}M09",
                        period_type="year_to_date" if ytd else "month",
                        report_period=period,
                        carrier_key="VOLARIS",
                        entity_as_reported="Controladora Vuela Compañía de Aviación, S.A.B. de C.V.",
                        segment=segment,
                        metric_key=metric,
                        value=float(value),
                        unit=unit,
                        source_value=tokens[(0, 1, 3, 4)[column]],
                        scale_multiplier=scale,
                        value_normalized=float(value * scale),
                        normalized_unit="percent"
                        if percent
                        else "booked passengers"
                        if metric == "passengers_booked"
                        else "passenger-miles"
                        if metric == "rpm"
                        else "seat-miles",
                        reported_change=float(decimal(change_token.removesuffix("pp").strip()))
                        if change_token
                        else None,
                        reported_change_raw=change_token,
                        reported_change_reconciliation=(
                            "warning_within_5pct"
                            if warning
                            else "passed_printed_precision"
                            if change_token
                            else "not_applicable_prior_year"
                        ),
                        reported_change_unit="percentage_points" if percent else "relative_percent",
                        passenger_definition="booked_flight_segments_not_observed_flown_passengers",
                        flight_scope="itinerary_and_charter; load_factor_RPM_div_ASM",
                        is_preliminary=True,
                        is_unaudited=True,
                        reporting_precision="one_decimal_percent"
                        if percent
                        else "rounded_integer_native_thousands_or_millions",
                        source_system=original["source_system"],
                        source_file=original["source_file"],
                        source_hash=original["sha256"],
                        ingested_at=pd.Timestamp(original["downloaded_at"]),
                        source_page=1,
                        source_locator=f"page:1/table:{metric}/row:{segment}/column:{column}",
                        source_excerpt=match.group(0).strip(),
                        parser_version=VERSION,
                        agent_eligible=False,
                    )
                )
        for column in range(4):
            domestic, international, total = [
                native[s][column] for s in ("domestic", "international", "total")
            ]
            if not percent and abs(domestic + international - total) > Decimal("1.5"):
                warning = comparable_warning(
                    total, domestic + international, unit=unit, resolution=Decimal(1)
                )
                warning.update(
                    check="segment_total",
                    metric_key=metric,
                    column=column,
                    source_file=original["source_file"],
                    source_hash=original["sha256"],
                )
                numeric_warnings.append(warning)
            if not percent and domestic + international != total:
                rounding_deltas.append(
                    dict(
                        metric=metric,
                        column=column,
                        unit=unit,
                        reported_total=float(total),
                        component_sum=float(domestic + international),
                        difference_native_units=float(total - domestic - international),
                        status="within_printed_rounding_bound_original_values_preserved"
                        if abs(domestic + international - total) <= Decimal("1.5")
                        else "warning_within_5pct",
                    )
                )
        grid[metric] = native
    # Unlike AM/Viva's itinerary-only LF, this document defines the same RPM/ASM scope.
    for segment in ("domestic", "international", "total"):
        for column, (rpm, asm, factor) in enumerate(
            zip(grid["rpm"][segment], grid["asm"][segment], grid["load_factor"][segment], strict=True)
        ):
            if asm <= Decimal("0.5") or rpm > asm:
                raise ValueError("Volaris RPM/ASM invalid or denominator too close to zero")
            lower = max(Decimal(0), rpm - Decimal("0.5")) / (asm + Decimal("0.5")) * 100
            upper = (rpm + Decimal("0.5")) / (asm - Decimal("0.5")) * 100
            if factor + Decimal("0.05") < lower or factor - Decimal("0.05") > upper:
                warning = comparable_warning(
                    factor, rpm / asm * 100, unit="percent", resolution=Decimal("0.1")
                )
                warning.update(
                    check="load_factor_RPM_div_ASM",
                    metric_key="load_factor",
                    segment=segment,
                    column=column,
                    rpm_reported=str(rpm),
                    asm_reported=str(asm),
                    source_file=original["source_file"],
                    source_hash=original["sha256"],
                )
                numeric_warnings.append(warning)
    for warning in numeric_warnings:
        warning.update(
            product=PRODUCT,
            entity="VOLARIS",
            coverage="itinerary_and_charter",
            comparison_basis="same_verified_source_document_entity_period_units_and_definition",
        )
        if "column" in warning:
            warning["period_id"] = ("2026M09", "2025M09", "2026YTD09", "2025YTD09")[warning["column"]]
    frame = pd.DataFrame(output).sort_values(GRAIN).reset_index(drop=True)
    if len(frame) != 48 or frame.duplicated(GRAIN).any():
        raise ValueError("Volaris full48 native monthly/YTD grain incomplete")
    return frame, dict(
        rows=48,
        complete_month_certified=True,
        monthly_rows=24,
        ytd_rows=24,
        reported_variations=24,
        airports=None,
        source_report_date_as_reported=day.isoformat(),
        first_publication_date=None,
        publication_time=None,
        release_lag_days=None,
        source_preliminary=True,
        source_unaudited=True,
        native_reconciliations=48,
        reported_variation_reconciliations=24,
        numeric_warnings=numeric_warnings,
        numeric_warning_count=len(numeric_warnings),
        numeric_check_status="passed_with_warning" if numeric_warnings else "passed_printed_precision",
        numeric_policy_id="comparable_official_reference_5pct_v1",
        source_scope="authorized_Volaris_issuer_September2026_month_and_YTD_with_prior_year_not_SEC_or_AOC",
        scope="Volaris_issuer_traffic_bookings_and_miles_month_YTD_separate_not_financial_release",
        monthly_YTD_not_combined=True,
        official_values_preserved=True,
        rounding_policy=(
            "printed precision first (sums1.5 native units; ratio/change intervals), then comparable "
            "5% of absolute official reference with visible warning; zero/near-zero excluded; figures unchanged"
        ),
        rounding_reconciliation_deltas=rounding_deltas,
    )


def parse(inputs, period):
    content, original = inputs["pdf"]
    if not content.startswith(b"%PDF-") or len(content) > 2_000_000:
        raise ValueError("Volaris expected bounded genuine PDF")
    document = PdfReader(io.BytesIO(content))
    if document.is_encrypted or len(document.pages) != 2:
        raise ValueError("Volaris September PDF page/encryption contract changed")
    return texts([page.extract_text() or "" for page in document.pages], period, original)

"""Retained AICM AM-numbered slot assignments; no attribution to flights actually performed."""

from __future__ import annotations
from datetime import datetime, timedelta, date
import io
import re

import pandas as pd
import pdfplumber

VERSION = "aicm_retained_assignment_rows_v1"
TABLE = "fact_aicm_retained_slot_assignments"
FIELDS = [
    "movement_as_reported",
    "flight_number_as_reported",
    "flight_suffix_as_reported",
    "turnround_number_as_reported",
    "equipment_as_reported",
    "assigned_time_as_reported",
    "requested_time_as_reported",
    "origin_as_reported",
    "via_as_reported",
    "destination_as_reported",
    "start_as_reported",
    "end_as_reported",
    "frequency_as_reported",
    "operations_as_reported",
    "service_code_as_reported",
]
HEADERS = [
    None,
    "N° de Vuelo",
    "Sufijo",
    "N°Vuelo\nTurnround",
    "Equipo",
    "Hora Asignada",
    "Hora Solicitada",
    "Origen",
    "VIA",
    "Destino",
    "Inicio Periodo",
    "Fin Periodo",
    "Frecuencia",
    "Operaciones",
    "Carga",
]
GRAIN = FIELDS


def validate_row(row):
    if len(row) != 15 or row[0] not in {"A", "D"} or any(value is None for value in row):
        raise ValueError("Incomplete AICM assignment row")
    if not re.fullmatch(r"\d{1,5}", row[1]) or any(
        not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", row[i]) for i in [5, 6]
    ):
        raise ValueError("AICM flight number or clock changed")
    if any(value and not re.fullmatch(r"[A-Z]{3}", value) for value in row[7:10]):
        raise ValueError("AICM source airport code changed")
    counterpart = row[7] if row[0] == "A" else row[9]
    if not counterpart:
        raise ValueError("AICM directional endpoint missing")
    start, end = (datetime.strptime(row[i], "%d/%m/%Y").date() for i in [10, 11])
    if not date(2026, 3, 29) <= start <= end <= date(2026, 10, 24):
        raise ValueError("Assignment outside reviewed summer 2026 season")
    frequency = row[12]
    if (
        len(frequency) != 7
        or any(v not in {"-", str(i)} for i, v in enumerate(frequency, 1))
        or not re.fullmatch(r"\d+", row[13])
    ):
        raise ValueError("AICM frequency/count contract changed")
    count = 0
    day = start
    while day <= end:
        count += frequency[day.weekday()] == str(day.weekday() + 1)
        day += timedelta(days=1)
    if count != int(row[13]):
        raise ValueError("AICM assigned-date frequency does not reconcile to source count")
    return start.isoformat(), end.isoformat(), counterpart, count


def parse(inputs, period):
    content, original = inputs["pdf"]
    if not content.startswith(b"%PDF-") or len(content) > 5_000_000:
        raise ValueError("AICM slots PDF outside reviewed bound")
    output = []
    seen = set()
    duplicates = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) != 61:
            raise ValueError("AICM slot source page count changed")
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if (
                f"Pág {number} de 61" not in text
                or "Hora Asignada" not in text
                or "Operaciones" not in text
                or "Asignación de Históricos para la Temporada Verano 2026" not in text
                or "Horario UTC" not in text
                or "05/02/2026 12:13" not in text
            ):
                raise ValueError("AICM slot page/column coverage changed")
            tables = page.extract_tables()
            if len(tables) != 1 or not tables[0]:
                raise ValueError("AICM assignment table count changed")
            if number == 1:
                if tables[0][0][0] != "AM AEROMEXICO" or any(v is not None for v in tables[0][0][1:]):
                    raise ValueError("AICM AM-labelled first-page table changed")
            elif tables[0][0] != HEADERS:
                raise ValueError("AICM continuation-page assignment header changed")
            if len(tables[0]) < 2:
                raise ValueError("AICM continuation page has no assignment rows")
            for row_number, row in enumerate(tables[0][1:], 2):
                start, end, counterpart, count = validate_row(row)
                locator = f"page:{number}/table:1/row:{row_number}"
                key = tuple(row)
                if key in seen:
                    duplicates.append(locator)
                    continue
                seen.add(key)
                output.append(
                    {
                        **dict(zip(FIELDS, row, strict=True)),
                        "period_id": "2026S26",
                        "period_type": "assigned_schedule_season",
                        "metric_key": "assigned_operations_for_source_date_range",
                        "value": count,
                        "unit": "assigned_slot_operations",
                        "start_date": start,
                        "end_date": end,
                        "directional_counterpart_as_reported": counterpart,
                        "carrier_designator_as_reported": "AM",
                        "operator_icao": None,
                        "time_zone_as_reported": "UTC",
                        "observation_status": "assigned_slots_not_verified_performed_flights_or_passengers",
                        "source_system": original["source_system"],
                        "source_file": original["source_file"],
                        "source_hash": original["sha256"],
                        "ingested_at": pd.Timestamp(original["downloaded_at"]),
                        "source_locator": locator,
                        "parser_version": VERSION,
                        "agent_eligible": False,
                    }
                )
    frame = pd.DataFrame(output)
    if len(frame) != 2836 or len(frame) + len(duplicates) != 2836 or frame.duplicated(GRAIN).any():
        raise ValueError("AICM reviewed snapshot assignment coverage differs from 2836 unique source rows")
    return frame, dict(
        rows=len(frame),
        months_validated=[],
        schedule_season="2026S26",
        source_pages=61,
        source_assignment_rows=len(frame) + len(duplicates),
        exact_duplicate_assignment_locators=duplicates,
        source_frequency_reconciliations=len(frame) + len(duplicates),
        published_at=None,
        release_lag_days=None,
        scope="retained_full_summer_2026_AM_numbered_assignment_rows_not_quarter_traffic",
        overlapping_assignments_not_resolved_as_actual_flights=True,
        assigned_timezone_as_reported="UTC",
        internal_report_time_literal="05/02/2026 12:13",
        internal_report_time_is_not_proof_of_first_publication=True,
        scheduled_operations_not_performed=True,
        no_monthly_or_quarterly_flight_total_derived=True,
    )

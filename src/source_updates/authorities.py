"""Source-faithful retained ANAC, CAA and Aena candidates; no network or warehouse."""

from __future__ import annotations

import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation

import pandas as pd

from src.transform.international_routes import AENA_MONTHS, folded

VERSION = "retained_authorities_v1"
TABLES = {name: f"fact_{name}_retained_observations" for name in ("anac", "caa", "aena")}
GRAIN = [
    "period_id",
    "metric_key",
    "observation_scope",
    "operator_as_reported",
    "airport_base_as_reported",
    "counterpart_as_reported",
    "direction_as_reported",
]
CAA_FIELDS = "run_date reporting_period reporting_airport origin_destination_country origin_destination airline_name arrival_departure scheduled_charter number_flights_matched actual_flights_unmatched number_flights_cancelled flights_more_than_15_minutes_early_percent flights_15_minutes_early_to_1_minute_early_percent flights_0_to_15_minutes_late_percent flights_between_16_and_30_minutes_late_percent flights_between_31_and_60_minutes_late_percent flights_between_61_and_120_minutes_late_percent flights_between_121_and_180_minutes_late_percent flights_between_181_and_360_minutes_late_percent flights_more_than_360_minutes_late_percent flights_unmatched_percent flights_cancelled_percent average_delay_mins previous_year_month_flights_matched previous_year_month_early_to_15_mins_late_percent previous_year_month_average_delay".split()
AENA_COMPANY = "AEROVIAS DE MEXICO, S.A. DE C."
AENA_BASES = {"ADOLFO SUÁREZ MADRID-BARAJAS", "BARCELONA-EL PRAT J.T."}
AENA_MEXICO = "MEXICO CITY /JUAREZ INTERNACIO"


def month(period):
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Authority requires an explicit report month")
    return int(period[:4]), int(period[-2:])


def count(token, *, spanish=False):
    text = str(token).strip() if token is not None else ""
    if spanish:
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+)", text):
            raise ValueError("Missing/invalid Aena count; no implicit zero")
        text = text.replace(".", "")
    elif not re.fullmatch(r"\d+(?:\.0+)?", text):
        raise ValueError("Missing/invalid reported count; no implicit zero")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Invalid count") from exc
    if not result.is_finite() or result < 0 or result > 2**53 - 1 or result != result.to_integral_value():
        raise ValueError("Count cannot be represented exactly")
    return int(result)


def csv_rows(content, fields, *, utf16=False):
    if len(content) > 15_000_000:
        raise ValueError("Authority CSV exceeds reviewed bound")
    if utf16 and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("Expected original Aena UTF-16 export")
    reader = csv.DictReader(io.StringIO(content.decode("utf-16" if utf16 else "utf-8-sig", errors="strict")))
    if reader.fieldnames != fields:
        raise ValueError("Authority CSV field contract changed")
    rows = list(reader)
    if not rows or len(rows) > 100_000 or any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError("Empty, truncated or oversized authority CSV")
    return rows


def observation(
    original,
    period,
    metric,
    value,
    locator,
    *,
    scope,
    operator=None,
    base=None,
    counterpart=None,
    direction=None,
    definition,
    source_value,
):
    return dict(
        period_id=period,
        period_type="month",
        metric_key=metric,
        value=value,
        unit="count",
        observation_scope=scope,
        operator_as_reported=operator,
        airport_base_as_reported=base,
        counterpart_as_reported=counterpart,
        direction_as_reported=direction,
        metric_definition=definition,
        source_value=source_value,
        source_system=original["source_system"],
        source_file=original["source_file"],
        source_hash=original["sha256"],
        ingested_at=pd.Timestamp(original["downloaded_at"]),
        source_locator=locator,
        parser_version=VERSION,
        marketing_carrier=None,
        agent_eligible=False,
    )


def finish(output, period, *, scope, scanned, excluded, **details):
    frame = pd.DataFrame(output)
    if frame.empty or frame.duplicated(GRAIN).any():
        raise ValueError("Empty or duplicate authority native observation grain")
    periods = sorted(frame.period_id.unique())
    if period not in periods:
        raise ValueError("Requested retained edition lacks selected observations")
    return frame, dict(
        rows=len(frame),
        report_period=period,
        months_validated=periods,
        source_rows_scanned=scanned,
        source_rows_excluded=excluded,
        published_at=None,
        release_lag_days=None,
        scope=scope,
        missing_operator_is_not_zero=True,
        unsupported_metrics_not_invented=True,
        zero_semantics="explicit_source_numeric_zero_only",
        **details,
    )


def caa(inputs, period):
    month(period)
    content, original = inputs["csv"]
    rows = csv_rows(content, CAA_FIELDS)
    expected = period.replace("M", "")
    if {r["reporting_period"] for r in rows} != {expected}:
        raise ValueError("CAA file edition differs from explicit requested month")
    output = []
    selected = []
    for index, r in enumerate(rows, 1):
        if r["airline_name"] != "AEROMEXICO" or r["scheduled_charter"] != "S":
            continue
        if (r["reporting_airport"], r["origin_destination"], r["origin_destination_country"]) != (
            "HEATHROW",
            "MEXICO CITY",
            "MEXICO",
        ) or r["arrival_departure"] not in {"A", "D"}:
            raise ValueError("Unreviewed CAA endpoint or direction")
        selected.append(r)
        for field, metric in (
            ("number_flights_matched", "matched_flights"),
            ("actual_flights_unmatched", "unmatched_actual_flights"),
            ("number_flights_cancelled", "cancelled_flights"),
        ):
            output.append(
                observation(
                    original,
                    period,
                    metric,
                    count(r[field]),
                    f"record:{index}/{field}",
                    scope="carrier_direction_punctuality_sample",
                    operator=r["airline_name"],
                    base=r["reporting_airport"],
                    counterpart=r["origin_destination"],
                    direction=r["arrival_departure"],
                    definition="CAA Flight Punctuality source column; matched/unmatched/cancelled remain separate; no passenger, seat, world-network or complete operated-flight claim",
                    source_value=r[field],
                )
            )
    if len(selected) != 2 or {r["arrival_departure"] for r in selected} != {"A", "D"}:
        raise ValueError("CAA selected arrival/departure domain incomplete or duplicated")
    return finish(
        output,
        period,
        scope="retained_CAA_punctuality_Aeromexico_Heathrow_Mexico_City_only",
        scanned=len(rows),
        excluded=len(rows) - len(selected),
        generation_dates_as_reported=sorted({r["run_date"] for r in selected}),
    )


def aena(inputs, period):
    year, last = month(period)
    output = []
    scanned = selected_count = 0
    domains = {}
    operations = {}
    for role in ("company_operations", "company_passengers", "market_operations", "market_passengers"):
        content, original = inputs[role]
        company = role.startswith("company_")
        first = (
            "Compañía"
            if company
            else ("Aeropuerto Escala" if role.endswith("passengers") else "Aeropuerto ORI/DES")
        )
        metric = "airport_operations_as_reported" if role.endswith("operations") else "passengers"
        last_field = "Operaciones Totales" if role.endswith("operations") else "Pasajeros Totales"
        rows = csv_rows(content, [first, "Aeropuerto Base", "Mes", last_field], utf16=True)
        scanned += len(rows)
        domains[role] = set()
        for index, r in enumerate(rows, 1):
            # Export trailing totals lack Mes. They are never month observations.
            if not r["Mes"].strip():
                continue
            match = re.fullmatch(r"([A-Z]+)\s+DE\s+(\d{4})", folded(r["Mes"]).strip())
            if not match or match[1] not in AENA_MONTHS:
                raise ValueError("Aena month label changed")
            current = f"{int(match[2])}M{AENA_MONTHS[match[1]]:02d}"
            if int(match[2]) != year or AENA_MONTHS[match[1]] > last:
                raise ValueError("Aena selected export exceeds requested retained edition")
            if r[first] != (AENA_COMPANY if company else AENA_MEXICO):
                continue
            if r["Aeropuerto Base"] not in AENA_BASES:
                continue
            domains[role].add((current, r["Aeropuerto Base"]))
            if role == "company_operations":
                operations[(current, r["Aeropuerto Base"])] = count(r[last_field], spanish=True)
            selected_count += 1
            output.append(
                observation(
                    original,
                    current,
                    metric,
                    count(r[last_field], spanish=True),
                    f"record:{index}/{last_field}",
                    scope="carrier_airport" if company else "all_carrier_airport_pair",
                    operator=r[first] if company else None,
                    base=r["Aeropuerto Base"],
                    counterpart=None if company else r[first],
                    definition="Aena company×Spanish-airport total; counterpart unknown"
                    if company
                    else "Aena all-carrier airport-pair total; operator unknown; no company×route allocation",
                    source_value=r[last_field],
                )
            )
    expected = {(f"{year}M{m:02d}", base) for m in range(1, last + 1) for base in AENA_BASES}
    missing = expected - domains["company_passengers"]
    if (
        any(domains[role] != expected for role in domains if role != "company_passengers")
        or not domains["company_passengers"].issubset(expected)
        or any(operations.get(key) != 0 for key in missing)
    ):
        raise ValueError("Aena selected months/airports incomplete or duplicate coverage")
    return finish(
        output,
        period,
        scope="retained_Aena_Aerovias_airport_and_all_carrier_MEX_market_scopes_separate",
        scanned=scanned,
        excluded=scanned - selected_count,
        source_domains_crosschecked=4,
        company_route_join_performed=False,
        missing_passenger_observations=[
            {
                "period_id": p,
                "airport_base_as_reported": a,
                "value": None,
                "status": "missing_source_row_not_zero",
                "separate_reported_operation_count": operations[(p, a)],
            }
            for p, a in sorted(missing)
        ],
    )


def json_objects(content):
    """Consume every byte of concatenated JSON arrays, yielding one record at a time."""
    if not 1 <= len(content) <= 250_000_000:
        raise ValueError("ANAC payload outside reviewed bound")
    text = content.decode("utf-8-sig", errors="strict")
    decoder = json.JSONDecoder()
    position = 0
    arrays = 0
    count_rows = 0

    def skip(position):
        while position < len(text) and text[position].isspace():
            position += 1
        return position

    while (position := skip(position)) < len(text):
        if text[position] != "[":
            raise ValueError("ANAC payload must contain complete JSON arrays")
        arrays += 1
        position = skip(position + 1)
        if position < len(text) and text[position] == "]":
            position += 1
            continue
        while True:
            try:
                row, end = decoder.raw_decode(text, position)
            except ValueError as exc:
                raise ValueError("Truncated/malformed ANAC JSON record") from exc
            if not isinstance(row, dict):
                raise ValueError("ANAC record is not an object")
            count_rows += 1
            if count_rows > 300_000:
                raise ValueError("ANAC record bound exceeded")
            yield count_rows, row
            position = skip(end)
            if position >= len(text):
                raise ValueError("Truncated ANAC array")
            token = text[position]
            position = skip(position + 1)
            if token == "]":
                break
            if token != "," or position >= len(text) or text[position] == "]":
                raise ValueError("Malformed ANAC array separator")
    if not arrays or not count_rows:
        raise ValueError("Empty ANAC source")


def anac(inputs, period):
    year, last = month(period)
    content, original = inputs["json"]
    output = []
    scanned = selected = 0
    latest = None
    companies = set()
    for index, r in json_objects(content):
        scanned += 1
        y, m = count(r.get("ANO")), count(r.get("MES"))
        if not 2000 <= y <= 2100 or not 1 <= m <= 12:
            raise ValueError("ANAC source month invalid")
        source_period = f"{y}M{m:02d}"
        latest = max(latest or source_period, source_period)
        name = r.get("EMPRESA_NOME")
        if name != "AEROVÍAS DE MÉXICO S.A DE C.V - AEROMÉXICO":
            if any(token in folded(name) for token in ("AEROVIAS DE MEXICO", "AEROLITORAL")):
                raise ValueError(f"Unreviewed ANAC company identity: {name}")
            continue
        if r.get("GRUPO_DE_VOO") != "REGULAR" or y != year or m > last:
            continue
        origin, dest = r.get("AEROPORTO_DE_ORIGEM_SIGLA"), r.get("AEROPORTO_DE_DESTINO_SIGLA")
        if not all(isinstance(v, str) and re.fullmatch(r"[A-Z]{4}", v) for v in (origin, dest)):
            raise ValueError("ANAC selected airport identifiers invalid")
        countries = (r.get("AEROPORTO_DE_ORIGEM_PAIS"), r.get("AEROPORTO_DE_DESTINO_PAIS"))
        if set(countries) != {"MÉXICO", "BRASIL"}:
            continue
        if r.get("NATUREZA") != "INTERNACIONAL":
            raise ValueError("ANAC nature/country conflict")
        selected += 1
        companies.add(name)
        for field, metric in (
            ("PASSAGEIROS_PAGOS", "paid_passengers"),
            ("ASSENTOS", "seats_as_reported"),
            ("DECOLAGENS", "departures_as_reported"),
        ):
            output.append(
                observation(
                    original,
                    source_period,
                    metric,
                    count(r.get(field)),
                    f"record:{index}/{field}",
                    scope="reporting_company_directed_airport_pair_regular",
                    operator=name,
                    base=origin,
                    counterpart=dest,
                    direction="origin_to_destination",
                    definition=f"ANAC {field}; native reporting company and directed pair, regular Mexico–Brazil only; no free-passenger inclusion or harmonized load factor",
                    source_value=r[field],
                )
            )
    if latest != period:
        raise ValueError("Requested ANAC edition differs from latest month inside retained file")
    return finish(
        output,
        period,
        scope="retained_ANAC_selected_companies_regular_Mexico_Brazil_only",
        scanned=scanned,
        excluded=scanned - selected,
        companies_present=sorted(companies),
        latest_month_inside_selected_original=latest,
        selected_scope_months_absent=sorted(
            {f"{year}M{m:02d}" for m in range(1, last + 1)} - {row["period_id"] for row in output}
        ),
        selected_scope_presence_is_not_proof_of_complete_operator_or_direction_coverage=True,
    )

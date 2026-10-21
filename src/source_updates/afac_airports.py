"""Verify AFAC airport workbook cache against its visible pivot and summary tables."""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from decimal import Decimal, InvalidOperation
import io
import math
import re
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import openpyxl
import pandas as pd


VERSION = "afac_airports_cache_v1"
TABLE = "fact_afac_airport_observations"
BUSINESS_GRAIN = [
    "period_id",
    "metric_key",
    "market",
    "airport_group_as_reported",
    "airport_name_as_reported",
]
MONTHS = (
    "ENE/JAN",
    "FEB/FEB",
    "MAR/MAR",
    "ABR/APR",
    "MAY/MAY",
    "JUN/JUN",
    "JUL/JUL",
    "AGO/AUG",
    "SEP/SEP",
    "OCT/OCT",
    "NOV/NOV",
    "DIC/DEC",
)
SPANISH = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
METRICS = {
    "OPERACIONES/ FLIGHTS": ("airport_operations_as_reported", "count"),
    "PASAJEROS/PASSENGERS": ("passengers", "count"),
    "CARGA/ CARGO": ("cargo", "tonnes"),
}
MARKETS = {"NACIONAL/DOMESTIC": "domestic", "INTERNACIONAL/ INTERNATIONAL": "international"}
FIELDS = [
    "OPCIONES/ OPTIONS",
    "TIPO/ TYPE",
    "AÑO / YEAR",
    "GRUPO / GROUP",
    "AEROPUERTO / AIRPORT",
    *MONTHS,
    "TOTAL/TOTAL",
    "Acumulado Parcial",
]


def folded(value) -> str:
    value = unicodedata.normalize("NFKD", str(value))
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in value if not unicodedata.combining(c)).upper())


def number(token, *, count=False) -> Decimal:
    if isinstance(token, bool) or token is None:
        raise ValueError("Missing/invalid AFAC observation; never substitute zero")
    try:
        result = Decimal(str(token))
    except InvalidOperation as exc:
        raise ValueError("Unverified AFAC numeric token") from exc
    if (
        not result.is_finite()
        or result < 0
        or not math.isfinite(float(result))
        or (count and (result != result.to_integral_value() or result > 2**53 - 1))
    ):
        raise ValueError("AFAC value must be nonnegative, finite and in its reported unit")
    return result


def cache(content: bytes) -> tuple[list[list[str]], list[list[str]]]:
    if len(content) > 8_000_000:
        raise ValueError("Airport workbook exceeds the reviewed size bound")
    with ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in archive.infolist()) > 40_000_000:
            raise ValueError("Duplicate or oversized workbook ZIP members")
        definitions = [n for n in names if re.fullmatch(r"xl/pivotCache/pivotCacheDefinition\d+\.xml", n)]
        if definitions != ["xl/pivotCache/pivotCacheDefinition1.xml"]:
            raise ValueError("Expected one reviewed airport cache definition")
        xml = [archive.read(definitions[0]), archive.read("xl/pivotCache/pivotCacheRecords1.xml")]
        if any(b"<!DOCTYPE" in value or b"<!ENTITY" in value for value in xml):
            raise ValueError("Custom XML entities are not permitted")
        definition, records = (ET.fromstring(value) for value in xml)
    fields = definition.findall("{*}cacheFields/{*}cacheField")
    if [f.get("name") for f in fields] != FIELDS:
        raise ValueError("Airport cache fields or month order changed")
    shared = [[entry for entry in field.findall("{*}sharedItems/*")] for field in fields]
    if any(entry.tag.rsplit("}", 1)[-1] not in {"s", "n"} for values in shared for entry in values):
        raise ValueError("Unknown or missing shared airport cache item type")
    if (
        len(records) != int(definition.get("recordCount", -1))
        or len(records) != int(records.get("count", -1))
        or not 1 <= len(records) <= 100_000
    ):
        raise ValueError("Incomplete or oversized airport cache records")
    output = []
    for record in records:
        if len(record) != len(FIELDS):
            raise ValueError("Airport cache record width changed")
        row = []
        for index, cell in enumerate(record):
            kind = cell.tag.rsplit("}", 1)[-1]
            if kind == "x":
                try:
                    reference = int(cell.get("v"))
                    if reference < 0:
                        raise ValueError("Negative shared-item reference")
                    referenced = shared[index][reference]
                    kind = referenced.tag.rsplit("}", 1)[-1]
                    value = referenced.get("v")
                except (IndexError, TypeError, ValueError) as exc:
                    raise ValueError("Invalid shared-item reference") from exc
            elif kind in {"n", "s"}:
                value = cell.get("v")
            else:
                raise ValueError("Unknown or missing airport cache cell type")
            if index >= 5 and kind != "n":
                raise ValueError("Numeric airport cache field must retain numeric source type")
            if value is None:
                raise ValueError("Missing airport cache token")
            row.append(value)
        output.append(row)
    return output, shared


def compare(observed: Decimal, expected: Decimal, message: str) -> None:
    # Below one passenger/operation and one gram of cargo; only Excel binary serialization.
    if abs(observed - expected) > Decimal("0.000001"):
        raise ValueError(message)


def crosscheck(book, records: list[list[str]], year: int, month: int) -> int:
    pivot = list(book["TD Prod Aptos"].values)
    if (
        pivot[0][1] != "OPERACIONES/ FLIGHTS"
        or pivot[1][1] != "(Todas)"
        or pivot[3][0] != "Suma de " + MONTHS[month - 1]
        or pivot[4][0] != "Etiquetas de fila"
    ):
        raise ValueError("Visible pivot selected metric/market/month not verified")
    columns = [i for i, value in enumerate(pivot[4]) if value == year]
    if len(columns) != 1:
        raise ValueError("Visible pivot current-year column absent or ambiguous")
    operations = defaultdict(Decimal)
    groups = defaultdict(Decimal)
    for row in records:
        if row[0] == "OPERACIONES/ FLIGHTS":
            key = (folded(row[3]), folded(row[4]))
            operations[key] += number(row[4 + month], count=True)
            groups[key[0]] += number(row[4 + month], count=True)
    visible = defaultdict(list)
    group, grand, group_checks = None, None, 0
    for row in pivot[5:]:
        if row[0] is None:
            continue
        label = folded(row[0])
        value = number(row[columns[0]], count=True)
        if label == "TOTALGENERAL":
            if grand is not None:
                raise ValueError("Repeated pivot grand total")
            grand = value
        elif label in groups:
            group = label
            compare(value, groups[group], "Visible/cache airport group operations disagree")
            group_checks += 1
        else:
            key = (group, label)
            if key not in operations and value != 0:
                raise ValueError("Nonzero obsolete airport/group row outside current cache")
            visible[key].append(value)
    for airport, value in operations.items():
        if len(visible[airport]) != 1:
            raise ValueError("Airport missing or repeated in visible pivot")
        compare(visible[airport][0], value, "Cache/visible pivot airport operations disagree")
    if grand is None or group_checks != len(groups):
        raise ValueError("Visible pivot grand total missing")
    compare(grand, sum(operations.values()), "Airport operation grand total mismatch")
    checks = len(operations) + 1 + group_checks
    graph = list(book["graficos_graphics"].values)
    targets = {
        "ESTADISTICADEPASAJEROSDOMESTICOSPORGRUPOSAEROPORTUARIOS": (
            "PASAJEROS/PASSENGERS",
            "NACIONAL/DOMESTIC",
            Decimal(1000),
        ),
        "ESTADISTICADEPASAJEROSINTERNACIONALESPORGRUPOSAEROPORTUARIOS": (
            "PASAJEROS/PASSENGERS",
            "INTERNACIONAL/ INTERNATIONAL",
            Decimal(1000),
        ),
        "ESTADISTICADECARGADOMESTICAPORGRUPOSAEROPORTUARIOS": (
            "CARGA/ CARGO",
            "NACIONAL/DOMESTIC",
            Decimal(1),
        ),
        "ESTADISTICADECARGAINTERNACIONALPORGRUPOSAEROPORTUARIOS": (
            "CARGA/ CARGO",
            "INTERNACIONAL/ INTERNATIONAL",
            Decimal(1),
        ),
    }
    for marker, (metric, market, scale) in targets.items():
        starts = [
            i
            for i, row in enumerate(graph)
            if str(row[0]).split("\n")[0] and folded(str(row[0]).split("\n")[0]) == marker
        ]
        if len(starts) != 1:
            raise ValueError("Visible passenger/cargo group table missing or repeated")
        start = starts[0]
        if list(graph[start + 3][1:3]) != [year - 1, year]:
            raise ValueError("Group table current/prior year order changed")
        expected_unit = "miles / thousand" if scale == 1000 else "toneladas / tons"
        if graph[start + 2][0] != expected_unit:
            raise ValueError("Visible group units changed")
        totals = defaultdict(lambda: [Decimal(0), Decimal(0)])
        for row in records:
            if row[0] == metric and row[1] == market:
                group = folded(row[3])
                totals[group][0] += number(row[4 + month])
                totals[group][1] += sum(number(v) for v in row[5 : 5 + month])
        visible_groups = set()
        total_count = 0
        for row in graph[start + 5 :]:
            label = folded(row[0])
            if label.startswith("FUENTE"):
                break
            if label in {"TOTAL", "TOTALTOTAL"}:
                total_count += 1
                expected = [sum(values[i] for values in totals.values()) for i in (0, 1)]
            else:
                if label not in totals or label in visible_groups:
                    raise ValueError("Visible group domain missing, duplicated or changed")
                visible_groups.add(label)
                expected = totals[label]
            for column, wanted in zip((2, 6), expected, strict=True):
                compare(
                    number(row[column]) * scale, wanted, "Airport cache/group monthly or YTD totals disagree"
                )
                checks += 1
        if visible_groups != set(totals) or total_count != 1:
            raise ValueError("Incomplete visible airport group coverage")
    return checks


def parse(content: bytes, period: str, original: dict) -> tuple[pd.DataFrame, dict]:
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Airport report requires an explicit month")
    year, month = int(period[:4]), int(period[-2:])
    rows, _ = cache(content)
    if max(int(row[2]) for row in rows) != year:
        raise ValueError("Requested report year differs from the cache edition")
    with closing(openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)) as book:
        if set(book.sheetnames) != {"graficos_graphics", "TD Prod Aptos"}:
            raise ValueError("Airport workbook sheets changed")
        graph = list(book["graficos_graphics"].values)
        if not any(
            isinstance(value, str)
            and value.strip().startswith(f"{SPANISH[month - 1].title()} {year % 100:02d} /")
            for row in graph[:3]
            for value in row
        ):
            raise ValueError("Requested report month does not match workbook captions")
        notes = [
            str(row[0])
            for row in graph
            if isinstance(row[0], str) and row[0].startswith(("FUENTE:", "Nota:"))
        ]
        state_notes = [n.split(" / ")[0].strip() for n in notes if "operaciones oficiales o de Estado" in n]
        if (
            not any("Cifras proporcionadas por los grupos aeroportuarios" in n for n in notes)
            or not state_notes
            or set(state_notes)
            != {"Nota: No se contabiliza información de operaciones oficiales o de Estado"}
        ):
            raise ValueError("Airport source/coverage notes missing or contradictory")
        selected = [row for row in rows if int(row[2]) == year]
        domains = {}
        seen = set()
        output = []
        for index, row in enumerate(rows, 1):
            if int(row[2]) != year:
                continue
            if row[0] not in METRICS or row[1] not in MARKETS or tuple(row[:5]) in seen:
                raise ValueError("Unknown airport metric/market or duplicate cache grain")
            seen.add(tuple(row[:5]))
            metric, unit = METRICS[row[0]]
            values = [number(v, count=unit == "count") for v in row[5:17]]
            if any(values[month:]):
                raise ValueError(
                    "Nonzero observations after report month; edition/month interpretation changed"
                )
            compare(sum(values[:month]), number(row[17]), "Airport annual/partial source total mismatch")
            compare(sum(values[:month]), number(row[18]), "Airport YTD source total mismatch")
            domains.setdefault((metric, MARKETS[row[1]]), set()).add((row[3], row[4]))
            for offset, value in enumerate(values[:month], 1):
                output.append(
                    {
                        "period_id": f"{year}M{offset:02d}",
                        "period_type": "month",
                        "report_period": period,
                        "metric_key": metric,
                        "market": MARKETS[row[1]],
                        "airport_group_as_reported": row[3],
                        "airport_name_as_reported": row[4],
                        "value": float(value),
                        "unit": unit,
                        "source_value": row[4 + offset],
                        "service_scope": "as_reported_airport_group_statistics",
                        "excludes_official_state_operations": True,
                        "carrier_key": None,
                        "source_system": original["source_system"],
                        "source_file": original["source_file"],
                        "source_hash": original["sha256"],
                        "ingested_at": pd.Timestamp(original["downloaded_at"]),
                        "source_locator": f"xl/pivotCache/pivotCacheRecords1.xml/r[{index}]/{MONTHS[offset - 1]}",
                        "parser_version": VERSION,
                    }
                )
        if len(domains) != 6 or len({frozenset(value) for value in domains.values()}) != 1:
            raise ValueError("Airport metric/market domains are incomplete or inconsistent")
        checks = crosscheck(book, selected, year, month)
    frame = pd.DataFrame(output)
    if frame.empty or frame.duplicated(BUSINESS_GRAIN).any():
        raise ValueError("Empty or duplicate airport observation grain")
    return frame, {
        "report_period": period,
        "months_validated": sorted(frame.period_id.unique()),
        "rows": len(frame),
        "airports_as_reported": len(next(iter(domains.values()))),
        "cache_records_in_edition": len(selected),
        "visible_crosschecks": checks,
        "future_template_months_imported": 0,
        "zero_semantics": "source_reported_numeric_zero_not_proof_of_operational_absence",
        "published_at": None,
        "release_lag_days": None,
        "source_notes": sorted(set(notes)),
        "scope": "retained_report_months_airport_statistics_not_airline_or_network_passengers",
    }

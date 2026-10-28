"""September ASUR visible-table reconstruction; never original SEC file evidence.

This edition keeps the two tables used by the existing Mexico airport product.
Other geographic detail is context, not newly promised airport coverage. CPC and
worldwide printed YTD are preserved without asserting January–September scope.
"""

from decimal import Decimal

import pandas as pd

from src.source_updates.airport_group_native import ASUR, append, asur_values, reconcile
from src.source_updates.calendar import local_time

PERIOD = "2026M09"
URL = "https://www.sec.gov/Archives/edgar/data/1123452/000110465926114381/tm2627227d1_99-1.htm"
ALIAS = "asur_visible_reconstruction"
VERSION = "asur_visible_September2026_reconstruction_v1"
COUNT_KEYS = ("september_2025", "september_2026", "ytd_2025", "ytd_2026")
COUNTRIES = (
    ("Mexico", "MX", "MX"),
    ("Brazil and Others", "CPC", "MULTI_CPC"),
    ("San Juan, Puerto Rico", "PR", "PR"),
    ("Colombia", "CO", "CO"),
    ("Total Traffic", "ALL", "MULTI"),
)
MARKETS = ("domestic", "international", "total")
NOTICE = (
    "Authorized editable reconstruction of visible ASUR September2026 tables; "
    "not original SEC HTML. Hash identifies the reconstruction only. "
    "Mexico/Colombia exclude transit and general aviation; CPC countries exclude transit. "
    "Puerto Rico exclusion definition is not established by this note. "
    "CPC acquisition changes coverage: its printed YTD and the worldwide composite "
    "do not establish a comparable full January–September universe."
)


def parse_tables(summary, mexico, original):
    """Validate normalized *visible* rows; headers/provenance belong to input reader.

    Rows retain the source's four count columns and two printed changes. This
    function never downloads, fabricates original HTML, or changes an old dossier.
    """
    if original["source_system"] != ALIAS or original["source_url"] != URL:
        raise ValueError("Require explicit ASUR reconstruction identity, not a SEC original alias")
    if local_time(original["downloaded_at"]).date().isoformat() < "2026-10-07":
        raise ValueError("Reconstruction cannot precede the visible ASUR report date")
    if len(summary) != 15 or len(mexico) != 30:
        raise ValueError("ASUR September summary and nine-airport Mexico domains required")
    native, countries, checks = [], {}, 0

    def emit(entity, name, country, market, values, locator):
        append(
            native,
            original,
            "ASUR",
            entity,
            name,
            country,
            market,
            values,
            PERIOD,
            locator,
            scope=NOTICE,
        )
        for column, row in enumerate(native[-4:]):
            row.update(
                parser_version=VERSION,
                source_representation="authorized_visible_reconstruction",
                is_reconstruction=True,
                upstream_source_url=URL,
                upstream_original_sha256=None,
                value_status="reported_via_visible_reconstruction",
                source_locator=f"{locator}/cells_raw/{COUNT_KEYS[column]}",
            )
            if entity in {"CPC", "ALL"}:
                row["airport_iata"] = None
            if entity in {"CPC", "ALL"} and row["period_type"] == "year_to_date":
                row["period_type"] = "reported_ytd_coverage_unverified"
                row["period_id"] = row["period_id"].replace("YTD", "REPORTED_YTD")
            row["coverage_start_known"] = row["period_type"] == "month"

    for block, (label, entity, country) in enumerate(COUNTRIES):
        values = {}
        for offset, (native_label, market) in enumerate(
            ((label, "total"), ("Domestic Traffic", "domestic"), ("International Traffic", "international"))
        ):
            position = block * 3 + offset
            row = summary[position]
            if row[0] != native_label:
                raise ValueError("ASUR summary country or market identity changed")
            values[market] = asur_values(row)
            emit(entity, label, country, market, values[market], f"json/tables[id=summary]/rows[{position}]")
        for column in range(4):
            reconcile(
                values["total"][column], [values[m][column] for m in ("domestic", "international")], "0"
            )
            checks += 1
        countries[entity] = values
    for market in MARKETS:
        for column in range(4):
            reconcile(
                countries["ALL"][market][column],
                [countries[c][market][column] for c in ("MX", "CPC", "PR", "CO")],
                "0",
            )
            checks += 1
    airports = {}
    for block, (label, market) in enumerate(
        (
            ("Domestic Traffic", "domestic"),
            ("International Traffic", "international"),
            ("Traffic Total Mexico", "total"),
        )
    ):
        position = block * 10
        total = mexico[position]
        if total[0] != label or asur_values(total) != countries["MX"][market]:
            raise ValueError("ASUR reconstructed Mexico totals differ from visible country summary")
        checks += 4
        domain = {}
        for i in range(9):
            row = mexico[position + i + 1]
            if len(row) != 9 or row[0] not in ASUR or row[1] != ASUR[row[0]] or row[0] in domain:
                raise ValueError("ASUR reconstructed Mexico airport identity/domain changed")
            domain[row[0]] = asur_values(row, airport=True)
            emit(
                row[0],
                row[1],
                "MX",
                market,
                domain[row[0]],
                f"json/tables[id=mexico]/rows[{position + i + 1}]",
            )
        if set(domain) != set(ASUR):
            raise ValueError("Require all nine Mexican airports, without inferred allocation")
        for column in range(4):
            reconcile(countries["MX"][market][column], [domain[a][column] for a in ASUR], "0")
            checks += 1
        airports[market] = domain
    for airport in ASUR:
        for column in range(4):
            reconcile(
                airports["total"][airport][column],
                [airports[m][airport][column] for m in ("domestic", "international")],
                "0",
            )
            checks += 1
    frame = pd.DataFrame(native)
    if (
        frame.empty
        or frame.duplicated(["operator_group", "entity_key", "period_id", "period_type", "market"]).any()
        or frame.value.isna().any()
    ):
        raise ValueError("Incomplete or duplicate ASUR reconstructed observations")
    if any(Decimal(v) != Decimal(v).to_integral_value() for v in frame.source_value):
        raise ValueError("ASUR passengers must retain whole-person units")
    return frame, {
        "reconciliations": checks,
        "report_period": PERIOD,
        "source_report_date_as_reported": "2026-10-07",
        "source_representation": "authorized_visible_reconstruction",
        "is_original_SEC_HTML": False,
        "upstream_source_url": URL,
        "upstream_original_sha256": None,
        "first_publication_date": None,
        "release_lag_days": None,
        "latest_source_availability_verified": False,
        "complete_month_certified": True,
        "complete_month_scope": "nine_Mexico_airports_and_reported_summary_counts",
        "mexico_airports": 9,
        "native_monthly_and_YTD_kept_separate": True,
        "CPC_and_worldwide_printed_YTD_full_January_September_coverage_verified": False,
        "unselected_geographic_airport_detail": "not_certified_by_this_two_table_projection",
        "provenance_warning": NOTICE,
    }


def read(inputs, period):
    from src.source_updates.asur_reconstruction_inputs import FILES, KEYS, decode, validate_record

    if period != PERIOD or set(inputs) != set(FILES):
        raise ValueError("ASUR derived mode requires the four reviewed September2026 representations")
    for role, (_, original) in inputs.items():
        validate_record(original)
        if original["representation_role"] != role:
            raise ValueError("ASUR reconstructed artifact role differs from retention selection")
    document, proof = decode({k: v[0] for k, v in inputs.items()})
    observed = document["metadata"]["observation_time_utc"]
    if len({v[1]["downloaded_at"] for v in inputs.values()}) != 1 or any(
        v[1].get("source_observed_at") != observed or local_time(v[1]["downloaded_at"]) < local_time(observed)
        for v in inputs.values()
    ):
        raise ValueError("ASUR reconstructed observation/import timestamps differ or are reversed")
    tables = {t["id"]: t for t in document["tables"]}

    def normalized(identifier):
        result = []
        for row in tables[identifier]["rows"]:
            c = row["cells_raw"]
            values = [c[k] for k in KEYS]
            result.append(row["label_cells_raw"] + values[:3] + [""] + values[3:])
        return result

    frame, details = parse_tables(
        normalized("summary"), normalized("mexico"), inputs["reconstruction_json"][1]
    )
    return frame, {
        **details,
        "reconstruction_verification": proof,
        "source_observed_at": observed,
        "representation_imported_at": inputs["reconstruction_json"][1]["downloaded_at"],
        "source_HTTP_status": None,
        "original_SEC_capture_time": None,
        "reconstructed_artifact_sha256": {k: v[1]["sha256"] for k, v in inputs.items()},
        "unselected_geographic_airport_detail": (
            "all_five_tables_physically_retained_and_checked; only_summary_and_Mexico_projected"
        ),
    }

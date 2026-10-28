"""Q3 source observations from the authorized editable ZIP, not SEC originals."""

import re

import pandas as pd

from src.source_updates.carrier_source_contract import clean, record
from src.source_updates.volaris_q3_inputs import JSON_NAME, ROLE, decode, validate_record
from src.source_updates.volaris_q3_reconstructed import ALIAS, PERIOD, native_value, reporting_context
from src.source_updates.volaris_q3_spec import TABLES

ENTITY = "Controladora Vuela Compañía de Aviación, S.A.B. de C.V."


def dates(table, column, metric):
    year = 2025 if column == 2 else 2026
    if table == 315:
        return reporting_context("instant", year, quarter=4 if column == 2 else 3)
    if table == 291:
        return reporting_context("instant", year, quarter=2 if column == 4 else 3)
    if metric in {"aircraft_total", "closing_fx", "net_debt_to_ltm_ebitdar"}:
        return reporting_context("instant", year)
    return reporting_context(TABLES[table]["kind"], year)


def audit_flag(table, column):
    if table == 315:
        return column == 1
    # Only retained captions establish audit status; absence is not false.
    return True if table in {299, 302, 305, 311, 318} else None


def read(inputs, period):
    if period != PERIOD or set(inputs) != {ROLE}:
        raise ValueError("Require the specific authorized Volaris Q3 reconstruction ZIP")
    raw, source = inputs[ROLE]
    validate_record(source)
    document, proof = decode(raw)
    if document["metadata"]["issuer"] != ENTITY:
        raise ValueError("Volaris reconstructed consolidated issuer changed")
    by = {t["source_dom_table_index"]: t for t in document["tables"]}
    rows = []
    for table, definition in TABLES.items():
        t = by[table]
        source_rows = {r["source_row_index"]: r["cells"] for r in t["rows"]}
        for pos, header in enumerate(definition["header_rows"]):
            if [c["display"] for c in source_rows[pos]] != header:
                raise ValueError("Volaris reconstructed table header or duration changed")
        for row, (label, key, unit, scale, scope) in definition["rows"].items():
            cells = source_rows[row]
            if " ".join(cells[0]["display"].split()) != label:
                raise ValueError("Volaris reconstructed financial row label changed")
            for column in [1, 2, 4] if table == 291 else [1, 2]:
                cell = cells[column]
                token = cell["display"].strip()
                native_value(token, cell["value"], unit=unit, scale=scale)
                kind, identifier, start, end = dates(table, column, key)
                rows.append(
                    record(
                        "volaris_sec",
                        source,
                        edition=period,
                        entity=ENTITY,
                        carrier="VOLARIS",
                        statement=definition["statement"],
                        kind=kind,
                        period_id=identifier,
                        start=start,
                        end=end,
                        metric=key,
                        segment="total",
                        service=None,
                        token=token,
                        unit=unit,
                        scale=scale,
                        label=label,
                        locator=f"zip/{JSON_NAME}/table[{table}]/row[{row}]/cell[{column}]",
                        excerpt=" | ".join(c["display"] for c in cells),
                        table=str(table),
                        row=row,
                        column=column,
                        notes=proof["provenance_warning"]
                        + " | "
                        + " | ".join(document["notes_es"]["indicators"] + document["notes_es"]["cashflow"]),
                        aviation=scope,
                        unaudited=audit_flag(table, column),
                    )
                )
    frame = pd.DataFrame(rows)
    frame["parser_version"] = "volaris_reconstructed_2026Q3_v1"
    validate(frame)
    details = reconcile(frame)
    return frame, {
        **proof,
        **details,
        "scope": "authorized_Q3_reconstructed_eleven_report_tables_not_original_SEC_or_full_filing",
        "filing_date": "2026-10-27",
        "report_date": "2026-10-26",
        "sec_acceptance_at": "2026-10-26T21:31:25Z",
        "sec_filing_lag_days": 27,
        "report_date_is_first_availability": False,
        "monthly_coverage_verified": False,
        "guidance_projected": False,
        "thousands_USD_notes_projected": False,
        "primary_metadata_status": "observed_reconstructed_not_original_SEC_documents",
    }


def validate_row(r):
    try:
        table, row, column = int(r["source_table"]), r["source_row_number"], r["source_column"]
        label, key, unit, scale, scope = TABLES[table]["rows"][row]
        if column not in ([1, 2, 4] if table == 291 else [1, 2]):
            raise ValueError("Volaris Q3 physical source column differs")
    except (KeyError, TypeError) as exc:
        raise ValueError("Volaris Q3 unreviewed physical table/row") from exc
    if (
        r["product"],
        r["edition"],
        r["entity_as_reported"],
        r["carrier_key"],
        r["source_system"],
        r["metric_key"],
        r["source_label"],
        r["unit"],
        r["scale"],
        r["aviation_scope"],
        r["statement"],
    ) != (
        "volaris_sec",
        PERIOD,
        ENTITY,
        "VOLARIS",
        ALIAS,
        key,
        label,
        unit,
        float(scale),
        scope,
        TABLES[table]["statement"],
    ):
        raise ValueError("Volaris Q3 source, metric, units or scope differs")
    if (r["period_type"], r["period_id"], r["period_start_date"], r["period_end_date"]) != dates(
        table, column, key
    ):
        raise ValueError("Volaris Q3 quarter/YTD/instant periods differ")
    if r["source_locator"] != f"zip/{JSON_NAME}/table[{table}]/row[{row}]/cell[{column}]":
        raise ValueError("Volaris Q3 locator must identify the real reconstructed ZIP member/cell")
    native_value(r["source_value"], r["value"], unit=unit, scale=scale)
    if not (
        r["is_unaudited"] is audit_flag(table, column)
        and r["is_preliminary"] is None
        and r["source_estimated"] is None
        and r["segment"] == "total"
        and r["service_type"] is None
        and r["source_group"] is None
        and r["mapping_evidence"] is None
    ):
        raise ValueError("Volaris reconstructed audit or consolidated mapping differs")


def validate(frame):
    expected = {
        (str(t), r, c)
        for t, d in TABLES.items()
        for r in d["rows"]
        for c in ([1, 2, 4] if t == 291 else [1, 2])
    }
    if (
        len(frame) != len(expected)
        or set(
            frame[["source_table", "source_row_number", "source_column"]].itertuples(index=False, name=None)
        )
        != expected
    ):
        raise ValueError("Require all 446 reviewed Volaris Q3 financial/operating cells")
    for r in frame.to_dict("records"):
        validate_row(clean(r))
    return frame


def reconcile(frame):
    from src.source_updates.volaris_source_checks import reconcile as check_equations

    # Reuse identical statement equations through explicit logical layout mapping.
    # This view is never stored as source observations: native locators keep Q3.
    view = frame.copy()
    reverse = {t: d["logical_check_table"] for t, d in TABLES.items()}
    view["source_table"] = view.source_table.map(lambda t: str(reverse[int(t)]))
    result = check_equations(view)
    forward = {str(v): str(k) for k, v in reverse.items()}

    def physical_labels(value):
        if isinstance(value, str):
            return (
                re.sub(r"\b(?:" + "|".join(forward) + r")\b", lambda m: forward[m[0]], value)
                .replace("Q2/H1", "Q3/YTD")
                .replace("June", "September")
                .replace("current H1", "current YTD")
            )
        return value

    for field in ("reconciliation_details", "unresolved_source_identity_checks"):
        result[field] = [physical_labels(x) for x in result[field]]
    for warning in result["numeric_warnings"]:
        warning["check"] = physical_labels(warning["check"])
    return {
        **result,
        "reconciliation_layout_mapping": {str(k): v for k, v in reverse.items()},
        "reconciliation_view_not_source_observations": True,
    }


def project(frame):
    validate(frame)
    reconcile(frame)
    selected = frame.value.notna()
    selected &= ~frame.statement.eq("highlights") | frame.metric_key.isin(
        ["ebitdar", "ebitdar_margin", "net_debt_to_ltm_ebitdar"]
    )
    selected &= ~frame.statement.str.startswith("operations_") | ~frame.metric_key.isin(
        [
            "total_revenue",
            "operating_expenses",
            "operating_result",
            "depreciation_total",
            "variable_aircraft_engine_lease_expense",
            "net_result",
            "aircraft_total",
            "average_fx",
            "closing_fx",
        ]
    )
    selected &= ~frame.statement.str.startswith("ancillary_") | frame.metric_key.eq("ancillary_revenues")
    return frame.loc[selected].copy()

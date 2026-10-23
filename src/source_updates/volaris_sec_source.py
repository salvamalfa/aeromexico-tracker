"""Read the retained Volaris 6-K 2Q26 dossier, never select a different filing implicitly."""

from __future__ import annotations

import json

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates.carrier_source_contract import amount, clean, record
from src.source_updates.volaris_source_spec import ACCESSION, DIRECTORY, DOCUMENT, EXHIBIT, TABLES

PRODUCT = "volaris_sec"
ENTITY = "Controladora Vuela Compañía de Aviación, S.A.B. de C.V."


def cells(table):
    return [
        [" ".join(c.stripped_strings) for c in r.find_all(["td", "th"], recursive=False)]
        for r in table.find_all("tr")
        if r.find_parent("table") == table
    ]


def dates(table, column, metric):
    year = 2025 if column == 2 else 2026
    kind = TABLES[table]["kind"]
    end = f"{year}-06-30"
    if table == 313 and column == 2:
        end = "2025-12-31"
    if table == 289 and column == 4:
        end = "2026-03-31"
    if metric in {"aircraft_total", "closing_fx", "net_debt_to_ltm_ebitdar"}:
        kind = "instant"
    start = None if kind == "instant" else f"{year}-{'04-01' if kind == 'quarter' else '01-01'}"
    period = end if kind == "instant" else f"{year}{'Q2' if kind == 'quarter' else 'H1'}"
    return kind, period, start, end


def metadata(inputs):
    if set(inputs) != {"html", "primary", "submissions", "index"}:
        raise ValueError("Volaris needs the exhibit, 6-K, submissions and accession index")
    submission = json.loads(inputs["submissions"][0])
    if str(submission.get("cik")).lstrip("0") != "1520504" or submission.get("name") != (
        "Controladora Vuela Compania de Aviacion, S.A.B. de C.V."
    ):
        raise ValueError("Volaris submissions entity/CIK differ")
    recent = submission["filings"]["recent"]
    positions = [i for i, a in enumerate(recent["accessionNumber"]) if a == ACCESSION]
    if len(positions) != 1:
        raise ValueError("Volaris accession is absent or ambiguous in submissions")
    i = positions[0]
    expected = dict(
        form="6-K",
        reportDate="2026-06-30",
        filingDate="2026-07-21",
        acceptanceDateTime="2026-07-21T21:30:26.000Z",
        primaryDocument=DOCUMENT,
    )
    if any(
        len(recent[k]) != len(recent["accessionNumber"]) or recent[k][i] != v for k, v in expected.items()
    ):
        raise ValueError("Volaris SEC filing identity, dates or primary document changed")
    directory = json.loads(inputs["index"][0])["directory"]
    if directory["name"] != DIRECTORY:
        raise ValueError("Volaris accession index directory differs")
    urls = dict(
        html="https://www.sec.gov" + DIRECTORY + "/" + EXHIBIT,
        primary="https://www.sec.gov" + DIRECTORY + "/" + DOCUMENT,
        index="https://www.sec.gov" + DIRECTORY + "/index.json",
        submissions="https://data.sec.gov/submissions/CIK0001520504.json",
    )
    for role, url in urls.items():
        content, source = inputs[role]
        if source["source_url"] != url or source["source_system"] != "sec":
            raise ValueError("Volaris selected role URL/alias does not identify this exact filing")
        if pd.Timestamp(source["downloaded_at"]) < pd.Timestamp(expected["acceptanceDateTime"]):
            raise ValueError("Volaris capture precedes the selected SEC acceptance")
        if role in {"html", "primary"}:
            found = [r for r in directory["item"] if r["name"] == (EXHIBIT if role == "html" else DOCUMENT)]
            if len(found) != 1 or int(found[0]["size"]) != len(content):
                raise ValueError("Volaris index document identity/size differs")
    primary = BeautifulSoup(inputs["primary"][0], "lxml")
    text = " ".join(primary.get_text(" ", strip=True).split())
    if not all(
        s in text
        for s in [
            "FORM 6-K",
            ENTITY,
            "July 2026",
            "July 21, 2026",
            "Financial Results for the Second Quarter 2026",
        ]
    ):
        raise ValueError("Volaris primary 6-K entity, period or explanatory note differs")
    exhibit_links = {a.get("href") for a in primary.find_all("a", href=True) if "ex99" in a["href"].lower()}
    if exhibit_links != {EXHIBIT}:
        raise ValueError("Volaris primary document does not link the unique selected exhibit")


def read(inputs, period):
    if period != "2026Q2":
        raise ValueError("Volaris reviewed 2026Q2 dossier only; no monthly, Q3 or annual substitution")
    metadata(inputs)
    content, source = inputs["html"]
    if len(content) > 4_000_000 or b"<!ENTITY" in content.upper():
        raise ValueError("Volaris exhibit size/entity declaration differs")
    soup = BeautifulSoup(content, "lxml")
    text = " ".join(soup.get_text(" ", strip=True).split())
    needed = [
        "Consolidated Quarter: 2 Year: 2026",
        "Mexico City, Mexico July 21, 2026",
        "International Financial Reporting Standards (IFRS)",
        "(2) Includes scheduled and charter.",
        "(4) Includes scheduled.",
        "Each ADS represents ten CPOs",
        "EBITDAR",
    ]
    if not all(s in text for s in needed):
        raise ValueError("Volaris report entity, quarter, accounting or aviation scope changed")
    tables = soup.find_all("table")
    if len(tables) != 318:
        raise ValueError("Volaris reviewed table inventory changed")
    rows = []
    for index, definition in TABLES.items():
        rr = cells(tables[index])
        if len(rr) != definition["row_count"] or rr[: len(definition["headers"])] != definition["headers"]:
            raise ValueError("Volaris table headers/quarter-H1 ordering/units changed")
        for row_index, (label, key, unit, scale, scope) in definition["rows"].items():
            row = rr[row_index]
            if row[0] != label or len(row) != (6 if index == 289 else 3 if index in (313, 316, 317) else 4):
                raise ValueError("Volaris row label/column layout changed")
            for column in [1, 2, 4] if index == 289 else [1, 2]:
                kind, p, start, end = dates(index, column, key)
                rows.append(
                    record(
                        PRODUCT,
                        source,
                        edition=period,
                        entity=ENTITY,
                        carrier="VOLARIS",
                        statement=definition["statement"],
                        kind=kind,
                        period_id=p,
                        start=start,
                        end=end,
                        metric=key,
                        segment="total",
                        service=None,
                        token=row[column],
                        unit=unit,
                        scale=scale,
                        label=label,
                        locator=f"html/table[{index}]/row[{row_index}]/cell[{column}]",
                        excerpt=" | ".join(row),
                        table=str(index),
                        row=row_index,
                        column=column,
                        notes="Report uses IFRS with separately reported non-IFRS/operating measures; "
                        "printed date 2026-07-21, not first availability. " + " | ".join(rr[-1]),
                        aviation=scope,
                        unaudited=(column != 2) if index == 313 else None if index == 289 else True,
                    )
                )
    frame = pd.DataFrame(rows)
    validate(frame)
    from src.source_updates.volaris_source_checks import reconcile

    details = reconcile(frame)
    return frame, {
        **details,
        "scope": "retained_Volaris_2026Q2_report_tables_not_monthly_or_latest_availability",
        "report_date": "2026-07-21",
        "filing_date": "2026-07-21",
        "sec_acceptance_at": "2026-07-21T21:30:26Z",
        "sec_filing_lag_days": 21,
        "report_date_is_first_availability": False,
        "monthly_coverage_verified": False,
    }


def validate(frame):
    expected = {
        (str(t), r, c)
        for t, d in TABLES.items()
        for r in d["rows"]
        for c in ([1, 2, 4] if t == 289 else [1, 2])
    }
    if set(
        frame[["source_table", "source_row_number", "source_column"]].itertuples(index=False, name=None)
    ) != expected or len(frame) != len(expected):
        raise ValueError("Volaris complete table/row/column domain required")
    for raw in frame.to_dict("records"):
        validate_row(clean(raw))
    return frame


def validate_row(row):
    from types import SimpleNamespace

    r = SimpleNamespace(**row)
    try:
        t = int(r.source_table)
        if r.source_column not in ([1, 2, 4] if t == 289 else [1, 2]):
            raise ValueError("Volaris source column differs")
        label, key, unit, scale, scope = TABLES[t]["rows"][r.source_row_number]
        if (r.metric_key, r.source_label, r.unit, r.scale, r.aviation_scope, r.statement) != (
            key,
            label,
            unit,
            float(scale),
            scope,
            TABLES[t]["statement"],
        ) or (r.period_type, r.period_id, r.period_start_date, r.period_end_date) != dates(
            t, r.source_column, key
        ):
            raise ValueError("Volaris metric, date, unit or aviation scope differs from reviewed semantics")
        token = r.source_value.strip("()")
        if (unit == "percent") != token.endswith("%") or (unit == "times_ltm") != token.endswith("x"):
            raise ValueError("Volaris unit and reported token disagree")
        value = amount(r.source_value)
        if unit in {"aircraft", "departures", "shares"} and value is not None and (value < 0 or value % 1):
            raise ValueError("Volaris source count is not a nonnegative integer")
        if (
            value is not None
            and unit == "percent"
            and key.startswith("load_factor")
            and not 0 <= value <= 100
        ):
            raise ValueError("Volaris scheduled load factor outside percent domain")
        if r.entity_as_reported != ENTITY or r.carrier_key != "VOLARIS" or r.edition != "2026Q2":
            raise ValueError("Volaris consolidated entity/edition mismatch")
    except (KeyError, TypeError) as exc:
        raise ValueError("Volaris unreviewed table/row semantics") from exc
    expected_audit = (r.source_column != 2) if t == 313 else None if t == 289 else True
    if r.is_unaudited is not expected_audit or r.is_preliminary is not None or r.source_estimated is not None:
        raise ValueError("Volaris financial audit/unknown preliminary-estimate flags differ")
    if (
        r.source_system != "sec"
        or r.segment != "total"
        or r.service_type is not None
        or r.source_group is not None
        or r.mapping_evidence is not None
    ):
        raise ValueError("Volaris source scope or consolidated mapping differs")
    if r.source_table != str(t) or r.source_locator != (
        f"html/table[{t}]/row[{r.source_row_number}]/cell[{r.source_column}]"
    ):
        raise ValueError("Volaris physical source locator differs")


def project(native):
    validate(native)
    from src.source_updates.volaris_source_checks import reconcile

    reconcile(native)
    selected = native.value.notna()
    selected &= ~native.statement.eq("highlights") | native.metric_key.isin(
        ["ebitdar", "ebitdar_margin", "net_debt_to_ltm_ebitdar"]
    )
    selected &= ~native.statement.str.startswith("operations_") | ~native.metric_key.isin(
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
    selected &= ~native.statement.str.startswith("ancillary_") | native.metric_key.eq("ancillary_revenues")
    return native.loc[selected].copy()

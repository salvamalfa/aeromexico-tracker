"""Reviewed September2026 monthly traffic in official IR6-K Exhibit99.4 only."""

import hashlib
import re
from datetime import date
from decimal import Decimal

import pandas as pd
from bs4 import BeautifulSoup, Tag

from src.source_updates.am_traffic import METRICS, NUMBER, validate
from src.source_updates.checks import period_end

URL = "https://ir.aeromexico.com/node/9131/html"
PERIOD = "2026M09"
KEY = "aeromexico_ir|am_traffic_ir_2026M09_6K|2026M09|html"
ANCHOR = "aeromxicoseptembertrafficr.htm"
TITLE = "Aeroméxico September 2026 Traffic Results"
DAY = "2026-10-06"
HEADINGS = {
    "Passengers (itinerary + charter, thousands)": "Passengers",
    "ASMs (itinerary + charter, millions)": "ASMs",
    "RPMs (itinerary + charter, millions)": "RPMs",
    "Load Factor (itinerary, %)": "Load Factor",
}


def text(node):
    return " ".join(node.get_text(" ", strip=True).split())


def cells(row):
    return row.find_all(["td", "th"], recursive=False)


def document(body, original):
    if (
        not 0 < len(body) <= 600_000
        or original.get("source_system") != "aeromexico_ir"
        or original.get("source_url") != URL
        or original.get("logical_key") != KEY
        or original.get("sha256") != hashlib.sha256(body).hexdigest()
    ):
        raise ValueError("Traffic HTML requires its actual monthly IR identity and physical SHA integrity")
    soup = BeautifulSoup(body, "html.parser")
    blocks = soup.select("#block-client-site-content")
    if len(blocks) != 1:
        raise ValueError("Traffic IR6-K content is missing or ambiguous")
    block = blocks[0]
    docs = block.find_all("html", recursive=False)
    if len(docs) != 5:
        raise ValueError("Reviewed IR6-K must contain cover and four bounded exhibits")
    cover = text(docs[0])
    if any(
        v not in cover
        for v in ("FORM 6-K", "Commission File Number: 001-42931", "Grupo Aeroméxico, S.A.B. de C.V.", TITLE)
    ):
        raise ValueError("Traffic IR6-K issuer or September report attribution changed")
    indexes = [c for tr in docs[0].find_all("tr") if (c := cells(tr)) and text(c[0]) == "99.4"]
    if (
        len(indexes) != 1
        or TITLE not in text(indexes[0][-1])
        or not re.search(r"dated October 6\s*,\s*2026", text(indexes[0][-1]))
        or {a.get("href") for c in indexes[0] for a in c.find_all("a", href=True)} != {"#" + ANCHOR}
    ):
        raise ValueError("Traffic99.4 index attribution must identify September and its October6 report day")
    anchors = block.find_all("a", attrs={"name": ANCHOR})
    if len(anchors) != 1 or anchors[0].parent.parent is not block:
        raise ValueError("Traffic99.4 anchor missing, duplicated or outside the reviewed boundary")
    following = [n for n in anchors[0].parent.next_siblings if isinstance(n, Tag)]
    if len(following) != 1 or following[0] is not docs[4]:
        raise ValueError("Traffic99.4 must be one separately bounded final HTML document")
    scope = following[0]
    intro = text(scope)
    if (
        TITLE not in intro
        or not re.search(
            r"Mexico City, Mexico, October 6, 2026\s*[-–]\s*Grupo Aeroméxico S\.A\.B\. de C\.V\.", intro
        )
        or "reports its September 2026 operational results" not in intro
        or "not been audited" not in intro
        or "Figures may not sum to total due to rounding" not in intro
    ):
        raise ValueError(
            "Traffic financial-exhibit confusion, report day, issuer or audit/rounding evidence missing"
        )
    if re.search(r"\bpreliminar\w*\b", intro, re.I):
        raise ValueError("Traffic preliminary indication changed; reviewed unknown status cannot be asserted")
    if re.search(r"\b(?:kilomet(?:er|re)s?|kil[oó]metros?)\b", intro, re.I):
        raise ValueError("Traffic kilometre exception conflicts with the reviewed native mile basis")
    glossary = intro.split("Glossary:")
    miles = (
        "Revenue Passenger Miles represent one revenue-passenger transported one mile.",
        "This includes itinerary and charter flights.",
        "Available Seat Miles represent the number of available seats multiplied by the distance flown.",
        "It equals one seat offered for one mile, whether the seat is used.",
        "This metric considers the total passengers transported and total seats available "
        "in itinerary flights only.",
    )
    if len(glossary) != 2 or any(v not in glossary[1] for v in miles):
        raise ValueError("Traffic glossary must establish explicit ASM/RPM miles and itinerary-only LF")
    return scope


def grid(scope):
    tables = [t for t in scope.find_all("table") if "Cumulative to September" in text(t)]
    if len(tables) != 1:
        raise ValueError("September monthly traffic table missing or duplicated within99.4")
    table = tables[0]
    if table.find("caption") is not None:
        raise ValueError("Traffic monthly table caption/unit declaration is outside the reviewed edition")
    groups, years, section, observations = 0, 0, None, {}
    for row_number, row in enumerate(table.find_all("tr"), 1):
        c = cells(row)
        tokens = [text(v) for v in c]
        if not any(tokens):
            continue
        if tokens == ["", "September", "Cumulative to September"]:
            if [v.get("colspan") for v in c] != ["3", "9", "9"]:
                raise ValueError("Traffic monthly/YTD header spans changed")
            groups += 1
            continue
        if tokens == ["", "2026", "2025", "Var.", "2026", "2025", "Var."]:
            years += 1
            continue
        if len(c) != 7 or any(v.get("colspan") != "3" for v in c) or groups != 1 or years != 1:
            raise ValueError("Traffic monthly/prior/YTD column layout changed")
        if tokens[0] in HEADINGS:
            if any(tokens[1:]) or HEADINGS[tokens[0]] in {k[0] for k in observations}:
                raise ValueError("Traffic unit/service heading repeated or has unexpected values")
            section = HEADINGS[tokens[0]]
            continue
        segment = tokens[0].lower()
        if (
            section is None
            or segment not in {"domestic", "international", "total"}
            or (section, segment) in observations
        ):
            raise ValueError("Traffic segment/metric row unknown or duplicated")
        lf = section == "Load Factor"
        parsed = []
        for index in (1, 2, 4, 5):
            token = tokens[index]
            if not re.fullmatch(NUMBER + ("%" if lf else ""), token):
                raise ValueError("Traffic native numeric token missing, invalid or wrong source unit")
            amount = Decimal(token.replace(",", "").rstrip("%"))
            if amount < 0 or lf and amount > 100 or not lf and amount != int(amount):
                raise ValueError("Traffic value outside its source percentage/count domain")
            parsed.append(amount)
        for index in (3, 6):
            delta = tokens[index].replace("(", "-").replace(")", "")
            if not re.fullmatch(r"-?\d+(?:\.\d+)?\s*p\.p\." if lf else r"-?\d+(?:\.\d+)?%", delta):
                raise ValueError("Traffic comparison variation layout changed; no silent dropped cells")
        observations[(section, segment)] = parsed, tokens, row_number
    expected = {(m, s) for m in METRICS for s in ("domestic", "international", "total")}
    if groups != 1 or years != 1 or set(observations) != expected:
        raise ValueError("Traffic grid must contain all four metrics and three segments exactly once")
    for metric in METRICS:
        for index in range(4):
            d, i, total = [
                observations[(metric, s)][0][index] for s in ("domestic", "international", "total")
            ]
            if metric == "Load Factor":
                if not min(d, i) - Decimal("0.1") <= total <= max(d, i) + Decimal("0.1"):
                    raise ValueError("Reported itinerary load factor outside component range")
            elif abs(d + i - total) > Decimal("1.5"):
                raise ValueError("Traffic components fail reconciliation within source rounding")
    return observations, scope.find_all("table").index(table) + 1


def parse(body, period, original):
    if period != PERIOD:
        raise ValueError("Only reviewed September2026 official IR6-K traffic is supported")
    observations, table = grid(document(body, original))
    records = []
    for (section, segment), (amounts, tokens, row) in observations.items():
        metric, unit, scale, normalized, service = METRICS[section]
        for offset in (0, 1):
            year = 2026 - offset
            observed = f"{year}M09"
            records.append(
                dict(
                    carrier_key="AEROMEXICO",
                    accession_number="IR-2026M09",
                    period_id=observed,
                    period_type="month",
                    period_start_date=date(year, 9, 1),
                    period_end_date=period_end(observed),
                    calendar_period_id=observed,
                    fiscal_period_id=observed,
                    metric_key=metric,
                    metric_label_raw=section,
                    segment=segment,
                    value_raw=float(amounts[offset]),
                    source_value=tokens[offset + 1],
                    unit_raw=unit,
                    scale_multiplier=float(scale),
                    value_normalized=float(amounts[offset] * scale),
                    unit_normalized=normalized,
                    service_scope=service,
                    reporting_status="unaudited",
                    is_preliminary=None,
                    is_yoy_comparison=bool(offset),
                    reported_in_period=period,
                    source_excerpt=" | ".join(tokens),
                    source_page=None,
                    source_locator=f"exhibit:99.4/{ANCHOR}/table:{table}/tr:{row}/td:{offset + 2}",
                    published_date=date.fromisoformat(DAY),
                    extraction_method="official_IR_HTML_6K_Ex99.4_monthly_columns_only",
                    extraction_confidence=0.99,
                    source_system=original["source_system"],
                    source_file=original["source_file"],
                    source_hash=original["sha256"],
                    ingested_at=pd.Timestamp(original["downloaded_at"]),
                    parser_version="am_ir_monthly_html_2026m09_v1",
                )
            )
    frame = pd.DataFrame(records).sort_values(["period_id", "metric_key", "segment"]).reset_index(drop=True)
    validate(frame)
    return frame, dict(
        published_date=DAY,
        source_report_date_as_reported=DAY,
        publication_time=None,
        first_available_at=None,
        first_publication_date=None,
        release_lag_days=None,
        rows=24,
        observation_months=["2025M09", PERIOD],
        monthly_rows=12,
        comparative_rows=12,
        cumulative_rows_imported=0,
        source_format="official_IR_HTML_6K_Ex99.4",
        financial_exhibit_imported=False,
        source_preliminary_status="not_stated",
        source_preliminary=None,
        gold_preliminary_flag_basis="observed_predicate_source_marks_preliminary_false_not_confirmation_final",
        rounding_policy="sum of rounded components within 1.5 published units",
        load_factor_policy="reported itinerary-only; not derived from itinerary-plus-charter RPM/ASM",
    )

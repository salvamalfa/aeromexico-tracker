"""Independent SEC airport contracts; synthetic fixtures never prove live availability."""

from __future__ import annotations

import calendar
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from bs4 import BeautifulSoup

from src.common.storage import save_bronze
from src.source_updates import airport_group_candidate as candidate
from src.source_updates import airport_group_native as native
from src.source_updates import readiness, retained
from src.source_updates.catalog import ROOT

MONTH = "2026M07"
CUTOFF = "2026-10-23T12:00:00-06:00"
MX_GAP = [
    "Guadalajara",
    "Tijuana*",
    "Los Cabos",
    "Puerto Vallarta",
    "Guanajuato",
    "Hermosillo",
    "Morelia",
    "La Paz",
    "Mexicali",
    "Aguascalientes",
    "Los Mochis",
    "Manzanillo",
]
JAMAICA = ["Montego Bay", "Kingston"]
ASUR_MX = [
    ("CUN", "Cancun"),
    ("CZM", "Cozumel"),
    ("HUX", "Huatulco"),
    ("MID", "Merida"),
    ("MTT", "Minatitlan"),
    ("OAX", "Oaxaca"),
    ("TAP", "Tapachula"),
    ("VER", "Veracruz"),
    ("VSA", "Villahermosa"),
]
CBX_NOTE = "Passengers in Tijuana who use CBX in both directions are classified as international."
ASUR_NOTE = "Transit and general aviation passengers are excluded only for Mexico and Colombia."


def html_table(rows, **attrs):
    attributes = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return (
        "<table "
        + attributes
        + ">"
        + "".join("<tr>" + "".join("<td>" + str(c) + "</td>" for c in row) + "</tr>" for row in rows)
        + "</table>"
    )


def gap_document(*, period=MONTH, ytd_factor=None):
    end = int(period[-2:])
    year = int(period[:4])
    abbr = calendar.month_abbr[end]
    full = calendar.month_name[end]
    factor = Decimal(end if ytd_factor is None else ytd_factor)
    title = (
        "GRUPO AEROPORTUARIO DEL PACÍFICO announces preliminary terminal passenger "
        f"traffic figures for {full} {year} "
        "GUADALAJARA, Mexico, Aug. 05, 2026 "
        "12 Mexican airports operated by GAP. GAP’s airports in Jamaica. " + CBX_NOTE
    )
    header = [
        "Airport",
        f"{abbr}-{year - 1 - 2000:02d}",
        f"{abbr}-{year - 2000:02d}",
        "% Change",
        f"Jan - {abbr} {year - 1 - 2000:02d}",
        f"Jan - {abbr} {year - 2000:02d}",
        "% Change",
    ]
    for market, prior, current in [
        ("Domestic", "10.1", "11.2"),
        ("International", "2.3", "2.4"),
        ("Total", "12.4", "13.6"),
    ]:
        rows = [header]
        summed = [Decimal(0)] * 4
        for airport in MX_GAP + JAMAICA:
            country_factor = 10 if airport in JAMAICA else 1
            values = [
                Decimal(prior) * country_factor,
                Decimal(current) * country_factor,
                Decimal(prior) * country_factor * factor,
                Decimal(current) * country_factor * factor,
            ]
            summed = [a + b for a, b in zip(summed, values, strict=True)]
            tokens = [f"{v:,.1f}" for v in values]
            rows.append([airport, *tokens[:2], "0.0", "%", *tokens[2:], "0.0", "%"])
        tokens = [f"{v:,.1f}" for v in summed]
        rows.append(["Total", *tokens[:2], "0.0", "%", *tokens[2:], "0.0", "%"])
        title += f"<p>{market} Terminal Passengers (in thousands):</p>" + html_table(
            rows, market=market.lower()
        )
    title += "<p>CBX users (in thousands):</p>" + html_table(
        [header, ["Tijuana", "1.0", "999.9", "0.0", "%", "2.0", "999.9", "0.0", "%"]]
    )
    return ('<html><head><meta charset="utf-8"></head><body>' + title + "</body></html>").encode()


def asur_document(*, period=MONTH, ytd_factor=None):
    year = int(period[:4])
    end = int(period[-2:])
    full = calendar.month_name[end]
    factor = end if ytd_factor is None else ytd_factor
    body = (
        f"ASUR Announces Total Passenger Traffic for {full} {year} "
        "Grupo Aeroportuario del Sureste, S.A.B. de C.V. "
        + ASUR_NOTE
        + " Mexico City, August 5, 2026 - "
        + f"from {full} 1 to {full} {calendar.monthrange(year, end)[1]}, {year}, and from {full} 1 "
        f"to {full} {calendar.monthrange(year - 1, end)[1]}, {year - 1}"
    )

    def headers(title):
        return [
            [title, "", "", "", "", "", ""],
            ["", full, "% Chg", "", "Year to date", "% Chg"],
            [str(year - 1), str(year), "", str(year - 1), str(year)],
        ]

    def row(label, value):
        return [
            label,
            f"{value:,}",
            f"{value * 2:,}",
            "0.0",
            "",
            f"{value * factor:,}",
            f"{value * 2 * factor:,}",
            "0.0",
        ]

    # Nine Mexico airports sum domestic45/international90/total135; other countries differ.
    countries = [
        ("Mexico", 45, 90),
        ("San Juan, Puerto Rico", 4, 5),
        ("Colombia", 7, 8),
        ("Total Traffic", 56, 103),
    ]
    summary = headers("Passenger Traffic Summary")
    for label, domestic, international in countries:
        summary += [
            row(label, domestic + international),
            row("Domestic Traffic", domestic),
            row("International Traffic", international),
        ]
    body += html_table(summary, scope="summary")
    detail = headers("Mexico Passenger Traffic")
    for label, multiplier in [
        ("Domestic Traffic", 1),
        ("International Traffic", 2),
        ("Traffic Total Mexico", 3),
    ]:
        detail.append(row(label, 45 * multiplier))
        for index, (code, name) in enumerate(ASUR_MX, 1):
            detail.append([code, name, *row("", index * multiplier)[1:]])
    return (
        '<html><head><meta charset="utf-8"></head><body>'
        + body
        + html_table(detail, scope="mexico")
        + "</body></html>"
    ).encode()


def original(product):
    cik = "1347557" if product == "gap_traffic" else "1123452"
    return dict(
        source_system="sec_edgar",
        source_file=f"{product}.htm",
        sha256="a" * 64,
        downloaded_at="2026-08-21T00:16:26Z",
        source_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/0001/exhibit.htm",
    )


def parse(product, body=None, period=MONTH):
    body = body or (gap_document(period=period) if product == "gap_traffic" else asur_document(period=period))
    return native.read(product, {"html": (body, original(product))}, period)


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic"])
def test_native_domains_country_and_month_ytd_remain_explicit(product):
    frame, details = parse(product)
    assert not frame.duplicated(native.GRAIN).any()
    assert set(frame.period_id) == {"2025M07", "2026M07", "2025YTD07", "2026YTD07"}
    assert details["first_publication_date"] is None and details["release_lag_days"] is None
    assert not details["latest_source_availability_verified"]
    if product == "gap_traffic":
        assert len(frame) == 192 and set(frame.unit) == {"thousand_passengers"} and frame.is_preliminary.all()
        current = frame.loc[frame.period_id.eq("2026M07") & frame.market.eq("total")]
        assert current.loc[current.entity_key.eq("MX"), "source_value"].tolist() == ["163.2"]
        assert current.loc[current.entity_key.eq("ALL"), "source_value"].tolist() == ["435.2"]
        assert current.loc[current.entity_key.eq("TIJ"), "source_value"].tolist() == ["13.6"]
        assert set(frame.loc[frame.country.eq("JM"), "entity_key"]) == {"MBJ", "KIN"}
    else:
        assert len(frame) == 156 and set(frame.unit) == {"passengers"}
        assert len(frame.loc[frame.country.eq("MX") & frame.airport_iata.notna(), "entity_key"].unique()) == 9
        current = frame.loc[frame.period_id.eq("2026M07") & frame.market.eq("total")]
        assert current.loc[current.entity_key.eq("MX"), "value"].tolist() == [270]
        assert current.loc[current.entity_key.eq("ALL"), "value"].tolist() == [318]


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic"])
@pytest.mark.parametrize("period,factor", [(MONTH, 0), ("2026M01", 2)])
def test_ytd_contains_month_and_january_is_the_same_period(product, period, factor):
    body = (gap_document if product == "gap_traffic" else asur_document)(period=period, ytd_factor=factor)
    with pytest.raises(ValueError, match="YTD|accumul|January|month|period"):
        parse(product, body, period)


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic"])
@pytest.mark.parametrize(
    "change",
    ["wrong_issuer", "wrong_month", "scope", "missing_airport", "duplicate", "blank", "negative", "unit"],
)
def test_invalid_source_identity_scope_and_native_domain_block(product, change):
    body = (gap_document() if product == "gap_traffic" else asur_document()).decode()
    soup = BeautifulSoup(body, "html.parser")
    if change == "wrong_issuer":
        body = (
            body.replace("GRUPO AEROPORTUARIO DEL PACÍFICO", "OTRO EMISOR")
            if product == "gap_traffic"
            else body.replace("Grupo Aeroportuario del Sureste", "Otro Emisor")
        )
    elif change == "wrong_month":
        body = body.replace("July 2026", "June 2026")
    elif change == "scope":
        body = (
            body.replace(CBX_NOTE, "CBX passengers are domestic.")
            if product == "gap_traffic"
            else body.replace(ASUR_NOTE, "Transit and general aviation included.")
        )
    elif change == "unit":
        body = (
            body.replace("(in thousands)", "(in passengers)")
            if product == "gap_traffic"
            else body.replace("Mexico Passenger Traffic", "Mexico Passenger Traffic (in thousands)")
        )
    else:
        table = soup.select_one(
            'table[market="domestic"]' if product == "gap_traffic" else 'table[scope="mexico"]'
        )
        rows = table.find_all("tr")
        row = rows[1] if product == "gap_traffic" else rows[4]
        if change == "missing_airport":
            row.decompose()
        elif change == "duplicate":
            table.append(BeautifulSoup(str(row), "html.parser").find("tr"))
        else:
            row.find_all("td")[1 if product == "gap_traffic" else 2].string = (
                "" if change == "blank" else "-1"
            )
        body = str(soup)
    with pytest.raises(ValueError):
        parse(product, body.encode())


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic"])
def test_sec_group_cik_cannot_be_replaced_by_other_issuer(product):
    row = original(product)
    row["source_url"] = row["source_url"].replace(
        "1347557" if product == "gap_traffic" else "1123452", "1561861"
    )
    body = gap_document() if product == "gap_traffic" else asur_document()
    with pytest.raises(ValueError, match="CIK"):
        native.read(product, {"html": (body, row)}, MONTH)


@pytest.mark.parametrize("difference,allowed", [("0.1", True), ("0.2", False)])
def test_gap_component_rounding_bound_preserves_reported_value(difference, allowed):
    soup = BeautifulSoup(gap_document(), "html.parser")
    row = soup.select_one('table[market="total"]').find_all("tr")[1]
    row.find_all("td")[2].string = str(Decimal("13.6") + Decimal(difference))
    if allowed:
        frame, _ = parse("gap_traffic", str(soup).encode())
        selected = frame.loc[
            frame.entity_key.eq("GDL") & frame.market.eq("total") & frame.period_id.eq("2026M07")
        ]
        assert selected.source_value.tolist() == [str(Decimal("13.6") + Decimal(difference))]
    else:
        with pytest.raises(ValueError, match="rounding|reconcil"):
            parse("gap_traffic", str(soup).encode())


def test_asur_one_passenger_mismatch_is_not_given_gap_rounding_tolerance():
    soup = BeautifulSoup(asur_document(), "html.parser")
    row = soup.select_one('table[scope="mexico"]').find_all("tr")[4]
    row.find_all("td")[2].string = "2"
    with pytest.raises(ValueError, match="reconcil|differs"):
        parse("asur_traffic", str(soup).encode())


@pytest.fixture(params=["gap_traffic", "asur_traffic"])
def stored(request, tmp_path, monkeypatch):
    product = request.param
    workspace = ROOT / "tmp/source-updates" / ("independent-group-" + uuid4().hex)
    source = tmp_path / "bronze"
    body = gap_document() if product == "gap_traffic" else asur_document()
    row = original(product)
    path = save_bronze(
        body,
        "sec_edgar",
        product,
        MONTH,
        "htm",
        row["source_url"],
        "manual",
        bronze_root=source,
        downloaded_at=datetime(2026, 8, 21, tzinfo=UTC),
    )

    def no_http(*args, **kwargs):
        pytest.fail("No external source request allowed")

    monkeypatch.setattr(httpx.Client, "send", no_http)
    saved = retained.retain(
        workspace, source, product, {"html": path.relative_to(source).as_posix()}, execute=True
    )
    try:
        yield workspace, product, saved["run_id"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_gold_mexico_only_exact_scaling_nulls_and_derived_lineage(stored):
    workspace, product, run_id = stored
    result = candidate.run(workspace, product, MONTH, CUTOFF, run_id, execute=True)
    airport = pd.read_parquet(workspace / "data/gold/fact_airport_traffic.parquet")
    group = pd.read_parquet(workspace / "data/gold/fact_airport_group_traffic.parquet")
    bridge = pd.read_parquet(workspace / "data/gold/bridge_record_lineage.parquet")
    assert set(airport.country) == set(group.country) == {"MX"}
    assert not airport.airport_iata.isin(["MBJ", "KIN", "SJU"]).any()
    assert airport.operations.isna().all() and airport.cargo_tons.isna().all()
    current = group.loc[group.period_id.eq("2026M07")].iloc[0]
    assert current.passengers_total == (163200 if product == "gap_traffic" else 270)
    selected = bridge.loc[bridge.record_id.eq(current.record_id)]
    if product == "gap_traffic":
        assert set(selected.lineage_type) == {"derived"}
        assert selected.lineage_note.str.contains("bound600").all()
        native_frame = pd.read_parquet(workspace / "data/silver/airport_group_native.parquet")
        assert (
            native_frame.loc[native_frame.entity_key.eq("MX"), "value_status"]
            .eq("calculated_sum_of_rounded_airports")
            .all()
        )
    else:
        assert set(selected.lineage_type) == {"direct_artifact"}
    before = candidate.inventory(workspace)
    replay = candidate.run(workspace, product, MONTH, CUTOFF, run_id, check=True)
    assert replay["output_sha256"] == result["output_sha256"] and candidate.inventory(workspace) == before
    assert not result["ready_for_calendar_incorporation"] and result["activation"] == "none"


@pytest.mark.parametrize("change", ["YTD", "scope", "country", "preliminary"])
def test_revisions_include_ytd_and_native_semantics(stored, change):
    workspace, product, run_id = stored
    originals, _ = retained.originals(workspace, product, run_id, CUTOFF)
    frame, _ = native.read(product, originals, MONTH)
    before = frame.copy()
    if change == "YTD":
        index = before.index[before.period_type.eq("year_to_date")][0]
        before.loc[index, "value"] += 1
    elif change == "scope":
        before.loc[0, "source_definition"] = "different native definition"
    elif change == "country":
        before.loc[0, "country"] = "OTHER"
    else:
        before.loc[0, "is_preliminary"] = not before.loc[0, "is_preliminary"]
    path = workspace / "baselines/prior.parquet"
    path.parent.mkdir()
    before.to_parquet(path, index=False)
    result = candidate.revisions(
        workspace, "baselines/prior.parquet", product, {"silver/airport_group_native": frame}
    )
    assert result["changed"] == 1


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic"])
@pytest.mark.parametrize("adapter", ["retained", "government", "airport_group"])
def test_readiness_rejects_cross_family_adapters_before_source_reads(product, adapter):
    root = ROOT / "tmp/source-updates" / ("independent-static-" + uuid4().hex)
    item = dict(
        id="group",
        product=product,
        period=MONTH,
        adapter=adapter,
        workspace=str(root / "source"),
        receipt_id="a" * 32,
        required=True,
        candidate_as_of=CUTOFF,
    )
    proposal = dict(version=1, as_of=CUTOFF, required_items=["group"], items=[item])
    if adapter == "airport_group":
        assert readiness.preflight(proposal, root / "round")[0]["adapter"] == adapter
    else:
        with pytest.raises(ValueError, match="adapter"):
            readiness.preflight(proposal, root / "round")
    item["adapter"] = "airport_group"
    item["period"] = "2026Q3"
    with pytest.raises(ValueError, match="monthly"):
        readiness.preflight(proposal, root / "round")
    assert not root.exists()


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic", "aicm_traffic", "aifa_traffic"])
@pytest.mark.parametrize("entrypoint", ["run", "frames"])
def test_generic_path_rejects_every_dedicated_product_before_any_source_read(
    monkeypatch, product, entrypoint
):
    workspace = ROOT / "tmp/source-updates" / ("independent-dedicated-guard-" + uuid4().hex)

    def forbidden(*args, **kwargs):
        pytest.fail("A dedicated product entered the generic source reader")

    monkeypatch.setattr(retained, "originals", forbidden)
    with pytest.raises(ValueError, match="candidate"):
        getattr(retained, entrypoint)(workspace, product, MONTH, CUTOFF, "a" * 32)
    assert not workspace.exists()

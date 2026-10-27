"""AM Q3 source contracts; synthetic fixtures never establish real acquisition."""

import hashlib
import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.source_updates import availability, financials, retained
from src.source_updates import availability_am_financials as discovery
from src.source_updates import financials_html as source
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect

# Independent expected domain and reported units/values, from the reviewed layout.
METRICS = [
    ("total_revenue", "Total revenue", "1,619"),
    ("operating_expenses_total", "Total operating expenses", "1,429"),
    ("operating_income", "Total operating income", "190"),
    ("net_income", "Net income (loss) for the period", "41"),
    ("income_before_tax", "Income before income tax", "48"),
    ("income_tax", "Income tax (benefit)", "7"),
    ("jet_fuel_expense", "Jet-fuel", "469"),
    ("wages_salaries_benefits", "Wages, salaries and benefits", "325"),
    ("maintenance_expense", "Maintenance", "66"),
    ("depreciation_amortization", "Depreciation and amortization", "196"),
    ("aircraft_leasing_expense", "Aircraft leasing", "3"),
    ("adjusted_ebitdar", "Adjusted EBITDAR (1)", "389"),
    ("ebitdar_margin", "Adjusted EBITDAR margin (1) (% revenue)", "24.0%"),
    ("operating_margin", "Operating income margin (% of revenue)", "11.7%"),
    ("asm", "Total ASMs (millions)", "9,395"),
    ("rpm", "Total RPMs (millions)", "8,296"),
    ("load_factor", "Load factor on scheduled flights (%)", "88.3%"),
    ("passengers", "Passengers ('000)", "6,161"),
    ("fuel_liters", "Total liters of fuel ('000)", "445,237"),
    ("casm_ex_fuel", "Total cost excluding fuel / ASM (USD cents)", "10.1"),
]
TITLE = "Aeroméxico Reports Unaudited Third Quarter 2026 Results"
ANCHORS = [
    "aeromxicoreportsunauditedt.htm",
    "aeromxicojulytrafficreport.htm",
    "aeromxicoaugusttrafficrepo.htm",
    "aeromxicoseptembertrafficr.htm",
]
INDEX = b'<h2>2026</h2><h3>Q3</h3><a href="/system/files-encrypted/3Q26.pdf">Quarterly Earnings Release</a>'


def seven(values):
    return "<tr>" + "".join(f'<td colspan="3">{v}</td>' for v in values) + "</tr>"


def report():
    index = (
        "<table>"
        + "".join(
            f'<tr><td><a href="#{a}">99.{i}</a></td><td></td><td><a href="#{a}">'
            + (f"Press Release dated October 19, 2026, titled {TITLE}" if i == 1 else f"Traffic report {i}")
            + "</a></td></tr>"
            for i, a in enumerate(ANCHORS, 1)
        )
        + "</table>"
    )
    cover = "FORM 6-K For the month of October 2026 Commission File Number: 001-42931 "
    cover += (
        f"On October 19, 2026, Grupo Aeroméxico, S.A.B. de C.V. issued {TITLE} "
        "as Exhibit 99.1 Date: October 19, 2026"
    )
    groups = (
        '<tr><td colspan="3"></td><td colspan="9">Three Months Ended September 30</td>'
        '<td colspan="9">Nine Months Ended September 30</td></tr>'
    )
    statement = (
        "<table><tr><td>Consolidated Statements of Profit or Loss and other Comprehensive "
        "Income (Unaudited)</td></tr>"
    )
    statement += groups + seven(["", "2026", "2025", "Var. %", "2026", "2025", "Var. %"])
    indicators = (
        "<table>" + groups + seven(["Financial Indicators", "2026", "2025", "Var.", "2026", "2025", "Var."])
    )
    for i, (_, label, token) in enumerate(METRICS):
        row = seven([label, token, "1", "NA", "999", "2", "NA"])
        if i < 11:
            statement += row
        else:
            if i == 14:
                indicators += seven(["Operating Indicators", "2026", "2025", "Var.", "2026", "2025", "Var."])
            indicators += row
    intro = f"{TITLE} Mexico City, Mexico, October 19, 2026 - Grupo Aeroméxico S.A.B. de C.V. "
    intro += (
        "reported unaudited consolidated financial results for the three months ended September 30, 2026. "
    )
    intro += "The Company has used the U.S. dollar, its functional currency, as the presentation currency. "
    intro += (
        "All figures are expressed in millions of U.S. dollars unless otherwise indicated. "
        "available seat miles (ASMs)"
    )
    html = f'<div id="block-client-site-content"><html><body>{cover}{index}</body></html>'
    for i, anchor in enumerate(ANCHORS):
        content = intro + statement + "</table>" + indicators + "</table>" if i == 0 else "Traffic data only"
        html += f'<div><a name="{anchor}"></a></div><html><body>{content}</body></html>'
    return (html + "</div>").encode("utf-8")


def original(body):
    return dict(
        source_system="aeromexico_ir",
        source_url="https://ir.aeromexico.com/node/9131/html",
        source_file="synthetic/am-q3.html",
        logical_key="aeromexico_ir|am_financials_2026Q3_6K|2026Q3|html",
        downloaded_at="2026-10-27T13:20:28Z",
        sha256=hashlib.sha256(body).hexdigest(),
    )


def parsed(body):
    return financials.parse({"html": (body, original(body))}, "2026Q3")


def test_exact_twenty_quarter_metrics_and_explicit_unknown_preliminary():
    frame, result = parsed(report())
    assert list(frame.metric_key) == [k for k, _, _ in METRICS]
    assert frame.set_index("metric_key").value.to_dict() == {
        key: float(token.replace(",", "").replace("%", "")) for key, _, token in METRICS
    }
    assert frame.is_preliminary.isna().all() and frame.is_unaudited.all() and frame.not_ytd.all()
    assert result["source_preliminary"] is None and result["source_report_date_as_reported"] == "2026-10-19"
    assert result["first_publication_date"] is result["release_lag_days"] is None
    assert set(frame.loc[frame.metric_key.isin(["asm", "rpm"]), "unit"]) == {
        "million ASM-mile",
        "million RPM-mile",
    }
    assert frame.set_index("metric_key").loc["casm_ex_fuel", "unit"] == "USD cents per ASM-mile"
    assert not frame.normalized_unit_conversion_performed.any()
    assert result["excluded_traffic_exhibits"] == ["99.2", "99.3", "99.4"]
    assert frame.source_locator.str.startswith("exhibit:99.1/").all()
    assert retained.spec("am_financials")["role_sets"] == [{"pdf"}, {"html"}]
    for roles, period in (
        ({"pdf": (b"", {})}, "2026Q3"),
        ({"html": (report(), original(report()))}, "2026Q2"),
        ({"pdf": (b"", {}), "html": (report(), original(report()))}, "2026Q3"),
    ):
        with pytest.raises(ValueError, match="editions"):
            financials.parse(roles, period)


def test_documentary_scope_dates_columns_units_and_amounts_are_not_guessed():
    raw = report().decode()
    mutations = [
        ("cover-issuer", "Grupo Aeroméxico, S.A.B. de C.V.", "Other Airline, S.A.B. de C.V."),
        ("cover-day", "Date: October 19, 2026", "Date: October 20, 2026"),
        ("body-day", "Mexico City, Mexico, October 19, 2026", "Mexico City, Mexico, October 20, 2026"),
        ("quarter", "three months ended September 30, 2026", "three months ended June 30, 2026"),
        ("anchor", 'name="aeromxicoreportsunauditedt.htm"', 'name="unrelated.htm"'),
        ("wrong-exhibit", 'href="#aeromxicoreportsunauditedt.htm"', 'href="#aeromxicojulytrafficreport.htm"'),
        ("YTD", "Three Months Ended September 30", "Nine Months Ended September 30"),
        ("year", '>2026</td><td colspan="3">2025', '>2025</td><td colspan="3">2026'),
        ("currency", "millions of U.S. dollars", "millions of Mexican pesos"),
        ("ASM", "Total ASMs (millions)", "Total ASKs (millions)"),
        (
            "CASM",
            "Total cost excluding fuel / ASM (USD cents)",
            "Total cost excluding fuel / ASK (USD cents)",
        ),
        ("nan", ">1,619<", ">NaN<"),
        ("identity", ">1,619<", ">1,650<"),
        ("percent", ">88.3%<", ">88.3<"),
        ("negative-physical", ">9,395<", ">-9,395<"),
        ("preliminary", "reported unaudited", "reported preliminary unaudited"),
    ]
    for name, before, after in mutations:
        assert before in raw, name
        with pytest.raises(ValueError):
            parsed(raw.replace(before, after).encode())
    duplicated = seven(["Jet-fuel", "469", "1", "NA", "999", "2", "NA"])
    with pytest.raises(ValueError, match="duplicated"):
        parsed(raw.replace(duplicated, duplicated + duplicated).encode())
    with pytest.raises(ValueError, match="SHA integrity"):
        financials.parse({"html": (report() + b"changed", original(report()))}, "2026Q3")


def test_local_monetary_table_exceptions_override_intro_without_relabeling_physical_units():
    raw = report().decode()
    targets = (
        "<table><tr><td>Consolidated Statements",
        '<table><tr><td colspan="3"></td><td colspan="9">Three Months',
    )
    for target in targets:
        assert target in raw
        for unit in (
            "Amounts in millions of Mexican pesos",
            "Cifras en millones de pesos mexicanos",
            "Amounts in thousands of U.S. dollars",
            "USD thousands",
            "Importes expresados en miles de dólares estadounidenses",
            "Mexican pesos (millions)",
            "Statement amounts denominated in Mexican pesos",
            "Statement amounts denominated in thousands of U.S. dollars",
        ):
            inserted = f'<tr><td colspan="21">{unit}</td></tr>'
            changed = raw.replace(target, "<table>" + inserted + target.removeprefix("<table>"))
            with pytest.raises(ValueError, match="local monetary table heading"):
                parsed(changed.encode())
        # Monetary default remains USD millions; separately labelled quantities/ratios are unchanged.
        unit = (
            "Amounts in millions of U.S. dollars; passengers in thousands; "
            "fuel in thousand liters; CASM in USD cents per ASM"
        )
        changed = raw.replace(
            target, '<table><tr><td colspan="21">' + unit + "</td></tr>" + target.removeprefix("<table>")
        )
        frame, _ = parsed(changed.encode())
        assert frame.set_index("metric_key").loc["passengers", "unit"] == "thousand passengers"
        assert frame.set_index("metric_key").loc["fuel_liters", "unit"] == "thousand liters"
        assert frame.set_index("metric_key").loc["casm_ex_fuel", "unit"] == "USD cents per ASM-mile"


@pytest.fixture
def physical():
    root = ROOT / "tmp/source-updates" / ("am-financial-html-test-" + uuid4().hex)
    collection, candidate = root / "collection", root / "candidate"
    bodies = {discovery.INDEX: INDEX, source.URL: report()}

    class Client:
        def __init__(self, *args, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kw):
            return httpx.Response(200, content=bodies[url], request=httpx.Request(method, url))

    selection = dict(
        version=1,
        items=[
            dict(
                id=key,
                product="am_financials",
                source_system="aeromexico_ir",
                entity=entity,
                period=period,
                extension="html",
                purpose=purpose,
                url=url,
            )
            for key, entity, period, purpose, url in (
                ("index", "am_financials_catalog", "current", "catalog", discovery.INDEX),
                ("native", "am_financials_2026Q3_6K", "2026Q3", "data", source.URL),
            )
        ],
    )
    try:
        collected = collect(selection, collection, execute=True, client_factory=Client)
        cutoff = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
        row = next(r for r in collected["items"] if r["id"] == "native")
        retained_receipt = retained.retain(
            candidate, collection / "data/bronze", "am_financials", {"html": row["source_file"]}, execute=True
        )
        inputs, receipt_sha = retained.originals(
            candidate, "am_financials", retained_receipt["run_id"], cutoff
        )
        frame, result = financials.parse(inputs, "2026Q3")
        path = candidate / "data/silver/source_products/am_financials.parquet"
        path.parent.mkdir(parents=True)
        frame.to_parquet(path)
        # Direct availability binding fixture, never a complete accepted candidate/runtime proof.
        result.update(status="checks_passed", retention_receipt_sha256=receipt_sha)
        item = dict(
            product="am_financials",
            adapter="retained",
            period="2026Q3",
            workspace=str(candidate),
            receipt_id=retained_receipt["run_id"],
            availability=dict(
                workspace=str(collection),
                run_id=collected["run_id"],
                catalog_item="index",
                artifact_item="native",
            ),
        )
        yield root, item, result, cutoff
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_physical_availability_uses_distinct_official_formats_without_pdf_equivalence(physical):
    root, item, result, cutoff = physical
    before = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    proof = availability.verify(item, result, cutoff)
    assert proof["latest_available_period"] == "2026Q3"
    assert proof["source_report_date_as_reported"] == "2026-10-19"
    assert not proof["direct_index_link_to_native_artifact"] and not proof["PDF_byte_equivalence_claimed"]
    assert proof["first_publication_date"] is proof["release_lag_days"] is None
    assert proof["announced_pdf_url"] != proof["source_artifact_url"]
    after = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    assert before == after
    for key, value in (
        ("source_report_date_as_reported", "2026-10-20"),
        ("source_preliminary", False),
        ("financial_exhibit", "99.2"),
    ):
        changed = deepcopy(result)
        changed[key] = value
        with pytest.raises(ValueError, match="report evidence"):
            availability.verify(item, changed, cutoff)
    with pytest.raises(ValueError, match="explicit round date"):
        availability.verify(item, result, (datetime.fromisoformat(cutoff) + timedelta(days=1)).isoformat())
    native = root / "candidate/data/silver/source_products/am_financials.parquet"
    frame = pd.read_parquet(native)
    frame.loc[0, "value"] += 1
    frame.to_parquet(native)
    with pytest.raises(ValueError, match="exact official"):
        availability.verify(item, result, cutoff)


def test_index_latest_quarter_and_physical_receipt_cannot_be_asserted(physical, tmp_path):
    root, item, result, cutoff = physical
    for body in (
        INDEX.replace(b"Q3", b"Q2"),
        INDEX + INDEX.replace(b"3Q26", b"other"),
        INDEX.replace(b"Quarterly Earnings Release", b"Transcript"),
    ):
        path = tmp_path / "index.html"
        path.write_bytes(body)
        if body == INDEX.replace(b"Q3", b"Q2"):
            assert discovery.latest_quarter(path)[0] == "2026Q2"
        else:
            with pytest.raises(ValueError):
                discovery.latest_quarter(path)
    receipt = root / "collection/receipts" / f"collection-{item['availability']['run_id']}.json"
    original_receipt = receipt.read_bytes()
    changed = json.loads(original_receipt)
    next(r for r in changed["items"] if r["id"] == "native")["response_url"] = discovery.INDEX
    receipt.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        availability.verify(item, result, cutoff)
    receipt.write_bytes(original_receipt)
    raw_row = next(r for r in changed["items"] if r["id"] == "native")
    raw = root / "collection/data/bronze" / raw_row["source_file"]
    raw.write_bytes(raw.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="successful direct official capture"):
        availability.verify(item, result, cutoff)


def test_updated_releases_and_malformed_future_quarters_cannot_disappear_from_discovery(tmp_path):
    path = tmp_path / "index.html"
    for suffix in (
        '<a href="/system/files-encrypted/updated.pdf">Quarterly Earnings Release (Updated)</a>',
        '<h3>Q4 amended</h3><a href="/system/files-encrypted/4Q26.pdf">Quarterly Earnings Release</a>',
        (
            '<h2>2027 amended</h2><h3>Q1</h3><a href="/system/files-encrypted/1Q27.pdf">'
            "Quarterly Earnings Release</a>"
        ),
    ):
        path.write_bytes(INDEX + suffix.encode())
        with pytest.raises(ValueError, match="pertinent quarterly earnings release"):
            discovery.latest_quarter(path)
    # Other documents do not announce another quarterly earnings release.
    path.write_bytes(
        INDEX + b'<h3>Q4 planned</h3><a href="/presentation.pdf">Investor Presentation</a>'
        b'<a href="/annual.pdf">Annual Earnings Release</a>'
    )
    assert discovery.latest_quarter(path)[0] == "2026Q3"

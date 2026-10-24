"""Independent adversarial checks with synthetic inputs, never copied source figures."""

from __future__ import annotations

import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from src.source_updates.afac_carrier_source import estimate, pdf_dates, pdf_values
from src.source_updates.carrier_source_candidate import period_check
from src.source_updates.carrier_source_contract import amount
from src.source_updates.carrier_source_inputs import inputs, retain
from src.source_updates.catalog import ROOT
from src.source_updates.volaris_sec_source import dates, metadata


@pytest.mark.parametrize("token", ["(12", "12)", "(-12)", "(12))", "((12)", "1,23", "NaN", "1e4"])
def test_malformed_financial_tokens_cannot_be_accepted_or_flip_sign(token):
    with pytest.raises(ValueError):
        amount(token)


def test_dash_remains_unknown_and_parentheses_have_one_negative_meaning():
    assert amount("-") is None
    assert amount("0") == Decimal(0)
    assert amount("(12)") == amount("-12") == Decimal(-12)
    assert amount("(12.50%)") == Decimal("-12.50")


def test_pdf_suffix_columns_do_not_split_world_two_fly_name():
    line = "World 2 Fly 1,200 1,300 8.3% 0.3% 800 900 12.5% 0.2% 100 110 10.0% 0.5%"
    name, counts = pdf_values(line)
    assert name == "World 2 Fly"
    assert counts == ["1,200", "1,300", "800", "900", "100", "110"]


@pytest.mark.parametrize(
    "line",
    [
        "World 2 Fly 1,20 130 8.3% 0.3% 80 90 12.5% 0.2% 10 11 10.0% 0.5%",
        "World 2 Fly 120 130 8.3% 0.3% 80 90 12.5% 0.2% 10 11 10.0%",
        "World 2 Fly 120 130 8.3% 0.3% 80 90 12.5% 0.2% 10 - 10.0% 0.5%",
    ],
)
def test_pdf_malformed_count_or_missing_column_is_not_shifted(line):
    with pytest.raises(ValueError):
        pdf_values(line)


def test_annual_ytd_month_and_instant_dates_remain_distinct():
    assert pdf_dates(1, 8) == ("year", "2024FY", "2024-01-01", "2024-12-31")
    assert pdf_dates(4, 8) == ("year_to_date", "2026YTD08", "2026-01-01", "2026-08-31")
    assert pdf_dates(6, 8) == ("month", "2026M08", "2026-08-01", "2026-08-31")
    assert dates(297, 1, "total_revenue") == ("quarter", "2026Q2", "2026-04-01", "2026-06-30")
    assert dates(300, 1, "total_revenue") == ("half_year", "2026H1", "2026-01-01", "2026-06-30")
    assert dates(313, 2, "total_assets") == ("instant", "2025-12-31", None, "2025-12-31")
    assert dates(289, 4, "aircraft_total") == ("instant", "2026-03-31", None, "2026-03-31")


def test_estimation_note_applies_to_documented_period_only():
    notes = "Datos estimados de Synthetic para marzo 2026."
    assert estimate("Synthetic Air", "2026-03-01", "2026-03-31", notes) is True
    assert estimate("Synthetic Air", "2026-01-01", "2026-08-31", notes) is True
    assert estimate("Synthetic Air", "2026-08-01", "2026-08-31", notes) is None
    assert estimate("Other Air", "2026-03-01", "2026-03-31", notes) is None


@pytest.mark.parametrize("period", ["2026M06", "2026Q3", "2026FY", "2025Q2"])
def test_quarterly_volaris_does_not_satisfy_monthly_or_other_edition(period):
    with pytest.raises(ValueError):
        period_check("volaris_sec", period)


def dossier():
    """Only public filing identifiers are literal; no report amounts or source body."""
    directory = "/Archives/edgar/data/1520504/000129281426003836"
    accession = "0001292814-26-003836"
    primary = (
        "<html>FORM 6-K Controladora Vuela Compañía de Aviación, S.A.B. de C.V. "
        "July 2026 July 21, 2026 Financial Results for the Second Quarter 2026 "
        '<a href="ex99-1.htm">Exhibit</a><a href="ex99-1.htm">Exhibit again</a></html>'
    ).encode()
    bodies = {
        "html": b"<html>Synthetic exhibit, no financial figures</html>",
        "primary": primary,
        "submissions": json.dumps(
            {
                "cik": "0001520504",
                "name": "Controladora Vuela Compania de Aviacion, S.A.B. de C.V.",
                "filings": {
                    "recent": {
                        "accessionNumber": [accession],
                        "form": ["6-K"],
                        "reportDate": ["2026-06-30"],
                        "filingDate": ["2026-07-21"],
                        "acceptanceDateTime": ["2026-07-21T21:30:26.000Z"],
                        "primaryDocument": ["vlrspr2q26_6k.htm"],
                    }
                },
            }
        ).encode(),
    }
    bodies["index"] = json.dumps(
        {
            "directory": {
                "name": directory,
                "item": [
                    {"name": "ex99-1.htm", "size": str(len(bodies["html"]))},
                    {"name": "vlrspr2q26_6k.htm", "size": str(len(primary))},
                ],
            }
        }
    ).encode()
    urls = dict(
        html="https://www.sec.gov" + directory + "/ex99-1.htm",
        primary="https://www.sec.gov" + directory + "/vlrspr2q26_6k.htm",
        index="https://www.sec.gov" + directory + "/index.json",
        submissions="https://data.sec.gov/submissions/CIK0001520504.json",
    )
    return {
        role: (
            body,
            dict(source_url=urls[role], source_system="sec", downloaded_at="2026-08-01T12:00:00+00:00"),
        )
        for role, body in bodies.items()
    }


def test_two_anchors_to_one_exhibit_are_one_supported_filing():
    metadata(dossier())


@pytest.mark.parametrize("change", ["cik", "acceptance", "index_size", "alias", "role_url", "early_capture"])
def test_filing_identity_and_supporting_roles_cannot_be_borrowed(change):
    data = dossier()
    if change in {"cik", "acceptance"}:
        value = json.loads(data["submissions"][0])
        if change == "cik":
            value["cik"] = "9999999"
        else:
            value["filings"]["recent"]["acceptanceDateTime"] = ["2026-07-20T21:30:26.000Z"]
        data["submissions"] = json.dumps(value).encode(), data["submissions"][1]
    elif change == "index_size":
        value = json.loads(data["index"][0])
        value["directory"]["item"][0]["size"] = "1"
        data["index"] = json.dumps(value).encode(), data["index"][1]
    elif change == "alias":
        data["html"][1]["source_system"] = "sec_edgar"
    elif change == "role_url":
        data["html"][1]["source_url"] = data["primary"][1]["source_url"]
    else:
        data["html"][1]["downloaded_at"] = "2026-07-01T12:00:00+00:00"
    with pytest.raises(ValueError):
        metadata(data)


@pytest.fixture
def retained_sources():
    root = ROOT / "tmp/source-updates" / ("carrier-independent-" + uuid4().hex)
    original = root / "original"
    original.mkdir(parents=True)
    records = {}
    for role, body in {
        "pdf": b"Synthetic PDF bytes, not a candidate",
        "database": b"Synthetic ZIP bytes",
    }.items():
        name = f"{role}.{'pdf' if role == 'pdf' else 'zip'}"
        p = original / name
        p.write_bytes(body)
        records[role] = dict(
            source_file=name,
            source_system="afac",
            source_url=(
                "https://datatur.sectur.gob.mx/Documentoscompartidos/afac/"
                + ("AFAC_2026_08.pdf" if role == "pdf" else "DB_AFAC.zip")
            ),
            logical_key=f"afac|synthetic_{role}|2026M08|{p.suffix[1:]}",
            downloaded_at="2026-10-19T12:00:00+00:00",
            bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            http_status=200,
            logical_version=1,
            filename_version=1,
            content_type="application/pdf" if role == "pdf" else "application/zip",
            download_method="synthetic_offline_fixture",
            notes="Synthetic contract fixture, no official source figures.",
        )
        Path(str(p) + ".meta.json").write_text(json.dumps(records[role]))
    (original / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records.values()))
    try:
        yield root, original, records
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("change", ["body", "sidecar", "ambiguous_manifest", "missing_http", "alias"])
def test_originals_require_consistent_physical_capture_before_retaining(retained_sources, change):
    root, original, records = retained_sources
    row = records["pdf"]
    p = original / row["source_file"]
    if change == "body":
        p.write_bytes(p.read_bytes() + b"tamper")
    elif change == "sidecar":
        side = Path(str(p) + ".meta.json")
        meta = json.loads(side.read_text())
        meta["source_url"] = "https://datatur.sectur.gob.mx/other.pdf"
        side.write_text(json.dumps(meta))
    elif change == "ambiguous_manifest":
        with (original / "_manifest.jsonl").open("a") as stream:
            stream.write(json.dumps(row) + "\n")
    else:
        row["http_status" if change == "missing_http" else "source_system"] = (
            None if change == "missing_http" else "afac_research"
        )
        (original / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records.values()))
        Path(str(p) + ".meta.json").write_text(json.dumps(row))
    with pytest.raises(ValueError):
        retain(
            root / "candidate",
            original,
            "afac_carriers",
            {r: v["source_file"] for r, v in records.items()},
            execute=True,
        )
    assert not (root / "candidate").exists()


@pytest.mark.parametrize("change", ["paid_requests", "new_source_capture", "retained_at"])
def test_retention_receipt_flags_and_chronology_are_not_trusted(retained_sources, change):
    root, original, records = retained_sources
    candidate = root / "candidate"
    saved = retain(
        candidate, original, "afac_carriers", {r: v["source_file"] for r, v in records.items()}, execute=True
    )
    path = candidate / "receipts" / f"retained-{saved['run_id']}.json"
    receipt = json.loads(path.read_text())
    receipt[change] = (
        "2026-01-01T00:00:00+00:00" if change == "retained_at" else 1 if change == "paid_requests" else True
    )
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        inputs(candidate, "afac_carriers", saved["run_id"], "2026-10-23T16:00:00-06:00")
    assert not (candidate / "data/gold").exists()


def test_afac_preliminary_status_requires_its_documentary_declaration(monkeypatch):
    from types import SimpleNamespace

    from src.source_updates import afac_carrier_source

    count = "12 14 16.7% 100.0% 8 10 25.0% 100.0% 2 3 50.0% 100.0%"
    headings = "2024 2025\n2025 2026\n"
    domestic = headings + "Synthetic Air " + count + "\nTotal general " + count
    international = (
        headings + "Total Mexicanas " + count + "\nSynthetic Air " + count + "\nT O T A L " + count
    )
    notes = "\nNotas:\nNotas sin declaración de preliminar.\nConsidera vuelos regulares.\nFuente: Synthetic\n"
    texts = [
        domestic + notes + "Pasajeros transportados en vuelos nacionales regulares y agosto de 2025 - 2026",
        international
        + notes
        + "Pasajeros transportados en vuelos internacionales regulares y agosto de 2025 - 2026",
    ]
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda t=t: t) for t in texts])
    monkeypatch.setattr(afac_carrier_source, "PdfReader", lambda _: reader)
    source_row = dict(
        source_system="afac",
        source_file="synthetic.pdf",
        sha256="a" * 64,
        downloaded_at="2026-10-19T12:00:00+00:00",
    )
    with pytest.raises(ValueError):
        afac_carrier_source.bulletin(b"Synthetic fake PDF parser input", source_row, "2026M08")


def synthetic_afac(retained_sources):
    """A two-page PDF and XLSX with synthetic counts for every required period."""
    import io
    from datetime import datetime
    from zipfile import ZipFile

    import openpyxl
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    _, original, records = retained_sources
    names = {
        "Nacional": ["Aeroméxico (Aerovías de México)", "Aeroméxico Connect (Aerolitoral)"],
        "Internacional": ["World 2 Fly", "Synthetic International"],
    }
    observations = []
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "AFAC"
    sheet.append(["Año", "Tipo", "Servicio", "Región", "Aerolinea", "Id_mes", "Mes", "Pasajeros", "Fecha"])
    for year in (2024, 2025, 2026):
        for month in range(1, (8 if year == 2026 else 12) + 1):
            for market, operators in names.items():
                for index, name in enumerate(operators):
                    for service in ("Regular", "Fletamento"):
                        value = 100 + month * 2 + index * 5 if service == "Regular" else 10 + month + index
                        row = [
                            year,
                            market,
                            service,
                            "Mexicana" if market == "Nacional" else "Europea",
                            name,
                            month,
                            "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()[month - 1],
                            value,
                            datetime(year, month, 1),
                        ]
                        sheet.append(row)
                        observations.append(row)
    workbook = io.BytesIO()
    book.save(workbook)
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("DB_AFAC.xlsx", workbook.getvalue())

    def six_values(market, name):
        result = []
        for year, limit, only_august in [
            (2024, 12, False),
            (2025, 12, False),
            (2025, 8, False),
            (2026, 8, False),
            (2025, 8, True),
            (2026, 8, True),
        ]:
            result.append(
                sum(
                    r[7]
                    for r in observations
                    if r[0] == year
                    and r[1] == market
                    and r[2] == "Regular"
                    and (name is None or r[4] == name)
                    and (r[5] == 8 if only_august else r[5] <= limit)
                )
            )
        return result

    def source_line(name, values):
        return (
            name
            + " "
            + " ".join(
                [
                    str(values[0]),
                    str(values[1]),
                    "0.0%",
                    "50.0%",
                    str(values[2]),
                    str(values[3]),
                    "0.0%",
                    "50.0%",
                    str(values[4]),
                    str(values[5]),
                    "0.0%",
                    "50.0%",
                ]
            )
        )

    pdf = PdfWriter()
    for market, operators in names.items():
        lines = ["2024 2025", "2025 2026"]
        if market == "Internacional":
            lines.append(source_line("Total Europeas", six_values(market, None)))
        lines.extend(source_line(name, six_values(market, name)) for name in operators)
        lines.append(
            source_line("Total general" if market == "Nacional" else "T O T A L", six_values(market, None))
        )
        lines.extend(
            [
                "Notas:",
                "Las cifras pueden variar debido a correcciones o ajustes por parte de la fuente,",
                "por lo que es importante tomarlas con carácter preliminar.",
                "Considera el flujo de pasajeros en vuelos regulares.",
                "Datos estimados de Synthetic International para marzo 2026.",
                "Fuente: Synthetic contract fixture.",
                "Pasajeros transportados en vuelos "
                + ("nacionales" if market == "Nacional" else "internacionales"),
                "(enero - agosto) y agosto de 2025 - 2026",
            ]
        )
        page = pdf.add_blank_page(width=1000, height=850)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): pdf._add_object(font)})}
        )
        content = b"BT /F1 7 Tf 20 820 Td "
        for line in lines:
            literal = (
                line.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            )
            content += b"(" + literal + b") Tj 0 -12 Td\n"
        stream = DecodedStreamObject()
        stream.set_data(content + b"ET")
        page[NameObject("/Contents")] = pdf._add_object(stream)
    body = io.BytesIO()
    pdf.write(body)
    for role, content in {"pdf": body.getvalue(), "database": archive.getvalue()}.items():
        row = records[role]
        p = original / row["source_file"]
        p.write_bytes(content)
        row.update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        Path(str(p) + ".meta.json").write_text(json.dumps(row))
    (original / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records.values()))
    return observations


def afac_native(retained_sources):
    from src.source_updates.afac_carrier_source import read
    from src.source_updates.carrier_source_contract import identifier

    synthetic_afac(retained_sources)
    root, original, records = retained_sources
    selected = {role: ((original / row["source_file"]).read_bytes(), row) for role, row in records.items()}
    native, details = read(selected, "2026M08")
    native["record_id"] = native.apply(identifier, axis=1)
    return native, details


def test_synthetic_afac_full_chain_replay_and_operator_ancestry(retained_sources):
    import pandas as pd

    from src.source_updates.carrier_source_candidate import inventory, run

    observations = synthetic_afac(retained_sources)
    root, original, records = retained_sources
    candidate = root / "candidate"
    saved = retain(
        candidate, original, "afac_carriers", {r: v["source_file"] for r, v in records.items()}, execute=True
    )
    args = (candidate, "afac_carriers", "2026M08", "2026-10-23T16:00:00-06:00", saved["run_id"])
    accepted = run(*args, execute=True)
    before = inventory(candidate)
    assert run(*args, check=True)["output_sha256"] == accepted["output_sha256"]
    assert inventory(candidate) == before
    native = pd.read_parquet(candidate / "data/silver/afac_carriers_source_native.parquet")
    facts = pd.read_parquet(candidate / "data/gold/fact_afac_carrier_source.parquet")
    assert len(native) == 298 and len(facts) == 8
    assert set(facts.period_id) == {"2026M08"}
    assert set(facts.unit) == {"passengers_transported"}
    assert {"AEROMEXICO", "AEROMEXICO_CONNECT"} <= set(facts.carrier_key.dropna())
    world = facts.loc[facts.entity_as_reported.eq("World 2 Fly")]
    assert len(world) == 2 and world.carrier_key.isna().all()
    assert facts.source_estimated.isna().all()
    for r in facts.itertuples(index=False):
        parents = json.loads(r.native_parent_record_ids)
        rows = native.set_index("record_id").loc[parents]
        assert len(parents) == (2 if r.service_type == "scheduled" else 1)
        assert set(rows.entity_as_reported) == {r.entity_as_reported}
        assert set(rows.period_id) == {"2026M08"}
        expected = next(
            v[7]
            for v in observations
            if v[0] == 2026
            and v[5] == 8
            and v[4] == r.entity_as_reported
            and v[2] == ("Regular" if r.service_type == "scheduled" else "Fletamento")
        )
        assert r.value == expected
    with pytest.raises(ValueError, match="immutable"):
        run(*args, execute=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_table", "PDF:2"),
        ("source_locator", "pdf/page[1]/line[9999]/count[6]"),
        ("source_column", 5),
        ("is_preliminary", False),
        ("is_unaudited", True),
        ("source_estimated", True),
        ("period_start_date", "2026-01-01"),
        ("aviation_scope", "scheduled_and_charter"),
        ("carrier_key", "AEROMEXICO_CONNECT"),
    ],
)
def test_afac_native_row_semantics_cannot_be_relabelled(retained_sources, field, value):
    from src.source_updates.afac_carrier_source import validate

    native, _ = afac_native(retained_sources)
    index = native.index[
        native.statement.eq("pdf_operator")
        & native.period_id.eq("2026M08")
        & native.carrier_key.eq("AEROMEXICO")
    ][0]
    native.loc[index, field] = value
    with pytest.raises(ValueError):
        validate(native)


def test_gold_does_not_accept_omitted_parent_or_history_projection(retained_sources):
    from src.source_updates.carrier_source_gold import projection, verify_projection

    native, _ = afac_native(retained_sources)
    gold = projection(native, "afac_carriers")
    row = gold.index[gold.service_type.eq("scheduled")][0]
    gold.loc[row, "native_parent_record_ids"] = json.dumps(
        json.loads(gold.loc[row, "native_parent_record_ids"])[:1]
    )
    with pytest.raises(ValueError):
        verify_projection(native, gold, "afac_carriers")


@pytest.mark.parametrize(
    "layer,table",
    [
        ("silver", "afac_carriers_source_native"),
        ("gold", "fact_afac_carrier_source"),
        ("gold", "dim_source_artifact"),
        ("gold", "bridge_record_lineage"),
    ],
)
def test_synthetic_afac_replay_rejects_each_output_corruption_without_writes(retained_sources, layer, table):
    import pandas as pd

    from src.source_updates.carrier_source_candidate import inventory, run

    synthetic_afac(retained_sources)
    root, original, records = retained_sources
    candidate = root / "candidate"
    saved = retain(
        candidate, original, "afac_carriers", {r: v["source_file"] for r, v in records.items()}, execute=True
    )
    args = (candidate, "afac_carriers", "2026M08", "2026-10-23T16:00:00-06:00", saved["run_id"])
    run(*args, execute=True)
    path = candidate / "data" / layer / (table + ".parquet")
    frame = pd.read_parquet(path)
    frame = frame.iloc[1:].reset_index(drop=True)
    frame.to_parquet(path, index=False)
    before = inventory(candidate)
    with pytest.raises(ValueError):
        run(*args, check=True)
    assert inventory(candidate) == before


@pytest.mark.parametrize("table", [297, 300])
@pytest.mark.parametrize("column", [1, 2])
@pytest.mark.parametrize(
    "row,token", [(10, "2"), (11, "2"), (13, "20"), (14, "20"), (16, "100000000"), (17, "100000000")]
)
def test_volaris_eps_ads_and_exact_shares_must_reconcile(table, column, row, token):
    from src.source_updates.volaris_sec_source import read
    from src.source_updates.volaris_source_checks import reconcile
    from tests.test_source_update_carrier import synthetic_volaris

    native, _ = read(synthetic_volaris(), "2026Q2")
    index = native.index[
        native.source_table.eq(str(table))
        & native.source_row_number.eq(row)
        & native.source_column.eq(column)
    ][0]
    native.loc[index, "source_value"] = token
    native.loc[index, "value"] = float(token)
    with pytest.raises(ValueError, match="IAS33 EPS|ADS=10CPO"):
        reconcile(native)

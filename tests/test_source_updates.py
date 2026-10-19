"""No live sources: calendar boundaries and collection-to-parser evidence with fixtures."""

import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.source_updates.__main__ import main
from src.source_updates.build import build
from src.source_updates.catalog import ROOT, product_map
from src.source_updates.checks import check_candidate, row_changes, verify_bronze
from src.source_updates.collection import collect, safe_workspace, validate_url, writer


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / f"pytest-{uuid4().hex}"
    yield path
    if path.exists():
        shutil.rmtree(path)


def selection(*, mode="get", extension="json", purpose="data", url="https://www.eia.gov/test.json"):
    return {
        "version": 1,
        "items": [
            {
                "id": "fuel",
                "product": "fuel",
                "source_system": "eia",
                "entity": "EER_EPJK_PF4_RGC_DPG",
                "period": "2015-01-01_2026-09-30",
                "purpose": purpose,
                "url": url,
                "extension": extension,
                "mode": mode,
            }
        ],
    }


def test_collect_dry_run_does_not_construct_client_or_write(workspace):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run constructed HTTP client")

    result = collect(selection(), workspace, client_factory=forbidden)
    assert result["base_requests"] == 1
    assert not workspace.exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://www.eia.gov/a",
        "https://eia.gov.evil.test/a",
        "https://eia.gov@evil.test/a",
        "https://www.eia.gov/a?token=x",
        "https://www.eia.gov:8080/a",
    ],
)
def test_only_public_catalogue_hosts_without_credentials(url):
    with pytest.raises(ValueError):
        validate_url(url, ["eia.gov"])


def test_no_active_workspace_writes(workspace):
    with pytest.raises(ValueError, match="Candidate"):
        safe_workspace(ROOT)
    with writer(workspace):
        with pytest.raises(FileExistsError):
            with writer(workspace):
                pass
    assert not (workspace / ".source-update.lock").exists()


class FakeClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        status, content, headers = self.responses.pop(0)
        return httpx.Response(status, content=content, headers=headers, request=httpx.Request(method, url))


@pytest.fixture
def fake_client():
    FakeClient.calls = []
    FakeClient.responses = []
    return FakeClient


def test_revalidate_dedupe_and_revision_keep_all_originals(workspace, fake_client):
    fake_client.responses = [(200, b'{"value":1}', {})] * 2 + [(200, b'{"value":2}', {})]
    receipts = [collect(selection(), workspace, execute=True, client_factory=fake_client) for _ in range(3)]
    assert len(fake_client.calls) == 3  # Existing URL is rechecked every round.
    assert receipts[0]["items"][0]["source_file"] == receipts[1]["items"][0]["source_file"]
    assert receipts[2]["items"][0]["sha256"] != receipts[0]["items"][0]["sha256"]
    events = (workspace / "data/bronze/_restatements.jsonl").read_text().splitlines()
    assert len(events) == 1
    assert len(verify_bronze(workspace)) == 2
    assert all(row["items"][0]["latest_validated_period"] is None for row in receipts)


@pytest.mark.parametrize("status,body", [(403, b"denied"), (200, b"<html>captcha</html>"), (200, b"")])
def test_access_failure_never_becomes_empty_success(workspace, fake_client, status, body):
    fake_client.responses = [(status, body, {})]
    result = collect(selection(), workspace, execute=True, client_factory=fake_client)
    assert result["status"] == "incomplete"
    assert result["items"][0]["status"] == "access_or_payload_failed"
    assert not (workspace / "data/bronze/_manifest.jsonl").exists()


def test_redirect_is_checked_before_following(workspace, fake_client):
    fake_client.responses = [(302, b"", {"location": "https://evil.test/steal"})]
    result = collect(selection(), workspace, execute=True, client_factory=fake_client)
    assert result["status"] == "incomplete"
    assert len(fake_client.calls) == 1


def test_real_http_wrapper_redirects_are_bounded_and_checked(workspace):
    from src.common.http import SourceHttpClient, TokenBucket

    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/test.json":
            return httpx.Response(302, headers={"location": "https://www.eia.gov/next.json"})
        return httpx.Response(200, content=b'{"value": 1}')

    def factory(source, **kwargs):
        return SourceHttpClient(
            source, transport=httpx.MockTransport(handler), limiter=TokenBucket(10000), **kwargs
        )

    result = collect(selection(), workspace, execute=True, client_factory=factory)
    assert result["status"] == "collected_unvalidated"
    assert len(requested) == 2


def test_catalogue_links_are_discovered_but_not_downloaded(workspace, fake_client):
    fake_client.responses = [(200, b'<a href="/new.pdf">new</a><a href="https://evil.test/a">no</a>', {})]
    result = collect(
        selection(extension="html", purpose="catalog"), workspace, execute=True, client_factory=fake_client
    )
    assert result["items"][0]["status"] == "collected_catalog"
    assert result["items"][0]["discovered_links"] == [{"url": "https://www.eia.gov/new.pdf", "label": "new"}]
    assert len(fake_client.calls) == 1


def prepare_fuel_fixture(workspace):
    """Synthetic workbook through the REAL fuel parser in a fresh subprocess."""
    (workspace / "imports").mkdir(parents=True)
    stream = BytesIO()
    frame = pd.DataFrame({"date": pd.to_datetime(["2026-09-01", "2026-09-02"]), "price": [2.5, 2.6]})
    with pd.ExcelWriter(stream, engine="openpyxl") as excel:
        frame.to_excel(excel, sheet_name="Data 1", index=False, startrow=2)
    content = stream.getvalue()
    (workspace / "imports/fuel.xlsx").write_bytes(content)
    selected = selection(mode="manual", extension="xlsx")
    selected["items"][0].update(local_file="fuel.xlsx", sha256=hashlib.sha256(content).hexdigest())
    collect(selected, workspace, execute=True)
    return selected


def fuel_spec():
    return {
        "as_of": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "checks": [
            {
                "product": "fuel",
                "layer": "silver",
                "table": "fuel_prices",
                "period_column": "date",
                "expected_period": "2026M09",
                "filters": {"series_id": "EER_EPJK_PF4_RGC_DPG"},
                "value_columns": ["price_usd_per_gallon"],
            }
        ],
    }


def test_real_offline_parser_and_checks_end_to_end(workspace):
    prepare_fuel_fixture(workspace)
    result = build(workspace, ["parse.fuel"], execute=True)
    assert result["status"] == "completed", result
    assert result["period_acceptance"] == "not_checked"
    checked = check_candidate(workspace, fuel_spec())
    assert checked["status"] == "checks_passed", checked
    assert checked["checks"][0]["rows"] == 2
    assert checked["checks"][0]["release_lag_days"] is None
    assert checked["checks"][0]["latest_available_period"] is None
    assert checked["checks"][0]["latest_parsed_period"] == "2026M09"
    assert checked["publication"] == "not_authorized"
    missing = fuel_spec()
    missing["checks"][0]["expected_period"] = "2026M08"
    assert check_candidate(workspace, missing)["status"] == "blocked"
    artifact = next((workspace / "data/bronze/eia").glob("*.xlsx"))
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_bronze(workspace)


def test_missing_inputs_block_instead_of_using_active_checkout(workspace):
    result = build(workspace, ["parse.fuel"], execute=True)
    assert result["status"] == "failed"
    assert not (workspace / "data/silver/fuel_prices.parquet").exists()


def test_uncertified_product_cannot_borrow_another_products_table(workspace):
    prepare_fuel_fixture(workspace)
    spec = fuel_spec()
    spec["checks"][0].update(product="afac_airports", table="afac_monthly_stats")
    checked = check_candidate(workspace, spec)
    assert checked["status"] == "blocked"
    assert "No check adapter" in checked["checks"][0]["reason"]


def test_forbidden_steps_never_execute(workspace):
    for name in ("ingest.market", "analytics.stage7", "publish", "analysis.approve", "aerodatabox"):
        with pytest.raises(ValueError):
            build(workspace, [name])


def test_bmv_parser_is_not_advertised_without_offline_member_registration(workspace):
    assert product_map()["bmv_xbrl"]["parser_step"] is None
    with pytest.raises(ValueError, match="ZIP-member registration"):
        build(workspace, ["parse.bmv"])


def test_h10_only_is_not_a_sufficient_banxico_parser_input(workspace):
    (workspace / "imports").mkdir(parents=True)
    content = b"Time Period,RXI_N.B.MX\n2026-09-01,18.0\n"
    (workspace / "imports/h10.csv").write_bytes(content)
    selected = selection(mode="manual", extension="csv", url="https://www.federalreserve.gov/releases/h10/")
    selected["items"][0].update(
        product="h10",
        source_system="federal_reserve_h10",
        entity="usd_mxn",
        local_file="h10.csv",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    assert collect(selected, workspace, execute=True)["status"] == "collected_unvalidated"
    result = build(workspace, ["parse.fx"], execute=True)
    assert result["status"] == "failed"
    assert "Banxico" in result["steps"][0]["reason"]
    assert not (workspace / "data/silver/fx_rates.parquet").exists()
    fallback = build(workspace, ["parse.h10"], execute=True)
    assert fallback["status"] == "completed", fallback
    frame = pd.read_parquet(workspace / "data/silver/fx_rates.parquet")
    assert set(frame["source_system"]) == {"federal_reserve_h10"}
    assert set(frame["series_id"]) == {"H10/H10/RXI_N.B.MX"}
    assert fallback["steps"][0]["details"]["complete_macro_coverage"] is False


def test_market_declares_candidate_sec_identity_evidence(workspace):
    (workspace / "imports").mkdir(parents=True)
    content = b"date,close,volume\n2025-11-06,18.0,1\n"
    (workspace / "imports/market.csv").write_bytes(content)
    selected = selection(mode="manual", extension="csv", url="https://finance.yahoo.com/quote/AERO/")
    selected["items"][0].update(
        product="equities",
        source_system="yahoo_finance",
        entity="AERO",
        local_file="market.csv",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    collect(selected, workspace, execute=True)
    result = build(workspace, ["parse.market"], execute=True)
    assert result["status"] == "failed"
    assert "sec_report_text.parquet" in result["steps"][0]["reason"]
    assert "parse.market" in build(workspace, ["parse.market"])["prerequisites"]


def test_aeromexico_ir_uses_its_configured_rate(workspace, fake_client):
    rates = []

    def factory(rate, **kwargs):
        rates.append(rate)
        return fake_client(rate, **kwargs)

    selected = selection(
        extension="html",
        purpose="catalog",
        url="https://ir.aeromexico.com/financial-information/quarterly-results",
    )
    selected["items"][0].update(product="am_financials", source_system="aeromexico_ir")
    fake_client.responses = [(200, b'<html><a href="/financial-information/">IR</a></html>', {})]
    assert (
        collect(selected, workspace, execute=True, client_factory=factory)["status"]
        == "collected_unvalidated"
    )
    assert rates == ["aeromexico_ir"]


def test_all_operational_products_have_navigable_acquisition_recipes():
    from src.source_updates.recipes import acquisition_config, describe

    config = acquisition_config()
    assert set(config["products"]) == set(product_map())
    for product in product_map():
        recipe = describe(product)
        assert recipe["procedure"] and recipe["format"]
        assert recipe["entry_url"] is not None or recipe["state"] == "internal"


def test_generated_fuel_recipe_uses_canonical_endpoint_and_period(workspace):
    from src.ingest.macro.fuel import EIA_XLS_URL
    from src.source_updates.recipes import macro_round

    recipe = macro_round("fuel", "2026M09", "2026-10-18T18:00:00-06:00")
    assert recipe["selection"]["items"][0]["url"] == EIA_XLS_URL
    assert recipe["selection"]["items"][0]["period"] == "2015-01-01_2026-09-30"
    assert recipe["steps"] == ["parse.fuel"]
    assert collect(recipe["selection"], workspace)["base_requests"] == 1


def test_generated_banxico_recipe_posts_exact_public_forms_and_parses(workspace, fake_client):
    from src.source_updates.recipes import macro_round

    recipe = macro_round("banxico", "2026M09", (datetime.now(UTC) + timedelta(minutes=1)).isoformat())
    fake_client.responses = [
        (200, f'"Fecha","{item["entity"]}"\n"01/09/2026","18.0"\n'.encode(), {})
        for item in recipe["selection"]["items"]
    ]
    collected = collect(recipe["selection"], workspace, execute=True, client_factory=fake_client)
    assert collected["status"] == "collected_unvalidated", collected
    assert [method for method, _ in fake_client.calls] == ["POST"] * 3
    built = build(workspace, recipe["steps"], execute=True)
    assert built["status"] == "completed", built
    checked = check_candidate(workspace, recipe["checks"])
    assert checked["status"] == "checks_passed", checked


def test_generated_h10_recipe_declares_exact_series_and_separate_parser():
    from src.source_updates.recipes import macro_round

    recipe = macro_round("h10", "2026M09", "2026-10-18T18:00:00-06:00")
    assert "rel=H10" in recipe["selection"]["items"][0]["url"]
    assert recipe["steps"] == ["parse.h10"]
    assert recipe["checks"]["checks"][0]["filters"]["series_id"] == "H10/H10/RXI_N.B.MX"


def test_revisions_count_nulls_without_filling_them():
    before = pd.DataFrame({"key": [1, 2, 3], "value": [None, 2, 3]})
    after = pd.DataFrame({"key": [1, 2, 4], "value": [None, 5, 4]})
    assert row_changes(before, after, ["key"], ["value"]) == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "unchanged": 1,
    }
    with pytest.raises(ValueError, match="Duplicate"):
        row_changes(before, pd.concat([after, after]), ["key"], ["value"])


def test_bts_year_refresh_is_explicit_including_old_years(workspace):
    from src.ingest.bts.t100 import FORM_URL

    selected = selection()
    selected["items"][0].update(
        product="bts_segments",
        source_system="bts_t100",
        period="2023",
        year=2023,
        mode="bts_year",
        extension="zip",
        url=FORM_URL,
    )
    result = collect(selected, workspace)
    assert result["base_requests"] == 2
    assert "historical_bts_years" in result["revalidation"]
    assert not workspace.exists()


def test_bts_capture_keeps_existing_parser_logical_url(workspace, fake_client, monkeypatch):
    import zipfile
    from types import SimpleNamespace

    import src.parse.bts.t100 as parser
    from src.ingest.bts.t100 import FORM_URL

    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("fixture.csv", "YEAR,MONTH\n2023,12\n")
    fake_client.responses = [
        (200, b'<form method="post" action="/download"></form>', {}),
        (200, stream.getvalue(), {}),
    ]
    selected = selection()
    selected["items"][0].update(
        product="bts_segments",
        source_system="bts_t100",
        period="2023",
        year=2023,
        mode="bts_year",
        extension="zip",
        url=FORM_URL,
    )
    captured = collect(selected, workspace, execute=True, client_factory=fake_client)
    assert captured["status"] == "collected_unvalidated"
    assert "requested_year=2023" in captured["items"][0]["source_url"]
    monkeypatch.setattr(parser, "PATHS", SimpleNamespace(bronze=workspace / "data/bronze"))
    assert len(parser._manifest_records()) == 1


def test_cli_sample_round_dry_run_does_not_write(workspace, capsys):
    assert (
        main(
            [
                "round",
                "--recipe",
                str(ROOT / "config/source_update_round.example.json"),
                "--workspace",
                str(workspace),
                "--dry-run",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "planned_not_executed"
    assert not workspace.exists()


def test_news_dedupe_preserves_each_provenance_and_dated_editions():
    from src.source_updates.news import deduplicate

    records = [
        {
            "source_system": source,
            "source_file": source + ".json",
            "source_hash": source * 32,
            "title": "Synthetic headline",
            "url": "https://example.test/article" + tracking,
            "published_at": stamp,
        }
        for source, tracking, stamp in [
            ("rss", "?utm_source=google", "2026-09-01T12:00:00Z"),
            ("gdelt", "?fbclid=abc", "2026-09-01T12:00:00Z"),
            ("gdelt", "", "2026-09-02T12:00:00Z"),
        ]
    ]
    output = deduplicate(records)
    assert len(output) == 2
    assert len(json.loads(output[0]["provenance_json"])) == 2
    assert output[0]["canonical_url"] == "https://example.test/article"
    records[0]["source_system"] = "news_http_error"
    with pytest.raises(ValueError, match="eligible"):
        deduplicate(records)


def test_gold_contract_and_direct_lineage_are_checked(workspace):
    (workspace / "imports").mkdir(parents=True)
    content = b'{"synthetic": true}'
    (workspace / "imports/prices.json").write_bytes(content)
    selected = selection(mode="manual", url="https://finance.yahoo.com/quote/AERO/")
    selected["items"][0].update(
        product="equities",
        source_system="yahoo_finance",
        entity="AERO",
        local_file="prices.json",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    collected = collect(selected, workspace, execute=True)["items"][0]
    from src.transform.stage6_contracts import add_record_id

    frame = pd.DataFrame(
        [
            {
                "carrier_key": "AEROMEXICO",
                "ticker": "AERO",
                "date": pd.Timestamp("2026-09-01"),
                "calendar_period_id": "2026-09-01",
                "fiscal_period_id": "2026-09-01",
                "close": 10.0,
                "adj_close": 10.0,
                "volume": 100,
                "currency": "USD",
                "return_1d": None,
                "return_ytd": None,
                "volatility_30d": None,
                "source_system": "yahoo_finance",
                "source_file": collected["source_file"],
                "source_hash": collected["sha256"],
                "ingested_at": pd.Timestamp.now(tz="UTC").tz_localize(None),
            }
        ]
    )
    frame = add_record_id("fact_market_data", frame)
    (workspace / "data/gold").mkdir()
    output = workspace / "data/gold/fact_market_data.parquet"
    frame.to_parquet(output)
    spec = {
        "as_of": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "checks": [
            {
                "product": "equities",
                "layer": "gold",
                "table": "fact_market_data",
                "period_column": "date",
                "expected_period": "2026M09",
                "filters": {"carrier_key": "AEROMEXICO"},
                "value_columns": ["close"],
            }
        ],
    }
    checked = check_candidate(workspace, spec)
    assert checked["status"] == "checks_passed", checked
    frame["source_hash"] = "0" * 64
    frame.to_parquet(output)
    blocked = check_candidate(workspace, spec)
    assert blocked["status"] == "blocked"
    assert "lineage" in blocked["checks"][0]["reason"]


def test_news_offline_parser_keeps_cross_source_provenance(workspace):
    (workspace / "imports").mkdir(parents=True)
    rss = (
        b"<rss><channel><item><title>Synthetic headline</title>"
        b"<link>https://example.test/article?utm_source=google</link>"
        b"<pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate><source>Fixture</source>"
        b"</item></channel></rss>"
    )
    gdelt = json.dumps(
        {
            "articles": [
                {
                    "title": "Synthetic headline",
                    "url": "https://example.test/article",
                    "seendate": "20260901T120000Z",
                    "language": "English",
                }
            ]
        }
    ).encode()
    selected = {"version": 1, "items": []}
    for name, product, source, entity, url, extension, content in [
        ("rss", "rss", "rss", "google_en", "https://news.google.com/rss/search?q=fixture", "xml", rss),
        (
            "gdelt",
            "gdelt",
            "gdelt",
            "aeromexico_articles",
            "https://api.gdeltproject.org/api/v2/doc/doc?query=fixture",
            "json",
            gdelt,
        ),
    ]:
        filename = name + "." + extension
        (workspace / "imports" / filename).write_bytes(content)
        selected["items"].append(
            {
                "id": name,
                "product": product,
                "source_system": source,
                "entity": entity,
                "period": "2026M09",
                "purpose": "data",
                "url": url,
                "extension": extension,
                "mode": "manual",
                "local_file": filename,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    assert collect(selected, workspace, execute=True)["status"] == "collected_unvalidated"
    built = build(workspace, ["parse.news"], execute=True)
    assert built["status"] == "completed", built
    output = pd.read_parquet(workspace / "data/silver/news_headlines.parquet")
    assert len(output) == 1
    assert output.iloc[0]["language"] == "en"
    assert len(json.loads(output.iloc[0]["provenance_json"])) == 2


def test_symlink_inside_candidate_is_rejected(workspace):
    workspace.mkdir(parents=True)
    (workspace / "data").symlink_to(ROOT / "data", target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        safe_workspace(workspace)

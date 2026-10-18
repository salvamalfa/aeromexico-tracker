"""No live sources: calendar boundaries and collection-to-parser evidence with fixtures."""

import hashlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.source_updates import calendar
from src.source_updates.__main__ import main
from src.source_updates.build import build
from src.source_updates.catalog import FAMILIES, ROOT, load_catalog, plan, product_map
from src.source_updates.checks import check_candidate, row_changes, verify_bronze
from src.source_updates.collection import collect, safe_workspace, validate_url, writer


@pytest.fixture
def holidays():
    return json.loads((ROOT / "config/source_update_holidays.json").read_text())


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


def test_catalogue_all_sources_have_unique_family_and_products():
    sources = load_catalog()
    assert len(sources) == 29
    assert set(sources) == {key for keys in FAMILIES.values() for key in keys}
    assert {row["source_key"] for row in product_map().values()} == set(sources)
    assert not any("aerodatabox" in key for key in product_map())


def test_monthly_holiday_weekend_and_no_unverified_year(holidays):
    assert calendar.monthly(2026, 8, holidays) == date(2026, 8, 17)
    assert calendar.monthly(2026, 11, holidays) == date(2026, 11, 17)
    assert calendar.monthly(2026, 10, holidays) == date(2026, 10, 15)
    assert calendar.roll_forward(date(2026, 11, 2), holidays) == date(2026, 11, 3)
    with pytest.raises(ValueError, match="Unverified"):
        calendar.monthly(2027, 1, holidays)


def releases():
    # Synthetic scheduling fixture. These are NOT assertions about actual releases.
    return [
        {
            "entity": entity,
            "period": "2026Q3",
            "published_at": "2026-10-30T23:00:00Z",
            "kind": "financial_report",
            "confirmed": True,
            "document_url": "https://example.test/report",
        }
        for entity in calendar.CENTRAL
    ]


def test_quarterly_two_strictly_later_business_days_and_local_zone(holidays):
    result = calendar.quarterly("2026Q3", releases(), "2026-11-01T00:00:00Z", holidays)
    assert result["date"] == "2026-11-04"  # Friday report; Monday Nov 2 is bank holiday.
    assert calendar.local_time("2026-11-01T02:00:00Z").date() == date(2026, 10, 31)


@pytest.mark.parametrize("change", ["missing", "announcement", "unconfirmed", "future", "different_quarter"])
def test_quarterly_unknown_dates_are_not_invented(holidays, change):
    records = releases()
    if change == "missing":
        records.pop()
    elif change == "announcement":
        records[0]["kind"] = "earnings_call"
    elif change == "unconfirmed":
        records[0]["confirmed"] = False
    elif change == "future":
        records[0]["published_at"] = "2026-11-02T12:00:00-06:00"
    else:
        records[0]["period"] = "2026Q2"
    assert calendar.quarterly("2026Q3", records, "2026-11-01T00:00:00Z", holidays)["date"] is None


@pytest.mark.parametrize(("quarter_date", "expected_count"), [("2026-10-22", 1), ("2026-10-23", 2)])
def test_combine_uses_inclusive_seven_natural_days(quarter_date, expected_count):
    rounds = [{"kind": "monthly", "date": "2026-10-15"}, {"kind": "quarterly", "date": quarter_date}]
    result = calendar.combine(rounds)
    assert len(result) == expected_count
    if len(result) == 1:
        assert result[0]["date"] == quarter_date
        assert result[0]["kind"] == "combined"


def test_retries_are_proposals_with_a_two_reschedule_limit(holidays):
    result = calendar.retry_date(today=date(2026, 10, 30), attempts=0, reason="technical", holidays=holidays)
    assert result["date"] == "2026-11-03"
    assert (
        calendar.retry_date(today=date(2026, 10, 30), attempts=2, reason="unknown", holidays=holidays)[
            "status"
        ]
        == "blocked_for_decision"
    )


def test_plan_is_source_collection_not_gold_freshness():
    result = plan("monthly", "2026-10-18T12:00:00Z")
    assert result["network_requests"] == 0 and result["writes"] == []
    assert {"rss", "gdelt"} <= {row["id"] for row in result["products"]}
    assert all(row["target_period"] == "2026M09" for row in result["products"])
    assert all(row["latest_validated_period"] is None for row in result["products"])
    quarterly = plan("quarterly", "2026-10-18T12:00:00Z", "2026Q3")
    assert not {"rss", "gdelt"} & {row["id"] for row in quarterly["products"]}
    assert {"anac", "aerocivil", "caa"} <= {row["id"] for row in quarterly["products"]}


def test_cannot_plan_unclosed_quarter():
    with pytest.raises(ValueError, match="not closed"):
        plan("quarterly", "2026-10-18T12:00:00Z", "2026Q4")


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


def test_forbidden_steps_never_execute(workspace):
    for name in ("ingest.market", "analytics.stage7", "publish", "analysis.approve", "aerodatabox"):
        with pytest.raises(ValueError):
            build(workspace, [name])


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

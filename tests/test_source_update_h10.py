"""H.10 contract failures and isolated candidate lifecycle, using synthetic official layouts."""

import csv
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import io
import json
import shutil
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.source_updates import h10
from src.source_updates.catalog import ROOT
from src.source_updates.h10_capture import BoundedFedClient, MAX_BYTES, URLS
from src.source_updates.h10_parse import csv_rates, holiday_evidence, html_rates, quote, reconcile


HOLIDAYS = [
    ("New Year's Day", "January 1"),
    ("Birthday of Martin Luther King, Jr.", "January 19"),
    ("Washington's Birthday", "February 16"),
    ("Memorial Day", "May 25"),
    ("Juneteenth National Independence Day", "June 19"),
    ("Independence Day", "July 4*"),
    ("Labor Day", "September 7"),
    ("Columbus Day", "October 12"),
    ("Veterans Day", "November 11"),
    ("Thanksgiving Day", "November 26"),
    ("Christmas Day", "December 25"),
]
K8 = (
    "For holidays falling on Saturday, Federal Reserve Banks open preceding Friday; "
    "Board of Governors will be closed. For holidays falling on Sunday, closed following Monday."
    "<table><tr><th></th><th>2026</th></tr>"
    + "".join(f"<tr><td>{name}</td><td>{day}</td></tr>" for name, day in HOLIDAYS)
    + "</table>"
).encode()


def samples(period="2026M09"):
    start, end = h10.month_bounds(period)
    holidays = holiday_evidence(K8, start.year)
    data = {
        day.date(): "ND" if day.date() in holidays else str(Decimal("18.0000") + Decimal(i) / 10000)
        for i, day in enumerate(pd.bdate_range(start, end))
    }
    return data


def csv_sample(data):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerows(
        [
            ["Series Description", "Japanese Yen", "Mexican Peso"],
            ["Unit:", "Currency", "Currency"],
            ["Multiplier:", "1", "1"],
            ["Currency:", "JPY", "MXN"],
            ["Unique Identifier: ", "H10/H10/RXI_N.B.JA", "H10/H10/RXI_N.B.MX"],
            ["Time Period", "RXI_N.B.JA", "RXI_N.B.MX"],
        ]
    )
    writer.writerows([[day.isoformat(), "150.0000", value] for day, value in data.items()])
    return out.getvalue().encode()


def html_sample(data):
    return (
        "Historical Rates for the Mexican Peso. (Rates in Mexican pesos per U.S. dollar) "
        "Release Date: Tuesday, October 13, 2026 <table><tr><th>Date</th><th>Rate</th></tr>"
        + "".join(
            f"<tr><td>{day.strftime('%d-%b-%y').upper()}</td><td>{value}</td></tr>"
            for day, value in data.items()
        )
        + "</table>"
    ).encode()


def bodies():
    data = samples()
    return {
        "csv": csv_sample(data),
        "history": html_sample(data),
        "holidays": K8,
        "definition": b"The data are noon buying rates in New York. Past releases are not revised.",
        "release": b"ND = No data for this date.",
        "transition": b"Build Your Package removed week of November 9, 2026; later retirement not dated.",
    }


def fixture_client(payloads, calls):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            calls.append(url)
            role = "csv" if "Output.aspx" in url else next(k for k, u in URLS.items() if u == url)
            return httpx.Response(200, content=payloads[role], request=httpx.Request(method, url))

    return Client


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("h10-test-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def cutoff():
    return (datetime.now(UTC) + timedelta(minutes=1)).isoformat()


def accepted(workspace):
    return h10.run(workspace, "2026M09", cutoff(), execute=True, client_factory=fixture_client(bodies(), []))


def test_dry_run_never_opens_client_or_creates_workspace(workspace):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    result = h10.run(workspace, "2026M09", cutoff(), client_factory=forbidden)
    assert result["network_requests"] == 0 and not workspace.exists()
    assert result["collection"]["base_requests"] == 6
    assert result["collection"]["maximum_http_requests"] == 30
    assert result["collection"]["paid_requests"] == 0


def test_h10_month_reaches_nullable_silver_monthly_gold_and_verified_lineage(workspace):
    result = accepted(workspace)
    assert result["status"] == "checks_passed", result
    assert result["rows"] == 22 and result["observed_values"] == 21
    assert result["source_nd_dates"] == ["2026-09-07"]
    fx = pd.read_parquet(workspace / "data/silver/fx_rates.parquet")
    assert fx.date.is_unique and fx.rate_close.isna().sum() == 1
    missing = fx.loc[fx.observation_status.eq("ND")].iloc[0]
    assert missing.source_value == "ND" and pd.isna(missing.rate_close)
    assert missing.holiday_evidence == "Labor Day"
    assert set(fx.currency_pair) == {"USD/MXN"} and set(fx.unit) == {"mxn_per_usd"}
    gold = pd.read_parquet(workspace / "data/gold/fact_macro.parquet")
    expected = [Decimal(value) for value in samples().values() if value != "ND"]
    assert gold.set_index("aggregation").value.to_dict() == {
        "average": float(sum(expected) / len(expected)),
        "close": float(expected[-1]),
    }
    assert set(gold.period_type) == {"month"} and set(gold.indicator_key) == {"usd_mxn"}
    assert set(gold.source_system) == {"federal_reserve_h10"} and set(gold.unit) == {"mxn_per_usd"}
    assert (
        result["lineage"]["records_expected"] == 2
        and result["lineage"]["declared_without_exact_link_records"] == 0
    )
    assert result["lineage"]["artifact_count"] == 6
    assert result["first_publication_date"] is None and result["release_lag_days"] is None
    assert not result["fix"] and result["activation"] == "none"
    before = dict(result["output_sha256"])
    checked = h10.run(workspace, "2026M09", cutoff(), check=True)
    assert checked["output_sha256"] == before
    with pytest.raises(ValueError, match="immutable"):
        accepted(workspace)
    assert checked["output_sha256"] == before


def test_rejected_new_capture_leaves_no_gold_and_preserves_raw_evidence(workspace):
    payload = bodies()
    data = samples()
    data.pop(date(2026, 9, 30))
    payload["csv"] = csv_sample(data)
    result = h10.run(workspace, "2026M09", cutoff(), execute=True, client_factory=fixture_client(payload, []))
    assert result["status"] == "blocked_certification"
    assert not (workspace / "data/gold").exists()
    assert len(list((workspace / "data/bronze").rglob("*.csv"))) == 1
    assert not (workspace / "receipts/h10-2026M09.json").exists()


def test_existing_gold_cannot_be_relabelled_or_rescaled(workspace):
    assert accepted(workspace)["status"] == "checks_passed"
    path = workspace / "data/gold/fact_macro.parquet"
    frame = pd.read_parquet(path)
    frame["unit"] = "usd_per_mxn"
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="differs from its verified originals"):
        h10.run(workspace, "2026M09", cutoff(), check=True)


def test_bronze_tampering_is_detected_before_gold_use(workspace):
    assert accepted(workspace)["status"] == "checks_passed"
    path = next((workspace / "data/bronze").rglob("*.csv"))
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        h10.run(workspace, "2026M09", cutoff(), check=True)


def test_allowed_host_receipt_tampering_still_invalidates_acceptance(workspace):
    result = accepted(workspace)
    path = workspace / "receipts" / f"collection-{result['collection_run_id']}.json"
    receipt = json.loads(path.read_text())
    receipt["items"][0]["response_url"] = URLS["definition"]
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="collection receipt hash changed"):
        h10.run(workspace, "2026M09", cutoff(), check=True)


def test_check_rejects_capture_after_cutoff(workspace):
    assert accepted(workspace)["status"] == "checks_passed"
    with pytest.raises(ValueError, match="captured after"):
        h10.run(workspace, "2026M09", "2026-10-02T00:00:00Z", check=True)


@pytest.mark.parametrize("vintage", [b"September 29, 2026", b"October 13, 2027"])
def test_history_vintage_must_cover_month_without_looking_ahead(workspace, vintage):
    payload = bodies()
    payload["history"] = payload["history"].replace(b"October 13, 2026", vintage)
    result = h10.run(workspace, "2026M09", cutoff(), execute=True, client_factory=fixture_client(payload, []))
    assert result["status"] == "blocked_certification"
    assert not (workspace / "data/gold").exists()


def test_failed_http_never_builds_silver_or_gold(workspace):
    class Failed(fixture_client(bodies(), [])):
        def request(self, method, url, **kwargs):
            return httpx.Response(503, request=httpx.Request(method, url))

    result = h10.run(workspace, "2026M09", cutoff(), execute=True, client_factory=Failed)
    assert result["status"] == "blocked_collection"
    assert not (workspace / "data/gold").exists()
    assert not (workspace / "data/silver").exists()


def test_other_macro_source_is_never_overwritten(workspace):
    path = workspace / "data/silver/fx_rates.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"source_system": ["banxico_sie"]}).to_parquet(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="cannot overwrite"):
        accepted(workspace)
    assert path.read_bytes() == before and not (workspace / "data/bronze").exists()


@pytest.mark.parametrize(
    "reader,sample", [(csv_rates, csv_sample), (lambda content: html_rates(content)[0], html_sample)]
)
def test_duplicate_dates_are_rejected_even_when_values_agree(reader, sample):
    body = sample(samples())
    if reader is csv_rates:
        body += body.splitlines(keepends=True)[6]
    else:
        row = b"<tr><td>01-SEP-26</td><td>18.0000</td></tr>"
        body = body.replace(b"</table>", row + b"</table>")
    with pytest.raises(ValueError, match="Duplicate"):
        reader(body)


@pytest.mark.parametrize("change", ["last_day", "holiday", "swap_weekend"])
def test_truncated_or_false_same_count_month_is_rejected(change):
    data = samples()
    if change == "last_day":
        data.pop(date(2026, 9, 30))
    elif change == "holiday":
        data.pop(date(2026, 9, 7))
    else:
        data[date(2026, 9, 5)] = data.pop(date(2026, 9, 1))
    with pytest.raises(ValueError, match="Incomplete"):
        reconcile(data, data, "2026M09", holiday_evidence(K8, 2026))


def test_nonholiday_nd_requires_separate_evidence_and_source_disagreement_blocks():
    data = samples()
    data[date(2026, 9, 1)] = "ND"
    with pytest.raises(ValueError, match="separate source review"):
        reconcile(data, data, "2026M09", holiday_evidence(K8, 2026))
    left = samples()
    right = dict(left)
    right[date(2026, 9, 1)] = "0.0555556"
    with pytest.raises(ValueError, match="sources disagree"):
        reconcile(left, right, "2026M09", holiday_evidence(K8, 2026))


@pytest.mark.parametrize("value", ["", "NaN", "Inf", "-1", "0", "18,30", "1e2", " 18.3 "])
def test_ambiguous_or_invalid_quotes_are_not_missing_values(value):
    with pytest.raises(ValueError):
        quote(value)


@pytest.mark.parametrize(
    "before,after",
    [
        (b"Mexican Peso", b"Japanese Yen"),
        (b"Unit:,Currency,Currency", b"Unit:,Currency,Percent"),
        (b"1,1", b"1,1000"),
        (b"JPY,MXN", b"JPY,USD"),
        (b"H10/H10/RXI_N.B.MX", b"H10/H10/RXI$US_N.B.MX"),
    ],
)
def test_wrong_series_scale_currency_or_metadata_blocks(before, after):
    with pytest.raises(ValueError):
        csv_rates(csv_sample(samples()).replace(before, after, 1))


def test_inverse_html_unit_and_unverified_calendar_year_block():
    with pytest.raises(ValueError, match="per one U.S. dollar"):
        html_rates(
            html_sample(samples()).replace(b"Mexican pesos per U.S. dollar", b"U.S. dollars per Mexican peso")
        )
    with pytest.raises(ValueError, match="not verified"):
        holiday_evidence(K8, 2027)


@pytest.mark.parametrize(
    "period,rows,observed", [("2026M02", 20, 19), ("2026M07", 23, 22), ("2026M09", 22, 21)]
)
def test_month_coverage_is_calendar_driven_not_fixed_twenty_one(period, rows, observed):
    result = reconcile(samples(period), samples(period), period, holiday_evidence(K8, 2026))
    assert len(result) == rows and sum(r["observation_status"] == "observed" for r in result) == observed


def test_k8_does_not_invent_nd_when_both_sources_report_a_quote():
    data = samples()
    data[date(2026, 9, 7)] = "18.0000"
    assert all(
        r["observation_status"] == "observed"
        for r in reconcile(data, data, "2026M09", holiday_evidence(K8, 2026))
    )


def test_streaming_client_rejects_declared_and_decoded_oversize(monkeypatch):
    import gzip

    import src.source_updates.h10_capture as capture

    monkeypatch.setattr(
        capture, "get_rate_limiter", lambda _: type("Limiter", (), {"acquire": lambda self: None})()
    )

    class Stream(httpx.SyncByteStream):
        def __init__(self, body):
            self.body = body

        def __iter__(self):
            yield self.body

    for headers, body in [
        ({"content-length": str(MAX_BYTES + 1)}, b""),
        ({}, b"x" * (MAX_BYTES + 1)),
        ({"content-encoding": "gzip"}, gzip.compress(b"x" * (MAX_BYTES + 1))),
    ]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, headers=headers, stream=Stream(body), request=request)
        )
        with BoundedFedClient("default", transport=transport) as client:
            with pytest.raises(ValueError, match="size limit"):
                client.request("GET", URLS["history"], follow_redirects=False)

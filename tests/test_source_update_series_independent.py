"""Independent synthetic contracts; passing fixtures never certify real sources."""

import csv
import hashlib
import io
import json
import math
from datetime import date
from statistics import stdev
from urllib.parse import urlencode

import pandas as pd
import pytest

from src.source_updates import series_gold as gold
from src.source_updates import series_native as native


@pytest.mark.parametrize(
    "period,start,end,months",
    [
        ("2024M02", date(2024, 2, 1), date(2024, 2, 29), ["2024M02"]),
        ("2025M02", date(2025, 2, 1), date(2025, 2, 28), ["2025M02"]),
        ("2026M09", date(2026, 9, 1), date(2026, 9, 30), ["2026M09"]),
        ("2026M12", date(2026, 12, 1), date(2026, 12, 31), ["2026M12"]),
        ("2026Q1", date(2026, 1, 1), date(2026, 3, 31), ["2026M01", "2026M02", "2026M03"]),
        ("2026Q2", date(2026, 4, 1), date(2026, 6, 30), ["2026M04", "2026M05", "2026M06"]),
        ("2026Q3", date(2026, 7, 1), date(2026, 9, 30), ["2026M07", "2026M08", "2026M09"]),
        ("2026Q4", date(2026, 10, 1), date(2026, 12, 31), ["2026M10", "2026M11", "2026M12"]),
    ],
)
def test_window_has_exact_closed_calendar_months(period, start, end, months):
    assert native.window(period) == (start, end, months)


@pytest.mark.parametrize(
    "period",
    [
        "2026M9",
        "2026M00",
        "2026M13",
        "2026Q0",
        "2026Q5",
        "2026Q03",
        "2026q3",
        "2026-09",
        "2026M09extra",
        "../2026M09",
        "",
        None,
        True,
        202609,
    ],
)
def test_window_rejects_ambiguous_or_malformed_periods(period):
    with pytest.raises((ValueError, TypeError)):
        native.window(period)


BANXICO_URL = (
    "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?accion=consultarSeries"
)
FUEL_URL = "https://www.eia.gov/dnav/pet/hist_xls/EER_EPJK_PF4_RGC_DPGd.xls"
FUEL_SERIES = "EER_EPJK_PF4_RGC_DPG"
FUEL_LABEL = "U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB (Dollars per Gallon)"
TICKERS = {"AERO": "AEROMEXICO", "VLRS": "VOLARIS", "RYAAY": "RYANAIR", "DAL": "DELTA", "ICAGY": "IAG"}


def banxico_bytes(series, observations=None, *, metadata_changes=None):
    metadata = {
        "SF43718": {
            "Título": "Tipo de Cambio (FIX)",
            "Periodicidad": "Diaria",
            "Unidad": "Pesos por Dólar",
            "Cifra": "Tipo de Cambio",
        },
        "SP1": {
            "Título": "Índice General",
            "Periodicidad": "Mensual",
            "Unidad": "Sin Unidad",
            "Cifra": "Indices",
            "Base": "2Q Jul 2018",
        },
        "SF61745": {
            "Título": "Tasa Objetivo",
            "Periodicidad": "Diaria",
            "Unidad": "Sin Unidad",
            "Cifra": "Porcentajes",
        },
    }[series]
    metadata.update(metadata_changes or {})
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerows(metadata.items())
    writer.writerow(["Fecha", series])
    writer.writerows(observations or [("01/07/2026", "10"), ("01/08/2026", "20"), ("01/09/2026", "30")])
    return output.getvalue().encode("latin1")


def fuel_bytes(observations=None, *, series=FUEL_SERIES, label=FUEL_LABEL):
    rows = [
        [None, None],
        ["Sourcekey", series],
        ["Date", label],
        *(
            observations
            or [
                (pd.Timestamp("2026-07-01"), 1),
                (pd.Timestamp("2026-08-03"), 2),
                (pd.Timestamp("2026-09-01"), 3),
            ]
        ),
    ]
    output = io.BytesIO()
    pd.DataFrame(rows).to_excel(output, sheet_name="Data 1", index=False, header=False, engine="openpyxl")
    return output.getvalue()


def original(body, source, entity, url, extension):
    return body, {
        "source_system": source,
        "source_file": f"synthetic-contract/{entity}.{extension}",
        "source_url": url,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "downloaded_at": "2026-10-18T12:00:00Z",
        "logical_key": f"{source}|{entity}|2015-01-01_2026-09-30|{extension}",
        "http_status": 200,
        "content_type": {
            "html": "text/html",
            "json": "application/json",
            "csv": "text/csv",
            "xls": "application/vnd.ms-excel",
        }[extension],
        "download_method": "httpx",
        "logical_version": 1,
        "filename_version": 1,
    }


def macro_inputs(product):
    if product == "fuel":
        return {"workbook": original(fuel_bytes(), "eia", FUEL_SERIES, FUEL_URL, "xls")}
    return {
        series: original(banxico_bytes(series), "banxico_sie", series, BANXICO_URL, "csv")
        for series in ("SF43718", "SP1", "SF61745")
    }


def chart_bytes(ticker, *, dates=None):
    if dates is None:
        dates = [
            "2025-11-06",
            "2026-01-02",
            "2026-06-30",
            "2026-07-01",
            "2026-07-02",
            "2026-08-03",
            "2026-09-01",
            "2026-09-30",
        ]
        if ticker != "AERO":
            dates.insert(0, "2015-01-02")
        # Sparse synthetic observations exercise native-history contracts,
        # never completeness of actual trading sessions.
        first = "2025-11-01" if ticker == "AERO" else "2015-01-01"
        dates.extend(
            day.replace(day=15).strftime("%Y-%m-%d") for day in pd.date_range(first, "2026-09-01", freq="MS")
        )
        dates = sorted(set(dates))
    count = len(dates)
    prices = [float(100 + i) for i in range(count)]
    return json.dumps(
        {
            "chart": {
                "error": None,
                "result": [
                    {
                        "meta": {
                            "symbol": ticker,
                            "currency": "USD",
                            "instrumentType": "EQUITY",
                            "shortName": "Grupo Aeromexico S.A.B. de C.V." if ticker == "AERO" else ticker,
                            "exchangeTimezoneName": "America/New_York",
                            "dataGranularity": "1d",
                            "exchangeName": {
                                "AERO": "NYQ",
                                "VLRS": "NYQ",
                                "RYAAY": "NMS",
                                "DAL": "NYQ",
                                "ICAGY": "PNK",
                            }[ticker],
                            "firstTradeDate": int(pd.Timestamp("2025-11-06T15:30:00Z").timestamp()),
                        },
                        "timestamp": [int(pd.Timestamp(day + "T15:30:00Z").timestamp()) for day in dates],
                        "indicators": {
                            "quote": [
                                {
                                    "open": prices,
                                    "high": [p + 1 for p in prices],
                                    "low": [p - 1 for p in prices],
                                    "close": prices,
                                    "volume": [0, *range(1, count)],
                                }
                            ],
                            "adjclose": [{"adjclose": [p * 0.9 for p in prices]}],
                        },
                    }
                ],
            }
        }
    ).encode()


def equities_inputs():
    query = urlencode(
        {
            "period1": int(pd.Timestamp("2015-01-01T00:00:00Z").timestamp()),
            "period2": int(pd.Timestamp("2026-10-01T00:00:00Z").timestamp()),
            "interval": "1d",
            "events": "div,splits",
        }
    )
    inputs = {
        ticker: original(
            chart_bytes(ticker),
            "yahoo_finance",
            ticker + "_chart",
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}",
            "json",
        )
        for ticker in TICKERS
    }
    body = (
        "<html><body>November 6, 2025, Aeromexico began trading on the New York Stock Exchange "
        "under the ticker symbol AERO.</body></html>"
    ).encode()
    inputs["identity"] = original(
        body,
        "sec",
        "AEROMEXICO",
        "https://www.sec.gov/Archives/edgar/data/1561861/000156186125000010/synthetic-contract.htm",
        "html",
    )
    return inputs


@pytest.mark.parametrize("series", ["SF43718", "SP1", "SF61745"])
def test_native_banxico_preserves_tokens_dates_and_row_locators(series):
    frame = native.banxico_file(banxico_bytes(series), series)
    assert frame.value.tolist() == [10, 20, 30]
    assert frame.source_value.tolist() == ["10", "20", "30"]
    assert frame.date.dt.strftime("%Y-%m-%d").tolist() == ["2026-07-01", "2026-08-01", "2026-09-01"]
    assert frame.source_locator.nunique() == 3


@pytest.mark.parametrize("token", ["ND", "N/E", "-", "", "NaN", "Infinity", "not-a-number", "1,234"])
def test_banxico_cannot_silently_discard_invalid_or_unapproved_missing_tokens(token):
    body = banxico_bytes("SF43718", [("01/09/2026", "20"), ("02/09/2026", token)])
    with pytest.raises(ValueError):
        native.banxico_file(body, "SF43718")


@pytest.mark.parametrize(
    "series,changes",
    [
        ("SF43718", {"Unidad": "Dólares por Peso"}),
        ("SF43718", {"Cifra": "Miles"}),
        ("SP1", {"Base": "2010"}),
        ("SP1", {"Periodicidad": "Diaria"}),
        ("SF61745", {"Cifra": "Fracción"}),
        ("SF61745", {"Título": "Tasa de otro banco"}),
    ],
)
def test_banxico_cannot_relabel_units_scale_frequency_or_index_base(series, changes):
    with pytest.raises(ValueError):
        native.banxico_file(banxico_bytes(series, metadata_changes=changes), series)


@pytest.mark.parametrize("value", ["20", "21"])
def test_duplicate_native_banxico_dates_are_not_a_revision_policy(value):
    with pytest.raises(ValueError):
        native.banxico_file(
            banxico_bytes("SF43718", [("01/09/2026", "20"), ("01/09/2026", value)]), "SF43718"
        )


def test_fuel_preserves_observations_and_does_not_require_fixed_twenty_one_days():
    frame = native.fuel_file(fuel_bytes())
    assert frame.value.tolist() == [1, 2, 3]
    assert frame.source_locator.str.startswith("Data 1!").all()
    tables, details = native.read("fuel", macro_inputs("fuel"), "2026Q3")
    assert len(tables["fuel_prices"]) == 3
    assert details["coverage"][FUEL_SERIES]["calendar_completeness_certified"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"series": "OTHER_FUEL"},
        {"label": FUEL_LABEL.replace("Gallon", "Liter")},
        {"label": FUEL_LABEL.replace("Dollars", "Euros")},
    ],
)
def test_fuel_series_and_native_units_come_from_workbook_not_filename(kwargs):
    with pytest.raises(ValueError):
        native.fuel_file(fuel_bytes(**kwargs))


@pytest.mark.parametrize("token", [None, "ND", "broken", -1])
def test_fuel_cannot_silently_drop_or_replace_an_invalid_observation(token):
    with pytest.raises(ValueError):
        native.fuel_file(fuel_bytes([(pd.Timestamp("2026-09-01"), 2), (pd.Timestamp("2026-09-02"), token)]))


@pytest.mark.parametrize("product", ["banxico", "fuel", "equities"])
def test_complete_product_requires_every_native_role(product):
    inputs = equities_inputs() if product == "equities" else macro_inputs(product)
    inputs.pop(next(iter(inputs)))
    with pytest.raises(ValueError):
        native.read(product, inputs, "2026Q3")


@pytest.mark.parametrize("missing", ["2026-07-01", "2026-08-01", "2026-09-01"])
def test_quarterly_banxico_requires_each_month_for_each_series(missing):
    inputs = macro_inputs("banxico")
    rows = [
        (day, str(i))
        for i, day in enumerate(["01/07/2026", "01/08/2026", "01/09/2026"], 1)
        if pd.to_datetime(day, format="%d/%m/%Y").strftime("%Y-%m-%d") != missing
    ]
    inputs["SP1"] = original(banxico_bytes("SP1", rows), "banxico_sie", "SP1", BANXICO_URL, "csv")
    with pytest.raises(ValueError, match="month"):
        native.read("banxico", inputs, "2026Q3")


def test_banxico_contains_all_three_indicators_in_native_units_without_h10_substitution():
    tables, details = native.read("banxico", macro_inputs("banxico"), "2026Q3")
    macro = tables["macro_indicators"]
    assert set(macro.indicator_key) == {"usd_mxn_fix", "inpc", "policy_rate"}
    assert macro.groupby("indicator_key").unit.first().to_dict() == {
        "usd_mxn_fix": "mxn_per_usd",
        "inpc": "index",
        "policy_rate": "percent",
    }
    assert set(tables["fx_rates"].series_id) == {"SF43718"}
    assert len(macro) == 9 and len(tables["fx_rates"]) == 3
    assert all(c["calendar_completeness_certified"] is False for c in details["coverage"].values())


def test_equities_preserves_history_needed_for_returns_before_target_projection():
    tables, details = native.read("equities", equities_inputs(), "2026Q3")
    market = tables["market_prices"]
    assert set(zip(market.ticker, market.carrier_key, strict=True)) == set(TICKERS.items())
    assert market.loc[market.ticker.eq("AERO"), "date"].min() == pd.Timestamp("2025-11-06")
    assert market.loc[market.ticker.eq("VLRS"), "date"].min() == pd.Timestamp("2015-01-02")
    assert not market.adj_close.eq(market.close).any()
    assert market.volume.eq(0).any()
    assert set(details["coverage"]) == set(TICKERS)


@pytest.mark.parametrize("ticker", sorted(TICKERS))
def test_quarterly_equities_cannot_hide_one_missing_month_of_one_ticker(ticker):
    inputs = equities_inputs()
    body = json.loads(inputs[ticker][0])
    chart = body["chart"]["result"][0]
    keep = [i for i, stamp in enumerate(chart["timestamp"]) if pd.Timestamp(stamp, unit="s").month != 8]
    chart["timestamp"] = [chart["timestamp"][i] for i in keep]
    for values in [chart["indicators"]["quote"][0], chart["indicators"]["adjclose"][0]]:
        for key in values:
            values[key] = [values[key][i] for i in keep]
    inputs[ticker] = (json.dumps(body).encode(), inputs[ticker][1])
    with pytest.raises(ValueError, match="month"):
        native.read("equities", inputs, "2026Q3")


@pytest.mark.parametrize("mutation", ["cik", "source", "body", "date"])
def test_aero_identity_requires_the_physical_sec_document(mutation):
    inputs = equities_inputs()
    body, record = inputs["identity"]
    if mutation == "cik":
        record["source_url"] = record["source_url"].replace("1561861/", "9999999/")
    elif mutation == "source":
        record["source_system"] = "aeromexico_ir"
    elif mutation == "body":
        body = b"<html>Silver alone says AERO began trading, but this original does not.</html>"
    else:
        body = body.replace(b"November 6, 2025", b"November 6, 2024")
    inputs["identity"] = (body, record)
    with pytest.raises(ValueError):
        native.read("equities", inputs, "2026Q3")


@pytest.mark.parametrize("symbol", ["AEROV", "NOAERO", "AERO.MX"])
def test_aero_identity_cannot_accept_a_different_symbol_sharing_aero_prefix(symbol):
    inputs = equities_inputs()
    body, record = inputs["identity"]
    inputs["identity"] = (body.replace(b"symbol AERO.", f"symbol {symbol}.".encode()), record)
    with pytest.raises(ValueError):
        native.read("equities", inputs, "2026Q3")


def test_market_cannot_certify_observations_later_than_their_physical_capture():
    inputs = equities_inputs()
    inputs["AERO"][1]["downloaded_at"] = "2026-09-01T12:00:00Z"
    with pytest.raises(ValueError):
        native.read("equities", inputs, "2026Q3")


def test_equities_cannot_restart_ytd_by_shortening_the_native_request():
    inputs = equities_inputs()
    record = inputs["VLRS"][1]
    original_start = str(int(pd.Timestamp("2015-01-01T00:00:00Z").timestamp()))
    truncated_start = str(int(pd.Timestamp("2026-07-01T00:00:00Z").timestamp()))
    record["source_url"] = record["source_url"].replace(original_start, truncated_start)
    with pytest.raises(ValueError):
        native.read("equities", inputs, "2026Q3")


def test_quarterly_macro_weights_native_observations_not_three_monthly_means():
    inputs = macro_inputs("banxico")
    rows = [
        ("01/07/2026", "10"),
        ("02/07/2026", "20"),
        ("03/07/2026", "30"),
        ("03/08/2026", "100"),
        ("01/09/2026", "40"),
        ("02/09/2026", "60"),
    ]
    inputs["SF43718"] = original(banxico_bytes("SF43718", rows), "banxico_sie", "SF43718", BANXICO_URL, "csv")
    tables, _ = native.read("banxico", inputs, "2026Q3")
    facts = gold.macro_facts("banxico", "2026Q3", tables)
    quarterly = facts.loc[facts.period_id.eq("2026Q3") & facts.indicator_key.eq("usd_mxn_fix")]
    assert quarterly.set_index("aggregation").value.to_dict() == {
        "average": pytest.approx(260 / 6),
        "close": 60,
    }
    assert quarterly.unit.eq("mxn_per_usd").all()
    assert len(facts) == 24  # Three indicators, three months plus quarter, average and close.
    assert set(facts.loc[facts.indicator_key.eq("policy_rate"), "unit"]) == {"percent"}


def test_fuel_quarter_aggregates_all_observations_and_last_date_in_original_units():
    rows = [
        (pd.Timestamp("2026-07-02"), "1.25"),
        (pd.Timestamp("2026-07-01"), "1.00"),
        (pd.Timestamp("2026-08-03"), "2.00"),
        (pd.Timestamp("2026-09-30"), "4.00"),
    ]
    inputs = {"workbook": original(fuel_bytes(rows), "eia", FUEL_SERIES, FUEL_URL, "xls")}
    tables, _ = native.read("fuel", inputs, "2026Q3")
    facts = gold.macro_facts("fuel", "2026Q3", tables)
    quarterly = facts.loc[facts.period_id.eq("2026Q3")].set_index("aggregation")
    assert quarterly.loc["average", "value"] == 2.0625
    assert quarterly.loc["close", "value"] == 4
    assert facts.unit.eq("usd_per_gallon").all() and len(facts) == 8


def test_market_gold_uses_pre_period_adjusted_close_and_year_anchor():
    tables, _ = native.read("equities", equities_inputs(), "2026Q3")
    source = tables["market_prices"]
    facts = gold.market_facts("2026Q3", source)
    assert facts.date.min() == pd.Timestamp("2026-07-01")
    assert facts.date.max() == pd.Timestamp("2026-09-30")
    for ticker in TICKERS:
        history = source.loc[source.ticker.eq(ticker)].sort_values("date")
        target = facts.loc[facts.ticker.eq(ticker)].sort_values("date").iloc[0]
        previous = history.loc[history.date.lt(target.date)].iloc[-1]
        year_first = history.loc[history.date.dt.year.eq(2026)].iloc[0]
        assert target.return_1d == pytest.approx(target.adj_close / previous.adj_close - 1)
        assert target.return_ytd == pytest.approx(target.adj_close / year_first.adj_close - 1)
        assert target.return_ytd != 0
    assert facts.record_id.is_unique


def materialize(inputs, workspace):
    """Only local synthetic files, never retained real-source evidence."""
    bronze = workspace / "data/bronze"
    records = []
    for body, record in inputs.values():
        path = bronze / record["source_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(record))
        records.append(record)
    (bronze / "_manifest.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))


@pytest.mark.parametrize("product", ["banxico", "fuel", "equities"])
def test_complete_gold_has_exact_artifact_links_for_every_record(product, tmp_path):
    inputs = equities_inputs() if product == "equities" else macro_inputs(product)
    materialize(inputs, tmp_path)
    tables, details = native.read(product, inputs, "2026Q3")
    outputs, checked = gold.frames(tmp_path, product, "2026Q3", tables, details)
    fact_name = "fact_market_data" if product == "equities" else "fact_macro"
    facts = outputs[f"gold/{fact_name}"]
    artifacts = outputs["gold/dim_source_artifact"]
    bridge = outputs["gold/bridge_record_lineage"]
    assert set(facts.record_id) == set(bridge.record_id)
    assert bridge.lineage_status.eq("resolved_to_artifact").all()
    assert bridge.artifact_id.isin(artifacts.artifact_id).all()
    assert checked["calendar_completeness_certified"] is False
    assert set(artifacts.artifact_sha256) == {row["sha256"] for _, row in inputs.values()}
    files = artifacts.set_index("artifact_id").source_file.to_dict()
    if product == "equities":
        for row in facts.itertuples(index=False):
            contributors = set(bridge.loc[bridge.record_id.eq(row.record_id), "artifact_id"].map(files))
            expected = {inputs[row.ticker][1]["source_file"]}
            if row.ticker == "AERO":
                expected.add(inputs["identity"][1]["source_file"])
            assert contributors == expected
    else:
        roles = {
            "usd_mxn_fix": "SF43718",
            "inpc": "SP1",
            "policy_rate": "SF61745",
            "jet_fuel_usd_per_gallon": "workbook",
        }
        for row in facts.itertuples(index=False):
            contributors = set(bridge.loc[bridge.record_id.eq(row.record_id), "artifact_id"].map(files))
            assert contributors == {inputs[roles[row.indicator_key]][1]["source_file"]}


def test_market_gold_requires_physical_sec_artifact_not_only_its_silver_reference(tmp_path):
    inputs = equities_inputs()
    materialize(inputs, tmp_path)
    tables, details = native.read("equities", inputs, "2026Q3")
    (tmp_path / "data/bronze" / inputs["identity"][1]["source_file"]).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        gold.frames(tmp_path, "equities", "2026Q3", tables, details)


def test_unselected_later_source_dates_do_not_change_certified_window():
    inputs = macro_inputs("banxico")
    rows = [("01/07/2026", "7.75"), ("01/08/2026", "7.50"), ("01/09/2026", "7.50"), ("19/10/2026", "7.25")]
    body, record = original(banxico_bytes("SF61745", rows), "banxico_sie", "SF61745", BANXICO_URL, "csv")
    record["downloaded_at"] = "2026-10-19T00:50:00Z"
    inputs["SF61745"] = (body, record)
    tables, details = native.read("banxico", inputs, "2026Q3")
    rate = tables["macro_indicators"].loc[lambda f: f.series_id.eq("SF61745")]
    assert len(rate) == 3 and rate.date.max() == pd.Timestamp("2026-09-01")
    assert details["coverage"]["SF61745"]["calendar_completeness_certified"] is False


def test_volatility_uses_thirty_preserved_observation_returns_before_projection():
    tables, _ = native.read("equities", equities_inputs(), "2026M09")
    source = tables["market_prices"]
    prices = source.loc[source.ticker.eq("VLRS")].sort_values("date").adj_close.tolist()
    returns = [right / left - 1 for left, right in zip(prices, prices[1:])]
    facts = gold.market_facts("2026M09", source)
    row = facts.loc[facts.ticker.eq("VLRS")].sort_values("date").iloc[-1]
    assert row.volatility_30d == pytest.approx(stdev(returns[-30:]) * math.sqrt(252))

"""Synthetic FJE physical-binding contracts; official captures are tested separately."""

import csv
import io
import json
import shutil
from datetime import UTC, datetime
from uuid import uuid4
from zipfile import ZipFile

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.ingest.bts.t100 import FORM_URL, logical_source_url
from src.source_updates import availability
from src.source_updates import availability_bts as bts
from src.source_updates.bts_native import DATA_MEMBER, DOC_MEMBER, DOCUMENTATION, FIELDS
from src.source_updates.catalog import ROOT

CUTOFF = "2026-10-27T08:00:00+00:00"


def history():
    return (
        '<table><tr><td><a href="releaseinfo.asp?6o=FJE&amp;qv52ynB=qn6n">'
        "T-100 International Segment (All Carriers)</a></td><td>7/2026 View reporting carriers</td>"
        "<td>10/9/2026: 7/2026 added 12/2023 updated</td></tr></table>"
    )


def historic_zip(year):
    target = io.BytesIO()
    data = io.StringIO()
    csv.writer(data, lineterminator="\n").writerows(
        [FIELDS, [str(year) if f == "YEAR" else "x" for f in FIELDS]]
    )
    docs = io.StringIO()
    csv.writer(docs, lineterminator="\n").writerows(
        [["SYS_FIELD_NAME", "FIELD_DESC"], *DOCUMENTATION.items()]
    )
    with ZipFile(target, "w") as archive:
        archive.writestr(DATA_MEMBER, data.getvalue())
        archive.writestr(DOC_MEMBER, docs.getvalue())
    return target.getvalue()


@pytest.mark.parametrize(
    "attack",
    [
        None,
        "market",
        "us_only",
        "duplicate",
        "no_row",
        "month",
        "event",
        "format",
        "early_release",
        "future_revision",
    ],
)
def test_latest_bts_is_the_exact_fje_table_not_neighboring_release_dates(tmp_path, attack):
    text = history()
    if attack == "market":
        text = text.replace("6o=FJE", "6o=FJD")
    elif attack == "us_only":
        text = text.replace("(All Carriers)", "(US Carriers Only)")
    elif attack == "duplicate":
        text += text
    elif attack == "no_row":
        text = text.replace("<tr>", "<div>").replace("</tr>", "</div>")
    elif attack == "month":
        text = text.replace("7/2026 View", "8/2026 View")
    elif attack == "event":
        text = text.replace("12/2023 updated", "12/2023 corrected somehow")
    elif attack == "format":
        text = text.replace("7/2026 View", "13/2026 View")
    elif attack == "early_release":
        text = text.replace("10/9/2026", "10/9/2025")
    elif attack == "future_revision":
        text = text.replace("12/2023 updated", "12/2029 updated")
    path = tmp_path / "history.html"
    path.write_text(text)
    if attack:
        with pytest.raises(ValueError):
            bts.latest(path)
    else:
        result = bts.latest(path)
        assert result["latest_available_period"] == "2026M07"
        assert result["reported_release_date"] == "2026-10-09"
        assert result["events"][-1] == {"period": "2023M12", "kind": "updated"}


@pytest.mark.parametrize("variant", ["plus", "dataset", "extra", "duplicate", "missing", "fragment"])
def test_bts_response_equivalence_preserves_exact_dataset_and_query(variant):
    url = FORM_URL
    if variant == "plus":
        url = url.replace("%20", "+")
    elif variant == "dataset":
        url = url.replace("FJE", "FJD")
    elif variant == "extra":
        url += "&carrier=only_one"
    elif variant == "duplicate":
        url += "&gnoyr_VQ=FJE"
    elif variant == "missing":
        url = url.split("&")[0]
    elif variant == "fragment":
        url += "#another"
    assert bts.response_is_form(url) is (variant == "plus")


def test_cli_bts_catalog_discovery_and_paired_selection_are_offline_and_bounded(tmp_path, capsys):
    from src.source_updates.__main__ import main
    from src.source_updates.collection import collect
    from src.source_updates.recipes import describe

    args = ["recipe", "--product", "bts_segments", "--output", "selection"]
    assert main(args) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["items"][0]["url"] == bts.HISTORY
    assert catalog["items"][0]["purpose"] == "catalog"
    assert describe("bts_segments")["entry_url"] == FORM_URL
    index = tmp_path / "release.html"
    index.write_text(history())
    assert main([*args, "--catalog-file", str(index), "--period", "latest"]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["discovery"]["linked_period"] == "2026M07"
    assert selected["discovery"]["selected_years"] == [2026, 2023]
    assert selected["items"][0] == catalog["items"][0]
    assert [i["year"] for i in selected["items"][1:]] == [2026, 2023]
    workspace = ROOT / "tmp/source-updates" / ("test-bts-plan-" + uuid4().hex)
    plan = collect(selected, workspace)
    assert plan["base_requests"] == 5 and plan["maximum_http_requests"] == 25
    assert plan["paid_requests"] == 0 and not workspace.exists()
    assert main([*args, "--catalog-file", str(index), "--period", "2026M06"]) == 1
    assert "latest month" in capsys.readouterr().out
    assert main([*args, "--source-url", FORM_URL, "--period", "2026M07"]) == 1
    assert "Explicit source URL requires Viva" in capsys.readouterr().out


@pytest.fixture
def physical():
    root = ROOT / "tmp/source-updates" / ("test-bts-availability-" + uuid4().hex)
    collection, candidate = root / "collection", root / "candidate"
    bronze = collection / "data/bronze"
    rows = []
    for i, (key, body, url, period, extension) in enumerate(
        [
            ("index", history().encode(), bts.HISTORY, "current", "html"),
            (
                "current",
                b"synthetic current ZIP; native checker runs before binder",
                logical_source_url(2026),
                "2026",
                "zip",
            ),
            ("revised", historic_zip(2023), logical_source_url(2023), "2023", "zip"),
        ]
    ):
        path = save_bronze(
            body,
            "bts_t100",
            key,
            period,
            extension,
            url,
            "httpx",
            bronze_root=bronze,
            downloaded_at=datetime(2026, 10, 27, 7, 0, i, tzinfo=UTC),
            http_status=200,
        )
        row = dict(
            id=key,
            product="bts_segments",
            requested_period=period,
            status="collected_catalog" if key == "index" else "collected_unvalidated",
            source_file=path.relative_to(bronze).as_posix(),
            sha256=availability.sha(path),
            source_url=url,
            response_url=bts.HISTORY if key == "index" else FORM_URL,
            bytes=len(body),
            http_status=200,
        )
        if key != "index":
            row["request_url"] = FORM_URL
        rows.append(row)
    rid = "c" * 32
    receipt = dict(
        run_id=rid,
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
        started_at="2026-10-27T06:59:59+00:00",
        finished_at="2026-10-27T07:00:03+00:00",
        items=rows,
    )
    saved = collection / "receipts" / f"collection-{rid}.json"
    saved.parent.mkdir()
    saved.write_text(json.dumps(receipt))
    native = candidate / "data/silver/bts_t100_segment.parquet"
    native.parent.mkdir(parents=True)
    pd.DataFrame(
        dict(
            source_file=[rows[1]["source_file"]],
            source_hash=[rows[1]["sha256"]],
            source_system=["bts_t100"],
            period_id=["2026M07"],
            year=[2026],
        )
    ).to_parquet(native)
    item = dict(
        product="bts_segments",
        adapter="bts",
        period="2026M07",
        workspace=str(candidate),
        availability=dict(
            workspace=str(collection), run_id=rid, catalog_item="index", artifact_item="current"
        ),
    )
    result = dict(
        selected_month_observations_certified=True,
        complete_month_certified=False,
        operator_coverage_verified=False,
        observed_max_period="2026M07",
    )
    yield dict(item=item, result=result, receipt=receipt, saved=saved, native=native, bronze=bronze)
    shutil.rmtree(root)


@pytest.mark.parametrize(
    "attack",
    [
        None,
        "post",
        "response",
        "period",
        "unused",
        "complete",
        "operator",
        "selected",
        "missing_revision",
        "revision_year",
    ],
)
def test_bts_current_year_and_announced_revision_are_bound_without_claiming_census(physical, attack):
    s = physical
    if attack == "post":
        s["receipt"]["items"][1].pop("request_url")
    elif attack == "response":
        s["receipt"]["items"][1]["response_url"] += "&carrier=one"
    elif attack == "period":
        s["item"]["period"] = "2026M06"
    elif attack == "unused":
        frame = pd.read_parquet(s["native"])
        frame["source_hash"] = "0" * 64
        frame.to_parquet(s["native"])
    elif attack in {"complete", "operator", "selected"}:
        key = {
            "complete": "complete_month_certified",
            "operator": "operator_coverage_verified",
            "selected": "selected_month_observations_certified",
        }[attack]
        s["result"][key] = not s["result"][key]
    elif attack == "missing_revision":
        s["receipt"]["items"].pop()
    elif attack == "revision_year":
        row = s["receipt"]["items"][-1]
        path = s["bronze"] / row["source_file"]
        path.write_bytes(historic_zip(2024))
        row.update(sha256=availability.sha(path), bytes=path.stat().st_size)
        records = [json.loads(x) for x in (s["bronze"] / "_manifest.jsonl").read_text().splitlines()]
        records[-1]["sha256"] = row["sha256"]
        (s["bronze"] / "_manifest.jsonl").write_text("".join(json.dumps(x) + "\n" for x in records))
        path.with_name(path.name + ".meta.json").write_text(json.dumps(records[-1]))
    s["saved"].write_text(json.dumps(s["receipt"]))
    if attack:
        with pytest.raises(ValueError):
            availability.verify(s["item"], s["result"], CUTOFF)
    else:
        result = availability.verify(s["item"], s["result"], CUTOFF)
        assert result["latest_available_period"] == "2026M07"
        assert result["complete_month_certified"] is result["operator_coverage_verified"] is False
        assert result["first_available_at"] is result["release_lag_days"] is None
        assert result["historical_revision_archives"][0]["year"] == 2023
        assert result["historical_revision_archives"][0]["contributes_to_selected_month"] is False

"""Canonical physical query contracts; fixtures do not claim source extraction/calendar completeness."""

import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.source_updates import availability
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect
from src.source_updates.recipes import macro_round


@pytest.fixture(params=["fuel", "banxico", "equities"])
def physical(request):
    product = request.param
    root = ROOT / "tmp/source-updates" / ("series-availability-test-" + uuid4().hex)
    collection = root / "collection"
    candidate = root / "candidate"
    cutoff = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    selection = macro_round(product, "2026M09", cutoff)["selection"]

    class Client:
        def __init__(self, *args, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kw):
            body = json.dumps({"synthetic_query_contract": url, "public_form": kw.get("data")}).encode()
            return httpx.Response(200, content=body, request=httpx.Request(method, url))

    receipt = collect(selection, collection, execute=True, client_factory=Client)
    cutoff = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    planned = {
        "workbook" if product == "fuel" else row["entity"].removesuffix("_chart"): row
        for row in selection["items"]
    }
    table, column = {
        "fuel": ("fuel_prices", "series_id"),
        "banxico": ("macro_indicators", "series_id"),
        "equities": ("market_prices", "ticker"),
    }[product]
    rows = []
    for role, target in planned.items():
        acquired = next(r for r in receipt["items"] if r["id"] == target["id"])
        rows.append(
            {
                column: target["entity"] if product == "fuel" else role,
                "source_file": acquired["source_file"],
                "source_hash": acquired["sha256"],
                "source_system": target["source_system"],
            }
        )
    native = candidate / "data/silver" / (table + ".parquet")
    native.parent.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(native)
    item = dict(
        product=product,
        adapter="series",
        period="2026M09",
        workspace=str(candidate),
        availability=dict(
            workspace=str(collection),
            run_id=receipt["run_id"],
            series_items={role: t["id"] for role, t in planned.items()},
        ),
    )
    result = dict(
        scope="all_observations_in_selected_retained_originals_not_verified_publication_calendar",
        calendar_completeness_certified=False,
    )
    yield dict(
        root=root,
        collection=collection,
        candidate=candidate,
        item=item,
        result=result,
        cutoff=cutoff,
        receipt=receipt,
        native=native,
    )
    shutil.rmtree(root)


def test_current_canonical_queries_bind_native_sources_while_calendar_stays_unknown(physical):
    s = physical
    proof = availability.verify(s["item"], s["result"], s["cutoff"])
    assert len(proof["responses"]) == len(s["item"]["availability"]["series_items"])
    assert proof["latest_available_period"] is None and proof["first_publication_date"] is None
    assert proof["calendar_completeness_certified"] is False
    assert "not_expected_calendar" in proof["availability_basis"]
    assert (proof["identity_basis"] is not None) == (s["item"]["product"] == "equities")


def test_missing_roles_wrong_product_unverified_calendar_or_old_capture_fail_closed(physical):
    s = physical
    roles = s["item"]["availability"]["series_items"]
    for changed in ({}, {k: [] for k in roles}, {k: next(iter(roles.values())) for k in roles}):
        # A single-role product has no distinct-ID violation; test a missing item instead.
        if changed == roles:
            continue
        x = deepcopy(s["item"])
        x["availability"]["series_items"] = changed
        with pytest.raises(ValueError):
            availability.verify(x, s["result"], s["cutoff"])
    with pytest.raises(ValueError):
        availability.verify(s["item"], {**s["result"], "calendar_completeness_certified": True}, s["cutoff"])
    x = deepcopy(s["item"])
    x["period"] = "2026M08"
    with pytest.raises(ValueError):
        availability.verify(x, s["result"], s["cutoff"])
    with pytest.raises(ValueError, match="explicit round date"):
        availability.verify(
            s["item"], s["result"], (datetime.fromisoformat(s["cutoff"]) + timedelta(days=1)).isoformat()
        )
    frame = pd.read_parquet(s["native"])
    frame.loc[0, "source_hash"] = "a" * 64
    frame.to_parquet(s["native"])
    with pytest.raises(ValueError, match="native observations"):
        availability.verify(s["item"], s["result"], s["cutoff"])


def test_receipt_duplicate_manifest_and_banxico_actual_post_form_are_checked(physical):
    s = physical
    path = s["collection"] / "receipts" / f"collection-{s['receipt']['run_id']}.json"
    original = path.read_bytes()
    d = json.loads(original)
    if s["item"]["product"] == "banxico":
        d["items"][0]["public_request_form"] = {}
    else:
        d["items"][0]["response_url"] += "&not_the_selected_response=1"
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        availability.verify(s["item"], s["result"], s["cutoff"])
    path.write_bytes(original)
    manifest = s["collection"] / "data/bronze/_manifest.jsonl"
    data = manifest.read_bytes()
    manifest.write_bytes(data + data.splitlines()[0] + b"\n")
    with pytest.raises(ValueError, match="unique query captures"):
        availability.verify(s["item"], s["result"], s["cutoff"])

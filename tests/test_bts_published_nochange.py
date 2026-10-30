from __future__ import annotations

import copy
import hashlib
import json

import pandas as pd
import pytest

from scripts import source_update_bts_nochange as module


def fixture(tmp_path, monkeypatch):
    root, candidate = tmp_path / "repo", tmp_path / "candidate"
    site = root / "site"
    (root / "data/gold").mkdir(parents=True)
    (candidate / "data/gold").mkdir(parents=True)
    rows = [
        dict(
            carrier_key=carrier,
            route_key="MEX-JFK",
            period_id="2026M07",
            aircraft_type=7,
            service_class="F",
            passengers=100.0,
            seats=110.0,
            departures_performed=1.0,
            departures_scheduled=1.0,
            asm_miles=110.0,
            rpm_miles=100.0,
            ask_km=177.02784,
            rpk_km=160.9344,
            distance_miles=1.0,
            distance_km=1.609344,
            freight_kg=0.0,
            mail_kg=0.0,
            load_factor=100 / 110,
            calendar_period_id="2026M07",
            fiscal_period_id="2026M07",
            source_system="bts_t100",
            record_id="old-" + carrier,
            source_file="older.csv",
            source_hash="a" * 64,
            ingested_at="2026-10-18T10:00:00Z",
        )
        for carrier in ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS")
    ]
    active = pd.DataFrame(rows)
    active.to_parquet(root / "data/gold/fact_route_traffic.parquet")
    fresh = active.assign(
        record_id="new", source_file="new.csv", source_hash="b" * 64, ingested_at="2026-10-28T10:00:00Z"
    )
    fresh.to_parquet(candidate / "data/gold/fact_route_traffic.parquet")
    checked = {
        "latest_source_availability_verified": True,
        "output_sha256": {
            "gold/fact_route_traffic": hashlib.sha256(
                (candidate / "data/gold/fact_route_traffic.parquet").read_bytes()
            ).hexdigest()
        },
    }
    item = {
        "product": "bts_segments",
        "period": "2026M09",
        "source_period": "2026M07",
        "workspace": str(candidate),
        "receipt_id": "d" * 32,
        "candidate_as_of": "2026-10-28T10:01:00Z",
    }
    binding = {k: item[k] for k in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["period"] = "2026M07"
    binding["output_sha256"] = checked["output_sha256"]
    monkeypatch.setattr(module.readiness, "check_task", lambda *args: copy.deepcopy(checked))
    paths = {}
    listing = {"international": ["2026M07"], "entities": {}}
    for entity in (module.AEROMEXICO_ROUTES, *module.EXTRA_ROUTE_ENTITIES):
        if entity.key != "AEROMEXICO":
            listing["entities"][entity.key] = {"international": ["2026M07"]}
        name = (
            "data/v1/flights/international/2026M07.json"
            if entity.key == "AEROMEXICO"
            else f"data/v1/flights/entities/{entity.key}/international/2026M07.json"
        )
        paths[name] = json.dumps(
            {"routes": [{"flight_components": module._expected(active, entity.t100_carriers)}]}
        ).encode()
    paths["data/v1/flights/quarters.json"] = json.dumps({"available_periods": listing}).encode()
    paths["publication_manifest.json"] = json.dumps(
        {"files": [{"path": name, "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in paths.items()]}
    ).encode()
    for name, raw in paths.items():
        target = site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for name in module.CONSUMERS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("unchanged relevant consumer\n")
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda args, **kw: ("c" * 40 + "\n") if kw.get("text") else paths[args[-1].split(":site/")[1]],
    )

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"follow_redirects": False, "timeout": 30}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            class Response:
                pass

            value = Response()
            value.status_code = 200
            value.content = paths[url.split("aeromexico-tracker/")[1]]
            return value

    monkeypatch.setattr(module.httpx, "Client", Client)
    return root, candidate, site, item, binding, paths


def test_exact_business_facts_and_actual_four_published_consumers_pass(tmp_path, monkeypatch):
    root, candidate, site, item, binding, _ = fixture(tmp_path, monkeypatch)
    proof = module.verify(item, binding, root=root, site=site)
    assert proof["status"] == "no_visual_change"
    assert proof["native_months"] == ["2026M07"]
    assert proof["rows_compared"] == 3
    assert len(proof["served_files"]) == 6
    assert proof["source_fact_sha256"] != proof["published_input_fact_sha256"]
    assert proof["publication_performed"] is False
    assert proof == module.verify(item, binding, root=root, site=site)


@pytest.mark.parametrize(
    "field,value",
    [("passengers", 101.0), ("departures_performed", 2.0), ("service_class", "L"), ("period_id", "2026M08")],
)
def test_new_or_changed_bts_business_data_is_never_reported_as_noop(tmp_path, monkeypatch, field, value):
    root, _, site, item, binding, _ = fixture(tmp_path, monkeypatch)
    path = root / "data/gold/fact_route_traffic.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, field] = value
    frame.to_parquet(path)
    with pytest.raises(ValueError, match="business facts changed"):
        module.verify(item, binding, root=root, site=site)


def test_hash_or_source_binding_cannot_be_substituted(tmp_path, monkeypatch):
    root, _, site, item, binding, _ = fixture(tmp_path, monkeypatch)
    wrong = copy.deepcopy(binding)
    wrong["receipt_id"] = "e" * 32
    with pytest.raises(ValueError, match="binding"):
        module.verify(item, wrong, root=root, site=site)


def test_missing_published_month_blocks_even_when_gold_matches(tmp_path, monkeypatch):
    root, _, site, item, binding, _ = fixture(tmp_path, monkeypatch)
    path = site / "data/v1/flights/quarters.json"
    listing = json.loads(path.read_bytes())
    listing["available_periods"]["entities"]["VOLARIS"]["international"] = []
    path.write_text(json.dumps(listing))
    with pytest.raises(ValueError, match="advertised"):
        module.verify(item, binding, root=root, site=site)


def test_changed_public_component_is_not_proved_from_gold_alone(tmp_path, monkeypatch):
    root, _, site, item, binding, paths = fixture(tmp_path, monkeypatch)
    name = "data/v1/flights/entities/VOLARIS/international/2026M07.json"
    payload = json.loads(paths[name])
    payload["routes"][0]["flight_components"][0]["departures"] += 1
    raw = json.dumps(payload).encode()
    (site / name).write_bytes(raw)
    manifest = json.loads((site / "publication_manifest.json").read_bytes())
    next(entry for entry in manifest["files"] if entry["path"] == name)["sha256"] = hashlib.sha256(
        raw
    ).hexdigest()
    (site / "publication_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="flight cells"):
        module.verify(item, binding, root=root, site=site)


def test_correct_local_files_do_not_prove_served_state(tmp_path, monkeypatch):
    root, _, site, item, binding, paths = fixture(tmp_path, monkeypatch)
    paths["publication_manifest.json"] += b"\n"
    with pytest.raises(ValueError, match="Git baseline"):
        module.verify(item, binding, root=root, site=site)

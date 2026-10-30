from __future__ import annotations

import copy
import hashlib
import json

import pandas as pd
import pytest

from src.publish import peer_monthly_projection as module


def facts(tmp_path, product):
    gold = tmp_path / "data/gold"
    gold.mkdir(parents=True)
    values = {
        "2025M09": {"domestic": 2131, "international": 234, "total": 2364},
        "2026M09": {"domestic": 1969, "international": 228, "total": 2197},
    }
    rows = []
    for period, segments in values.items():
        for segment, value in segments.items():
            common = dict(
                period_id=period,
                period_type="month",
                segment=segment,
                value=float(value),
                metric_key="passengers_booked",
                unit="thousand booked passengers",
                carrier_key=module.ENTITIES[product],
                is_preliminary=True,
                source_hash="a" * 64,
                ingested_at="2026-10-28T15:00:00Z",
                entity_as_reported="Viva brand; legal issuer/operator not established by this release"
                if product == "viva_traffic"
                else "Controladora Vuela Compañía de Aviación, S.A.B. de C.V.",
            )
            rows.append(
                {
                    **common,
                    **(
                        dict(
                            definition="booked_not_necessarily_flown_itinerary_and_charter",
                            reporting_status="preliminary",
                        )
                        if product == "viva_traffic"
                        else dict(
                            passenger_definition="booked_flight_segments_not_observed_flown_passengers",
                            flight_scope="itinerary_and_charter; load_factor_RPM_div_ASM",
                            scale_multiplier=1000,
                            value_normalized=value * 1000,
                            normalized_unit="booked passengers",
                            is_unaudited=True,
                        )
                    ),
                }
            )
    pd.DataFrame(rows).to_parquet(gold / (module.TABLES[product] + ".parquet"))
    pd.DataFrame([dict(artifact_sha256="a" * 64, source_url="https://issuer.example/report.pdf")]).to_parquet(
        gold / "dim_source_artifact.parquet"
    )
    checked = {
        "output_sha256": {
            "gold/" + p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in gold.glob("*.parquet")
        },
        "document_date": "2026-10-09",
        "source_report_date_as_reported": "2026-10-06",
    }
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    receipt = receipts / f"certified-{product}-2026M09.json"
    receipt.write_text(
        json.dumps({"document_date": "2026-10-09", "source_report_date_as_reported": "2026-10-06"})
    )
    checked["accepted_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    return {"product": product, "period": "2026M09", "workspace": str(tmp_path)}, checked


@pytest.mark.parametrize("product", ["viva_traffic", "volaris_traffic_ir"])
def test_native_thousands_keep_reported_total_and_rounded_segment_sum_separate(tmp_path, product):
    item, checked = facts(tmp_path, product)
    series = module.project_series(item, checked)
    previous, current = series["records"]
    assert previous["reported_total"] == 2364000
    assert previous["total_segment_sum"] == 2365000
    assert previous["reconciliation_delta"] == 1000
    assert current["reported_total"] == 2197000
    assert current["domestic"] == 1969000
    assert current["international"] == 228000
    assert series["scope"] == module.SCOPE
    assert series["captured_at"] == "2026-10-28T15:00:00Z"
    assert series["source_sha256"] == "a" * 64
    if product == "viva_traffic":
        assert "legal issuer/operator not established" in series["entity_attribution"]


@pytest.mark.parametrize(
    "change", ["unit", "scope", "ytd", "one_segment", "year", "precision", "negative", "preliminary"]
)
def test_source_meaning_and_report_domain_cannot_be_substituted(tmp_path, change):
    item, checked = facts(tmp_path, "viva_traffic")
    path = tmp_path / "data/gold" / ("fact_viva_monthly_source_metrics.parquet")
    frame = pd.read_parquet(path)
    if change == "unit":
        frame.loc[0, "unit"] = "passengers flown"
    elif change == "scope":
        frame.loc[0, "definition"] = "regular services only"
    elif change == "ytd":
        frame.loc[0, "period_type"] = "year_to_date"
    elif change == "one_segment":
        frame = frame.drop(index=0)
    elif change == "year":
        frame.loc[0, "period_id"] = "2024M09"
    elif change == "precision":
        frame.loc[0, "value"] = 2131.1
    elif change == "negative":
        frame.loc[0, "value"] = -1
    else:
        frame.loc[0, "is_preliminary"] = False
    frame.to_parquet(path)
    checked["output_sha256"]["gold/fact_viva_monthly_source_metrics"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError):
        module.project_series(item, checked)


def test_peer_update_preserves_afac_am_foreign_peer_and_every_unrelated_field(tmp_path):
    item, checked = facts(tmp_path, "viva_traffic")
    series = module.project_series(item, checked)
    before = {
        "schema_version": "flight_dashboard_payload_v1",
        "quarters": [{"period_id": "2026Q2"}],
        "monthly_passengers": {"source": "afac", "records": [{"period_id": "2026M06"}]},
        "corporate_monthly_passengers": {"entity": "AEROMEXICO"},
        "corporate_peer_monthly_passengers": {"VOLARIS": {"do_not_modify": "approved previous payload"}},
    }
    original = copy.deepcopy(before)
    projection = {"product": "viva_traffic", "period": "2026M09", "series": series}
    output = module.public_outputs({module.TARGETS[0]: json.dumps(before).encode()}, projection)
    after = json.loads(output[module.TARGETS[0]])
    assert before == original
    assert after["monthly_passengers"] == before["monthly_passengers"]
    assert after["quarters"] == before["quarters"]
    assert after["corporate_monthly_passengers"] == before["corporate_monthly_passengers"]
    assert (
        after["corporate_peer_monthly_passengers"]["VOLARIS"]
        == before["corporate_peer_monthly_passengers"]["VOLARIS"]
    )
    assert after["corporate_peer_monthly_passengers"]["VIVA_AEROBUS"] == series
    assert module.public_outputs(output, projection) == output


def test_a_new_edition_cannot_silently_drop_older_points_or_relabel_their_provenance(tmp_path):
    item, checked = facts(tmp_path, "viva_traffic")
    series = module.project_series(item, checked)
    old = copy.deepcopy(series)
    old["records"][0]["period_id"] = "2024M09"
    before = {
        "schema_version": "flight_dashboard_payload_v1",
        "corporate_peer_monthly_passengers": {"VIVA_AEROBUS": old},
    }
    with pytest.raises(ValueError, match="point-level provenance"):
        module.public_outputs(
            {module.TARGETS[0]: json.dumps(before).encode()},
            {"product": "viva_traffic", "period": "2026M09", "series": series},
        )


@pytest.mark.parametrize("change", ["quarter", "other_entity", "document_date", "timezone", "reconciliation"])
def test_closed_public_projection_guards_remain_active(tmp_path, change):
    item, checked = facts(tmp_path, "viva_traffic")
    series = module.project_series(item, checked)
    projection = {"product": "viva_traffic", "period": "2026M09", "series": series}
    if change == "quarter":
        projection["period"] = "2026Q3"
    elif change == "other_entity":
        series["entity"] = "AEROMEXICO"
    elif change == "document_date":
        series["documentary_date"] = "2026-09-15"
    elif change == "timezone":
        series["captured_at"] = "2026-10-28T15:00:00"
    else:
        series["records"][0]["reconciliation_delta"] = False
    with pytest.raises(ValueError):
        module.public_outputs(
            {module.TARGETS[0]: b'{"schema_version":"flight_dashboard_payload_v1"}'}, projection
        )

"""A consumed capture cannot change without invalidating research provenance."""

import hashlib

import pandas as pd

from scripts.research.afac_frozen_flights import international_status_profile, private_input_hashes


def test_changed_or_added_international_capture_changes_input_identity(tmp_path):
    for relative in [
        "derived/aerodatabox_international/2026M04/international_seed_2026M04.parquet",
        "snapshot/data/silver/domestic_slots/aicm_amx_assigned_flight_days.parquet",
        *[f"derived/aerodatabox/{period}/route_carrier_flight_counts_{period}.parquet"
          for period in ["2026M04", "2026M05", "2026M06"]],
    ]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"unchanged input")
    empty = private_input_hashes(tmp_path)
    capture = tmp_path / "derived/aerodatabox_international/2026M06/international_capture_route_operator_2026M06.parquet"
    capture.parent.mkdir(parents=True)
    pd.DataFrame({"flights": [100.0], "status_incomplete": [10.0], "codeshare_unknown": [0.0]}).to_parquet(capture)
    before = private_input_hashes(tmp_path)
    relative = capture.relative_to(tmp_path).as_posix()
    assert set(before) - set(empty) == {relative}
    assert before[relative] == hashlib.sha256(capture.read_bytes()).hexdigest()
    assert international_status_profile(tmp_path)[0]["incomplete_status_fraction"] == .1
    pd.DataFrame({"flights": [100.0], "status_incomplete": [20.0], "codeshare_unknown": [0.0]}).to_parquet(capture)
    after = private_input_hashes(tmp_path)
    assert international_status_profile(tmp_path)[0]["incomplete_status_fraction"] == .2
    assert before[relative] != after[relative]
    assert {key for key in before if before[key] != after[key]} == {relative}

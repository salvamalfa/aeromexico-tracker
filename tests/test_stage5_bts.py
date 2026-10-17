from __future__ import annotations

from src.ingest.bts.t100 import FIELDS, _post_payload
from src.parse.bts.t100 import _map_carrier


def test_bts_post_is_bounded_to_mexico_and_one_year() -> None:
    html = """
    <form method="post" action="./download">
      <input type="hidden" name="__VIEWSTATE" value="abc" />
    </form>
    """

    action, payload = _post_payload(html, year=2015)

    assert action.endswith("/download")
    assert payload["cboGeography"] == "Mexico"
    assert payload["cboYear"] == "2015"
    assert payload["chkDownloadZip"] == "on"
    assert all(payload[field] == "on" for field in FIELDS)


def test_t100_crosswalk_maps_known_and_fallback_identities() -> None:
    assert _map_carrier("AIRLINE_ID_19790", "Delta Air Lines Inc.") == "DELTA"
    assert _map_carrier("AIRLINE_ID_20398", "Aeromexico") == "AEROMEXICO"
    assert _map_carrier("ENTITY_06038", "Historical Carrier") == "BTS_ENTITY_06038"


def test_t100_keeps_aerolitoral_separate_from_aerovias() -> None:
    assert _map_carrier("AIRLINE_ID_20250", "Aerolitoral") == "AEROMEXICO_CONNECT"
    assert _map_carrier("AIRLINE_ID_20250", "Aeromexico Connect") == "AEROMEXICO_CONNECT"
    assert _map_carrier("AIRLINE_ID_19534", "Aeromexico") == "AEROMEXICO"


def test_t100_build_preserves_operator_class_and_performed_counts(tmp_path, monkeypatch) -> None:
    import io
    import zipfile
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import polars as pl

    from src.parse.bts import t100

    rows = []
    for identity, carrier, name, service_class, scheduled, performed in [
        (19534, "AM", "Aeromexico", "F", 100, 98),
        (20250, "5D", "Aerolitoral", "F", 30, 28),
        (20250, "5D", "Aerolitoral", "L", 0, 2),
    ]:
        row = {column.lower(): 0 for column in FIELDS}
        row.update(
            airline_id=identity,
            unique_carrier=carrier,
            carrier=carrier,
            unique_carrier_name=name,
            carrier_name=name,
            unique_carrier_entity=str(identity),
            origin="MEX",
            dest="LAX",
            origin_country="MX",
            dest_country="US",
            year=2026,
            quarter=2,
            month=6,
            **{"class": service_class},
            departures_scheduled=scheduled,
            departures_performed=performed,
            seats=performed * 100,
            passengers=performed * 80,
            distance=1500,
        )
        rows.append(row)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("T_T100I_SEGMENT_ALL_CARRIER.csv", pl.DataFrame(rows).write_csv())
    monkeypatch.setattr(t100, "PATHS", SimpleNamespace(root=tmp_path, silver=tmp_path / "silver"))
    monkeypatch.setattr(
        t100,
        "_manifest_records",
        lambda: [
            {
                "source_file": "bts/2026.zip",
                "sha256": "fixture",
                "downloaded_at": datetime.now(UTC).isoformat(),
            }
        ],
    )
    monkeypatch.setattr(t100, "read_bronze_verified", lambda *args: archive.getvalue())

    frame, crosswalk = t100.build_t100()

    assert set(crosswalk["carrier_key"]) == {"AEROMEXICO", "AEROMEXICO_CONNECT"}
    connect = frame.filter(pl.col("carrier_key") == "AEROMEXICO_CONNECT")
    assert connect["iata_code"].to_list() == ["5D", "5D"]
    assert connect["icao_code"].to_list() == ["SLI", "SLI"]
    assert connect.select("class", "departures_performed").rows() == [("F", 28.0), ("L", 2.0)]
    assert frame["departures_performed"].sum() == 128
    assert frame["departures_scheduled"].sum() == 130

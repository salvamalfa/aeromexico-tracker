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


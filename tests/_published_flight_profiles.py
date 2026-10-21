"""Exact expectations for the three signed flight contracts we support.

The production baseline predates flight components and June BTS coverage.
Select expectations from the verified contract, never from query output.
"""

from src.conversational_analytics.data.snapshot import Snapshot

LEGACY_FLIGHTS = "17fb7e131da94435190bea925fe9733e298754d04e9b9c5e76fbbea8bef119a7"
COMPONENT_FLIGHTS = "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6"
REGULAR_MAP_FLIGHTS = "3eb5e9425dd346a38088ddef500ff0ff5f71d62dad6559bba7b486135f8ccc58"


def has_signed_flight_components(snapshot: Snapshot) -> bool:
    contract = snapshot.manifest["contracts"]["flights.schema.json"]
    assert contract in {LEGACY_FLIGHTS, COMPONENT_FLIGHTS, REGULAR_MAP_FLIGHTS}, (
        "Review published-route expectations for this new signed flight contract",
        contract,
    )
    return contract != LEGACY_FLIGHTS


def has_regular_map_projection(snapshot: Snapshot) -> bool:
    return snapshot.manifest["contracts"]["flights.schema.json"] == REGULAR_MAP_FLIGHTS


LEGACY_SCHEDULED_DEPARTURES = {
    "AMS<>MEX": 182,
    "BCN<>MEX": 156,
    "CDG<>MEX": 182,
    "EZE<>MEX": 182,
    "FCO<>MEX": 182,
    "GUA<>MEX": 364,
    "HAV<>MEX": 182,
    "ICN<>MEX": 91,
    "LIM<>MEX": 182,
    "MAD<>MEX": 540,
    "MEX<>MGA": 104,
    "MEX<>NRT": 91,
    "MEX<>PTY": 364,
    "MEX<>PUJ": 182,
    "MEX<>RDU": 182,
    "MEX<>SAL": 364,
    "MEX<>SAP": 78,
    "MEX<>SDQ": 364,
    "MEX<>SJO": 361,
    "MEX<>SNA": 182,
    "MEX<>UIO": 181,
    "MEX<>XPL": 176,
    "MEX<>YUL": 182,
    "MEX<>YVR": 182,
    "MEX<>YYZ": 182,
    "CDG<>MTY": 68,
}

# Incomplete baseline quarters retain carrier values but have no comparable sum.
# Tuples are AM Group, Volaris, Viva; missing June must never become zero.
LEGACY_SHARED_PASSENGERS = {
    "MEX<>SAT": (16598, 13293, 14356),
    "MEX<>ORD": (37059, 44514, 17644),
    "LAX<>MEX": (75284, 42134, 18710),
    "LAS<>MEX": (16922, 23337, 23285),
    "IAH<>MEX": (30065, 19788, 16348),
    "GDL<>ORD": (12607, 35161, 20403),
}

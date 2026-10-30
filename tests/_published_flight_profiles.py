"""Exact expectations for the four signed flight contracts we support.

The legacy baseline predates flight components and June BTS coverage.
Select expectations from the verified contract, never from query output.
"""

from src.conversational_analytics.data.snapshot import Snapshot

LEGACY_FLIGHTS = "17fb7e131da94435190bea925fe9733e298754d04e9b9c5e76fbbea8bef119a7"
COMPONENT_FLIGHTS = "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6"
REGULAR_MAP_FLIGHTS = "3eb5e9425dd346a38088ddef500ff0ff5f71d62dad6559bba7b486135f8ccc58"
MOVEMENT_FLIGHTS = "6b5626c10552c7a3af385a6aa6a251fadef31f0e317067c6532869a9c0a96721"


def _signed_contract(snapshot: Snapshot) -> str:
    contract = snapshot.manifest["contracts"]["flights.schema.json"]
    assert contract in {LEGACY_FLIGHTS, COMPONENT_FLIGHTS, REGULAR_MAP_FLIGHTS, MOVEMENT_FLIGHTS}, (
        "Review published-route expectations for this new signed flight contract",
        contract,
    )
    return contract


def has_signed_flight_components(snapshot: Snapshot) -> bool:
    return _signed_contract(snapshot) != LEGACY_FLIGHTS


def has_regular_map_projection(snapshot: Snapshot) -> bool:
    return _signed_contract(snapshot) in {REGULAR_MAP_FLIGHTS, MOVEMENT_FLIGHTS}


def has_recorded_movements(snapshot: Snapshot) -> bool:
    return _signed_contract(snapshot) == MOVEMENT_FLIGHTS


# The correction removes Aerocivil from flight components. Four markets retain
# only their separately published AICM slots, explicitly scheduled, not observed.
# Their literal movement counts below are a different metric and never halved.
MOVEMENT_SCHEDULED_DEPARTURES = {
    "BOG<>MEX": 542,
    "CLO<>MEX": 164,
    "CTG<>MEX": 181,
    "MDE<>MEX": 364,
    "MEX<>SNA": None,
}
MOVEMENT_COUNTS_2026Q2 = {
    "BOG<>MEX": 552,
    "BOG<>TGZ": 1,
    "CLO<>MEX": 112,
    "CTG<>MEX": 182,
    "MDE<>MEX": 182,
}

# Public passenger values are unchanged. Longer provisional source/coverage text
# fits only the first six of these eight shared markets in the same tool budget.
MOVEMENT_SHARED_TOTALS_2026Q2 = {
    "GDL<>LAX": 212017,
    "LAX<>MEX": 190570,
    "MEX<>ORD": 141042,
    "GDL<>ORD": 104189,
    "IAH<>MEX": 99090,
    "LAS<>MEX": 88760,
    "MEX<>SAT": 64284,
    "GDL<>IAH": 36449,
}


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

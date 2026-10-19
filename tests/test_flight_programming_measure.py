"""Programming is an independent measure, including overlapping cells."""

from src.dashboard.flight_cells import apply_flight_cells, resolve_cells


def cell(kind, value, *, carrier="AEROMEXICO", origin="LAX", dest="MEX", priority=0):
    return dict(
        carrier_key=carrier,
        origin_iata=origin,
        destination_iata=dest,
        period_id="2026M06",
        kind=kind,
        departures=value,
        source_label="AICM" if kind == "scheduled" else kind,
        source_hashes=[],
        priority=priority,
    )


def endpoint(iata):
    return dict(iata=iata, city=iata, lat=1.0, lon=1.0)


def test_keeps_full_296_aicm_schedule_outside_143_observed_headline():
    cells = resolve_cells(
        [
            cell("observed", 143),
            cell("scheduled", 149, carrier="AEROMEXICO_GROUP"),
            cell("scheduled", 147, carrier="AEROMEXICO_GROUP", origin="MEX", dest="LAX"),
        ]
    )
    network = dict(routes=[])
    apply_flight_cells(network, cells, endpoint)
    route = network["routes"][0]
    assert route["departures"] == 143
    assert sum(c["departures"] for c in route["flight_components"] if c["kind"] == "scheduled") == 296
    assert route["directions"] == [
        dict(origin_iata="LAX", destination_iata="MEX", departures=143, passengers=None, seats=None)
    ]


def test_observed_zero_blocks_estimate_but_not_independent_programming():
    cells = resolve_cells([cell("observed", 0), cell("estimated", 99), cell("scheduled", 80)])
    assert [(c["kind"], c["departures"]) for c in cells] == [("observed", 0), ("scheduled", 80)]
    network = dict(routes=[])
    apply_flight_cells(network, cells, endpoint)
    assert network["routes"][0]["departures"] == 0


def test_keeps_one_schedule_source_per_cell_without_summing_duplicate_universes():
    a = cell("scheduled", 80, priority=0)
    b = {**cell("scheduled", 90, priority=2), "source_label": "other schedule"}
    selected = resolve_cells([cell("observed", 10), a, b])
    assert [(c["kind"], c["departures"]) for c in selected] == [("observed", 10), ("scheduled", 80)]

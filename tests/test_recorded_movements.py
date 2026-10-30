"""Movement evidence survives export, but cannot become observed departures."""

from copy import deepcopy

import duckdb
import pandas as pd
import pytest
from jsonschema import Draft202012Validator
from test_international_routes import AIRPORTS, ARTIFACT, CO

from src.dashboard.flights_html import integration_flight_payload
from src.dashboard.international_routes import extend_networks
from src.dashboard.recorded_movements import movement_payload
from src.transform.international_routes import normalize
from src.web_export.schemas import NETWORK_FILE_SCHEMA


def frame(count="30"):
    return pd.DataFrame(
        normalize("aerocivil", [{**CO, "mes": "07", "totaloperaciones": count}], ARTIFACT, AIRPORTS)
    )


def public_network(observations):
    airports = pd.DataFrame(
        [
            dict(airport_iata=code, name=code, city=code, country=country, latitude=lat, longitude=lon)
            for code, country, lat, lon in [("MEX", "MX", 19, -99), ("BOG", "CO", 4, -74)]
        ]
    )
    network = dict(
        period_label="3T26",
        expected_months=["2026M07", "2026M08", "2026M09"],
        observed_months=[],
        routes=[],
        airports=[],
        eligibility_reason="Cobertura parcial por fuente",
        source_url="",
    )
    with duckdb.connect() as connection:
        connection.register("fact_international_route_observations", observations)
        connection.register("dim_airport", airports)
        expanded = extend_networks(connection, {"2026Q3": network})
    payload = dict(
        schema_version="flight_dashboard_payload_v1",
        metadata={},
        quarters=[],
        monthly_passengers={},
        route_network={"world_geometry": {}},
        route_networks={},
        international_networks=expanded,
    )
    result = integration_flight_payload(payload)["route_networks"]["2026Q3"]
    Draft202012Validator(NETWORK_FILE_SCHEMA).validate(result)
    return result


def test_july_movements_keep_direction_native_partition_and_no_quarter_or_flight_claim():
    network = public_network(frame())
    route = network["routes"][0]
    measure = route["recorded_movements"]
    assert measure["count"] == 30  # Neither halved nor converted to salidas.
    assert measure["observed_months"] == ["2026M07"]
    assert measure["official_classification_confirmed"] is False
    assert measure["provisional"] is True and measure["agent_eligible"] is False
    assert measure["components"] == [
        dict(
            operator_icao="AMX",
            commercial_designator_as_reported="DIFFERENT",
            origin_iata="MEX",
            destination_iata="BOG",
            period_id="2026M07",
            operations=30,
            source_hash="a" * 64,
            source_locator="record:1",
        )
    ]
    assert route["departures"] is None and route["previous"]["departures"] is None
    assert route.get("flight_components", []) == []
    assert route["passengers"] is None and route["seats"] is None
    assert route["operation_status"] == "recorded_movements_provisional"
    assert len(route["directions"]) == 1 and route["directions"][0]["departures"] is None
    assert "provisional" in route["coverage_note"]
    assert "Colombia · Aerocivil" not in network["coverage_by_source"]
    assert network["coverage_by_source"][measure["source_label"]] == ["2026M07"]


@pytest.mark.parametrize("bad", [None, "", "nan", "inf", "-1", "1.5", str(2**53)])
def test_missing_or_nonintegral_source_movements_do_not_become_zero(bad):
    with pytest.raises(ValueError):
        frame(bad)


def test_native_zero_and_commercial_designator_partition_survive():
    zero = public_network(frame("0"))["routes"][0]
    assert zero["recorded_movements"]["count"] == 0 and zero["departures"] is None
    two = pd.concat(
        [
            frame(),
            pd.DataFrame(
                normalize("aerocivil", [{**CO, "mes": "07", "empresa": "OTHER"}], ARTIFACT, AIRPORTS)
            ),
        ],
        ignore_index=True,
    )
    assert movement_payload(two)["count"] == 60
    with pytest.raises(ValueError, match="Duplicate"):
        movement_payload(pd.concat([frame(), frame()]))


@pytest.mark.parametrize(
    "column,value",
    [
        ("departures", 30),
        ("metric_key", "combined"),
        ("operations", None),
        ("operations", -1),
        ("operations", float("inf")),
        ("source_flight_type_code", "N"),
        ("source_traffic_code", "N"),
        ("seats", 10),
    ],
)
def test_mistyped_gold_or_changed_scope_fails_before_publication(column, value):
    observations = frame()
    observations[column] = value
    with pytest.raises(ValueError, match="Aerocivil|movements"):
        public_network(observations)


def test_public_contract_refuses_official_or_eligible_claim_and_fractional_movements():
    network = public_network(frame())
    for key, value in [
        ("official_classification_confirmed", True),
        ("provisional", False),
        ("agent_eligible", True),
        ("count", 0.5),
    ]:
        forged = deepcopy(network)
        forged["routes"][0]["recorded_movements"][key] = value
        assert list(Draft202012Validator(NETWORK_FILE_SCHEMA).iter_errors(forged))

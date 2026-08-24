from src.verify_identities import verify_ciks


def test_configured_ciks_are_compared_as_zero_padded_values() -> None:
    payload = {
        "0": {"cik_str": 1561861, "ticker": "AERO", "title": "Grupo Aeromexico"},
        "1": {"cik_str": 1520504, "ticker": "VLRS", "title": "Controladora Vuela"},
        "2": {"cik_str": 1038683, "ticker": "RYAAY", "title": "Ryanair Holdings"},
        "3": {"cik_str": 27904, "ticker": "DAL", "title": "Delta Air Lines"},
    }

    results = verify_ciks(payload)

    assert len(results) == 4
    assert all(result["matches"] for result in results)
    assert {result["sec_cik"] for result in results} == {
        "0001561861",
        "0001520504",
        "0001038683",
        "0000027904",
    }


def test_missing_ticker_is_reported_as_mismatch() -> None:
    results = verify_ciks(
        {"0": {"cik_str": 1561861, "ticker": "AERO", "title": "Grupo Aeromexico"}}
    )

    volaris = next(result for result in results if result["carrier_key"] == "VOLARIS")
    assert volaris["matches"] is False
    assert volaris["sec_cik"] == ""

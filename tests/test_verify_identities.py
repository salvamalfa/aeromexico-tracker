from src.verify_identities import verify_ciks


def test_configured_ciks_are_compared_as_zero_padded_values() -> None:
    payload = {
        "0": {"cik_str": 1561861, "ticker": "AERO", "title": "Grupo Aeromexico"},
        "1": {"cik_str": 1520504, "ticker": "VLRS", "title": "Controladora Vuela"},
    }

    results = verify_ciks(payload)

    assert len(results) == 2
    assert all(result["matches"] for result in results)
    assert {result["sec_cik"] for result in results} == {"0001561861", "0001520504"}


def test_missing_ticker_is_reported_as_mismatch() -> None:
    results = verify_ciks(
        {"0": {"cik_str": 1561861, "ticker": "AERO", "title": "Grupo Aeromexico"}}
    )

    volaris = next(result for result in results if result["carrier_key"] == "VOLARIS")
    assert volaris["matches"] is False
    assert volaris["sec_cik"] == ""

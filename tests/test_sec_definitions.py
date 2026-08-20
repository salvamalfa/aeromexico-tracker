from src.parse.sec.definitions import STAGE_LENGTH_PATTERN


def test_stage_length_formula_preserves_source_reference() -> None:
    old = "SLA RASK = RASK * (Carrier average stage length / 1,834) ^ (0.5)."
    current = "SLA RASK = RASK * (Carrier average stage length / 1,982) ^ (0.5)."

    assert STAGE_LENGTH_PATTERN.search(old).group(1) == "1,834"
    assert STAGE_LENGTH_PATTERN.search(current).group(1) == "1,982"

from pathlib import Path

from src.config import CARRIERS, CIK_AEROMEXICO, ProjectPaths, RATE_LIMITS


def test_aeromexico_identity_is_zero_padded() -> None:
    assert CIK_AEROMEXICO == "0001561861"
    assert CARRIERS["AEROMEXICO"]["cik"] == CIK_AEROMEXICO
    assert CARRIERS["AEROMEXICO"]["iata"] == "AM"


def test_all_rate_limits_are_positive() -> None:
    assert RATE_LIMITS
    assert all(value > 0 for value in RATE_LIMITS.values())
    assert RATE_LIMITS["sec"] <= 5.0


def test_runtime_directories_are_derived_from_root(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    paths.ensure_runtime_directories()

    assert paths.bronze.is_dir()
    assert paths.silver.is_dir()
    assert paths.gold.is_dir()
    assert paths.quality.is_dir()
    assert paths.logs.is_dir()
    assert paths.warehouse == tmp_path / "data" / "warehouse.duckdb"

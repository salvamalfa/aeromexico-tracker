from types import SimpleNamespace
import hashlib
import subprocess

import duckdb
import pandas as pd
import pytest

from scripts.research import build_flight_coverage_preview as preview
from src.transform import stage6_warehouse as warehouse


def test_preview_rejects_uncommitted_builder_before_reading_data(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    script = root / "scripts/research/build_flight_coverage_preview.py"
    script.parent.mkdir(parents=True)
    script.write_text("committed builder")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "baseline"], cwd=root, check=True)
    script.write_text("uncommitted builder")
    monkeypatch.setattr(preview, "PATHS", SimpleNamespace(root=root))
    with pytest.raises(RuntimeError, match="build_flight_coverage_preview.py"):
        preview.build_preview(tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_preview_refreshes_a_stale_warehouse_from_the_gold_it_attests(tmp_path, monkeypatch):
    gold, sql = tmp_path / "gold", tmp_path / "sql"
    gold.mkdir()
    sql.mkdir()
    path = gold / "fact_international_route_observations.parquet"
    pd.DataFrame({"record_id": ["current Gold"]}).to_parquet(path, index=False)
    paths = SimpleNamespace(data=tmp_path, gold=gold, bronze=tmp_path / "bronze", warehouse=tmp_path / "warehouse.duckdb")
    with duckdb.connect(str(paths.warehouse)) as connection:
        connection.execute("CREATE TABLE fact_international_route_observations AS SELECT 'stale warehouse' AS record_id")
    monkeypatch.setattr(preview, "PATHS", paths)
    monkeypatch.setattr(warehouse, "PATHS", paths)
    monkeypatch.setattr(warehouse, "SQL_DIR", sql)
    monkeypatch.setattr(warehouse, "table_definitions", lambda **kwargs: {})
    hashes = preview.refresh_retained_warehouse()
    with duckdb.connect(str(paths.warehouse), read_only=True) as connection:
        assert connection.execute("SELECT record_id FROM fact_international_route_observations").fetchall() == [("current Gold",)]
    assert hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}


def test_preview_refuses_gold_changed_during_warehouse_refresh(tmp_path, monkeypatch):
    path = tmp_path / "fact.parquet"
    path.write_bytes(b"initial Gold")
    monkeypatch.setattr(preview, "PATHS", SimpleNamespace(gold=tmp_path))
    monkeypatch.setattr(preview, "build_warehouse", lambda **kwargs: path.write_bytes(b"changed Gold"))
    with pytest.raises(ValueError, match="Gold changed"):
        preview.refresh_retained_warehouse()

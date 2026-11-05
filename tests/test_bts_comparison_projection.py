"""Public-payload negatives and real retained native BTS repair replay."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.config import PATHS
from src.publish import bts_comparison_projection as repair
from src.publish.source_data_scope import encoded


def example():
    before = {name: (PATHS.root / "site" / name).read_bytes() for name in repair.TARGETS}
    projection = dict(
        product=repair.PRODUCT,
        period=repair.PERIOD,
        comparisons={name: {} for name in repair.TARGETS},
        unavailable={name: {} for name in repair.TARGETS},
        current_context_sha256={name: repair.context(json.loads(raw)) for name, raw in before.items()},
    )
    projection["comparisons"][repair.TARGETS[1]]["GDL<>ONT"] = 124.0
    return before, projection


def test_only_comparison_changes_and_repeat_is_byte_identical():
    before, projection = example()
    outputs = repair.public_outputs(before, projection)
    for name in repair.TARGETS:
        current, original = json.loads(outputs[name]), json.loads(before[name])
        for route, old in zip(current["routes"], original["routes"], strict=True):
            route["previous"]["departures"] = old["previous"]["departures"]
        assert current == original
    assert repair.public_outputs(outputs, projection) == outputs


@pytest.mark.parametrize(
    "field,value", [("departures", 1234), ("agent_eligible", True), ("eligibility_reason", "new eligibility")]
)
def test_current_counts_and_eligibility_cannot_change(field, value):
    before, projection = example()
    name = repair.TARGETS[1]
    value_doc = json.loads(before[name])
    if field == "departures":
        value_doc["routes"][0][field] = value
    else:
        value_doc[field] = value
    before[name] = encoded(value_doc)
    with pytest.raises(ValueError, match="context changed"):
        repair.public_outputs(before, projection)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_comparison_cannot_be_fabricated_as_invalid_count(value):
    before, projection = example()
    projection["comparisons"][repair.TARGETS[1]]["GDL<>ONT"] = value
    with pytest.raises(ValueError, match="finite native"):
        repair.public_outputs(before, projection)


def test_charter_is_not_relabelled_as_regular_comparison():
    before, projection = example()
    projection["comparisons"][repair.TARGETS[1]] = {"CUN<>CVG": 14}
    with pytest.raises(ValueError, match="service type"):
        repair.public_outputs(before, projection)


def test_actual_native_archives_restore_77_only_and_leave_charter_unavailable(tmp_path):
    archive = PATHS.root.parent / "private-linux-release/snapshot/data/bronze/bts/t100"
    if not archive.is_dir():
        pytest.skip("Restore the exact retained 2025/2026 native BTS ZIPs and capture sidecars")
    # Native parser and original hash verification are real, including the
    # bundled official dictionary and exact six-field operator crosswalk.
    profile = dict(schema_version="bts_comparison_source_v1", historical_baseline=repair.HISTORICAL_BASELINE)
    profile["crosswalk"] = dict(
        path="config/carrier_crosswalk.csv",
        sha256=hashlib.sha256((PATHS.root / "config/carrier_crosswalk.csv").read_bytes()).hexdigest(),
    )
    files = []
    for role, year, tag in (("current", 2026, "20261017"), ("previous", 2025, "20260824")):
        source = next((archive / str(year)).glob(f"*{tag}*.zip"))
        source_meta = source.with_suffix(".zip.meta.json")
        destination = tmp_path / source.name
        destination.write_bytes(source.read_bytes())
        destination.with_suffix(".zip.meta.json").write_bytes(source_meta.read_bytes())
        files.extend([destination, destination.with_suffix(".zip.meta.json")])
        profile[role] = dict(
            path=destination.relative_to(tmp_path).as_posix(),
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            metadata_sha256=hashlib.sha256(source_meta.read_bytes()).hexdigest(),
        )
    # repo must also provide the actual frozen Git historical selection. Put
    # retained copies in this checkout's ignored scratch for that read-only API.
    from tempfile import TemporaryDirectory

    scratch = PATHS.root / "tmp/source-updates"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=scratch, prefix="bts-repair-test-") as folder:
        for role in ("current", "previous"):
            item = profile[role]
            source = tmp_path / item["path"]
            target = Path(folder) / source.name
            target.write_bytes(source.read_bytes())
            target.with_suffix(".zip.meta.json").write_bytes(
                source.with_suffix(".zip.meta.json").read_bytes()
            )
            item["path"] = target.relative_to(PATHS.root).as_posix()
        result = repair.replay(profile, PATHS.root / "site")
        projection = result["projection"]
        assert [len(projection["comparisons"][name]) for name in repair.TARGETS] == [7, 70]
        assert "CUN<>CVG" in projection["unavailable"][repair.TARGETS[1]]
        assert projection["comparisons"][repair.TARGETS[1]]["BJX<>SMF"] == 28
        assert projection["comparisons"][repair.TARGETS[1]]["GDL<>ONT"] == 124
        broken = deepcopy(profile)
        broken["previous"]["sha256"] = "a" * 64
        with pytest.raises(ValueError, match="hashes"):
            repair.replay(broken, PATHS.root / "site")
        broken = deepcopy(profile)
        broken["crosswalk"]["sha256"] = "a" * 64
        with pytest.raises(ValueError, match="crosswalk changed"):
            repair.replay(broken, PATHS.root / "site")
        assert PATHS.root / "config/carrier_crosswalk.csv" in result["input_files"]
        before = {name: (PATHS.root / "site" / name).read_bytes() for name in repair.TARGETS}
        outputs = result["outputs"]
        for name in repair.TARGETS:
            after = json.loads(outputs[name])
            old = json.loads(before[name])
            assert after["agent_eligible"] is False
            for route, prior in zip(after["routes"], old["routes"], strict=True):
                route["previous"]["departures"] = prior["previous"]["departures"]
            assert after == old
        assert repair.public_outputs(outputs, projection) == outputs


def test_native_identity_mapping_cannot_change_behind_its_profile(tmp_path, monkeypatch):
    canonical = (PATHS.root / "config/carrier_crosswalk.csv").read_bytes()
    changed = tmp_path / "config/carrier_crosswalk.csv"
    changed.parent.mkdir()
    changed.write_bytes(canonical + b"\n")
    monkeypatch.setattr(repair.bts_native, "ROOT", tmp_path)
    profile = dict(
        schema_version="bts_comparison_source_v1",
        historical_baseline=repair.HISTORICAL_BASELINE,
        current={},
        previous={},
        crosswalk={"path": "config/carrier_crosswalk.csv", "sha256": hashlib.sha256(canonical).hexdigest()},
    )
    with pytest.raises(ValueError, match="crosswalk changed"):
        repair.replay(profile, PATHS.root / "site", repo=tmp_path)

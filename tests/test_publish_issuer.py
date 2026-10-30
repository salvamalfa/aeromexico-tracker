"""Independent issuer publication must preserve peer/history authority and units."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.publish import issuer_projection as projection
from src.publish import issuer_scope as scope


@pytest.fixture
def projected(monkeypatch):
    baseline = json.loads((Path(__file__).parents[1] / "site/data/v1/executive.json").read_bytes())
    # First-edition tests use a pre-release snapshot even after production has
    # published this quarter. Never depend on a moving served edition's length.
    for entity in projection.ENTITIES:
        block = baseline["entities"][entity]
        block["records"] = [r for r in block["records"] if r["period_id"] != "2026Q3"]
        block["views"].pop("2026Q3", None)
        block["first_period"] = block["records"][0]["period_id"]
        block["last_period"] = block["records"][-1]["period_id"]
        block["quarter_count"] = len(block["records"])
    package = {"entity_key": "VIVA_AEROBUS", "period_id": "2026Q3"}
    numbers = {
        "2026Q3": dict(passengers=8_000_000, asm=10e9, rpm=8.5e9, load=0.86, trasm=7.5, casm=7, casm_ex=4),
        "2025Q3": dict(passengers=7_000_000, asm=9e9, rpm=7.5e9, load=0.85, trasm=7, casm=6, casm_ex=3),
    }
    nodes = [{"period_id": p, "key": k, "value": v} for p, ns in numbers.items() for k, v in ns.items()]
    calls = []
    module = SimpleNamespace(verify=lambda p: calls.append(p), calculate=lambda p: {"nodes": nodes})
    monkeypatch.setitem(sys.modules, "src.analysis_agent.issuer_quarter", module)
    return baseline, package, nodes, calls


def test_projection_units_and_booked_passengers(projected):
    baseline, package, _, calls = projected
    before = copy.deepcopy(baseline)
    result = projection.executive_projection(baseline, package)
    assert calls == [package]
    assert baseline == before
    current = result["entities"]["VIVA_AEROBUS"]["records"][-1]
    assert current["ask_km"] == pytest.approx(16_093_440_000)
    assert current["rask_cents_per_km"] == pytest.approx(7.5 / 1.609344)
    assert current["unit_margin_cents_per_km"] == pytest.approx(0.5 / 1.609344)
    assert current["load_factor"] == 0.86
    view = result["entities"]["VIVA_AEROBUS"]["views"]["2026Q3"]
    passenger_kpi = next(k for k in view["kpis"] if k["key"] == "passengers")
    assert passenger_kpi["label"] == "Pasajeros con boleto"
    assert passenger_kpi["yoy"]["raw"] == pytest.approx(8 / 7 - 1)
    assert result["entities"]["VIVA_AEROBUS"]["records"][:-1] == before["entities"]["VIVA_AEROBUS"]["records"]
    assert result["entities"]["AEROMEXICO"] == before["entities"]["AEROMEXICO"]
    assert result["entities"]["INDUSTRY"] == before["entities"]["INDUSTRY"]
    assert result["records"] == before["records"]
    projection.require_scope(before, result, "VIVA_AEROBUS", "2026Q3")


def test_identical_projection_is_idempotent(projected):
    baseline, package, _, _ = projected
    once = projection.executive_projection(baseline, package)
    assert projection.executive_projection(once, package) == once


@pytest.mark.parametrize(
    "entity,current,prior_year,expected_yoy,expected_qoq",
    [
        ("VIVA_AEROBUS", 0.892, 0.882, "+1.0 pp", "+3.3 pp"),
        ("VOLARIS", 0.857, 0.844, "+1.3 pp", "+0.9 pp"),
    ],
)
def test_reported_occupancy_comparisons_use_percentage_points(
    projected,
    entity,
    current,
    prior_year,
    expected_yoy,
    expected_qoq,
):
    baseline, package, nodes, _ = projected
    before = copy.deepcopy(baseline)
    package["entity_key"] = entity
    for node in nodes:
        if node["key"] == "load":
            node["value"] = current if node["period_id"] == "2026Q3" else prior_year
    after = projection.executive_projection(baseline, package)
    block = after["entities"][entity]
    load = next(k for k in block["views"]["2026Q3"]["kpis"] if k["key"] == "load_factor")
    assert load["display_value"] == f"{current:.1%}"
    assert load["yoy"] == {
        "available": True,
        "raw": pytest.approx((current - prior_year) * 100),
        "display": expected_yoy,
        "direction": "up",
    }
    quarter_prior = next(
        r["load_factor"] for r in before["entities"][entity]["records"] if r["period_id"] == "2026Q2"
    )
    assert load["qoq"] == {
        "available": True,
        "raw": pytest.approx((current - quarter_prior) * 100),
        "display": expected_qoq,
        "direction": "up",
    }
    assert block["views"]["2026Q3"]["conclusions"][1].endswith(f"La ocupación cambió {expected_qoq}.")
    assert "load_factor_reported" not in block["records"][-1]
    assert not any(k["key"] == "load_factor_reported" for k in block["views"]["2026Q3"]["kpis"])
    assert block["records"][:-1] == before["entities"][entity]["records"]
    assert {p: v for p, v in block["views"].items() if p != "2026Q3"} == before["entities"][entity]["views"]
    assert baseline == before
    projection.require_scope(before, after, entity, "2026Q3")


@pytest.mark.parametrize("entity", ["VIVA_AEROBUS", "VOLARIS"])
def test_missing_occupancy_quarter_comparison_stays_unavailable(projected, entity):
    baseline, package, _, _ = projected
    package["entity_key"] = entity
    block = baseline["entities"][entity]
    block["records"] = [r for r in block["records"] if r["period_id"] != "2026Q2"]
    block["views"].pop("2026Q2")
    block["quarter_count"] = len(block["records"])
    block["last_period"] = block["records"][-1]["period_id"]
    after = projection.executive_projection(baseline, package)
    load = next(k for k in after["entities"][entity]["views"]["2026Q3"]["kpis"] if k["key"] == "load_factor")
    assert load["qoq"] == {"available": False, "raw": None, "display": "No disponible", "direction": "na"}
    assert "La ocupación cambió" not in " ".join(after["entities"][entity]["views"]["2026Q3"]["conclusions"])


@pytest.mark.parametrize("entity,period", [("INDUSTRY", "2026Q3"), ("VOLARIS", "2026Q4")])
def test_other_scope_rejected(projected, entity, period):
    baseline, package, _, _ = projected
    package.update(entity_key=entity, period_id=period)
    with pytest.raises(ValueError, match="profile"):
        projection.executive_projection(baseline, package)


@pytest.mark.parametrize("key,value", [("load", 85), ("asm", 0), ("passengers", float("nan"))])
def test_bad_quantities_fail_closed(projected, key, value):
    baseline, package, nodes, _ = projected
    next(n for n in nodes if n["period_id"] == "2026Q3" and n["key"] == key)["value"] = value
    with pytest.raises(ValueError):
        projection.executive_projection(baseline, package)


def test_duplicate_calculation_rejected(projected):
    baseline, package, nodes, _ = projected
    nodes.append(dict(nodes[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        projection.executive_projection(baseline, package)


@pytest.mark.parametrize(
    "mutation", ["peer", "historical_record", "historical_view", "root", "first", "missing_view"]
)
def test_structural_scope_is_separate_from_output_hash(projected, mutation):
    baseline, package, _, _ = projected
    after = projection.executive_projection(baseline, package)
    block = after["entities"]["VIVA_AEROBUS"]
    if mutation == "peer":
        after["entities"]["VOLARIS"]["note"] += " altered"
    elif mutation == "historical_record":
        block["records"][0]["passengers"] += 1
    elif mutation == "historical_view":
        key = next(iter(baseline["entities"]["VIVA_AEROBUS"]["views"]))
        block["views"][key]["period_label"] = "altered"
    elif mutation == "root":
        after["metadata"]["default_period"] = "2026Q3"
    elif mutation == "first":
        block["first_period"] = "2026Q3"
    else:
        del block["views"]["2026Q3"]
    with pytest.raises(ValueError):
        projection.require_scope(baseline, after, "VIVA_AEROBUS", "2026Q3")


def test_historical_verifier_failure_is_not_ignored(tmp_path, monkeypatch):
    spec = {"baseline_commit": "a" * 40}
    old = {"code_commit": "b" * 40, "files": []}
    monkeypatch.setattr(scope.transport, "baseline", lambda *a: (old, b'{"files":[]}'))
    monkeypatch.setattr(scope.transport, "_git", lambda *a: b"")
    actions = []

    def run(command, **kwargs):
        actions.append(command)
        if "worktree" in command and "add" in command:
            target = Path(command[-2])
            (target / "site").mkdir(parents=True)
            (target / "site/publication_manifest.json").write_bytes(b'{"files":[]}')
        return SimpleNamespace(returncode=1 if "-m" in command else 0)

    monkeypatch.setattr(scope.subprocess, "run", run)
    with pytest.raises(ValueError, match="own released verifier rejected"):
        scope.verify_historical_baseline(tmp_path, spec, tmp_path)
    assert any("src.publish.verify" in c for c in actions)
    assert actions[-1][1:3] == ["worktree", "remove"]


def test_anchor_must_be_committed(tmp_path, monkeypatch):
    path = tmp_path / scope.ANCHOR
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{}")
    monkeypatch.setattr(scope.transport, "_git", lambda *a: b"altered")
    with pytest.raises(ValueError, match="must be committed"):
        scope.anchor(tmp_path)


def test_runtime_verifier_rejection_cannot_fall_back(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, "anchor", lambda *a: {"producer_code_version": "wrong"})
    monkeypatch.setattr(scope, "verify_historical_baseline", lambda *a: pytest.fail("must reject first"))
    result = scope.verify_issuer(tmp_path)
    assert len(result) == 1
    assert "runtime differs" in result[0]


def test_revision_replaces_only_existing_current_quarter(projected):
    baseline, package, nodes, _ = projected
    first = projection.executive_projection(baseline, package)
    previous = copy.deepcopy(first)
    next(n for n in nodes if n["period_id"] == "2026Q3" and n["key"] == "passengers")["value"] += 1
    revised = projection.executive_projection(first, package)
    projection.require_scope(previous, revised, package["entity_key"], package["period_id"])
    assert first == previous
    old, new = previous["entities"][package["entity_key"]], revised["entities"][package["entity_key"]]
    assert new["quarter_count"] == old["quarter_count"]
    assert new["records"][:-1] == old["records"][:-1]
    assert new["records"][-1]["passengers"] == old["records"][-1]["passengers"] + 1

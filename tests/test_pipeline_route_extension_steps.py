"""Route-extension generators must run inside `just rebuild`'s DAG.

Regression coverage for the gap where `src.transform.stage6_warehouse`'s
fail-closed `RouteExtensionMissingError` guard could fire on every offline
rebuild: the six route-extension generators (`src.transform.domestic_slots`,
`aicm_international_slots`, `oma_documented_routes`, `international_routes`,
`aifa_shared_presence`, `afac_exclusive_domestic`) were not registered as
pipeline steps, so a clean checkout's Bronze research documents were copied
in but their Gold was never regenerated before the guard checked for it.

These tests assert (1) each generator is now registered, gated on exactly the
bronze file(s) its own module reads, and ordered after `transform.stage6`
(which builds the `dim_airport` warehouse table every generator queries) and
before `dashboard.materialize_stage9` (whose `build_warehouse` call enforces
the guard); (2) the registry's literal bronze patterns have not drifted from
`src.transform.stage6_warehouse.ROUTE_EXTENSION_BRONZE_SOURCES`, which they
duplicate only because importing that module from the registry would be a
circular import; and (3) the guard still raises when a registered generator's
declared Gold output is missing at load time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.registry import PIPELINE_STEPS
from src.transform import stage6_warehouse as warehouse


def _step(step_id: str):
    matches = [step for step in PIPELINE_STEPS if step.step_id == step_id]
    assert len(matches) == 1, f"expected exactly one {step_id} step, found {len(matches)}"
    return matches[0]


def _index(step_id: str) -> int:
    return next(i for i, step in enumerate(PIPELINE_STEPS) if step.step_id == step_id)


ROUTE_EXTENSION_STEP_IDS = (
    "transform.domestic_slots",
    "transform.aicm_international_slots",
    "transform.oma_documented_routes",
    "transform.international_routes",
    "transform.aifa_shared_presence",
    "transform.afac_exclusive_domestic",
)


def test_every_route_extension_generator_step_is_registered_and_optional():
    for step_id in ROUTE_EXTENSION_STEP_IDS:
        step = _step(step_id)
        assert step.requirement.value == "optional", (
            f"{step_id} must be optional: a snapshot without its bronze research "
            "must not fail the rebuild"
        )
        assert step.depends_on == ("transform.stage6",)


def test_route_extension_steps_run_after_stage6_and_before_stage9_materialize():
    stage6_index = _index("transform.stage6")
    stage9_index = _index("dashboard.materialize_stage9")
    for step_id in ROUTE_EXTENSION_STEP_IDS:
        step_index = _index(step_id)
        assert stage6_index < step_index < stage9_index, (
            f"{step_id} must run after transform.stage6 (builds dim_airport) and "
            "before dashboard.materialize_stage9 (rebuilds the warehouse and "
            "enforces RouteExtensionMissingError)"
        )


def test_route_extension_step_outputs_match_the_guarded_gold_tables():
    """Each step's declared outputs are exactly the tables that generator's
    module writes, matching `ROUTE_EXTENSION_GENERATOR_STEPS` in
    `stage6_warehouse` (the guard's own map of table -> generator step)."""

    step_outputs = {
        step_id: {Path(output).stem for output in _step(step_id).outputs}
        for step_id in ROUTE_EXTENSION_STEP_IDS
    }
    for table, step_id in warehouse.ROUTE_EXTENSION_GENERATOR_STEPS.items():
        assert table in step_outputs[step_id], (
            f"{step_id} does not declare {table}.parquet as an output, but "
            "stage6_warehouse.ROUTE_EXTENSION_GENERATOR_STEPS says it produces it"
        )


@pytest.mark.parametrize(
    ("step_id", "bronze_sources_key"),
    [
        ("transform.domestic_slots", "fact_domestic_scheduled_route_movements"),
        ("transform.aicm_international_slots", "fact_aicm_international_scheduled_route_movements"),
        ("transform.oma_documented_routes", "fact_oma_documented_routes"),
        ("transform.international_routes", "fact_international_route_observations"),
        ("transform.aifa_shared_presence", "fact_aifa_shared_route_presence"),
        ("transform.afac_exclusive_domestic", "fact_domestic_exclusive_market_inferences"),
    ],
)
def test_route_extension_step_inputs_match_stage6_warehouse_bronze_sources(step_id, bronze_sources_key):
    """The registry's literal bronze patterns (duplicated to avoid a circular
    import) must name exactly the same files as the guard's own source list."""

    step = _step(step_id)
    assert len(step.inputs) == 1
    registered_patterns = {Path(pattern).name for pattern in step.inputs[0].path_patterns}
    guarded_sources = warehouse.ROUTE_EXTENSION_BRONZE_SOURCES[bronze_sources_key]
    assert guarded_sources is not None
    expected_names = {source.name for source in guarded_sources}
    assert registered_patterns == expected_names


def test_guard_still_raises_when_a_registered_generators_output_is_missing(tmp_path, monkeypatch):
    """Registering the generator as a pipeline step does not weaken the guard:
    if its Gold ever goes missing while its bronze is present, the warehouse
    rebuild must still fail loudly rather than silently drop the table."""

    from types import SimpleNamespace

    name = "fact_domestic_scheduled_route_movements"
    assert warehouse.ROUTE_EXTENSION_GENERATOR_STEPS[name] == "transform.domestic_slots"

    fake_bronze = tmp_path / "bronze"
    fake_bronze.mkdir()
    present = fake_bronze / "present.pdf"
    present.write_bytes(b"stub")
    monkeypatch.setattr(
        warehouse,
        "ROUTE_EXTENSION_BRONZE_SOURCES",
        {**warehouse.ROUTE_EXTENSION_BRONZE_SOURCES, name: (present,)},
    )
    gold = tmp_path / "gold"
    gold.mkdir()
    sql = tmp_path / "sql"
    sql.mkdir()
    monkeypatch.setattr(
        warehouse,
        "PATHS",
        SimpleNamespace(data=tmp_path, gold=gold, bronze=fake_bronze, warehouse=tmp_path / "warehouse.duckdb"),
    )
    monkeypatch.setattr(warehouse, "SQL_DIR", sql)
    monkeypatch.setattr(warehouse, "table_definitions", lambda **kwargs: {})

    with pytest.raises(warehouse.RouteExtensionMissingError, match=name):
        warehouse.build_warehouse(max_stage=9)

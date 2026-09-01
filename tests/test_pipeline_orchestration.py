from __future__ import annotations

import json
from pathlib import Path
import socket

import pytest

from src.pipeline.model import (
    InputRequirement,
    PipelinePhase,
    PipelineRunError,
    PipelineStatus,
    PipelineStep,
    RequirementLevel,
)
from src.pipeline.offline import OfflineNetworkError, block_network
from src.pipeline.registry import PIPELINE_STEPS, validate_registry
from src.pipeline.runner import run_pipeline
from src.rebuild import (
    CORE_OUTPUTS,
    GENERATED_OUTPUTS,
    RebuildError,
    create_clean_checkout,
    publish_outputs,
)


ACTION_ROOT: Path | None = None


def write_test_output() -> dict[str, object]:
    assert ACTION_ROOT is not None
    target = ACTION_ROOT / "out" / "result.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("fresh", encoding="utf-8")
    return {"rows": 1}


def fail_test_action() -> None:
    raise ValueError("synthetic action failure")


def _step(
    step_id: str,
    *,
    requirement: RequirementLevel = RequirementLevel.REQUIRED,
    inputs: tuple[InputRequirement, ...] = (),
    callable_name: str = "write_test_output",
    depends_on: tuple[str, ...] = (),
    network_required: bool = False,
) -> PipelineStep:
    return PipelineStep(
        step_id=step_id,
        phase=PipelinePhase.PARSE,
        description=step_id,
        callable_ref=f"{__name__}:{callable_name}",
        requirement=requirement,
        inputs=inputs,
        outputs=("out/result.txt",),
        depends_on=depends_on,
        network_required=network_required,
    )


def test_registry_is_unique_ordered_and_covers_every_phase() -> None:
    validate_registry()
    assert {step.phase for step in PIPELINE_STEPS} == set(PipelinePhase)
    assert len({step.step_id for step in PIPELINE_STEPS}) == len(PIPELINE_STEPS)
    assert all(step.outputs and step.description for step in PIPELINE_STEPS)
    assert all(isinstance(step.inputs, tuple) for step in PIPELINE_STEPS)
    assert all(
        isinstance(requirement, InputRequirement)
        for step in PIPELINE_STEPS
        for requirement in step.inputs
    )
    assert any(step.requirement == RequirementLevel.OPTIONAL for step in PIPELINE_STEPS)
    assert any(step.requirement == RequirementLevel.REQUIRED for step in PIPELINE_STEPS)


def test_optional_missing_input_is_not_available_and_does_not_block_independent_step(
    tmp_path: Path,
) -> None:
    global ACTION_ROOT
    ACTION_ROOT = tmp_path
    optional = _step(
        "parse.optional",
        requirement=RequirementLevel.OPTIONAL,
        inputs=(InputRequirement("optional fixture", ("missing/*.json",)),),
    )
    required = _step("parse.required")

    report = run_pipeline(
        root=tmp_path,
        steps=(optional, required),
        phases=(PipelinePhase.PARSE,),
        include_dependencies=False,
        report_path=tmp_path / "receipt.json",
    )

    assert [item.status for item in report.steps] == [
        PipelineStatus.NOT_AVAILABLE.value,
        PipelineStatus.COMPLETED.value,
    ]
    assert "missing paths" in report.steps[0].reason
    assert json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))["status"] == "completed"


def test_required_missing_input_fails_and_dependent_step_is_explicitly_blocked(
    tmp_path: Path,
) -> None:
    global ACTION_ROOT
    ACTION_ROOT = tmp_path
    first = _step(
        "parse.required_input",
        inputs=(InputRequirement("required fixture", ("missing.parquet",)),),
    )
    second = _step("parse.downstream", depends_on=(first.step_id,))

    with pytest.raises(PipelineRunError) as captured:
        run_pipeline(
            root=tmp_path,
            steps=(first, second),
            phases=(PipelinePhase.PARSE,),
            report_path=tmp_path / "receipt.json",
        )

    report = captured.value.report
    assert len(report.steps) == 2
    assert [item.status for item in report.steps] == ["failed", "failed"]
    assert "missing paths" in report.steps[0].reason
    assert "blocked by dependencies" in report.steps[1].reason
    assert report.status == "failed"


def test_optional_action_failure_is_receipted_without_hiding_later_work(tmp_path: Path) -> None:
    global ACTION_ROOT
    ACTION_ROOT = tmp_path
    failing = _step(
        "parse.optional_failure",
        requirement=RequirementLevel.OPTIONAL,
        callable_name="fail_test_action",
    )
    succeeding = _step("parse.succeeds")

    report = run_pipeline(
        root=tmp_path,
        steps=(failing, succeeding),
        phases=(PipelinePhase.PARSE,),
        include_dependencies=False,
    )

    assert report.steps[0].status == "failed"
    assert "synthetic action failure" in report.steps[0].reason
    assert report.steps[1].status == "completed"


def test_offline_mode_marks_network_steps_without_executing_them(tmp_path: Path) -> None:
    global ACTION_ROOT
    ACTION_ROOT = tmp_path
    optional = _step(
        "parse.network_optional",
        requirement=RequirementLevel.OPTIONAL,
        network_required=True,
    )
    report = run_pipeline(
        root=tmp_path,
        steps=(optional,),
        offline=True,
        include_dependencies=False,
    )
    assert report.steps[0].status == "not_available"
    assert not (tmp_path / "out" / "result.txt").exists()


def test_offline_guard_blocks_direct_socket_connections() -> None:
    with block_network(), pytest.raises(OfflineNetworkError):
        socket.create_connection(("example.com", 443), timeout=0.01)


def test_offline_guard_allows_loopback_for_local_notebook_kernel() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.settimeout(1)
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with block_network():
            client = socket.create_connection(server.getsockname(), timeout=1)
            connection, _ = server.accept()
            client.close()
            connection.close()
    finally:
        server.close()


def test_clean_checkout_contains_bronze_but_no_previous_derived_data(tmp_path: Path) -> None:
    project = tmp_path / "project"
    bronze = project / "data" / "bronze"
    (project / "src").mkdir(parents=True)
    bronze.mkdir(parents=True)
    (project / "data" / "reference").mkdir()
    (project / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (project / "data" / "reference" / "carrier_crosswalk.csv").write_text(
        "source,canonical\nAERO,AEROMEXICO\n", encoding="utf-8"
    )
    artifact = bronze / "source.json"
    artifact.write_text("{}", encoding="utf-8")
    manifest = {
        "source_system": "fixture",
        "source_file": "source.json",
    }
    (bronze / "_manifest.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (project / "data" / "silver").mkdir()
    (project / "data" / "silver" / "stale.parquet").write_bytes(b"stale")
    (project / "data" / "gold").mkdir()
    (project / "data" / "gold" / "stale.parquet").write_bytes(b"stale")
    (project / "models").mkdir()
    (project / "models" / "stale.joblib").write_bytes(b"stale")
    (project / "notebooks").mkdir()
    (project / "notebooks" / "01_eda.ipynb").write_text("stale", encoding="utf-8")
    (project / "docs" / "analytics").mkdir(parents=True)
    (project / "docs" / "analytics" / "stale.md").write_text("stale", encoding="utf-8")
    (project / "docs" / "diccionario-datos.md").write_text("stale", encoding="utf-8")
    (project / "config").mkdir()
    (project / "config" / "carrier_crosswalk.csv").write_text("stale", encoding="utf-8")
    (project / ".env").write_text("SECRET=do-not-copy\n", encoding="utf-8")

    checkout = create_clean_checkout(project, bronze, tmp_path / "checkout")

    assert (checkout / "data" / "bronze" / "source.json").read_text(encoding="utf-8") == "{}"
    assert (checkout / "data" / "reference" / "carrier_crosswalk.csv").is_file()
    assert not (checkout / "data" / "silver").exists()
    assert not (checkout / "data" / "gold").exists()
    assert not (checkout / "models").exists()
    assert not (checkout / "notebooks").exists()
    assert not (checkout / "docs" / "analytics").exists()
    assert not (checkout / "docs" / "diccionario-datos.md").exists()
    assert not (checkout / "config" / "carrier_crosswalk.csv").exists()
    assert not (checkout / ".env").exists()


def test_publish_replaces_outputs_only_after_complete_staging(tmp_path: Path) -> None:
    project = tmp_path / "project"
    checkout = tmp_path / "checkout"
    for relative in GENERATED_OUTPUTS:
        generated = checkout / relative
        old = project / relative
        if Path(relative).suffix:
            generated.parent.mkdir(parents=True, exist_ok=True)
            old.parent.mkdir(parents=True, exist_ok=True)
            generated.write_bytes(b"fresh")
            old.write_bytes(b"stale")
        else:
            generated.mkdir(parents=True, exist_ok=True)
            old.mkdir(parents=True, exist_ok=True)
            (generated / "marker.txt").write_text("fresh", encoding="utf-8")
            (old / "marker.txt").write_text("stale", encoding="utf-8")

    published = publish_outputs(project, checkout)

    assert set(CORE_OUTPUTS) <= set(published)
    assert (project / "data" / "silver" / "marker.txt").read_text(encoding="utf-8") == "fresh"
    assert (project / "data" / "warehouse.duckdb").read_bytes() == b"fresh"


def test_publish_fails_before_swapping_when_any_generated_output_is_missing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    checkout = tmp_path / "checkout"
    for relative in GENERATED_OUTPUTS[:-1]:
        generated = checkout / relative
        if Path(relative).suffix:
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_bytes(b"fresh")
        else:
            generated.mkdir(parents=True, exist_ok=True)
            (generated / "marker.txt").write_text("fresh", encoding="utf-8")
    old = project / "data" / "warehouse.duckdb"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"stale")

    with pytest.raises(RebuildError, match="Required rebuild output is missing"):
        publish_outputs(project, checkout)

    assert old.read_bytes() == b"stale"


def test_publish_rolls_back_every_target_when_a_staged_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    checkout = tmp_path / "checkout"
    for relative in GENERATED_OUTPUTS:
        generated = checkout / relative
        old = project / relative
        if Path(relative).suffix:
            generated.parent.mkdir(parents=True, exist_ok=True)
            old.parent.mkdir(parents=True, exist_ok=True)
            generated.write_bytes(b"fresh")
            old.write_bytes(b"stale")
        else:
            generated.mkdir(parents=True, exist_ok=True)
            old.mkdir(parents=True, exist_ok=True)
            (generated / "marker.txt").write_text("fresh", encoding="utf-8")
            (old / "marker.txt").write_text("stale", encoding="utf-8")

    original_replace = Path.replace

    def fail_one_staged_move(path: Path, target: Path) -> Path:
        if (
            ".aeromexico-rebuild-publish-" in path.as_posix()
            and path.as_posix().endswith("data/warehouse.duckdb")
        ):
            raise OSError("synthetic staged move failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_one_staged_move)
    with pytest.raises(OSError, match="synthetic staged move failure"):
        publish_outputs(project, checkout)

    for relative in GENERATED_OUTPUTS:
        old = project / relative
        if Path(relative).suffix:
            assert old.read_bytes() == b"stale"
        else:
            assert (old / "marker.txt").read_text(encoding="utf-8") == "stale"

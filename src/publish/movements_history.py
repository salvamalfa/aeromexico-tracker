"""Private, read-only replay of all three original Aerocivil editions used by the site."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from src.source_updates import aerocivil, readiness
from src.source_updates.aerocivil_operational import accepted
from src.transform.international_routes import TABLE, normalize, validate
from src.transform.stage9_lineage import LineageSpec, build_bridge_record_lineage, build_dim_source_artifact
from src.transform.validate_stage9 import validate_lineage_frames

from .movements_projection import (
    CAPTURES,
    COLUMNS,
    GRAIN,
    HISTORICAL_SHA,
    JULY_SHA,
    TARGETS,
    project_file,
    projection_frame,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def profile_inputs(profile):
    """The publisher snapshots this entire closure before and after its slow build."""
    if (
        set(profile) != {"schema_version", "originals", "airport_reference", "july_item", "round_as_of"}
        or profile["schema_version"] != "aerocivil_movement_source_profile_v1"
    ):
        raise ValueError("Unsupported movement original source profile")
    paths = []
    for item in [*profile["originals"], profile["airport_reference"]]:
        if set(item) != {"path", "sha256", "metadata_path", "metadata_sha256"}:
            raise ValueError("Explicit pinned original and metadata paths required")
        paths.extend([Path(item["path"]), Path(item["metadata_path"])])
    workspace = Path(profile["july_item"]["workspace"])
    for folder in ("data", "receipts", "baselines"):
        paths.extend(p for p in (workspace / folder).rglob("*") if p.is_file())
    availability = profile["july_item"].get("availability")
    if availability:
        paths.extend(p for p in Path(availability["workspace"]).rglob("*") if p.is_file())
    if any(
        ".." in p.parts or not p.is_file() or any(node.is_symlink() for node in [p, *p.parents])
        for p in paths
    ):
        raise ValueError("Movement originals must be physical immutable files, not symlinks")
    return sorted(set(p.resolve() for p in paths))


def original(item):
    path, metadata = Path(item["path"]), Path(item["metadata_path"])
    if sha(path) != item["sha256"] or sha(metadata) != item["metadata_sha256"]:
        raise ValueError("Retained movement original or sidecar differs from pinned bytes")
    meta = json.loads(metadata.read_bytes())
    if meta["sha256"] != item["sha256"] or meta["bytes"] != path.stat().st_size:
        raise ValueError("Retained original/sidecar hash or size differs")
    return path, meta


def july_binding(item, round_as_of):
    """Replay the actual bounded candidate, preserving its original dates and receipt identity."""
    if (item["product"], item["adapter"], item.get("source_period", item["period"])) != (
        "aerocivil",
        "aerocivil",
        "2026M07",
    ):
        raise ValueError("Expected the physically retained July source item")
    task = {
        key: item[key] for key in ("id", "product", "adapter", "workspace", "receipt_id", "candidate_as_of")
    }
    task.update(period="2026M07", required=True)
    if "availability" in item:
        task["availability"] = item["availability"]
    recipe = {"version": 1, "as_of": round_as_of, "required_items": [task["id"]], "items": [task]}
    plan = readiness.preflight(
        recipe, Path(__file__).resolve().parents[2] / "tmp/source-updates/movement-readonly-check"
    )[0]
    checked = readiness.check_task(plan, task["candidate_as_of"], round_as_of)
    if not accepted(checked) or checked["operational_acceptance"]["official_confirmation"] is not False:
        raise ValueError("Aerocivil native checks and provisional operational policy must pass")
    workspace = Path(item["workspace"])
    frames, detail = aerocivil.frames(workspace, "2026M07", item["candidate_as_of"], item["receipt_id"])
    receipt = json.loads((workspace / "receipts/aerocivil-2026M07.json").read_bytes())
    if (
        receipt["collection_run_id"] != item["receipt_id"]
        or receipt["effective_as_of"] != item["candidate_as_of"]
        or receipt["reported_operations_under_selected_codes"] != 347
        or detail["reported_operations_under_selected_codes"] != 347
        or receipt["service_code_mapping_verified"] is not False
    ):
        raise ValueError("July candidate no longer matches its retained native receipt")
    hashes = {}
    for name, expected in frames.items():
        path = workspace / "data" / (name + ".parquet")
        pd.testing.assert_frame_equal(pd.read_parquet(path), expected, check_exact=True)
        hashes[name] = sha(path)
    if hashes != receipt["output_sha256"]:
        raise ValueError("July candidate physical output hashes differ from its original receipt")
    return {
        "product": "aerocivil",
        "period": "2026M07",
        "receipt_id": item["receipt_id"],
        "candidate_as_of": item["candidate_as_of"],
        "output_sha256": hashes,
    }


def normalized_editions(profile):
    reference_path, reference_meta = original(profile["airport_reference"])
    reference = pd.read_csv(reference_path, keep_default_na=False, low_memory=False)
    if reference.ident.duplicated().any():
        raise ValueError("Retained airport reference has ambiguous ICAO codes")
    airports = {r["ident"]: {"airport_iata": r["iata_code"]} for r in reference.to_dict("records")}
    if len(profile["originals"]) != 3 or {i["sha256"] for i in profile["originals"]} != set(CAPTURES):
        raise ValueError("All three exact source editions are required")
    frames, originals = [], []
    for item in sorted(profile["originals"], key=lambda i: i["sha256"]):
        path, meta = original(item)
        size, capture = CAPTURES[item["sha256"]]
        if (path.stat().st_size, meta["downloaded_at"]) != (size, capture):
            raise ValueError("Original capture timestamp/size must not be renewed")
        artifact = {
            "file": meta["source_file"],
            "sha256": meta["sha256"],
            "url": meta["source_url"],
            "downloaded_at": capture,
        }
        rows = normalize(
            "aerocivil",
            json.loads(path.read_bytes()),
            artifact,
            airports,
            aerocivil_operators=("AMX", "SLI", "VIV", "VOI"),
        )
        frame = pd.DataFrame(rows)
        for column in ("operations", "departures", "passengers", "seats", "load_factor"):
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
        validate(frame)
        frames.append(frame)
        originals.append(
            {
                "sha256": meta["sha256"],
                "bytes": size,
                "downloaded_at": capture,
                "source_url": meta["source_url"],
                "metadata_sha256": item["metadata_sha256"],
            }
        )
    return frames, originals, reference_meta


def source_projection(profile, baseline):
    inputs = profile_inputs(profile)
    before_hashes = {str(p): sha(p) for p in inputs}
    frames, originals, reference_meta = normalized_editions(profile)
    all_rows = pd.concat(frames, ignore_index=True)
    july = all_rows[all_rows.source_hash.eq(JULY_SHA)]
    historical_july = all_rows[all_rows.source_hash.eq(HISTORICAL_SHA) & all_rows.period_id.eq("2026M07")]
    keys = GRAIN[1:]
    if (
        july.groupby(keys).operations.sum().to_dict()
        != historical_july.groupby(keys).operations.sum().to_dict()
    ):
        raise ValueError("July revision differs from historical source cells; needs review")
    binding = july_binding(profile["july_item"], profile["round_as_of"])
    evidence = {
        "originals": originals,
        "source_binding": binding,
        "airport_reference": {
            "sha256": profile["airport_reference"]["sha256"],
            "metadata_sha256": profile["airport_reference"]["metadata_sha256"],
            "source_url": reference_meta["source_url"],
            "downloaded_at": reference_meta["downloaded_at"],
        },
    }
    rows = json.loads(all_rows[list(COLUMNS)].to_json(orient="records", double_precision=15))
    checked = projection_frame(rows, evidence)
    outputs = {}
    for name in TARGETS:
        document = json.loads((Path(baseline) / name).read_bytes())
        projected = project_file(name, document, checked)
        outputs[name] = (
            json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode()
    if before_hashes != {str(p): sha(p) for p in inputs}:
        raise ValueError("Movement inputs changed during replay")
    return {
        "source_binding": binding,
        "source_evidence": evidence,
        "projection_rows": rows,
        "network_outputs": outputs,
        "input_files": [str(p) for p in inputs],
    }


def typed_outputs(profile):
    """Regenerate complete Silver/Gold and fresh lineage separately for each source edition."""
    inputs = profile_inputs(profile)
    before = {str(path): sha(path) for path in inputs}
    frames, _, _ = normalized_editions(profile)
    july_binding(profile["july_item"], profile["round_as_of"])
    reference = profile["airport_reference"]
    outputs = {}
    for frame in frames:
        digest = frame.source_hash.iloc[0]
        selected = next(item for item in profile["originals"] if item["sha256"] == digest)
        with tempfile.TemporaryDirectory(prefix="movement-lineage-") as temporary:
            root = Path(temporary)
            records = []
            for item in (selected, reference):
                path, meta = original(item)
                target = root / meta["source_file"]
                if not target.resolve().is_relative_to(root):
                    raise ValueError("Original source_file escaped temporary Bronze")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                records.append(meta)
            manifest = root / "_manifest.jsonl"
            manifest.write_text("".join(json.dumps(row) + "\n" for row in records))
            artifacts = build_dim_source_artifact(manifest, verify_files=True)
            bridge = build_bridge_record_lineage(
                [
                    LineageSpec(
                        record_id=row.record_id,
                        table_name=TABLE,
                        lineage_type="derived",
                        artifact_ids=tuple(artifacts.artifact_id),
                        lineage_note="Recorded movements under provisional literal S/I codes; original and airport reference",
                    )
                    for row in frame.itertuples(index=False)
                ],
                artifacts,
            )
            validation = frame.assign(
                source="aerocivil",
                sha256=frame.source_hash,
                locator=frame.source_locator.str.removeprefix("record:").astype(int),
                parser=frame.parser_version,
            )
            validate_lineage_frames(
                tables={TABLE: validation},
                artifacts=artifacts,
                bridge=bridge,
                contracts={"tables": {TABLE: {"grain": ["source", "sha256", "locator", "parser"]}}},
            )
            for name, table in {
                "silver/international_routes/observations": frame,
                f"gold/{TABLE}": frame,
                "gold/dim_source_artifact": artifacts,
                "gold/bridge_international_route_lineage": bridge,
            }.items():
                buffer = io.BytesIO()
                table.to_parquet(buffer, index=False)
                outputs[f"editions/{digest}/{name}.parquet"] = buffer.getvalue()
    if before != {str(path): sha(path) for path in inputs}:
        raise ValueError("Movement source input changed during typed Gold generation")
    return outputs

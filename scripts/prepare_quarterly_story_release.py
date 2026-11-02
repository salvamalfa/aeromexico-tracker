"""Prepare exact reviewable Q3 drafts and scope in the publication environment.

No audit, approval, Gold activation or site publication occurs. The descriptor
contains explicit physical source references; no private artifact discovery.
"""

import argparse
import json
from pathlib import Path

from src.analysis_agent import quarterly_story as story
from src.analysis_agent.issuer_quarter import immutable
from src.analysis_agent.volaris_original_quarter import package_for
from src.config import PATHS
from src.publish.quarterly_story_update import inspect
from src.publish.source_data_update import file_ref
from src.source_updates.collection import safe_workspace


def prepare(descriptor, output):
    descriptor = json.loads(Path(descriptor).read_bytes())
    if (
        set(descriptor)
        != {"schema_version", "review_spec", "am_package", "viva_package", "volaris_capture", "sources"}
        or descriptor["schema_version"] != "quarterly_story_preparation_v1"
    ):
        raise ValueError("Unknown story preparation descriptor")
    output = safe_workspace(Path(output))
    spec = json.loads(file_ref(descriptor["review_spec"], PATHS.root).read_bytes())
    packages = {
        "AEROMEXICO": json.loads(file_ref(descriptor["am_package"], PATHS.root).read_bytes()),
        "VIVA_AEROBUS": json.loads(file_ref(descriptor["viva_package"], PATHS.root).read_bytes()),
        "VOLARIS": package_for(PATHS.root / descriptor["volaris_capture"]),
    }
    paths, review = [], {}
    for entity in story.ENTITIES:
        package = story.prepare(spec, packages, entity)
        path = story.import_draft(package)
        record = story.read(path)
        _, calculations, checks = story.verified_inputs(record)
        paths.append(path.relative_to(PATHS.root).as_posix())
        review[entity] = dict(
            record_path=paths[-1],
            record_sha256=story.sha(path),
            version=record["version"],
            content_hash=record["content_hash"],
            evidence_fingerprint=package["evidence_fingerprint"],
            calculation_fingerprint=calculations["calculation_fingerprint"],
            review_version=package["review_version"],
            document=calculations["document"],
            mechanical_checks={k: v for k, v in checks.items() if k != "rendered"},
        )
    request = dict(
        schema_version="quarterly_story_request_v1",
        record_paths=paths,
        sources=descriptor["sources"],
        authorization=None,
    )
    immutable(output / "request.json", request)
    immutable(output / "four-story-review.json", review)
    scope, _, _, _, _ = inspect(output / "request.json")
    immutable(output / "scope.json", scope)
    return dict(
        state="draft_pending_independent_audit_and_new_owner_decision",
        output=str(output),
        records={e: r["version"] for e, r in review.items()},
        scope_sha256=story.sha(output / "scope.json"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.descriptor, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()

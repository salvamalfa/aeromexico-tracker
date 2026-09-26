"""Regenerates the synthetic ``site/`` fixtures under this directory.

Run after changing ``contracts/web/*`` or ``src/publish/manifest.py`` (must
be run as a module so ``src`` resolves, exactly like pytest does):

    uv run python -m tests.fixtures.site._generate

Builds one valid fixture site from the public, synthetic
``tests/fixtures/web/*_sample.json`` payloads (no private data, no npm
build — plain files standing in for a built ``web/dist/``), then derives
six negative fixtures from it, each with exactly one problem
``src.publish.verify.verify_site`` must catch:

- ``altered_byte``: a data file changed after the manifest was signed.
- ``extra_file``: a file on disk the manifest does not list.
- ``missing_file``: a file the manifest lists that is absent on disk.
- ``disallowed_carrier``: a ``carrier_key`` outside
  ``contracts/web/privacy.yaml``'s allow-list.
- ``undeclared_field``: an analysis payload field
  ``contracts/web/analysis.schema.json`` does not declare
  (``additionalProperties: false``).
- ``malformed_approval``: an ``analysis_manifest`` entry with an empty
  required field.

See ``tests/test_publish_verify.py`` and ``src/publish/README.md``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.web_export.executive import export_executive
from src.web_export.flights import export_flights
from src.web_export.writer import write_json
from src.publish import manifest as manifest_mod

ROOT = Path(__file__).resolve().parents[3]
WEB_FIXTURES = ROOT / "tests" / "fixtures" / "web"
OUT = Path(__file__).resolve().parent

FLIGHTS_PAYLOAD = json.loads((WEB_FIXTURES / "flights_sample.json").read_text(encoding="utf-8"))
EXECUTIVE_PAYLOAD = json.loads((WEB_FIXTURES / "executive_sample.json").read_text(encoding="utf-8"))
ANALYSIS_PAYLOAD = json.loads((WEB_FIXTURES / "analysis_sample.json").read_text(encoding="utf-8"))
CODE_COMMIT = "a" * 40
GENERATED_AT = "2026-09-26T00:00:00+00:00"


def _shell(dist_dir: Path) -> None:
    """Stand-in for the built web/dist/ shell (index.html + one asset)."""

    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<!doctype html><html><body>fixture site</body></html>\n")
    (dist_dir / "assets").mkdir(exist_ok=True)
    (dist_dir / "assets" / "index.js").write_text("console.log('fixture');\n")


def _analysis_manifest() -> list[dict[str, str]]:
    return [
        {k: ANALYSIS_PAYLOAD[k] for k in (
            "period_id", "version", "content_hash", "evidence_fingerprint", "approval_event", "audit_hash",
        )}
    ]


def build_valid_dist(dist_dir: Path, *, flights_payload: dict | None = None) -> None:
    _shell(dist_dir)
    data_dir = dist_dir / "data" / "v1"
    export_flights(flights_payload if flights_payload is not None else FLIGHTS_PAYLOAD, data_dir, skip_input_check=True)
    export_executive(EXECUTIVE_PAYLOAD, data_dir, skip_input_check=True)
    write_json(data_dir / "analysis" / f"{ANALYSIS_PAYLOAD['period_id']}.json", ANALYSIS_PAYLOAD)


def sign(site_dir: Path) -> dict:
    manifest = manifest_mod.build_manifest(
        site_dir, _analysis_manifest(), code_commit=CODE_COMMIT, generated_at=GENERATED_AT
    )
    manifest_mod.write_manifest(site_dir, manifest)
    return manifest


def _inject_disallowed_carrier(payload: dict) -> bool:
    """Mutate the first carrier_key found (recursively) to a disallowed value."""

    if isinstance(payload, dict):
        if "carrier_key" in payload and payload["carrier_key"] is not None:
            payload["carrier_key"] = "DELTA"
            return True
        return any(_inject_disallowed_carrier(v) for v in payload.values())
    if isinstance(payload, list):
        return any(_inject_disallowed_carrier(v) for v in payload)
    return False


def main() -> None:
    if OUT.exists():
        for child in OUT.iterdir():
            if child.name != "_generate.py":
                shutil.rmtree(child) if child.is_dir() else child.unlink()

    valid = OUT / "valid"
    build_valid_dist(valid)
    sign(valid)

    altered = OUT / "altered_byte"
    shutil.copytree(valid, altered)
    target = altered / "data" / "v1" / "executive.json"
    text = target.read_text(encoding="utf-8")
    target.write_text(text[:-2] + "X" + text[-1], encoding="utf-8")

    extra = OUT / "extra_file"
    shutil.copytree(valid, extra)
    (extra / "data" / "v1" / "unexpected.json").write_text('{"sneaky":true}\n', encoding="utf-8")

    missing = OUT / "missing_file"
    shutil.copytree(valid, missing)
    (missing / "data" / "v1" / "executive.json").unlink()

    carrier_payload = json.loads(json.dumps(FLIGHTS_PAYLOAD))
    assert _inject_disallowed_carrier(carrier_payload), "fixture payload has no carrier_key to poison"
    carrier = OUT / "disallowed_carrier"
    # export_flights itself refuses a privacy violation, so this fixture is
    # assembled without going through export_flights' own check.
    _shell(carrier)
    data_dir = carrier / "data" / "v1"
    domestic_periods = {**carrier_payload["domestic_networks"], **carrier_payload["domestic_monthly_networks"]}
    international_periods = carrier_payload["route_networks"]
    write_json(
        data_dir / "flights" / "quarters.json",
        {
            "schema_version": carrier_payload["schema_version"],
            "metadata": carrier_payload["metadata"],
            "quarters": carrier_payload["quarters"],
            "monthly_passengers": carrier_payload["monthly_passengers"],
            "route_network": carrier_payload["route_network"],
            "available_periods": {
                "domestic": sorted(p for p in domestic_periods if "Q" in p),
                "domestic_monthly": sorted(p for p in domestic_periods if "M" in p),
                "international": sorted(international_periods),
            },
        },
    )
    for period_id, network in domestic_periods.items():
        write_json(data_dir / "flights" / "domestic" / f"{period_id}.json", network)
    for period_id, network in international_periods.items():
        write_json(data_dir / "flights" / "international" / f"{period_id}.json", network)
    export_executive(EXECUTIVE_PAYLOAD, data_dir, skip_input_check=True)
    write_json(data_dir / "analysis" / f"{ANALYSIS_PAYLOAD['period_id']}.json", ANALYSIS_PAYLOAD)
    sign(carrier)

    undeclared = OUT / "undeclared_field"
    build_valid_dist(undeclared)
    bad_analysis = json.loads(json.dumps(ANALYSIS_PAYLOAD))
    bad_analysis["unexpected_field"] = "not declared by analysis.schema.json"
    write_json(undeclared / "data" / "v1" / "analysis" / f"{ANALYSIS_PAYLOAD['period_id']}.json", bad_analysis)
    sign(undeclared)

    malformed = OUT / "malformed_approval"
    build_valid_dist(malformed)
    manifest = sign(malformed)
    manifest["analysis_manifest"][0]["approval_event"] = ""
    manifest_mod.write_manifest(malformed, manifest)

    print(f"wrote fixtures under {OUT}")


if __name__ == "__main__":
    main()

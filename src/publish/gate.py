"""The publication gate: ``analysis_runs`` records -> a verified ``site/``.

Replaces ``stage18.consumer_html``/``stage18.publish`` as the *signed
object* (§4.2 punto 5 of the migration audit): instead of one 7 MB HTML
file, the gate assembles a ``site/`` directory (the built ``web/`` plus its
``data/v1/`` payload) and signs it with ``publication_manifest.json`` — a
list of every file's SHA-256/size, the code commit, each contract's own
hash, and the current analysis-manifest entries.

Every step below reuses the same functions ``stage18`` and ``src/web_export``
already use and never reimplements approval, verification or export logic:

1. ``src.analysis_agent.lifecycle.consumer_payload``/``verified_inputs`` —
   the same fail-closed handoff ``stage18.publish`` calls — verify each
   given record is exactly, currently approved. Anything else raises and the
   CLI exits non-zero; nothing is written.
2. ``src.web_export.flights.export_flights`` / ``executive.export_executive``
   / ``analysis.export_period`` write the v1 payload into a temp directory,
   schema- and privacy-checked exactly as ``python -m src.web_export``
   already does. Only the given (approved) records' periods get an
   ``analysis/<period_id>.json``.
3. ``npm ci && npm run build`` in ``web/`` (Vite copies the temp payload
   under ``web/public/data/v1`` into ``dist/`` — see ``web/README.md``
   "Entradas/salidas"), producing the built site.
4. The manifest (``src/publish/manifest.py``) is written into a fresh
   ``site.tmp-*`` directory, which then atomically swaps for ``site/``
   (rename, mirroring ``stage18.publish``'s tempfile+``os.replace`` for the
   HTML file, extended to a directory).
5. An intent/published receipt, hashing the manifest, is written to
   ``analysis_runs/publications/`` (local, gitignored, same style as
   ``stage18``'s receipts under ``analysis_runs/lifecycle/publications/``).

Never writes to the approval ledger, never approves/revokes/records
anything, never touches ``static/aeromexico_tracker.html`` or ``stage18``.
"""

from __future__ import annotations

import copy
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.analysis_agent import lifecycle as flow
from src.config import PATHS
from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.flights import build_flight_payload
from src.web_export import analysis as analysis_export
from src.web_export.executive import export_executive
from src.web_export.flights import export_flights
from src.web_export.inputs import MissingWebInput
from src.web_export.privacy import PrivacyViolation, check_privacy, load_privacy_rules
from src.web_export.schemas import ANALYSIS_SCHEMA
from src.web_export.writer import write_json

from . import manifest as manifest_mod

WEB_DIR = PATHS.root / "web"
WEB_DATA_V1 = WEB_DIR / "public" / "data" / "v1"
WEB_DIST = WEB_DIR / "dist"
PUBLICATIONS_ROOT = PATHS.root / "analysis_runs" / "publications"

ANALYSIS_MANIFEST_FIELDS = (
    "period_id", "version", "content_hash", "evidence_fingerprint", "approval_event", "audit_hash",
)


class PublicationRefused(RuntimeError):
    """A record failed verification, or web_export/npm build failed. Nothing was written."""


def load_records(record_paths: list[Path]) -> list[dict[str, Any]]:
    import json

    records = []
    for path in record_paths:
        records.append(json.loads(Path(path).read_text(encoding="utf-8")))
    return records


def verify_records(records: list[dict[str, Any]], root: Path = flow.ROOT) -> list[dict[str, Any]]:
    """Return, per record, (authorized, package, calculations) under the
    ledger's writer lock — the same fail-closed calls stage18.publish makes
    before it would replace content, so a concurrent approval/revocation
    cannot race the gate. Raises PublicationRefused if any record is not
    exactly, currently approved."""

    root = Path(root)
    try:
        with flow.writer(root):
            entries = []
            for record in records:
                authorized = flow.consumer_payload(record, root)
                package, calculations, _ = flow.verified_inputs(record)
                entries.append((record, authorized, package, calculations))
            return entries
    except ValueError as error:
        raise PublicationRefused(f"record failed verification/approval: {error}") from error


def _analysis_payload(record: dict[str, Any], authorized: dict[str, Any], package, calculations) -> dict[str, Any]:
    """Same shape src.web_export.analysis.export_period writes, built from
    the (record, authorized, package, calculations) this gate already holds
    from verify_records, instead of re-querying the ledger a second time."""

    payload = analysis_export._drop_private_sections(copy.deepcopy(authorized), record)
    citations = analysis_export._citations_by_claim(record, package, calculations)
    for claim in payload["claims"]:
        claim["citations"] = citations.get(claim["claim_id"], [])
    return payload


def export_data(entries: list[tuple[Any, Any, Any, Any]], out_dir: Path) -> None:
    """Write flights/executive (every period) and analysis (only the given,
    approved periods) v1 payloads under out_dir."""

    try:
        export_flights(build_flight_payload(), out_dir)
        export_executive(build_executive_payload(), out_dir)
    except MissingWebInput as error:
        raise PublicationRefused(str(error)) from error

    validator = Draft202012Validator(ANALYSIS_SCHEMA)
    rules = load_privacy_rules()
    for record, authorized, package, calculations in entries:
        period_id = authorized["period_id"]
        payload = _analysis_payload(record, authorized, package, calculations)
        errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
        if errors:
            raise PublicationRefused(f"analysis/{period_id}.json does not match its schema: {errors[:5]}")
        try:
            check_privacy(payload, rules)
        except PrivacyViolation as error:
            raise PublicationRefused(f"analysis/{period_id}.json: {error}") from error
        write_json(out_dir / "analysis" / f"{period_id}.json", payload)


def build_web(web_dir: Path = WEB_DIR) -> Path:
    """npm ci && npm run build. Raises PublicationRefused on any non-zero exit."""

    npm = shutil.which("npm")
    if npm is None:
        raise PublicationRefused("npm is not on PATH; install Node 22 + npm 10 to run the publish gate.")
    for args in (["ci"], ["run", "build"]):
        result = subprocess.run([npm, *args], cwd=web_dir, capture_output=True, text=True)
        if result.returncode != 0:
            raise PublicationRefused(
                f"`npm {' '.join(args)}` failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
            )
    dist = web_dir / "dist"
    if not dist.is_dir():
        raise PublicationRefused(f"npm run build did not produce {dist}")
    return dist


def assemble_site(dist_dir: Path, analysis_manifest: list[dict[str, str]], out_dir: Path) -> dict[str, Any]:
    """Copy dist_dir into a fresh temp directory, write the manifest into it,
    and atomically swap it in for out_dir. Returns the written manifest."""

    out_dir = Path(out_dir).resolve()
    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=parent, prefix=out_dir.name + ".tmp-"))
    try:
        shutil.rmtree(tmp_dir)
        shutil.copytree(dist_dir, tmp_dir)
        manifest = manifest_mod.build_manifest(tmp_dir, analysis_manifest)
        manifest_mod.write_manifest(tmp_dir, manifest)

        previous = None
        if out_dir.exists():
            previous = parent / (out_dir.name + ".prev-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
            out_dir.rename(previous)
        try:
            tmp_dir.rename(out_dir)
        except OSError:
            if previous is not None:
                previous.rename(out_dir)
            raise
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
        return manifest
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def write_receipt(manifest: dict[str, Any], authorized: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    """intent/published receipt in analysis_runs/publications/, hashing the
    manifest (hash of hashes) rather than raw site/ bytes."""

    receipt = {
        "manifest_sha256": manifest_mod.manifest_hash(manifest),
        "output": str(Path(out_dir).resolve()),
        "code_commit": manifest["code_commit"],
        "periods": sorted(e["period_id"] for e in authorized),
        "versions": sorted(e["version"] for e in authorized),
        "approval_events": sorted(e["approval_event"] for e in authorized),
    }
    key = manifest_mod.manifest_hash(receipt)
    store = PUBLICATIONS_ROOT
    store.mkdir(parents=True, exist_ok=True)
    intent = store / (key + ".intent.json")
    done = store / (key + ".published.json")
    if not intent.exists():
        flow.atomic_json(intent, receipt)
    if not done.exists():
        flow.atomic_json(done, {**receipt, "published_at": datetime.now(timezone.utc).isoformat()})
    return receipt


def publish(
    record_paths: list[Path],
    out_dir: Path,
    *,
    root: Path = flow.ROOT,
    web_dir: Path = WEB_DIR,
    web_data_v1: Path = WEB_DATA_V1,
) -> dict[str, Any]:
    """Verify every record, export v1 data, build web/, assemble and swap in
    site/, and write the publications receipt. Raises PublicationRefused
    (nothing written to out_dir) on any failure."""

    records = load_records(record_paths)
    if not records:
        raise PublicationRefused("no --record given; refuse to publish an empty analysis manifest")

    entries = verify_records(records, root=root)
    authorized = [e[1] for e in entries]

    with tempfile.TemporaryDirectory(prefix="publish-data-") as tmp:
        export_data(entries, Path(tmp))
        # web/public/data/v1 is local/gitignored dev scratch (see .gitignore);
        # clearing it first guarantees the build sees exactly this run's
        # periods, not stale files from an earlier `web_export` run.
        if web_data_v1.exists():
            shutil.rmtree(web_data_v1)
        shutil.copytree(tmp, web_data_v1)

    dist_dir = build_web(web_dir)
    analysis_manifest = [{k: e[k] for k in ANALYSIS_MANIFEST_FIELDS} for e in authorized]
    manifest = assemble_site(dist_dir, analysis_manifest, out_dir)
    receipt = write_receipt(manifest, authorized, out_dir)
    return {"manifest": manifest, "receipt": receipt}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, action="append", default=[], dest="records")
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    args = parser.parse_args(argv)

    try:
        result = publish(args.records, args.out)
    except PublicationRefused as error:
        print(f"src.publish: refused: {error}", file=sys.stderr)
        return 1

    manifest = result["manifest"]
    print(f"site/ published: {len(manifest['files'])} file(s), commit {manifest['code_commit']}")
    print(f"receipt: {result['receipt']['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

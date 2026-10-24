"""The publication gate: ``analysis_runs`` records -> a verified ``site/``.

The gate assembles a ``site/`` directory (the built ``web/`` plus its
``data/v1/`` payload) and signs it with ``publication_manifest.json`` — a
list of every file's SHA-256/size, the code commit, each contract's own
hash, and the current analysis-manifest entries.

Every step below reuses existing functions (the Analysis Agent lifecycle and
``src/web_export``) and never reimplements approval, verification or export logic:

1. ``src.analysis_agent.lifecycle.consumer_payload``/``verified_inputs`` —
   the fail-closed handoff — verify each
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
4. Immediately before the swap, every record is re-verified a second time
   under the ledger's writer lock, and the lock is held through the swap
   itself (see ``verify_records``/``_verify_under_lock`` and ``publish()``):
   step 1's initial check runs *outside* any lock the export/npm-build
   steps hold, so a revocation racing those (slow, I/O-bound) steps is a
   real possibility, not a theoretical one; this second, locked check is
   what actually closes it, not the first.
5. The manifest (``src/publish/manifest.py``) is written into a fresh
   ``site.tmp-*`` directory (a unique ``tempfile.mkdtemp`` per run), which
   then atomically swaps for ``site/`` (tempfile + rename) while the lock from step 4 is still held.
6. An intent/published receipt, hashing the manifest, is written to
   ``analysis_runs/publications/`` (local, gitignored).

Never writes to the approval ledger, never approves/revokes/records
anything.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

from src.analysis_agent import lifecycle as flow
from src.config import PATHS
from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.flights import build_flight_payload
from src.dashboard.market import build_market_payload
from src.web_export import analysis as analysis_export
from src.web_export.executive import export_executive
from src.web_export.flights import export_flights
from src.web_export.inputs import MissingWebInput
from src.web_export.market import export_market
from src.web_export.news import export_news
from src.web_export.privacy import PrivacyViolation, check_privacy, load_privacy_rules
from src.web_export.schemas import ANALYSIS_SCHEMA
from src.web_export.writer import write_json

from . import manifest as manifest_mod
from . import receipts as receipt_mod
from .records import (
    ANALYSIS_MANIFEST_FIELDS as ANALYSIS_MANIFEST_FIELDS,
)
from .records import (
    PublicationRefused as PublicationRefused,
)
from .records import (
    _analysis_manifest_entry as _analysis_manifest_entry,
)
from .records import (
    _reject_duplicate_periods as _reject_duplicate_periods,
)
from .records import (
    load_records as load_records,
)

WEB_DIR = PATHS.root / "web"
WEB_DATA_V1 = WEB_DIR / "public" / "data" / "v1"
WEB_DIST = WEB_DIR / "dist"
PUBLICATIONS_ROOT = PATHS.root / "analysis_runs" / "publications"


def _trusted_site_commit(root: Path, trusted_ref: str = "origin/master") -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{trusted_ref}^{{commit}}"],
        cwd=Path(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise PublicationRefused(f"trusted site base {trusted_ref!r} is unavailable")
    return result.stdout.strip()


def require_trusted_site_baseline(
    site_dir: Path,
    *,
    root: Path = PATHS.root,
    trusted_ref: str = "origin/master",
    trusted_commit: str | None = None,
) -> None:
    """Require an unchanged, tracked site from the trusted published base.

    A self-consistent manifest is not enough: an edited payload could be
    paired with a freshly rebuilt manifest. Comparing the entire tracked site
    with the trusted base binds every reused data hash to the committed public
    snapshot before a UI-only build.
    """

    root = Path(root).resolve()
    site_dir = Path(site_dir).resolve()
    try:
        relative = site_dir.relative_to(root)
    except ValueError as error:
        raise PublicationRefused("UI-only publication must target site/ inside the code checkout") from error
    if relative.as_posix() != "site":
        raise PublicationRefused("UI-only publication must target the tracked site/ directory")

    ref_check = subprocess.run(
        ["git", "rev-parse", "--verify", f"{trusted_ref}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if ref_check.returncode != 0:
        raise PublicationRefused(f"trusted site base {trusted_ref!r} is unavailable")
    resolved_commit = ref_check.stdout.strip()
    if trusted_commit is not None and resolved_commit != trusted_commit:
        raise PublicationRefused(f"trusted site base {trusted_ref!r} changed during publication")
    trusted_commit = trusted_commit or resolved_commit
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "site"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise PublicationRefused("site/ has uncommitted or untracked files; cannot reuse it as trusted data")
    diff = subprocess.run(
        ["git", "diff", "--quiet", trusted_commit, "--", "site"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        raise PublicationRefused(f"site/ differs from the trusted published base {trusted_ref!r}")


def _verify_under_lock(records: list[dict[str, Any]], root: Path) -> list[tuple[Any, Any, Any, Any]]:
    """The actual (record, authorized, package, calculations) check, assuming
    the caller already holds ``flow.writer(root)``. Not exported: callers use
    ``verify_records`` (acquires its own lock) for a standalone check, or
    ``publish()``'s second call (already inside its own ``flow.writer``
    block) for the pre-swap re-check — never both at once, since
    ``flow.writer`` is not reentrant."""

    entries = []
    for record in records:
        authorized = flow.consumer_payload(record, root)
        package, calculations, _ = flow.verified_inputs(record)
        expected = manifest_mod.analysis_identity(record["draft"])
        if (
            manifest_mod.analysis_identity(authorized) != expected
            or authorized.get("version") != record["version"]
        ):
            raise ValueError("Authorized analysis entity/period/version differs from its record")
        if "entity_key" in record["draft"]:
            if (
                authorized.get("entity_key") != expected[0]
                or package.get("entity_key") != expected[0]
                or package.get("period_id") != expected[1]
            ):
                raise ValueError("Entity record, authorization and evidence identities differ")
        entries.append((record, authorized, package, calculations))
    return entries


def verify_records(records: list[dict[str, Any]], root: Path = flow.ROOT) -> list[dict[str, Any]]:
    """Return, per record, (authorized, package, calculations) under the
    ledger's writer lock — the fail-closed lifecycle calls. Raises PublicationRefused if any record
    is not exactly, currently approved.

    This on its own does **not** close the publish-time race: ``publish()``
    calls this once up front, then spends real wall-clock time on
    ``export_data``/``build_web`` (schema/privacy checks, an ``npm run
    build``) with the lock released, during which a human can revoke the
    approval this call just confirmed. ``publish()`` calls
    ``_verify_under_lock`` a second time, under a fresh lock held through the
    swap, immediately before replacing ``out_dir`` -- that second call, not
    this one, is what actually makes the race impossible."""

    root = Path(root)
    try:
        with flow.writer(root):
            return _verify_under_lock(records, root)
    except ValueError as error:
        raise PublicationRefused(f"record failed verification/approval: {error}") from error


def _analysis_payload(
    record: dict[str, Any], authorized: dict[str, Any], package, calculations
) -> dict[str, Any]:
    """Same shape src.web_export.analysis.export_period writes, built from
    the (record, authorized, package, calculations) this gate already holds
    from verify_records, instead of re-querying the ledger a second time."""

    return analysis_export.publication_payload(record, authorized, package, calculations)


def export_data(entries: list[tuple[Any, Any, Any, Any]], out_dir: Path) -> None:
    """Write flights/executive/market (every period) and analysis (only the given,
    approved periods) v1 payloads under out_dir."""

    try:
        export_flights(build_flight_payload(), out_dir)
        export_executive(build_executive_payload(), out_dir)
        export_market(build_market_payload(), out_dir)
        export_news(out_dir)
    except MissingWebInput as error:
        raise PublicationRefused(str(error)) from error

    # A public approval receipt is an explicit opt-in. No receipt means the
    # existing publication payload is byte-for-byte unaffected by F2.3.
    receipt = PATHS.root / "config/chat/business-metrics-approval-receipt.json"
    if receipt.is_file():
        from src.web_export.business_metrics import (
            export_approved_business_metrics,
        )

        try:
            export_approved_business_metrics(
                PATHS.root / "config/chat/business-metrics-proposal.json",
                PATHS.root / "config/chat/metrics-candidates.json",
                receipt,
                out_dir,
            )
        except (OSError, ValueError) as error:
            raise PublicationRefused(f"business metric approval rejected: {error}") from error

    validator = Draft202012Validator(ANALYSIS_SCHEMA)
    rules = load_privacy_rules()
    seen = set()
    for record, authorized, package, calculations in entries:
        period_id = authorized["period_id"]
        payload = _analysis_payload(record, authorized, package, calculations)
        identity = manifest_mod.analysis_identity(payload)
        if (
            identity != manifest_mod.analysis_identity(record["draft"])
            or payload["version"] != record["version"]
        ):
            raise PublicationRefused("Exported analysis entity/period/version differs from its record")
        if identity in seen:
            raise PublicationRefused(f"Multiple analysis payloads for entity/period {identity}")
        seen.add(identity)
        errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
        if errors:
            raise PublicationRefused(f"analysis/{period_id}.json does not match its schema: {errors[:5]}")
        try:
            check_privacy(payload, rules)
        except PrivacyViolation as error:
            raise PublicationRefused(f"analysis/{period_id}.json: {error}") from error
        write_json(out_dir / manifest_mod.analysis_relative_path(payload), payload)


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


def assemble_site(
    dist_dir: Path,
    analysis_manifest: list[dict[str, str]],
    out_dir: Path,
    *,
    contracts: dict[str, str] | None = None,
    validate_candidate: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """Copy dist_dir into a fresh temp directory, write the manifest into it,
    and atomically swap it in for out_dir. Returns the written manifest."""

    out_dir = Path(out_dir).resolve()
    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=parent, prefix=out_dir.name + ".tmp-"))
    try:
        shutil.rmtree(tmp_dir)
        shutil.copytree(dist_dir, tmp_dir)
        manifest = manifest_mod.build_manifest(tmp_dir, analysis_manifest, contracts=contracts)
        manifest_mod.write_manifest(tmp_dir, manifest)
        if validate_candidate is not None:
            validate_candidate(tmp_dir)

        previous = None
        if out_dir.exists():
            previous = parent / (
                out_dir.name + ".prev-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            )
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


def write_receipt(
    manifest: dict[str, Any], authorized: list[dict[str, Any]], out_dir: Path, *, root: Path = flow.ROOT
) -> dict[str, Any]:
    """Write paired normal and lifecycle receipts without changing this API."""
    store = PUBLICATIONS_ROOT if Path(root) == Path(flow.ROOT) else Path(root).parent / "publications"
    return receipt_mod.write_receipt(manifest, authorized, out_dir, root=root, store=store)


def publish(
    record_paths: list[Path],
    out_dir: Path,
    *,
    root: Path = flow.ROOT,
    web_dir: Path = WEB_DIR,
    web_data_v1: Path = WEB_DATA_V1,
) -> dict[str, Any]:
    """Verify every record, export v1 data, build web/, re-verify and swap in
    site/, and write the publications receipt. Raises PublicationRefused
    (nothing written to out_dir) on any failure -- including a revocation
    discovered by the second, pre-swap verification below, after export/build
    already ran."""

    root = Path(root)
    # Deliberately not `root` (that's the analysis ledger root, which tests
    # and CI point at an unrelated tmp directory): the build-inputs check
    # always looks at the actual code checkout, PATHS.root.
    try:
        manifest_mod.refuse_if_build_inputs_dirty()
    except RuntimeError as error:
        raise PublicationRefused(str(error)) from error

    records = load_records(record_paths)
    if not records:
        raise PublicationRefused("no --record given; refuse to publish an empty analysis manifest")

    entries = verify_records(records, root=root)

    with tempfile.TemporaryDirectory(prefix="publish-data-") as tmp:
        export_data(entries, Path(tmp))
        # web/public/data/v1 is local/gitignored dev scratch (see .gitignore);
        # clearing it first guarantees the build sees exactly this run's
        # periods, not stale files from an earlier `web_export` run.
        if web_data_v1.exists():
            shutil.rmtree(web_data_v1)
        shutil.copytree(tmp, web_data_v1)

    dist_dir = build_web(web_dir)

    # Re-verify every record immediately before the swap, under the same
    # ledger lock held through the swap itself: export_data/build_web above
    # ran with the lock released (an npm build is slow; holding a ledger
    # writer lock across it would block approvals/revocations for no
    # reason), so a revocation could have landed since the first check.
    # This second check, not the first, is what makes the race impossible --
    # see verify_records' docstring.
    # The built payload came from the first check's authorizations, so the
    # manifest must too; a revoke-and-re-approve during the build would pass
    # the second check with a new approval_event/audit_hash that no longer
    # matches what dist_dir contains, so any change aborts instead.
    authorized = [e[1] for e in entries]
    analysis_manifest = [_analysis_manifest_entry(e) for e in authorized]
    try:
        with flow.writer(root):
            current = [_analysis_manifest_entry(e[1]) for e in _verify_under_lock(records, root)]
            if current != analysis_manifest:
                raise ValueError("approval changed while the site was being built; rerun the publication")
            manifest = assemble_site(dist_dir, analysis_manifest, out_dir)
    except ValueError as error:
        raise PublicationRefused(
            f"record failed verification/approval just before publish (nothing swapped in): {error}"
        ) from error

    receipt = write_receipt(manifest, authorized, out_dir, root=root)
    return {"manifest": manifest, "receipt": receipt}


def publish_ui_only(
    record_paths: list[Path],
    out_dir: Path,
    *,
    root: Path = flow.ROOT,
    web_dir: Path = WEB_DIR,
    web_data_v1: Path = WEB_DATA_V1,
) -> dict[str, Any]:
    """Rebuild the frontend while retaining the exact currently published data.

    This path is only for interface-only changes. It verifies the existing site,
    pins its analysis manifest to the supplied currently approved records,
    copies its signed ``data/v1`` files into the frontend build, and refuses to
    swap if any output data hash changes. Approval is checked before the build
    and again under the ledger lock immediately before the atomic site swap.
    """

    root = Path(root)
    out_dir = Path(out_dir).resolve()
    try:
        manifest_mod.refuse_if_build_inputs_dirty()
    except RuntimeError as error:
        raise PublicationRefused(f"uncommitted UI build inputs: {error}") from error

    records = load_records(record_paths)
    if not records:
        raise PublicationRefused("no --record given; refuse to publish an empty analysis manifest")
    trusted_site_commit = _trusted_site_commit(PATHS.root)
    require_trusted_site_baseline(out_dir, root=PATHS.root, trusted_commit=trusted_site_commit)

    from .verify import verify_site

    site_problems = verify_site(out_dir)
    if site_problems:
        raise PublicationRefused(f"existing site is not valid for UI-only publication: {site_problems[:5]}")
    current_manifest = manifest_mod.load_manifest(out_dir)
    from .approval_cohorts import verify_approval_cohorts

    try:
        with flow.writer(root):
            verified = verify_approval_cohorts(
                record_paths, PATHS.root, trusted_site_commit, current_manifest, root
            )
    except ValueError as error:
        raise PublicationRefused(f"existing UI-only approval cohort failed verification: {error}") from error
    authorized = verified["authorized"]
    analysis_manifest = [_analysis_manifest_entry(entry) for entry in authorized]
    if current_manifest["analysis_manifest"] != sorted(analysis_manifest, key=manifest_mod.analysis_sort_key):
        raise PublicationRefused("existing site analysis manifest does not match the exact approved records")

    source_data = {
        item["path"]: (item["sha256"], item["bytes"])
        for item in current_manifest["files"]
        if item["path"].startswith("data/v1/")
    }
    source_dir = out_dir / "data/v1"
    if not source_data or not source_dir.is_dir():
        raise PublicationRefused("existing site has no published data/v1 payload to preserve")
    if Path(web_data_v1).exists():
        shutil.rmtree(web_data_v1)
    Path(web_data_v1).parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, web_data_v1)

    dist_dir = build_web(web_dir)
    built_data = {
        item["path"]: (item["sha256"], item["bytes"])
        for item in manifest_mod.file_entries(dist_dir)
        if item["path"].startswith("data/v1/")
    }
    if built_data != source_data:
        raise PublicationRefused("UI build changed the existing public data/v1 files")

    def validate_candidate(candidate: Path) -> None:
        candidate_data = {
            item["path"]: (item["sha256"], item["bytes"])
            for item in manifest_mod.file_entries(candidate)
            if item["path"].startswith("data/v1/")
        }
        if candidate_data != source_data:
            raise ValueError("UI candidate changed the existing public data/v1 files")
        problems = verify_site(candidate)
        if problems:
            raise ValueError(f"UI candidate failed verification: {problems[:5]}")

    try:
        with flow.writer(root):
            # Recheck the trusted payload at the last possible moment too;
            # the frontend build runs outside the ledger lock and the site
            # directory is not itself protected by that lock.
            require_trusted_site_baseline(
                out_dir,
                root=PATHS.root,
                trusted_commit=trusted_site_commit,
            )
            current = verify_approval_cohorts(
                record_paths, PATHS.root, trusted_site_commit, current_manifest, root
            )
            if current != verified:
                raise ValueError("approval changed while the UI was being built; rerun the publication")
            manifest = assemble_site(
                dist_dir,
                analysis_manifest,
                out_dir,
                contracts=current_manifest["contracts"],
                validate_candidate=validate_candidate,
            )
    except ValueError as error:
        raise PublicationRefused(
            f"record failed verification/approval just before UI-only publish (nothing swapped in): {error}"
        ) from error

    receipt = write_receipt(manifest, authorized, out_dir, root=root)
    return {"manifest": manifest, "receipt": receipt}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, action="append", default=[], dest="records")
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    publish_modes = parser.add_mutually_exclusive_group()
    publish_modes.add_argument(
        "--editorial-only", action="store_true",
        help="publish only the approved reading, inheriting remotely verified historical bytes",
    )
    publish_modes.add_argument(
        "--quarterly-only", action="store_true",
        help="add the audited Aeromexico 3Q26 financial release, preserving existing datasets and theses",
    )
    publish_modes.add_argument(
        "--ui-only",
        action="store_true",
        help="rebuild the frontend while preserving the exact existing public data and analysis manifest",
    )
    publish_modes.add_argument(
        "--preserve-published-data", action="store_true",
        help=("rebuild the flight presentation while preserving every trusted public data byte "
              "and approval identity"),
    )
    publish_modes.add_argument(
        "--flights-only", action="store_true",
        help=("publish the accepted Q2 flight projection while preserving every non-flight payload "
              "and thesis identity"),
    )
    publish_modes.add_argument(
        "--business-metrics-only",
        action="store_true",
        help="add only the separately approved business-metrics pair to the trusted published data baseline",
    )
    args = parser.parse_args(argv)

    try:
        if args.editorial_only:
            from .editorial import publish_editorial
            try:
                result = publish_editorial(args.records, args.out)
            except (ValueError, OSError, subprocess.CalledProcessError) as error:
                raise PublicationRefused(f"editorial publication rejected: {error}") from error
        elif args.quarterly_only:
            from .quarterly_overlay import publish_quarterly
            result = publish_quarterly(args.records, args.out)
        elif args.flights_only:
            from .flight_overlay import publish_flights_only

            result = publish_flights_only(args.records, args.out)
        elif args.preserve_published_data:
            from .frozen_data import publish_preserved_data

            result = publish_preserved_data(args.records, args.out)
        elif args.business_metrics_only:
            from .financial_overlay import publish_business_metrics_only

            result = publish_business_metrics_only(args.records, args.out)
        elif args.ui_only:
            result = publish_ui_only(args.records, args.out)
        else:
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

"""Fresh V2 witness with bounded retries of known transient transport failures.

No retry can change the expected bytes, their SHA, origin, method or baseline.
The original producer's V1 witness remains unchanged in historical replay.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import editorial as transport
from . import manifest as manifests
from .afac_history_contract import relative_name, sha, site_tree

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
RETRY_AFTER_CAP_SECONDS = 10.0
REQUEST_TIMEOUT_SECONDS = 45
LOG = logging.getLogger(__name__)


def retryable(error):
    if isinstance(error, HTTPError):
        return error.code in RETRY_STATUSES
    if isinstance(error, URLError):
        return isinstance(error.reason, (TimeoutError, socket.timeout, IncompleteRead))
    return isinstance(error, (TimeoutError, socket.timeout, IncompleteRead))


def retry_delay(error, attempt):
    delay = min(2.0 ** (attempt - 1), 4.0)
    value = error.headers.get("Retry-After") if isinstance(error, HTTPError) and error.headers else None
    if value:
        try:
            seconds = float(value)
        except ValueError:
            try:
                at = parsedate_to_datetime(value)
                seconds = (at - datetime.now(UTC)).total_seconds() if at.tzinfo else 0.0
            except (ValueError, TypeError, OverflowError):
                seconds = 0.0
        delay = max(delay, min(max(0.0, seconds), RETRY_AFTER_CAP_SECONDS))
    return min(delay, RETRY_AFTER_CAP_SECONDS)


def get_verified(name, expected):
    """GET exactly one trusted Pages path; a mismatching HTTP200 is fatal."""
    name = relative_name(name)
    url = transport.ORIGIN + "/" + quote(name, safe="/")
    request = Request(url, method="GET", headers={"User-Agent": "AirlineTracker-native-history-witness-v2"})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                if response.geturl() != url or response.status != 200:
                    raise ValueError("Witness origin/method/HTTP200 contract changed")
                raw = response.read()
            if len(raw) != len(expected) or sha(raw) != sha(expected):
                raise ValueError(f"Served HTTP200 differs from its unchanged expected size/SHA: {name}")
            return raw
        except (HTTPError, URLError, TimeoutError, IncompleteRead) as error:
            delay = retry_delay(error, attempt)
            if isinstance(error, HTTPError):
                error.close()
            if not retryable(error) or attempt == MAX_ATTEMPTS:
                raise ValueError(
                    f"Native witness GET failed closed after {attempt} attempt(s): {name}"
                ) from error
            LOG.warning("Transient native witness GET %s, bounded attempt %s/%s", name, attempt, MAX_ATTEMPTS)
            time.sleep(delay)
    raise AssertionError("Unreachable bounded witness loop")


def successful_deployment(repo, baseline, manifest_raw):
    rows = json.loads(
        subprocess.check_output(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "pages.yml",
                "--branch",
                "master",
                "--status",
                "success",
                "--limit",
                "30",
                "--json",
                "databaseId,headSha",
            ],
            cwd=repo,
        )
    )
    for row in rows:
        commit = row.get("headSha")
        if not isinstance(commit, str) or len(commit) != 40:
            continue
        try:
            transport._git(repo, "merge-base", "--is-ancestor", commit, baseline)
            same = transport._git(repo, "show", f"{commit}:site/publication_manifest.json") == manifest_raw
            unchanged = not transport._git(repo, "diff", "--name-only", commit, baseline, "--", "site")
        except subprocess.CalledProcessError:
            continue
        if same and unchanged and type(row.get("databaseId")) is int and row["databaseId"] > 0:
            return row
    raise ValueError("No successful deployment of the exact physically served baseline")


def witness_remote(repo, scope):
    head = manifests.current_commit(repo)
    remote = transport._git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
    if remote != scope["baseline_commit"]:
        raise ValueError("Remote base moved before fresh V2 witness")
    manifest, raw, files = site_tree(repo, remote)
    if sha(raw) != scope["baseline_manifest_sha256"]:
        raise ValueError("V2 witness baseline manifest differs from its exact inspected identity")
    deployment = successful_deployment(repo, remote, raw)
    get_verified("publication_manifest.json", raw)
    executor = ThreadPoolExecutor(max_workers=8)
    futures = [executor.submit(get_verified, name, expected) for name, expected in files.items()]
    try:
        for future in as_completed(futures):
            future.result()
    except BaseException:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    get_verified("publication_manifest.json", raw)
    if (
        transport._git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0] != remote
        or manifests.current_commit(repo) != head
    ):
        raise ValueError("HEAD or remote manifest base moved during fresh V2 witness")
    return {
        "baseline_commit": remote,
        "manifest_sha256": sha(raw),
        "files_verified": len(manifest["files"]),
        "deployment_commit": deployment["headSha"],
        "deployment_run": deployment["databaseId"],
        "origin": transport.ORIGIN,
        "verified_at": datetime.now(UTC).isoformat(),
    }

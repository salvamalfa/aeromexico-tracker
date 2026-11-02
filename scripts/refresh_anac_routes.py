"""Acquire and certify one complete public ANAC original in an isolated workspace.

The ordinary single GET may be truncated by the public server. Reuse its
version-bound range downloader, retain the exact assembled original, then run
the ordinary retained-product certifier. Never modifies active Gold or site/.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

import httpx

from src.common.http import SourceHttpClient
from src.common.storage import save_bronze
from src.ingest.international_routes import ANAC_URL, anac_content
from src.source_updates.authorities import json_objects
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.retained import retain, run

MAX_BYTES = 250_000_000
MAX_REQUESTS = 187  # 1 initial range + at most 62 further ranges * 3 attempts.


class RangeClient:
    def __init__(self, client):
        self.client, self.calls, self.lock = client, [], Lock()

    def get(self, url, **kwargs):
        if url != ANAC_URL:
            raise ValueError("ANAC range request escaped the exact public original")
        with self.lock:
            if len(self.calls) >= MAX_REQUESTS:
                raise ValueError("ANAC range request bound exceeded")
            entry = {
                "range": kwargs.get("headers", {}).get("Range"),
                "started_at": datetime.now(UTC).isoformat(),
            }
            self.calls.append(entry)
        try:
            response = self.client.request("GET", url, follow_redirects=False, **kwargs)
            if response.status_code not in {200, 206}:
                raise ValueError("ANAC range response is neither a complete original nor a range")
            entry.update(
                http_status=response.status_code,
                bytes=len(response.content),
                content_range=response.headers.get("content-range"),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                sha256=hashlib.sha256(response.content).hexdigest(),
            )
            return response
        except httpx.HTTPError as exc:
            entry["error_type"] = type(exc).__name__
            raise


def refresh(workspace, *, execute=False, resume=False):
    workspace = safe_workspace(workspace)
    plan = dict(
        product="anac",
        source_url=ANAC_URL,
        maximum_bytes=MAX_BYTES,
        maximum_http_requests=MAX_REQUESTS,
        paid_requests=0,
        destinations=[str(workspace / "collection"), str(workspace / "candidate")],
        activation="none",
        publication="not_authorized",
    )
    if not execute:
        return {**plan, "status": "dry_run"}
    collection, candidate = workspace / "collection", workspace / "candidate"
    if workspace.exists() and any(workspace.iterdir()):
        previous = collection / "receipt.json"
        if (
            not resume
            or not previous.is_file()
            or json.loads(previous.read_bytes()).get("status") != "incomplete"
            or (collection / "data/bronze").exists()
            or candidate.exists()
        ):
            raise ValueError(
                "Use a new workspace, or explicitly resume an incomplete acquisition "
                "without Bronze/candidate outputs"
            )
        previous.rename(collection / ("attempt-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"))
    receipt = {
        **plan,
        "started_at": datetime.now(UTC).isoformat(),
        "new_source_capture": True,
        "status": "incomplete",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with writer(workspace):
        collection.mkdir(parents=True, exist_ok=True)
        receipt["cached_ranges_before_acquisition"] = {
            str(path.relative_to(collection)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (collection / "ranges").rglob("*.part")
        }
        with SourceHttpClient("default", timeout_seconds=120, max_attempts=1) as client:
            bounded = RangeClient(client)
            try:
                content, headers = anac_content(
                    bounded, cache_root=collection / "ranges", max_bytes=MAX_BYTES
                )
                latest, rows = None, 0
                for _, row in json_objects(content):
                    period = f"{int(row['ANO']):04d}M{int(row['MES']):02d}"
                    latest, rows = max(latest or period, period), rows + 1
                path = save_bronze(
                    content,
                    "anac",
                    "complete_2021_2030",
                    latest,
                    "json",
                    ANAC_URL,
                    "httpx",
                    bronze_root=collection / "data/bronze",
                    http_status=bounded.calls[0]["http_status"],
                    content_type=headers.get("content-type", "application/json"),
                    notes=(
                        "Complete contiguous original, one ETag/Last-Modified; "
                        "range receipt retained; source rows not filtered"
                    ),
                )
                receipt.update(
                    status="collected_unvalidated",
                    source_file=path.relative_to(collection / "data/bronze").as_posix(),
                    source_sha256=hashlib.sha256(content).hexdigest(),
                    bytes=len(content),
                    source_rows=rows,
                    latest_month_inside_original=latest,
                )
            finally:
                receipt.update(http_requests=bounded.calls, finished_at=datetime.now(UTC).isoformat())
                (collection / "receipt.json").write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
    original = {"json": receipt["source_file"]}
    retain(candidate, collection / "data/bronze", "anac", original)
    retained = retain(candidate, collection / "data/bronze", "anac", original, execute=True)
    cutoff = datetime.now(UTC).isoformat()
    run(candidate, "anac", latest, cutoff, retained["run_id"])
    result = run(candidate, "anac", latest, cutoff, retained["run_id"], execute=True)
    run(candidate, "anac", latest, cutoff, retained["run_id"], check=True)
    result = dict(
        status="captured_certified_replayed",
        product="anac",
        period=latest,
        native_rows=rows,
        selected_rows=result["rows"],
        source_capture=receipt,
        candidate_receipt=str(candidate / "receipts" / f"certified-anac-{latest}.json"),
        activation="none",
        publication="not_authorized",
    )
    (workspace / "receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume only an incomplete range acquisition; preserve the prior attempt",
    )
    args = parser.parse_args()
    result = refresh(args.workspace, execute=args.execute, resume=args.resume)
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "source_capture"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()

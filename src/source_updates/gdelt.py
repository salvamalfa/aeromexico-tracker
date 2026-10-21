"""Bounded GDELT observation candidates, separate from publication-month news."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode

from src.ingest.news.rss_gdelt import GDELT_API_URL, GDELT_QUERY_PARAMS
from src.pipeline.offline import block_network
from src.source_updates.calendar import ZONE, local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.news import canonical_url
from src.source_updates.primary_review import original

VERSION = "gdelt_observed_metadata_v1"
OUTPUTS = ("silver/source_products/gdelt_metadata.json", "gold/fact_gdelt_observed_metadata.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe(period: str, as_of: str) -> dict:
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Choose one explicit observation month")
    end = period_end(period)
    if end >= local_time(as_of).date():
        raise ValueError("Observation month must be closed")
    start = datetime.combine(end.replace(day=1), time.min, tzinfo=ZONE)
    stop = datetime.combine(end + timedelta(days=1), time.min, tzinfo=ZONE)
    params = dict(
        GDELT_QUERY_PARAMS,
        startdatetime=start.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
        enddatetime=(stop.astimezone(UTC) - timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
    )
    return {
        "version": 1,
        "items": [
            {
                "id": "gdelt",
                "product": "gdelt",
                "source_system": "gdelt",
                "entity": "aeromexico_articles",
                "period": period,
                "purpose": "data",
                "url": GDELT_API_URL + "?" + urlencode(params),
                "extension": "json",
                "mode": "get",
                "relative_dir": "news/gdelt",
            }
        ],
        "bounds": {"base_requests": 1, "maximum_http_requests": 5, "maximum_rows": 250, "paid_requests": 0},
        "date_basis": "aggregator_first_seen_not_publication",
        "complete_month_certified": False,
        "activation": "none",
    }


def normalize(payload: dict, period: str, source: dict, as_of: str) -> tuple[dict, dict]:
    recipe(period, as_of)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"articles"}
        or not isinstance(payload["articles"], list)
    ):
        raise ValueError("Expected GDELT articles array, never an HTTP-200 error document")
    articles = payload["articles"]
    if len(articles) > 250:
        raise ValueError("Response exceeds selected bounded maximum")
    captured = local_time(source["downloaded_at"])
    if captured > local_time(as_of):
        raise ValueError("Source capture is after the requested cutoff")
    grouped = {}
    for index, item in enumerate(articles):
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) and item[k].strip() for k in ("url", "title", "seendate")
        ):
            raise ValueError("Missing URL, title or aggregator observation date")
        if not re.fullmatch(r"\d{8}T\d{6}Z", item["seendate"]):
            raise ValueError("Unknown GDELT observation-date format")
        seen = datetime.strptime(item["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if f"{local_time(seen.isoformat()):%YM%m}" != period or seen > captured:
            raise ValueError("Observation escaped requested Mexico month or is after capture")
        url = canonical_url(item["url"])
        key = (url, seen.isoformat())
        locator = f"/articles/{index}"
        if key not in grouped:
            record_id = hashlib.sha256(
                json.dumps([source["sha256"], url, key[1]], ensure_ascii=False).encode()
            ).hexdigest()
            grouped[key] = {
                "record_id": record_id,
                "url": url,
                "first_seen_at": key[1],
                "published_at": None,
                "event_date": None,
                "source_file": source["source_file"],
                "source_hash": source["sha256"],
                "source_system": "gdelt",
                "parser_version": VERSION,
                "contributors": [],
                "agent_eligible": False,
            }
        # Keep source variants and every locator without downloading articles/images.
        metadata = {
            k: item.get(k)
            for k in ("url", "title", "seendate", "domain", "language", "sourcecountry", "tone", "themes")
        }
        grouped[key]["contributors"].append({"source_locator": locator, "metadata": metadata})
    output = {
        "version": VERSION,
        "observation_period": period,
        "date_basis": "aggregator_first_seen_not_publication",
        "rows": list(grouped.values()),
        "activation": "none",
        "publication": "not_authorized",
        "complete_month_certified": False,
        "agent_eligible": False,
    }
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "contracts/source_updates/gdelt-observed-metadata.schema.json").read_text())
    Draft202012Validator(schema).validate(output)
    return output, {
        "raw_rows": len(articles),
        "rows": len(grouped),
        "duplicate_contributions": len(articles) - len(grouped),
        "result_cap_reached": len(articles) == 250,
        "days_observed": sorted(
            {local_time(row["first_seen_at"]).date().isoformat() for row in grouped.values()}
        ),
        "empty_result_is_not_absence_of_news": True,
        "latest_available_period": None,
        "latest_published_period": None,
        "published_at": None,
        "release_lag_days": None,
        "article_requests": 0,
        "complete_month_certified": False,
    }


def run(workspace: Path, period: str, as_of: str, collection: str, *, execute=False, check=False):
    workspace = safe_workspace(workspace)
    selection = recipe(period, as_of)
    if not re.fullmatch(r"[a-f0-9]{32}", collection):
        raise ValueError("Expected preserved collection receipt ID")
    accepted = workspace / "receipts" / f"gdelt-{period}.json"
    plan = dict(
        mode="dry_run",
        outputs=list(OUTPUTS),
        network_requests=0,
        paid_requests=0,
        activation="none",
        publication="not_authorized",
    )
    if not execute and not check:
        return plan
    allowed = {workspace / "data" / name for name in OUTPUTS}
    if any(
        p not in allowed for layer in ("silver", "gold") for p in (workspace / "data" / layer).rglob("*.*")
    ):
        raise ValueError("Use an isolated GDELT candidate")
    if execute and (accepted.exists() or any(p.exists() for p in allowed)):
        raise ValueError("Candidate is immutable; use a new workspace")
    receipt_path = workspace / "receipts" / f"collection-{collection}.json"
    with block_network():
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt.get("run_id") != collection
            or receipt.get("mode") != "collection"
            or receipt.get("status") != "collected_unvalidated"
            or len(receipt.get("items", [])) != 1
            or receipt.get("paid_requests") != 0
            or receipt.get("activation") != "none"
            or receipt.get("publication") != "not_authorized"
        ):
            raise ValueError("No complete successful GDELT source collection; preserve failed receipt")
        item = receipt["items"][0]
        expected = selection["items"][0]
        if (
            item.get("product") != "gdelt"
            or item.get("id") != expected["id"]
            or item.get("requested_period") != period
            or item.get("source_url") != expected["url"]
            or item.get("status") != "collected_unvalidated"
            or item.get("http_status") != 200
        ):
            raise ValueError("GDELT collection query/product/period/HTTP identity mismatch")
        manifest = workspace / "data/bronze/_manifest.jsonl"
        records = [json.loads(line) for line in manifest.read_text().splitlines()]
        if len(records) != 1:
            raise ValueError("Use one selected GDELT original")
        source = records[0]
        if (
            source.get("source_system") != "gdelt"
            or source.get("source_url") != expected["url"]
            or source.get("source_file") != item.get("source_file")
            or source.get("sha256") != item.get("sha256")
            or source.get("bytes") != item.get("bytes")
            or source.get("http_status") != 200
            or source.get("download_method") != "httpx"
            or source.get("logical_key") != f"gdelt|{expected['entity']}|{period}|json"
        ):
            raise ValueError("GDELT collection and original identity differ")
        path = original(workspace / "data/bronze", source)
        sidecar = json.loads(Path(str(path) + ".meta.json").read_text())
        if any(sidecar.get(key) != source[key] for key in ("logical_key", "download_method")):
            raise ValueError("GDELT sidecar collection identity differs")
        output, details = normalize(json.loads(path.read_text()), period, source, as_of)
    encoded = (json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    hashes = {name: hashlib.sha256(encoded).hexdigest() for name in OUTPUTS}
    result = dict(
        plan,
        **details,
        mode="offline_check" if check else "candidate",
        status="checks_passed" if details["rows"] else "empty_result_unproven_coverage",
        collection_run_id=collection,
        collection_sha256=digest(receipt_path),
        original_sha256=source["sha256"],
        output_sha256=hashes,
        observation_period=period,
        effective_as_of=as_of,
        code_sha256=digest(Path(__file__)),
        contract_sha256=digest(ROOT / "contracts/source_updates/gdelt-observed-metadata.schema.json"),
        lineage="every_contribution_exact_JSON_pointer_and_Bronze_file_SHA256",
        revision_comparison="not_compared_no_baseline",
        agent_eligible=False,
    )
    if check:
        prior = json.loads(accepted.read_text())
        # Replay verifies the frozen receipt's meaning as well as its hashes.
        # A new cutoff is a new review, not an in-place rewrite of acceptance.
        expected_receipt = dict(result, mode="candidate")
        if json.dumps(prior, sort_keys=True, allow_nan=False) != json.dumps(
            expected_receipt, sort_keys=True, allow_nan=False
        ):
            raise ValueError("Accepted GDELT receipt/inputs/code/contract changed")
        if any(path.read_bytes() != encoded for path in allowed):
            raise ValueError("GDELT candidate differs from source replay")
        return result
    with writer(workspace):
        if accepted.exists() or any(p.exists() for p in allowed):
            raise ValueError("Candidate changed before writer lock")
        for name in OUTPUTS:
            path = workspace / "data" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded)
        accepted.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["recipe", "certify"])
    parser.add_argument("--period", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--collection")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "recipe":
            result = recipe(args.period, args.as_of)
        else:
            if not args.workspace or not args.collection:
                raise ValueError("Certification requires workspace and collection receipt ID")
            result = run(
                args.workspace,
                args.period,
                args.as_of,
                args.collection,
                execute=args.execute,
                check=args.check,
            )
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps(dict(status="blocked", reason=str(exc), activation="none")))
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prepare monthly editorial candidates from recorded native web/publisher readings.

This offline adapter verifies the recorded review, not original publisher bytes
or exhaustive coverage. It never searches the web itself or approves publication.
"""

import argparse
import hashlib
import json
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from src.conversational_analytics.evidence_index import candidate_content_sha256
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end
from src.source_updates.collection import safe_workspace, validate_url, writer
from src.source_updates.news import canonical_url
from src.source_updates.news_cut import candidate_cut

SCHEMA = ROOT / "contracts/source_updates/editorial-news-review.schema.json"
PRIORITY = {k: 1 for k in ("results", "alliance", "regulation", "fleet", "capacity")}
COVERAGE = "Relevant events in recorded monthly searches and publisher readings; not exhaustive coverage"


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def public_url(value):
    host = urlsplit(value).hostname
    try:
        ip_address(host or "")
    except ValueError:
        pass
    else:
        raise ValueError("Editorial publisher URLs require a public DNS name, not an IP literal")
    if (
        not host
        or "." not in host
        or host.replace(".", "").isdigit()
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("Editorial source must reference a public publisher URL")
    validate_url(value, [host])  # Validation only, never a request or a network-policy change.
    return canonical_url(value)


def plan(period, as_of):
    cutoff = local_time(as_of)
    if period_end(period) >= cutoff.date():
        raise ValueError("Editorial task requires the closed month selected by the common calendar")
    month = (
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()[
            int(period[-2:]) - 1
        ]
    )
    return dict(
        id="editorial_news",
        family="news",
        cadence="monthly",
        period=period,
        as_of=as_of,
        status="native_web_review_required",
        calendar="common_source_calendar",
        suggested_searches=[
            f"{name} {month} {period[:4]}"
            for name in ("Aeroméxico", "Volaris", "Viva Aerobus", "aviación México")
        ],
        selection=(
            "Impact and verified relevance, no fixed item quota; "
            "exclude rumors, routine promotions and repeats"
        ),
        sources="Native web search and publisher/official pages; RSS complements discovery; GDELT optional",
        fallback="Verify current official navigation; use the supported browser when a source request fails",
        coverage=COVERAGE,
        network_requests=0,
        scheduled_executions=0,
        activation="none",
        publication="not_authorized",
    )


def prepare(payload):
    try:
        Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=FormatChecker()).validate(payload)
    except ValidationError as exc:
        raise ValueError("Invalid editorial observation contract: " + exc.message) from exc
    plan(payload["period"], payload["as_of"])
    cutoff = local_time(payload["as_of"])
    prefix = payload["period"].replace("M", "-")
    for search in payload["searches"]:
        if local_time(search["checked_at"]) > cutoff or local_time(search["checked_at"]).date() <= period_end(
            payload["period"]
        ):
            raise ValueError("Editorial search occurred after the review cutoff")
    if not any(
        s["outcome"] == "completed" and s["method"] in {"native_web", "browser_ui"}
        for s in payload["searches"]
    ):
        raise ValueError(
            "A completed native web/browser review is required; RSS and failures cannot substitute it"
        )
    for excluded in payload["exclusions"]:
        public_url(excluded["url"])
    if not payload["events"] and not (payload["empty_selection_reason"] or "").strip():
        raise ValueError(
            "An empty editorial selection needs its explicit review reason, not a claim of no news"
        )
    pending = [e for e in payload["exclusions"] if e.get("state") == "pending_verification"]
    if not payload["events"] and pending:
        raise ValueError("Publisher verification is still pending; this is not a reviewed empty selection")
    groups, source_events = {}, {}
    contributions = 0
    for event in payload["events"]:
        key = event["event_key"]
        semantic = {k: v for k, v in event.items() if k != "sources"}
        semantic["companies"] = sorted(semantic["companies"])
        if key in groups and groups[key]["semantic"] != semantic:
            raise ValueError("Conflicting summaries or event attribution require editorial reconciliation")
        group = groups.setdefault(key, dict(semantic=semantic, sources=[]))
        for source in event["sources"]:
            url = public_url(source["url"])
            if not source["published_on"].startswith(prefix):
                raise ValueError("Publisher publication day is outside the selected editorial month")
            if local_time(source["observed_at"]) > cutoff:
                raise ValueError("Publisher reading occurred after the review cutoff")
            if source["published_on"] > local_time(source["observed_at"]).date().isoformat():
                raise ValueError("Publisher publication is later than its recorded reading")
            identity = (
                key,
                source["published_on"],
                source["publisher"],
                source["title"],
                source.get("event_date"),
                source.get("event_end_date"),
            )
            if url in source_events and source_events[url] != identity:
                raise ValueError("The same publisher article cannot silently create different events")
            source_events[url] = identity
            observation = {
                **source,
                "canonical_url": url,
                "representation": "reviewed_web_observation_not_original_publisher_bytes",
                "original_page_sha256": None,
            }
            contributions += 1
            if observation not in group["sources"]:
                group["sources"].append(observation)
        for field in ("event_date", "event_end_date"):
            if event[field] is not None and not any(s.get(field) == event[field] for s in event["sources"]):
                raise ValueError("Event dates require an explicit supporting publisher observation")
        if event["event_date"] and event["event_end_date"] and event["event_end_date"] < event["event_date"]:
            raise ValueError("Event end precedes its start")
    records = []
    for key, group in sorted(groups.items()):
        event = group["semantic"]
        sources = sorted(
            group["sources"],
            key=lambda s: (
                s["source_kind"] != "official",
                s["published_on"],
                s["canonical_url"],
                s["observed_at"],
            ),
        )
        selected = sources[0]
        identity = sha(key.encode())[:24]
        observation_sha = sha(encoded(selected))
        row = dict(
            id="editorial_" + identity,
            story_id="event_" + identity,
            kind="news",
            title=event["title"],
            description=event["summary"],
            publisher=selected["publisher"],
            published_at=selected["published_on"],
            first_reported_on=min(s["published_on"] for s in sources),
            publication_precision="day",
            publication_date_basis="publisher_displayed_day_not_invented_UTC_timestamp",
            event_date=event["event_date"],
            event_end_date=event["event_end_date"],
            first_captured_at=min((s["observed_at"] for s in sources), key=local_time),
            first_capture_scope="selected_native_observations_not_first_publisher_availability",
            verified_at=max((s["observed_at"] for s in sources), key=local_time),
            companies=event["companies"],
            topics=[event["category"]],
            priority=PRIORITY.get(event["category"], 3 if event["category"] == "macro" else 2),
            impact_note=event["impact_note"],
            summary_kind="own_editorial_summary",
            source=dict(
                id="web_observation_" + observation_sha[:20],
                url=selected["url"],
                sha256=observation_sha,
                sha256_semantics="reviewed_observation_not_original_page_bytes",
            ),
            publisher_observations=sources,
            review_status="candidate_unapproved",
            agent_eligible=False,
        )
        records.append(row)
    records.sort(key=lambda r: (r["priority"], -int(r["published_at"].replace("-", "")), r["story_id"]))
    for index, row in enumerate(records):
        row["source"].update(
            artifact_file="candidates.json", json_pointer=f"/records/{index}/publisher_observations/0"
        )
        row["candidate_content_sha256"] = candidate_content_sha256(
            {k: v for k, v in row.items() if k != "candidate_content_sha256"}
        )
    candidate = dict(
        schema="monthly_news_candidate_v1",
        period=payload["period"],
        cut_at=payload["as_of"],
        coverage=COVERAGE,
        records=records,
        activation="none",
        publication="not_authorized",
    )
    if records:
        candidate_cut(candidate)  # Existing unapproved-candidate identity/date/hash contract.
    return candidate, dict(
        task_id="editorial_news",
        period=payload["period"],
        status="checks_passed",
        events=len(records),
        source_observations=sum(len(g["sources"]) for g in groups.values()),
        exact_contributions_deduplicated=contributions - sum(len(g["sources"]) for g in groups.values()),
        event_groups_merged=len(payload["events"]) - len(groups),
        searches=len(payload["searches"]),
        failed_searches=sum(s["outcome"] == "access_failed" for s in payload["searches"]),
        excluded_items=len(payload["exclusions"]),
        pending_publisher_observations=pending,
        last_search_at=max((s["checked_at"] for s in payload["searches"]), key=local_time),
        selection_outcome="reviewed_candidates" if records else "reviewed_no_relevant_selection",
        empty_selection_reason=payload["empty_selection_reason"],
        coverage=COVERAGE,
        publisher_reading_claim="recorded_native_review_not_offline_refetch_or_original_byte_authentication",
        ready_for_editorial_review=True,
        editorial_approval_required=True,
        ready_for_publication=False,
        network_requests=0,
        scheduled_executions=0,
        activation="none",
        publication="not_authorized",
    )


def fingerprints():
    paths = [
        Path(__file__),
        SCHEMA,
        ROOT / "src/conversational_analytics/evidence_index.py",
        *(
            ROOT / "src/source_updates" / name
            for name in ("news_cut.py", "news.py", "calendar.py", "collection.py")
        ),
    ]
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in paths}


def inventory(root):
    expected = {"review-input.json", "candidates.json", "receipt.json"}
    if {p.name for p in root.iterdir()} != expected or any(not (root / n).is_file() for n in expected):
        raise ValueError(
            "Editorial candidate must contain three regular immutable files, without an active writer"
        )
    return {name: sha((root / name).read_bytes()) for name in sorted(expected)}


def revisions(candidate, baseline, workspace):
    if baseline is None:
        return {"status": "not_compared_no_baseline"}
    path = Path(baseline).absolute()
    previous_root = safe_workspace(path.parent)
    if path.name != "candidates.json" or previous_root == workspace:
        raise ValueError("Editorial baseline must be another physical candidate's candidates.json")
    before_files = inventory(previous_root)
    raw = path.read_bytes()
    receipt = json.loads((previous_root / "receipt.json").read_text())
    previous = json.loads(raw)
    if sha(raw) != receipt["candidate_sha256"] or previous["period"] != candidate["period"]:
        raise ValueError("Editorial baseline changed or belongs to another month")
    if previous["records"]:
        candidate_cut(previous)
    if inventory(previous_root) != before_files:
        raise ValueError("Editorial baseline changed during its read-only comparison")

    def observations(value):
        keys = ("title", "description", "published_at", "event_date", "event_end_date", "companies", "topics")
        return {r["story_id"]: {k: r[k] for k in keys} for r in value["records"]}

    before, after = observations(previous), observations(candidate)
    common = before.keys() & after.keys()
    return dict(
        status="compared_same_month_event_metadata",
        baseline_file=str(path),
        baseline_sha256=sha(raw),
        added=len(after.keys() - before.keys()),
        removed=len(before.keys() - after.keys()),
        changed=sum(before[k] != after[k] for k in common),
        unchanged=sum(before[k] == after[k] for k in common),
    )


def run(workspace, payload=None, *, execute=False, check=False, baseline=None):
    root = safe_workspace(Path(workspace))
    if execute and check:
        raise ValueError("Choose one editorial execution mode")
    if check:
        if payload is not None:
            raise ValueError("Editorial replay cannot replace the recorded native review input")
        before = inventory(root)
        receipt_bytes = (root / "receipt.json").read_bytes()
        prior = json.loads(receipt_bytes)
        if receipt_bytes != encoded(prior):
            raise ValueError("Editorial receipt bytes differ from the immutable writer format")
        prior_baseline = prior["revisions"].get("baseline_file")
        if baseline is not None and str(Path(baseline).absolute()) != prior_baseline:
            raise ValueError("Editorial replay cannot change its immutable baseline selection")
        baseline = prior_baseline
        if prior["checker_code_files"] != fingerprints():
            raise ValueError("Editorial verifier changed; a new candidate receipt is required")
        raw = (root / "review-input.json").read_bytes()
        if sha(raw) != prior["input_sha256"]:
            raise ValueError("Recorded editorial observations changed")
        payload = json.loads(raw)
    if payload is None:
        raise ValueError("A recorded native editorial review is required")
    candidates, result = prepare(payload)
    result["revisions"] = revisions(candidates, baseline, root)
    raw, output = encoded(payload), encoded(candidates)
    result.update(input_sha256=sha(raw), candidate_sha256=sha(output), checker_code_files=fingerprints())
    if check:
        if result != prior or (root / "candidates.json").read_bytes() != output or inventory(root) != before:
            raise ValueError("Editorial replay differs from its immutable candidate receipt")
        return {**result, "receipt_sha256": sha((root / "receipt.json").read_bytes())}
    if not execute:
        return {**result, "status": "planned_not_written", "writes": []}
    with writer(root):
        if any(p.name != ".source-update.lock" for p in root.iterdir()):
            raise ValueError("Editorial candidate requires a new empty workspace")
        (root / "review-input.json").write_bytes(raw)
        (root / "candidates.json").write_bytes(output)
        (root / "receipt.json").write_bytes(encoded(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period")
    parser.add_argument("--as-of")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--baseline", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.input or args.check:
            if args.workspace is None:
                raise ValueError("Editorial candidate needs its explicit workspace")
            payload = json.loads(args.input.read_text()) if args.input else None
            result = run(
                args.workspace, payload, execute=args.execute, check=args.check, baseline=args.baseline
            )
        else:
            if not args.period or not args.as_of or args.execute:
                raise ValueError("Plan requires period and cutoff; execution requires recorded input")
            result = plan(args.period, args.as_of)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps(dict(status="blocked", reason=str(exc), activation="none")))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Certify one H.10 month in an isolated candidate; never publish or invoke other macro products."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from bs4 import BeautifulSoup
import pandas as pd

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import require_replay_cutoff, row_changes, verify_bronze
from src.source_updates.collection import collect, safe_workspace, writer, validate_url
from src.source_updates.h10_capture import BoundedFedClient, MAX_BYTES, month_bounds, selection
from src.source_updates.h10_parse import csv_rates, holiday_evidence, html_rates, reconcile


OUTPUTS = (
    "silver/fx_rates",
    "silver/macro_indicators",
    "gold/fact_macro",
    "gold/dim_period",
    "gold/dim_source_artifact",
    "gold/bridge_record_lineage",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def isolate(workspace: Path, period: str) -> None:
    allowed = {workspace / "data" / (name + ".parquet") for name in OUTPUTS}
    for layer in ("silver", "gold"):
        for path in (workspace / "data" / layer).glob("*.parquet"):
            if path not in allowed:
                raise ValueError("H.10 candidate contains other product outputs; use a separate workspace")
            frame = pd.read_parquet(path)
            if "source_system" in frame and not frame.source_system.eq("federal_reserve_h10").all():
                raise ValueError("H.10 cannot overwrite another source")
            if "period_id" in frame and not frame.period_id.eq(period).all():
                raise ValueError("Use one H.10 month per candidate workspace")


def originals(workspace: Path, period: str, cutoff: str, run_id: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Invalid candidate collection receipt ID")
    receipt_path = workspace / "receipts" / f"collection-{run_id}.json"
    receipt = json.loads(receipt_path.read_text())
    selected = selection(period, cutoff)["items"]
    if receipt.get("status") != "collected_unvalidated" or len(receipt["items"]) != len(selected):
        raise ValueError("Complete H.10 collection receipt required")
    records = verify_bronze(workspace)
    if any(row["source_system"] != "federal_reserve_h10" for row in records.values()):
        raise ValueError("H.10-only candidate cannot contain other Bronze sources")
    items = {row["id"]: row for row in receipt["items"]}
    if len(items) != len(selected):
        raise ValueError("Duplicate H.10 receipt item IDs")
    content, evidence = {}, {}
    for item in selected:
        observed = items[item["id"]]
        row = records.get(observed.get("source_file"))
        logical = f"federal_reserve_h10|{item['entity']}|{period}|{item['extension']}"
        if (
            row is None
            or row["sha256"] != observed.get("sha256")
            or row["source_url"] != item["url"]
            or row["logical_key"] != logical
        ):
            raise ValueError("H.10 receipt, Bronze hash, URL or identity differs from the selection")
        if observed.get("http_status") != 200 or not observed["status"].startswith("collected_"):
            raise ValueError("H.10 original was not successfully captured")
        validate_url(observed.get("response_url", ""), ["federalreserve.gov"])
        if local_time(row["downloaded_at"]) > local_time(cutoff):
            raise ValueError("H.10 original was captured after the requested cutoff")
        path = workspace / "data/bronze" / row["source_file"]
        sidecar = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text())
        if any(
            sidecar.get(key) != row[key] for key in ("source_url", "sha256", "downloaded_at", "logical_key")
        ):
            raise ValueError("H.10 Bronze sidecar differs from its acquisition manifest")
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Preserved H.10 original exceeds the size limit")
        role = item["id"].removeprefix("h10-")
        content[role], evidence[role] = path.read_bytes(), row
    return content, {"artifacts": evidence, "collection_receipt_sha256": digest(receipt_path)}


def evaluate(workspace: Path, period: str, cutoff: str, run_id: str) -> tuple[dict, dict]:
    from src.source_updates.h10_gold import frames

    content, provenance = originals(workspace, period, cutoff, run_id)
    text = {
        role: BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
        for role, body in content.items()
        if role != "csv"
    }
    if (
        "noon buying rates in New York" not in text["definition"]
        or "ND = No data for this date." not in text["release"]
    ):
        raise ValueError("Official H.10 quote/ND definitions missing; do not infer their interpretation")
    left = csv_rates(content["csv"])
    right, vintage = html_rates(content["history"])
    _, end = month_bounds(period)
    if not end <= vintage <= local_time(cutoff).date():
        raise ValueError("H.10 history release date does not cover the month at this cutoff")
    holidays = holiday_evidence(content["holidays"], end.year)
    daily = reconcile(left, right, period, holidays)
    outputs, lineage = frames(workspace, period, daily, provenance["artifacts"])
    nd = [row["date"].isoformat() for row in daily if row["observation_status"] == "ND"]
    result = {
        "status": "checks_passed",
        "product": "h10",
        "period": period,
        "scope": "one_H10_month_not_macro_family_certification",
        "rows": len(daily),
        "observed_values": len(daily) - len(nd),
        "source_nd_dates": nd,
        "unexpected_missing_weekdays": [],
        "duplicate_dates": 0,
        "crosscheck": "all_dates_statuses_decimal_values_equal",
        "unit": "mxn_per_usd",
        "currency_pair": "USD/MXN",
        "indicator_key": "usd_mxn",
        "fix": False,
        "quote_definition": "New York noon buying rate, not trading close",
        "gold_close_definition": "last observed H.10 noon quote in the month",
        "nd_policy": "source ND retained; K.8 Board observance is corroborating context, not an inferred cause or universal FX calendar",
        "history_release_date": vintage.isoformat(),
        "source_last_observation_dates": {"csv": max(left).isoformat(), "html": max(right).isoformat()},
        "target_first_date": daily[0]["date"].isoformat(),
        "target_last_date": daily[-1]["date"].isoformat(),
        "first_publication_date": None,
        "release_lag_days": None,
        "csv_publication_date": None,
        "alternative": {
            "source": "official_Mexico_history_HTML",
            "verified": True,
            "automatic_fallback": False,
        },
        "stability": {
            "build_your_package_notice_seen": "November 9, 2026" in text["transition"],
            "current_endpoint_shutdown_proven": False,
        },
        "lineage": lineage,
        **provenance,
        "activation": "none",
        "publication": "not_authorized",
        "approval": "human_review_required",
    }
    return outputs, result


def certify(workspace: Path, period: str, cutoff: str, run_id: str, *, write: bool = False) -> dict:
    from src.ingest.stage4_common import write_parquet_atomic

    workspace = safe_workspace(workspace)
    selection(period, cutoff)
    isolate(workspace, period)
    with block_network():
        outputs, result = evaluate(workspace, period, cutoff, run_id)
        result.update(
            version=1,
            collection_run_id=run_id,
            effective_as_of=cutoff,
            checked_at=datetime.now(UTC).isoformat(),
        )
        result["code_head"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        code = [*(ROOT / "src/source_updates").glob("h10*.py"), ROOT / "src/source_updates/__main__.py"]
        result["code_files"] = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(code)}
        previous = workspace / "data/silver/fx_rates.parquet"
        result["revisions"] = (
            row_changes(
                pd.read_parquet(previous),
                outputs["silver/fx_rates"],
                ["date", "series_id"],
                ["rate_close", "observation_status"],
            )
            if previous.exists()
            else {"status": "not_compared_no_prior_candidate"}
        )
        # All interpretation, period, contract and lineage checks precede any output write.
        for name, frame in outputs.items():
            path = workspace / "data" / (name + ".parquet")
            if write:
                write_parquet_atomic(frame, path)
            else:
                try:
                    pd.testing.assert_frame_equal(pd.read_parquet(path), frame, check_exact=True)
                except AssertionError as exc:
                    raise ValueError(
                        f"H.10 candidate output differs from its verified originals: {name}"
                    ) from exc
        result["output_sha256"] = {name: digest(workspace / "data" / (name + ".parquet")) for name in outputs}
    return result


def run(
    workspace: Path,
    period: str,
    as_of: str,
    *,
    execute=False,
    check=False,
    from_collection=None,
    check_at_completion=False,
    client_factory=None,
) -> dict:
    workspace = safe_workspace(workspace)
    chosen = selection(period, as_of)
    isolate(workspace, period)
    if check:
        accepted = json.loads((workspace / "receipts" / f"h10-{period}.json").read_text())
        require_replay_cutoff(accepted, as_of)
        result = certify(workspace, period, as_of, accepted["collection_run_id"])
        if result["collection_receipt_sha256"] != accepted["collection_receipt_sha256"]:
            raise ValueError("Accepted H.10 collection receipt hash changed")
        if result["output_sha256"] != accepted["output_sha256"]:
            raise ValueError("Accepted H.10 candidate artifact hash changed")
        return result
    if not execute and not from_collection:
        return {
            "mode": "dry_run",
            "collection": collect(chosen, workspace),
            "max_decoded_bytes_per_response": MAX_BYTES,
            "outputs": list(OUTPUTS),
            "coverage": "all_month_weekdays_plus_explicit_ND_and_official_crosscheck",
            "network_requests": 0,
            "paid_requests": 0,
            "activation": "none",
            "publication": "not_authorized",
        }
    if (workspace / "receipts" / f"h10-{period}.json").exists():
        raise ValueError("Accepted H.10 candidates are immutable; use a new workspace for a new capture")
    collected = (
        {"status": "collected_unvalidated", "run_id": from_collection}
        if from_collection
        else collect(chosen, workspace, execute=True, client_factory=client_factory or BoundedFedClient)
    )
    if collected["status"] != "collected_unvalidated":
        return {
            "status": "blocked_collection",
            "collection": collected,
            "activation": "none",
            "publication": "not_authorized",
        }
    effective = datetime.now(UTC).isoformat() if check_at_completion else as_of
    try:
        with writer(workspace):
            if (workspace / "receipts" / f"h10-{period}.json").exists():
                raise ValueError(
                    "Accepted H.10 candidates are immutable; use a new workspace for a new capture"
                )
            result = certify(workspace, period, effective, collected["run_id"], write=True)
            result["requested_as_of"] = as_of
            receipt = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            (workspace / "receipts" / f"h10-{uuid4().hex}.json").write_text(receipt)
            (workspace / "receipts" / f"h10-{period}.json").write_text(receipt)
            return result
    except (ValueError, OSError, AssertionError) as exc:
        result = {
            "status": "blocked_certification",
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "collection_run_id": collected["run_id"],
            "activation": "none",
            "publication": "not_authorized",
        }
        with writer(workspace):
            (workspace / "receipts" / f"h10-rejected-{uuid4().hex}.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
        return result

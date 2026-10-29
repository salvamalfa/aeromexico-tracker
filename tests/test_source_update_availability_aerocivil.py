"""Physical retained-query evidence; synthetic fixtures are never source captures."""

import copy
import hashlib
import json
import shutil
import socket
from pathlib import Path
from uuid import uuid4

import pytest

from src.source_updates import aerocivil_metadata, availability
from src.source_updates import availability_aerocivil as retained
from src.source_updates.aerocivil import OUTPUTS
from src.source_updates.catalog import ROOT

CUTOFF = "2026-10-21T05:00:00Z"
OBSERVED = "2026-10-21T00:32:01+00:00"
COLLECTION = "a" * 32


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def case(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Retained availability must never make network requests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    base = ROOT / "tmp/source-updates" / ("availability-aerocivil-test-" + uuid4().hex)
    collection, candidate = base / "query", base / "candidate"
    selection = aerocivil_metadata.availability_selection("2026")["items"][0]
    source_file = "international_routes/aerocivil/availability/synthetic.json"
    original = collection / "data/bronze" / source_file
    write_json(original, [{"anio": "2026", "mes": "07"}])
    record = dict(
        source_file=source_file,
        source_system="aerocivil",
        source_url=selection["url"],
        downloaded_at=OBSERVED,
        sha256=sha(original),
        bytes=original.stat().st_size,
        http_status=200,
        download_method="httpx",
        logical_key="aerocivil|latest_available_operator_month|current|json",
    )
    write_json(Path(str(original) + ".meta.json"), record)
    manifest = collection / "data/bronze/_manifest.jsonl"
    manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")
    row = dict(
        id=selection["id"],
        product="aerocivil",
        requested_period="current",
        status="collected_unvalidated",
        response_url=selection["url"],
        **{key: record[key] for key in ("source_file", "source_url", "sha256", "http_status", "bytes")},
    )
    receipt = dict(
        run_id=COLLECTION,
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
        started_at="2026-10-21T00:31:55+00:00",
        finished_at="2026-10-21T00:32:02+00:00",
        items=[row],
    )
    receipt_path = collection / "receipts" / f"collection-{COLLECTION}.json"
    write_json(receipt_path, receipt)
    hashes = {}
    for name in OUTPUTS:
        path = candidate / "data" / f"{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-hash-binding-after-external-offline-replay")
        hashes[name] = sha(path)
    item = dict(
        product="aerocivil",
        adapter="aerocivil",
        period="2026M07",
        workspace=str(candidate),
        candidate_as_of="2026-10-21T01:06:33+00:00",
        receipt_id="b" * 32,
        availability=dict(source_scope=retained.SCOPE, workspace=str(collection), collection_id=COLLECTION),
    )
    result = dict(
        status="checks_passed",
        period="2026M07",
        scope=retained.CANDIDATE_SCOPE,
        missing_operator_is_not_zero=True,
        activation="none",
        publication="not_authorized",
        effective_as_of=item["candidate_as_of"],
        collection_run_id=item["receipt_id"],
        output_sha256=hashes,
    )
    yield dict(
        item=item,
        result=result,
        collection=collection,
        candidate=candidate,
        original=original,
        manifest=manifest,
        record=record,
        row=row,
        receipt=receipt,
        receipt_path=receipt_path,
    )
    shutil.rmtree(base)


def rewrite(case):
    case["record"]["sha256"] = sha(case["original"])
    case["record"]["bytes"] = case["original"].stat().st_size
    for key in ("sha256", "bytes", "source_url"):
        case["row"][key] = case["record"][key]
    write_json(Path(str(case["original"]) + ".meta.json"), case["record"])
    case["manifest"].write_text(json.dumps(case["record"]) + "\n", encoding="utf-8")
    write_json(case["receipt_path"], case["receipt"])


def check(case, cutoff=CUTOFF):
    return availability.verify(case["item"], case["result"], cutoff)


def test_retained_maximum_month_is_verified_without_renewing_observation_or_certifying_coverage(case):
    before = {root: availability.collection_inventory(case[root]) for root in ("collection", "candidate")}
    result = check(case)
    assert result["latest_source_availability_verified"] is True
    assert result["latest_available_period"] == "2026M07"
    assert result["source_observation_current_for_round"] is True
    assert result["observed_at"] == result["downloaded_at"] == OBSERVED
    assert result["source_availability_observed_at"] == OBSERVED
    assert result["latest_semantics"] == "maximum_in_retained_AMX_SLI_query_at_original_observation_time"
    assert result["collection_receipt_sha256"] == sha(case["receipt_path"])
    assert result["source_artifact_sha256"] == sha(case["original"])
    assert result["complete_month_verified"] is result["complete_quarter_verified"] is False
    assert result["missing_operator_is_not_zero"] is True
    assert result["latest_published_period"] is result["latest_validated_period"] is None
    assert result["published_at"] is result["release_lag_days"] is None
    assert result["network_requests"] == 0 and result["new_source_capture"] is False
    assert before == {
        root: availability.collection_inventory(case[root]) for root in ("collection", "candidate")
    }


def test_retained_query_cannot_verify_latest_for_a_later_local_round_date(case):
    before = availability.collection_inventory(case["collection"])
    with pytest.raises(ValueError, match="round's local capture date"):
        check(case, "2026-10-29T12:00:00Z")
    with pytest.raises(ValueError, match="round's local capture date"):
        check(case, "2026-10-21T06:00:00Z")
    assert availability.collection_inventory(case["collection"]) == before
    # The separate metadata command still reproduces history without claiming
    # availability for the later round or changing original timestamps.
    historical = aerocivil_metadata.availability(
        case["collection"], "2026", "2026-10-29T12:00:00Z", COLLECTION
    )
    assert historical["latest_available_period"] == "2026M07"
    assert historical["downloaded_at"] == OBSERVED


@pytest.mark.parametrize(
    "field,value",
    [("collection_id", "../bad"), ("collection_id", "a" * 31), ("source_scope", "other"), ("extra", True)],
)
def test_preflight_rejects_wrong_or_extra_binding_fields(case, field, value):
    binding = copy.deepcopy(case["item"]["availability"])
    binding[field] = value
    with pytest.raises(ValueError):
        retained.preflight(binding, case["candidate"])


@pytest.mark.parametrize("placement", ["equal", "inside", "ancestor", "escape"])
def test_preflight_rejects_overlapping_or_outside_workspaces(case, placement):
    binding = copy.deepcopy(case["item"]["availability"])
    binding["workspace"] = str(
        {
            "equal": case["candidate"],
            "inside": case["candidate"] / "query",
            "ancestor": case["candidate"].parent,
            "escape": ROOT / "data/bronze",
        }[placement]
    )
    with pytest.raises(ValueError):
        retained.preflight(binding, case["candidate"])


@pytest.mark.parametrize(
    "field,value", [("product", "caa"), ("adapter", "retained"), ("period", "2026Q3"), ("period", "2025M07")]
)
def test_wrong_product_adapter_or_native_period_is_blocked(case, field, value):
    case["item"][field] = value
    with pytest.raises(ValueError):
        check(case)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "blocked"),
        ("period", "2026M08"),
        ("scope", "full_quarter"),
        ("missing_operator_is_not_zero", False),
        ("effective_as_of", CUTOFF),
        ("output_sha256", {}),
        ("activation", "active"),
        ("collection_run_id", "c" * 32),
    ],
)
def test_incomplete_or_unbound_candidate_replay_is_blocked(case, field, value):
    case["result"][field] = value
    with pytest.raises(ValueError):
        check(case)


@pytest.mark.parametrize("target", ["original", "manifest", "receipt_path", "sidecar", "native"])
def test_missing_physical_evidence_is_blocked(case, target):
    path = (
        Path(str(case["original"]) + ".meta.json")
        if target == "sidecar"
        else case["candidate"] / "data" / f"{OUTPUTS[0]}.parquet"
        if target == "native"
        else case[target]
    )
    path.unlink()
    with pytest.raises((ValueError, OSError)):
        check(case)


@pytest.mark.parametrize(
    "data",
    [[{"anio": "2026", "mes": "08"}], [], [{"anio": "2025", "mes": "07"}], [{"anio": "2026", "mes": "11"}]],
)
def test_other_maximum_month_or_empty_and_future_query_is_blocked(case, data):
    write_json(case["original"], data)
    rewrite(case)
    with pytest.raises(ValueError):
        check(case)


@pytest.mark.parametrize(
    "target",
    [
        "original",
        "receipt_id",
        "bytes",
        "sidecar",
        "query",
        "response_query",
        "receipt_status",
        "item_product",
        "requested_period",
    ],
)
def test_tampered_hash_receipt_query_or_binding_is_blocked(case, target):
    if target == "original":
        case["original"].write_bytes(b"altered bytes")
    elif target == "receipt_id":
        case["receipt"]["run_id"] = "f" * 32
        write_json(case["receipt_path"], case["receipt"])
    elif target == "sidecar":
        write_json(Path(str(case["original"]) + ".meta.json"), {**case["record"], "bytes": 999})
    elif target == "query":
        case["record"]["source_url"] += "&%24limit=2"
        case["row"]["response_url"] = case["record"]["source_url"]
        rewrite(case)
    else:
        field, value = {
            "bytes": ("bytes", 999),
            "response_query": ("response_url", case["row"]["response_url"] + "&%24limit=2"),
            "receipt_status": ("status", "blocked"),
            "item_product": ("product", "caa"),
            "requested_period": ("requested_period", "2026M07"),
        }[target]
        if target == "receipt_status":
            case["receipt"][field] = value
        else:
            case["row"][field] = value
        write_json(case["receipt_path"], case["receipt"])
    with pytest.raises(ValueError):
        check(case)


@pytest.mark.parametrize("cutoff", ["2026-10-20T12:00:00Z", "2026-10-21T00:32:01Z"])
def test_cutoff_before_candidate_or_finished_collection_is_blocked(case, cutoff):
    with pytest.raises(ValueError):
        check(case, cutoff)


def test_chronology_must_include_original_capture(case):
    case["receipt"]["started_at"] = "2026-10-21T00:32:02Z"
    write_json(case["receipt_path"], case["receipt"])
    with pytest.raises(ValueError, match="chronology"):
        check(case)


@pytest.mark.parametrize("workspace", ["collection", "candidate"])
def test_collection_or_candidate_mutation_during_metadata_replay_is_blocked(case, monkeypatch, workspace):
    original = aerocivil_metadata.availability

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        (case[workspace] / "unexpected-file").write_text("mutation")
        return result

    monkeypatch.setattr(aerocivil_metadata, "availability", mutate)
    with pytest.raises(ValueError, match="changed during read-only"):
        check(case)


def test_round_cutoff_cannot_precede_collection_finish_even_after_original_capture(case):
    case["item"]["candidate_as_of"] = case["result"]["effective_as_of"] = "2026-10-21T00:31:00Z"
    with pytest.raises(ValueError, match="chronology"):
        check(case, "2026-10-21T00:32:01Z")


@pytest.mark.parametrize("workspace", ["collection", "candidate"])
def test_active_writer_blocks_readonly_verification(case, workspace):
    (case[workspace] / ".source-update.lock").write_text("synthetic-writer")
    with pytest.raises(ValueError, match="active writer"):
        check(case)

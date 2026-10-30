"""Source/context fault injection; all receipts are synthetic and authorize nothing."""

import copy
import json
from pathlib import Path

import pytest

from scripts import source_update_handoffs as h
from scripts import source_update_semantic_identity as semantic
from src.pipeline.offline import block_network
from src.source_updates import collection, retained
from tests.test_source_update_financials_html import original, report

CUTOFF = "2026-10-29T15:53:59+00:00"


def file_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def candidate(tmp_path, name, raw, timestamp="2026-10-27T13:20:28Z"):
    source = tmp_path / "tmp/source-updates" / name / "source"
    meta = {
        **original(raw),
        "bytes": len(raw),
        "downloaded_at": timestamp,
        "http_status": 200,
        "logical_version": 1,
        "filename_version": 1,
        "content_type": "text/html",
        "download_method": "synthetic_offline_fixture",
    }
    path = source / meta["source_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    file_json(Path(str(path) + ".meta.json"), meta)
    (source / "_manifest.jsonl").write_text(json.dumps(meta) + "\n")
    workspace = source.parent / "candidate"
    with block_network():
        receipt = retained.retain(
            workspace, source, "am_financials", {"html": meta["source_file"]}, execute=True
        )
        retained.run(workspace, "am_financials", "2026Q3", CUTOFF, receipt["run_id"], execute=True)
    return {
        "item": {
            "product": "am_financials",
            "period": "2026Q3",
            "workspace": str(workspace),
            "receipt_id": receipt["run_id"],
            "candidate_as_of": CUTOFF,
        },
        "as_of": CUTOFF,
        "change_reason": "synthetic offline fault injection: " + name,
    }


def verified(observation, workspace=None):
    item = observation["item"]
    with block_network():
        checked = retained.run(
            Path(item["workspace"]),
            item["product"],
            item["period"],
            item["candidate_as_of"],
            item["receipt_id"],
            check=True,
        )
        facts = h.meaningful_data(item, checked)
        return {"checked": checked, **semantic.versions(item, facts), "source_binding": observation}


@pytest.fixture
def physical(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "ROOT", tmp_path)
    raw = report().replace(
        b"available seat miles (ASMs)", b"available seat miles (ASMs) Outlook constructive."
    )
    versions = {
        "original": candidate(tmp_path, "original", raw),
        "context": candidate(tmp_path, "context", raw.replace(b"constructive", b"deteriorating")),
        "format": candidate(tmp_path, "format", raw.replace(b"constructive", b"const<!--ignore-->ructive")),
        "capture": candidate(tmp_path, "capture", raw, "2026-10-27T13:20:29Z"),
    }
    # Test only the observe/state boundary; physical producer replay above is real.
    # No availability, authorization, acquisition or calendar evidence is fabricated.
    monkeypatch.setattr(h, "verify_source", verified)
    monkeypatch.setattr(h, "verify_candidate", verified)
    return tmp_path / "tmp/source-updates/outbox", versions


def action(workspace, operation, kind="observe", **kwargs):
    return h.run(workspace, action={"action": kind, "operation_id": operation, "at": CUTOFF, **kwargs})


def test_primary_revision_same_gold_queues_analysis_but_format_and_capture_do_not(physical):
    workspace, observations = physical
    results = {key: verified(obs) for key, obs in observations.items()}
    assert len({r["legacy_data_version"] for r in results.values()}) == 1
    assert results["original"]["data_version"] == results["format"]["data_version"]
    assert results["original"]["data_version"] == results["capture"]["data_version"]
    assert results["original"]["data_version"] != results["context"]["data_version"]
    for key in ("original", "format", "capture"):
        result = action(workspace, key, observation=observations[key])
        assert len(result["state"]["sources"]) == 1 and len(result["state"]["jobs"]) == 2
    result = action(workspace, "context", observation=observations["context"])
    assert len(result["state"]["sources"]) == 2
    assert sum(j["stage"] == "analysis" for j in result["state"]["jobs"].values()) == 2
    before = (workspace / "state.json").read_bytes()
    action(workspace, "context", observation=observations["context"])
    assert (workspace / "state.json").read_bytes() == before


@pytest.mark.parametrize("status", ["planned", "dispatch_intent", "running", "completed"])
def test_legacy_workers_keep_ids_versions_attempts_and_receipts(physical, status):
    workspace, observations = physical
    old = verified(observations["original"])
    result = action(workspace, "first", observation=observations["original"])
    state = result["state"]
    source_id = next(iter(state["sources"]))
    source = state["sources"][source_id]
    # Simulate a persisted v1 ledger, never an approval of a real source/worker.
    source["data_version"] = old["legacy_data_version"]
    del source["meaningful_identity"]
    del source["legacy_data_version"]
    analysis_id = next(key for key, j in state["jobs"].items() if j["stage"] == "analysis")
    job = state["jobs"][analysis_id]
    job.update(
        status=status, result={"synthetic_receipt": "immutable", "data_version": source["data_version"]}
    )
    if status != "planned":
        job["attempt"] = {"owner_lease_id": "local_lease:test", "native_call": {"existing": "unchanged"}}
    file_json(workspace / "state.json", state)
    preserved = copy.deepcopy(state)
    result = action(workspace, "same-new-observation", observation=observations["capture"])
    updated = result["state"]
    assert updated["heads"] == preserved["heads"] and updated["jobs"] == preserved["jobs"]
    assert updated["sources"][source_id]["data_version"] == source["data_version"]
    assert updated["sources"][source_id]["meaningful_identity"] == old["meaningful_identity"]
    before = (workspace / "state.json").read_bytes()
    action(workspace, "same-new-observation", observation=observations["capture"])
    assert (workspace / "state.json").read_bytes() == before
    if status == "planned":
        result = action(
            workspace, "claim-old", "claim", job_id=analysis_id, owner_lease_id="local_lease:test"
        )
        assert result["state"]["jobs"][analysis_id]["status"] == "dispatch_intent"
        assert result["state"]["sources"][source_id]["data_version"] == source["data_version"]
    else:
        with pytest.raises(ValueError, match="reconcile"):
            action(workspace, "claim-old", "claim", job_id=analysis_id, owner_lease_id="local_lease:test")
    result = action(workspace, "real-context-revision", observation=observations["context"])
    assert len(result["state"]["sources"]) == 2 and len(result["state"]["jobs"]) == 4


def test_legacy_claim_without_an_intervening_observe_remains_bound(physical):
    workspace, observations = physical
    old = verified(observations["original"])
    state = action(workspace, "first", observation=observations["original"])["state"]
    source = next(iter(state["sources"].values()))
    source["data_version"] = old["legacy_data_version"]
    del source["meaningful_identity"]
    job_id = next(key for key, j in state["jobs"].items() if j["stage"] == "analysis")
    file_json(workspace / "state.json", state)
    result = action(workspace, "claim-old", "claim", job_id=job_id, owner_lease_id="local_lease:test")
    assert result["state"]["jobs"][job_id]["status"] == "dispatch_intent"
    assert "meaningful_identity" not in next(iter(result["state"]["sources"].values()))


def test_missing_or_changed_previous_primary_fails_closed_without_writing_state(physical):
    workspace, observations = physical
    result = action(workspace, "first", observation=observations["original"])
    prior = next(iter(result["state"]["sources"].values()))
    receipt = Path(prior["source_binding"]["item"]["workspace"]) / "receipts"
    original_meta = json.loads(next(receipt.glob("retained-*.json")).read_text())["originals"]["html"]
    original_path = receipt.parent / "data/bronze" / original_meta["source_file"]
    original_path.write_bytes(original_path.read_bytes() + b"changed")
    before = (workspace / "state.json").read_bytes()
    with pytest.raises(ValueError):
        action(workspace, "capture", observation=observations["capture"])
    assert (workspace / "state.json").read_bytes() == before
    original_path.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        action(workspace, "capture2", observation=observations["capture"])
    assert (workspace / "state.json").read_bytes() == before


def test_unverified_legacy_bytes_do_not_get_rebaselined(physical):
    workspace, observations = physical
    state = action(workspace, "first", observation=observations["original"])["state"]
    source = next(iter(state["sources"].values()))
    source["data_version"] = "0" * 64
    source.pop("meaningful_identity")
    file_json(workspace / "state.json", state)
    before = (workspace / "state.json").read_bytes()
    with pytest.raises(ValueError, match="immutable physical binding"):
        action(workspace, "capture", observation=observations["capture"])
    assert (workspace / "state.json").read_bytes() == before


def test_aerocivil_capture_churn_is_ignored_business_semantics_preserved(tmp_path):
    item = {"product": "aerocivil", "period": "2026Q3", "workspace": str(tmp_path)}
    base = {
        "product": "aerocivil",
        "period": "2026Q3",
        "tables": {
            "gold/fact_test": [
                {
                    "value": {"float_hex": float(347).hex()},
                    "operator_icao": "AMX",
                    "metric_definition": "recorded movements; provisional literal S/I",
                    "agent_eligible": False,
                    "source_flight_type_code": "S",
                    "source_traffic_code": "I",
                    "downloaded_at": "old",
                    "artifact_id": "old",
                    "source_url": "https://same-source.test",
                }
            ]
        },
    }
    initial = semantic.versions(item, base)["data_version"]
    for field in semantic.CAPTURE_FIELDS:
        changed = copy.deepcopy(base)
        changed["tables"]["gold/fact_test"][0][field] = "new-capture"
        assert semantic.versions(item, changed)["data_version"] == initial
    for field, value in {
        "operator_icao": "SLI",
        "metric_definition": "different measure",
        "agent_eligible": True,
        "source_flight_type_code": "N",
        "source_traffic_code": "D",
        "value": {"float_hex": float(347.00000000000006).hex()},
    }.items():
        changed = copy.deepcopy(base)
        changed["tables"]["gold/fact_test"][0][field] = value
        assert semantic.versions(item, changed)["data_version"] != initial


def test_primary_context_never_silently_extends_an_edition(tmp_path):
    with pytest.raises(ValueError, match="reviewed Q2/Q3"):
        semantic.primary_context({"product": "am_financials", "period": "2026Q4"})
    with pytest.raises(KeyError):
        semantic.primary_context({"product": "viva_financials", "period": "2026Q3"})


def test_legacy_compatibility_never_accepts_changed_bytes_or_unknown_schema():
    fresh = {
        "data_version": "v2",
        "legacy_data_version": "v1",
        "meaningful_identity": {"schema_version": semantic.SCHEMA, "sha256": "v2"},
        "checked": {"output_sha256": {"gold/fact_test": "original-bytes"}},
    }
    prior = {"data_version": "v1", "checked": copy.deepcopy(fresh["checked"])}
    assert semantic.bound_matches(prior, fresh)
    changed = copy.deepcopy(fresh)
    changed["checked"]["output_sha256"]["gold/fact_test"] = "different-bytes"
    assert not semantic.bound_matches(prior, changed)
    new = {**prior, "data_version": "v2", "meaningful_identity": fresh["meaningful_identity"]}
    assert not semantic.bound_matches(new, changed)
    assert not semantic.bound_matches({**prior, "data_version": "v2"}, fresh)
    assert not semantic.bound_matches({**prior, "data_version": "wrong-v1"}, fresh)
    assert not semantic.bound_matches({**prior, "meaningful_identity": {"schema_version": "unknown"}}, fresh)
    del changed["meaningful_identity"]
    with pytest.raises(ValueError, match="complete semantic identity"):
        semantic.bound_matches(prior, changed)


def test_aerocivil_meaningful_revision_queues_one_dashboard_independently(tmp_path, monkeypatch):
    from tests.test_source_update_handoffs import NOW

    monkeypatch.setattr(collection, "ROOT", tmp_path)
    workspace = tmp_path / "tmp/source-updates/outbox"
    facts = {
        "tables": {
            "gold/fact_test": [
                {
                    "operations": {"float_hex": float(347).hex()},
                    "operator_icao": "AMX",
                    "metric_definition": "provisional recorded movements",
                    "downloaded_at": "old",
                    "artifact_id": "old",
                }
            ]
        }
    }
    item = {"product": "aerocivil", "period": "2026Q3", "source_period": "2026M07"}

    def verify(obs, _):
        current = copy.deepcopy(facts)
        current["tables"]["gold/fact_test"][0].update(obs.get("synthetic_change", {}))
        return {"checked": {"output_sha256": {}}, **semantic.versions(item, current), "source_binding": obs}

    monkeypatch.setattr(h, "verify_source", verify)
    monkeypatch.setattr(h, "verify_candidate", verify)
    observation = {"item": item, "as_of": NOW}
    action(workspace, "initial", observation=observation)
    capture = {**observation, "synthetic_change": {"downloaded_at": "new", "artifact_id": "new"}}
    result = action(workspace, "capture", observation=capture)
    assert len(result["state"]["jobs"]) == len(result["state"]["sources"]) == 1
    revised = {**observation, "synthetic_change": {"metric_definition": "different scope"}}
    result = action(workspace, "meaningful", observation=revised)
    assert len(result["state"]["jobs"]) == len(result["state"]["sources"]) == 2
    assert all(
        j["stage"] == "dashboard" and j["release_kind"] == "movements"
        for j in result["state"]["jobs"].values()
    )


def test_pdf_container_metadata_does_not_hide_a_visible_revision():
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    def pdf(text, producer):
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 10 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.add_metadata({"/Producer": producer})
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    first = pdf("Demand constructive", "old-container")
    container = pdf("Demand constructive", "new-container")
    changed = pdf("Demand deteriorating", "old-container")
    assert first != container
    assert semantic.pdf_text(first) == semantic.pdf_text(container)
    assert semantic.pdf_text(first) != semantic.pdf_text(changed)
    with pytest.raises(ValueError, match="missing or outside"):
        semantic.pdf_text(b"not PDF")

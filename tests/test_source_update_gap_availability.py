"""Synthetic binding contracts only; the five-original real verifier audit is separate."""

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from src.source_updates import airport_group_candidate, availability, availability_gap, readiness
from src.source_updates.catalog import ROOT

CUTOFF = "2026-08-20T18:20:00-06:00"


def binding(root):
    return {
        "source_scope": availability_gap.SCOPE,
        "historical": True,
        "snapshot_day": "2026-08-20",
        "workspace": str(root),
        "submissions": "airports/gap/sec_edgar_GAP_submissions_current_20260821T001637Z.json",
        "filings": {
            accession: {
                "index": (
                    f"airports/gap/{accession}/sec_edgar_GAP_{accession}"
                    f"_index_{accession}_20260821T001637Z.json"
                ),
                "documents": {
                    name: (
                        f"airports/gap/{accession}/sec_edgar_GAP_{accession}"
                        f"_{name}_{accession}_20260821T001637Z.htm"
                    )
                },
            }
            for accession, name in availability_gap.PRIMARY.items()
        },
    }


def test_historical_preflight_requires_explicit_scope_and_complete_filing_roles():
    candidate = ROOT / "tmp/source-updates/test-gap-preflight-candidate"
    value = binding(ROOT / "tmp/source-updates/test-gap-preflight-dossier")
    assert availability.preflight(value, candidate).name == "test-gap-preflight-dossier"
    for key, changed in [("historical", False), ("source_scope", "current"), ("snapshot_day", "2026-10-27")]:
        invalid = {**value, key: changed}
        with pytest.raises(ValueError):
            availability.preflight(invalid, candidate)
    invalid = {**value, "filings": {availability_gap.SELECTED: value["filings"][availability_gap.SELECTED]}}
    with pytest.raises(ValueError, match="every later"):
        availability.preflight(invalid, candidate)
    borrowed = json.loads(json.dumps(value))
    borrowed["filings"][availability_gap.LATER]["index"] = borrowed["submissions"]
    with pytest.raises(ValueError, match="borrow"):
        availability.preflight(borrowed, candidate)
    assert not candidate.exists()


@pytest.fixture
def physical(monkeypatch):
    import pandas as pd

    root = ROOT / "tmp/source-updates" / ("pytest-gap-physical-" + uuid4().hex)
    dossier, candidate = root / "dossier", root / "candidate"
    proposal = binding(dossier)
    bronze = dossier / "data/bronze"
    records = []

    def put(relative, body, url, stamp):
        path = bronze / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        row = dict(
            source_file=relative,
            source_system="sec_edgar",
            source_url=url,
            sha256=availability_gap.sha(path),
            bytes=len(body),
            http_status=200,
            download_method="httpx",
            downloaded_at=stamp,
        )
        Path(str(path) + ".meta.json").write_text(json.dumps(row))
        records.append(row)

    submissions = dict(
        cik="0001347557",
        name="Pacific Airport Group",
        filings=dict(
            files=[],
            recent=dict(
                accessionNumber=[availability_gap.LATER, availability_gap.SELECTED],
                filingDate=["2026-08-07", "2026-08-06"],
                reportDate=["2026-08-06", "2026-08-05"],
                form=["6-K", "6-K"],
                primaryDocument=[
                    availability_gap.PRIMARY[availability_gap.LATER],
                    availability_gap.PRIMARY[availability_gap.SELECTED],
                ],
            ),
        ),
    )
    put(
        proposal["submissions"],
        json.dumps(submissions).encode(),
        availability_gap.SUBMISSIONS,
        "2026-08-21T00:16:37Z",
    )
    for accession, entry in proposal["filings"].items():
        filename = availability_gap.PRIMARY[accession]
        body = b"<html><body>Synthetic contract disclosure only</body></html>"
        if accession == availability_gap.LATER:
            import hashlib

            monkeypatch.setattr(availability_gap, "NON_TRAFFIC_SHA", hashlib.sha256(body).hexdigest())
        directory = dict(
            directory={
                "name": f"/Archives/edgar/data/1347557/{accession.replace('-', '')}",
                "parent-dir": "/Archives/edgar/data/1347557",
                "item": [
                    *[
                        dict(name=accession + s, type="text.gif", size="")
                        for s in ("-index-headers.html", "-index.html", ".txt")
                    ],
                    dict(name=filename, type="text.gif", size=str(len(body))),
                ],
            }
        )
        put(
            entry["index"],
            json.dumps(directory).encode(),
            availability_gap.base_url(accession) + "index.json",
            "2026-08-21T00:16:38Z",
        )
        put(
            entry["documents"][filename],
            body,
            availability_gap.base_url(accession) + filename,
            "2026-08-21T00:16:39Z",
        )
    (bronze / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    selected = proposal["filings"][availability_gap.SELECTED]["documents"][
        availability_gap.PRIMARY[availability_gap.SELECTED]
    ]
    selected_record = next(r for r in records if r["source_file"] == selected)
    native = candidate / "data/silver/airport_group_native.parquet"
    native.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            dict(
                source_file=selected,
                source_hash=selected_record["sha256"],
                source_system="sec_edgar",
                operator_group="GAP",
            )
        ]
    ).to_parquet(native, index=False)
    run_id = "a" * 32
    receipt = candidate / "receipts"
    receipt.mkdir()
    (receipt / f"retained-{run_id}.json").write_text(json.dumps({"status": "retained_unvalidated"}))
    (receipt / "airport-group-gap_traffic-2026M07.json").write_text(
        json.dumps(
            dict(
                status="checks_passed",
                retention_run_id=run_id,
                effective_as_of=CUTOFF,
                activation="none",
                publication="not_authorized",
            )
        )
    )
    result = dict(
        status="checks_passed",
        complete_month_certified=True,
        output_sha256={"fixture_native_only": availability_gap.sha(native)},
        code_sha256="a" * 64,
        activation="none",
        publication="not_authorized",
    )
    monkeypatch.setattr(airport_group_candidate, "run", lambda *a, **kw: result)
    item = dict(
        id="gap",
        product="gap_traffic",
        period="2026M07",
        adapter="airport_group",
        workspace=str(candidate),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
        availability=proposal,
    )
    yield root, item, result
    shutil.rmtree(root)


def rewrite(physical, relative, transform):
    """Keep physical metadata consistent so each attack tests semantics, not a stale hash."""
    root, _, _ = physical
    bronze = root / "dossier/data/bronze"
    path = bronze / relative
    payload = transform(path.read_bytes())
    path.write_bytes(payload)
    records = [json.loads(line) for line in (bronze / "_manifest.jsonl").read_text().splitlines()]
    row = next(r for r in records if r["source_file"] == relative)
    row.update(sha256=availability_gap.sha(path), bytes=len(payload))
    Path(str(path) + ".meta.json").write_text(json.dumps(row))
    (bronze / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))


def test_contract_history_binds_five_artifacts_and_round_replay_without_writes(physical):
    root, item, result = physical
    before = readiness.inventory(root)
    evidence = availability.verify(item, result, CUTOFF)
    assert evidence["historical"] and not evidence["current_availability_verified"]
    assert evidence["latest_available_period"] == "2026M07"
    assert evidence["source_artifact_sha256"]
    assert len(evidence["filing_indexes_sha256"]) == 2
    replayed = readiness.check_task(item, CUTOFF, CUTOFF)
    assert replayed["latest_source_availability_verified"]
    assert replayed["source_availability_evidence"]["historical"]
    assert before == readiness.inventory(root)


def test_contract_actual_round_cutoff_cannot_relabel_history_as_current(physical):
    from src.source_updates import global_readiness

    root, item, _ = physical
    recipe = dict(version=1, as_of="2026-10-27T06:00:00-06:00", required_items=["gap"], items=[item])
    before = readiness.inventory(root)
    with pytest.raises(ValueError, match="another round date"):
        global_readiness.verify(item, root.parent / (root.name + "-global"), recipe["as_of"])
    output = readiness.execute(recipe, root.parent / (root.name + "-round"), write=True)
    try:
        assert output["status"] == "blocked_required_source"
        assert "another round date" in output["results"][0]["reason"]
        assert not output["ready_for_review"]
        assert before == readiness.inventory(root)
    finally:
        shutil.rmtree(root.parent / (root.name + "-round"))


@pytest.mark.parametrize(
    "attack",
    [
        "amendment",
        "issuer",
        "duplicate_accession",
        "archived_history",
        "size",
        "index_identity",
        "index_type",
        "unknown_annex",
        "changed_management",
        "opaque_link",
        "dynamic_content",
        "native_identity",
    ],
)
def test_contract_semantic_attacks_fail_closed_even_with_updated_hashes(physical, attack):
    root, item, result = physical
    b = item["availability"]
    if attack in {"amendment", "archived_history", "issuer", "duplicate_accession"}:

        def mutate(raw):
            value = json.loads(raw)
            if attack == "archived_history":
                value["filings"]["files"] = [{"name": "unverified-history.json"}]
            elif attack == "issuer":
                value["cik"] = "0001123452"
            elif attack == "duplicate_accession":
                value["filings"]["recent"]["accessionNumber"][0] = availability_gap.SELECTED
            else:
                recent = value["filings"]["recent"]
                for key, token in {
                    "accessionNumber": "0001171843-26-005500",
                    "filingDate": "2026-08-08",
                    "reportDate": "2026-08-08",
                    "form": "6-K/A",
                    "primaryDocument": "amendment.htm",
                }.items():
                    recent[key].append(token)
            return json.dumps(value).encode()

        rewrite(physical, b["submissions"], mutate)
    elif attack in {"size", "unknown_annex", "index_identity", "index_type"}:

        def mutate(raw):
            value = json.loads(raw)
            entries = value["directory"]["item"]
            if attack == "index_identity":
                value["directory"]["name"] = "/Archives/edgar/data/1123452/000117184326005334"
            elif attack == "index_type":
                entries[0]["type"] = "directory"
            elif attack == "size":
                next(v for v in entries if v["name"] == availability_gap.PRIMARY[availability_gap.LATER])[
                    "size"
                ] = "1"
            else:
                entries.append({"name": "additional.htm", "type": "text.gif", "size": "10"})
            return json.dumps(value).encode()

        rewrite(physical, b["filings"][availability_gap.LATER]["index"], mutate)
    elif attack in {"changed_management", "opaque_link", "dynamic_content"}:
        filename = availability_gap.PRIMARY[availability_gap.LATER]
        relative = b["filings"][availability_gap.LATER]["documents"][filename]
        rewrite(
            physical,
            relative,
            lambda raw: (
                raw
                + (
                    b"<p>unreviewed appended content</p>"
                    if attack == "changed_management"
                    else b'<script src="https://issuer.test/unknown"></script>'
                    if attack == "dynamic_content"
                    else b'<a href="attachment">document</a>'
                )
            ),
        )
        size = (root / "dossier/data/bronze" / relative).stat().st_size

        def mutate(raw):
            value = json.loads(raw)
            next(v for v in value["directory"]["item"] if v["name"] == filename)["size"] = str(size)
            return json.dumps(value).encode()

        rewrite(physical, b["filings"][availability_gap.LATER]["index"], mutate)
    else:
        import pandas as pd

        path = root / "candidate/data/silver/airport_group_native.parquet"
        frame = pd.read_parquet(path)
        frame["source_hash"] = "b" * 64
        frame.to_parquet(path, index=False)
    with pytest.raises(ValueError):
        availability.verify(item, result, CUTOFF)


def test_contract_missing_index_http_failure_and_raw_tamper_are_never_empty_success(physical):
    root, item, result = physical
    path = root / "dossier/data/bronze" / item["availability"]["filings"][availability_gap.LATER]["index"]
    original = path.read_bytes()
    path.unlink()
    with pytest.raises(ValueError, match="indexes missing"):
        availability.verify(item, result, CUTOFF)
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="exact successful"):
        availability.verify(item, result, CUTOFF)
    path.write_bytes(original)
    bronze = root / "dossier/data/bronze"
    records = [json.loads(line) for line in (bronze / "_manifest.jsonl").read_text().splitlines()]
    row = next(r for r in records if r["source_file"] == path.relative_to(bronze).as_posix())
    row["http_status"] = 403
    Path(str(path) + ".meta.json").write_text(json.dumps(row))
    (bronze / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    with pytest.raises(ValueError, match="exact successful"):
        availability.verify(item, result, CUTOFF)

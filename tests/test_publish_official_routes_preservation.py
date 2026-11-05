"""Legacy assemblers must not replace a site by dropping the official map or its proof."""

import pytest

from src.publish import gate, manifest
from src.publish import source_data_scope as scope
from src.publish.official_routes_preservation import CONTRACT, PROOF, PUBLIC_PATH


def write_file(site, path, raw=b"retained"):
    target = site / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


@pytest.mark.parametrize("missing", [PUBLIC_PATH, PROOF, CONTRACT])
def test_replacement_requires_map_contract_and_proof(tmp_path, missing):
    site = tmp_path / "site"
    dist = tmp_path / "dist"
    write_file(site, PUBLIC_PATH)
    write_file(site, PROOF)
    for path in [PUBLIC_PATH, PROOF]:
        if path != missing:
            write_file(dist, path)
    contracts = {} if missing == CONTRACT else {CONTRACT: "a" * 64}

    with pytest.raises(gate.PublicationRefused, match="published official routes"):
        gate.assemble_site(dist, [], site, contracts=contracts)

    assert (site / PUBLIC_PATH).read_bytes() == b"retained"
    assert (site / PROOF).read_bytes() == b"retained"
    assert not list(tmp_path.glob("site.tmp-*"))


def test_manifest_pin_also_guards_missing_local_map(tmp_path):
    site = tmp_path / "site"
    dist = tmp_path / "dist"
    write_file(site, PUBLIC_PATH)
    baseline = manifest.build_manifest(site, [], contracts={CONTRACT: "a" * 64})
    manifest.write_manifest(site, baseline)
    (site / PUBLIC_PATH).unlink()
    write_file(dist, "index.html")

    with pytest.raises(gate.PublicationRefused, match="published official routes"):
        gate.assemble_site(dist, [], site, contracts={})

    assert manifest.load_manifest(site) == baseline


def test_typed_replacement_with_official_provenance_still_uses_its_validator(tmp_path):
    site = tmp_path / "site"
    dist = tmp_path / "dist"
    for path in [PUBLIC_PATH, PROOF]:
        write_file(site, path)
        write_file(dist, path)
    write_file(dist, "executive.json", b"new")
    contracts = {CONTRACT: "a" * 64}
    validated = []

    def validate_candidate(candidate):
        assert (candidate / PUBLIC_PATH).read_bytes() == (site / PUBLIC_PATH).read_bytes()
        assert (candidate / PROOF).read_bytes() == (site / PROOF).read_bytes()
        validated.append(manifest.load_manifest(candidate)["contracts"])

    gate.assemble_site(dist, [], site, contracts=contracts, validate_candidate=validate_candidate)

    assert validated == [contracts]
    assert (site / "executive.json").read_bytes() == b"new"


def test_existing_premap_site_with_dormant_contract_can_still_rebuild(tmp_path):
    site = tmp_path / "site"
    dist = tmp_path / "dist"
    contracts = {CONTRACT: "a" * 64}
    write_file(site, "index.html", b"previous")
    manifest.write_manifest(site, manifest.build_manifest(site, [], contracts=contracts))
    write_file(dist, "index.html", b"new")

    gate.assemble_site(dist, [], site, contracts=contracts)

    assert (site / "index.html").read_bytes() == b"new"


def test_later_monthly_release_revalidates_retained_map_with_replaced_receipt(tmp_path, monkeypatch):
    site = tmp_path / "site"
    dist = tmp_path / "dist"
    target = "data/v1/executive.json"
    originals = {PUBLIC_PATH: b"{}", PROOF: b"prior receipt", target: b"{}", "index.html": b"<html>"}
    for path, raw in originals.items():
        write_file(site, path, raw)
    contracts = {CONTRACT: "a" * 64}
    thesis = dict(entity_key="AEROMEXICO", period_id="2026Q3", version="original")
    old = manifest.build_manifest(site, [thesis], contracts=contracts)
    manifest.write_manifest(site, old)
    outputs = {target: b'{"updated":true}'}
    spec = dict(
        product="am_traffic_ir",
        period_id="2026M10",
        projection={},
        source_binding=dict(
            product="am_traffic_ir",
            period="2026M10",
            receipt_id="a" * 32,
            candidate_as_of="2026-11-05",
            output_sha256={"candidate": "b" * 64},
        ),
        baseline_commit="c" * 40,
        baseline_manifest_sha256="d" * 64,
        contract_changes={},
        data_files=scope.pins(outputs),
        frontend_files=scope.transport.frontend_entries(site),
    )
    anchor = scope.encoded(spec)
    write_file(tmp_path, scope.ANCHOR, anchor)
    write_file(dist, "index.html", originals["index.html"])
    write_file(dist, PUBLIC_PATH, originals[PUBLIC_PATH])
    write_file(dist, target, outputs[target])
    write_file(
        dist,
        PROOF,
        scope.encoded(
            dict(
                schema_version="source_data_publication_v1",
                anchor_sha256=scope.sha(anchor),
                remote_witness=dict(
                    baseline_commit=spec["baseline_commit"],
                    manifest_sha256=spec["baseline_manifest_sha256"],
                    files_verified=len(old["files"]),
                    origin=scope.transport.ORIGIN,
                    deployment_run=1,
                    deployment_commit=spec["baseline_commit"],
                ),
            )
        ),
    )
    monkeypatch.setattr(scope.transport, "baseline", lambda *_: (old, b""))
    monkeypatch.setattr(
        scope.transport,
        "_git",
        lambda _repo, op, *args: originals[args[0].split(":site/")[1]] if op == "show" else b"",
    )
    monkeypatch.setattr(scope.members, "target_names", lambda *_: {target})
    monkeypatch.setattr(scope.members, "compose", lambda *_: outputs)

    def validate(candidate):
        assert scope.preserved_files(candidate, tmp_path, spec) == {PUBLIC_PATH}

    gate.assemble_site(dist, [thesis], site, contracts=contracts, validate_candidate=validate)
    assert (site / PUBLIC_PATH).read_bytes() == originals[PUBLIC_PATH]
    assert (site / PROOF).read_bytes() != originals[PROOF]

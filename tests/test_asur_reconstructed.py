"""Contract cases only: synthetic counts never establish the real reconstruction."""

from copy import deepcopy

import pytest

from src.source_updates.airport_group_native import ASUR
from src.source_updates.asur_reconstructed import ALIAS, URL, parse_tables


def source():
    return dict(
        source_system=ALIAS,
        source_url=URL,
        source_file="asur/derived.csv",
        sha256="a" * 64,
        downloaded_at="2026-10-28T02:00:00Z",
    )


def tables():
    def row(label, counts, name=None):
        a, b, c, d = map(str, counts)
        return [label] + ([name] if name else []) + [a, b, "0.0", "", c, d, "0.0"]

    dom = {code: [i, i + 1, i * 10, (i + 1) * 10] for i, code in enumerate(ASUR, 10)}
    intl = {code: [i, i + 2, i * 10, (i + 2) * 10] for i, code in enumerate(ASUR, 20)}
    total = {code: [a + b for a, b in zip(dom[code], intl[code], strict=True)] for code in ASUR}
    mx = {
        m: [sum(v[c] for v in domain.values()) for c in range(4)]
        for m, domain in (("domestic", dom), ("international", intl), ("total", total))
    }
    groups = [("Mexico", mx)]
    for label, scale in (("Brazil and Others", 1), ("San Juan, Puerto Rico", 4), ("Colombia", 5)):
        domestic = [100 * scale, 110 * scale, 100 * scale, 110 * scale]
        international = [20 * scale, 25 * scale, 20 * scale, 25 * scale]
        groups.append(
            (
                label,
                {
                    "domestic": domestic,
                    "international": international,
                    "total": [a + b for a, b in zip(domestic, international, strict=True)],
                },
            )
        )
    groups.append(
        (
            "Total Traffic",
            {
                m: [sum(g[m][c] for _, g in groups) for c in range(4)]
                for m in ("domestic", "international", "total")
            },
        )
    )
    summary = []
    for label, g in groups:
        summary.extend(
            [
                row(label, g["total"]),
                row("Domestic Traffic", g["domestic"]),
                row("International Traffic", g["international"]),
            ]
        )
    mexico = []
    for label, market, domain in (
        ("Domestic Traffic", "domestic", dom),
        ("International Traffic", "international", intl),
        ("Traffic Total Mexico", "total", total),
    ):
        mexico.append(row(label, mx[market]))
        mexico.extend(row(code, domain[code], name) for code, name in ASUR.items())
    return summary, mexico


def test_reconstruction_scope_and_count_contract():
    frame, proof = parse_tables(*tables(), source())
    assert len(frame) == 168 and proof["reconciliations"] == 92
    assert proof["is_original_SEC_HTML"] is False
    assert proof["upstream_original_sha256"] is None
    assert frame.is_reconstruction.all() and frame.source_representation.nunique() == 1
    ambiguous = frame.entity_key.isin(["CPC", "ALL"]) & ~frame.period_type.eq("month")
    assert ambiguous.sum() == 12
    assert set(frame.loc[ambiguous].period_type) == {"reported_ytd_coverage_unverified"}
    assert not frame.loc[ambiguous].coverage_start_known.any()
    assert frame.loc[frame.entity_key.eq("CPC")].airport_iata.isna().all()
    mx = frame.loc[frame.country.eq("MX")]
    assert len(mx) == 120
    assert mx.coverage_start_known.equals(mx.period_type.eq("month"))
    assert proof["complete_month_scope"] == "nine_Mexico_airports_and_reported_summary_counts"


def test_reconstruction_rejects_material_errors_without_zero_fill_or_source_relabel():
    summary, mexico = tables()
    failures = []
    for target, row, col, value in [
        ("summary", 0, 1, "999999"),
        ("summary", 3, 0, "Brazil"),
        ("summary", 4, 1, "-"),
        ("summary", 4, 1, "1.5"),
        ("mexico", 0, 1, "999999"),
        ("mexico", 1, 0, "NOPE"),
        ("mexico", 2, 0, "CUN"),
        ("mexico", 1, 2, "-"),
    ]:
        a, b = deepcopy(summary), deepcopy(mexico)
        (a if target == "summary" else b)[row][col] = value
        failures.append((a, b, source()))
    failures.extend(
        (summary, mexico, {**source(), **change})
        for change in [
            {"source_system": "sec_edgar"},
            {"source_url": URL + "?other"},
            {"downloaded_at": "2026-09-30T00:00:00Z"},
        ]
    )
    failures.extend([(summary[:-1], mexico, source()), (summary, mexico[:-1], source())])
    for args in failures:
        with pytest.raises(ValueError):
            parse_tables(*args)


def test_reconstruction_cannot_borrow_original_or_other_product_roles():
    from src.source_updates.airport_group_native import read
    from src.source_updates.asur_reconstruction_inputs import decode
    from src.source_updates.retained_registry import spec

    definition = spec("asur_traffic")
    assert definition["roles"]["html"] == ("sec", "sec_edgar", "sec_filing")
    assert ALIAS not in definition["roles"]["html"]
    for product, roles, period in [
        ("gap_traffic", {"reconstruction_json": (b"{}", source())}, "2026M09"),
        ("asur_traffic", {"reconstruction_json": (b"{}", source())}, "2026M09"),
        ("asur_traffic", {"html": (b"<html></html>", source())}, "2026M09"),
    ]:
        with pytest.raises(ValueError):
            read(product, roles, period)
    with pytest.raises(ValueError):
        decode({"reconstruction_json": b"{}"})


def test_reconstructed_alias_is_not_a_generic_SEC_capture_permission():
    from pathlib import Path

    from src.source_updates.catalog import ROOT
    from src.source_updates.collection import selection_plan

    for product in ("asur_traffic", "gap_traffic", "volaris_sec"):
        selection = {
            "version": 1,
            "items": [
                {
                    "id": "derived-not-original",
                    "product": product,
                    "source_system": ALIAS,
                    "url": URL,
                    "entity": "ASUR",
                    "period": "2026M09",
                    "extension": "json",
                    "purpose": "data",
                    "mode": "manual",
                    "local_file": "edited.json",
                    "sha256": "a" * 64,
                }
            ],
        }
        with pytest.raises(ValueError):
            selection_plan(selection, ROOT / Path("tmp/source-updates/asur-generic-rejection"))


def test_reconstruction_binding_is_narrow_and_disjoint():
    from src.source_updates.availability_asur_reconstructed import SCOPE, preflight
    from src.source_updates.catalog import ROOT

    root = ROOT / "tmp/source-updates/asur-binding-inputs"
    candidate = ROOT / "tmp/source-updates/asur-binding-candidate"
    binding = dict(source_scope=SCOPE, workspace=str(root), run_id="a" * 32)
    assert preflight(binding, candidate) == root
    for changed, target in [
        ({**binding, "original_SEC_hash": "b" * 64}, candidate),
        ({**binding, "run_id": "../other"}, candidate),
        (binding, root),
        (binding, root / "nested"),
    ]:
        with pytest.raises(ValueError):
            preflight(changed, target)


def test_reconstruction_provenance_cannot_claim_HTTP_original_or_change_observation():
    from src.source_updates.asur_reconstruction_inputs import FILES, OBSERVED_AT, validate_record

    role = "reconstruction_json"
    name, size, sha, mime = FILES[role]
    row = {
        **source(),
        "representation_role": role,
        "source_file": "asur/reconstructed/" + name,
        "bytes": size,
        "sha256": sha,
        "content_type": mime,
        "timestamp_semantics": "local_import_not_SEC_HTTP_capture",
        "source_url_role": "upstream_visible_reference_not_artifact_download_URL",
        "source_observed_at": OBSERVED_AT,
        "logical_key": f"{ALIAS}|ASUR_{role}|2026M09|json",
        "logical_version": 1,
        "filename_version": 1,
        "is_content_alias": False,
        "download_method": "authorized_visible_reconstruction_import",
        "http_status": 0,
        "source_http_status": None,
        "representation_kind": "authorized_visible_reconstruction",
        "source_original_sha256": None,
        "source_original_bytes_acquired": False,
    }
    validate_record(row)
    for change in [
        {"timestamp_semantics": "SEC_HTTP_capture"},
        {"source_url_role": "downloaded_original_SEC_URL"},
        {"source_observed_at": "2026-10-28T12:00:00Z"},
        {"content_type": "application/pdf"},
        {"logical_key": "wrong"},
        {"source_http_status": 200},
        {"source_original_sha256": "b" * 64},
    ]:
        with pytest.raises(ValueError):
            validate_record({**row, **change})


def test_reconstruction_false_Library_identity_set_is_not_accepted():
    from src.source_updates.asur_reconstruction_inputs import FILES, validate_library_identities

    for identities in ({k: "libfile_" + "0" * 32 for k in FILES}, {}):
        with pytest.raises(ValueError):
            validate_library_identities(identities)


def test_reconstruction_import_receipt_cannot_renew_source_observation(monkeypatch):
    import hashlib
    import json
    from uuid import uuid4

    from src.source_updates import availability_asur_reconstructed as subject
    from src.source_updates.catalog import ROOT

    root = ROOT / "tmp/source-updates" / ("asur-observation-regression-" + uuid4().hex)
    (root / "receipts").mkdir(parents=True)
    (root / "data/bronze").mkdir(parents=True)
    (root / "data/bronze/_manifest.jsonl").write_text("")
    shifted = "2026-10-28T12:00:00Z"  # Next Mexico day; immutable source observation was previous day.
    receipt = dict(
        mode="reconstruction_import",
        status="imported_reconstruction_unvalidated",
        product="asur_traffic",
        period="2026M09",
        run_id="a" * 32,
        source_representation="authorized_visible_reconstruction",
        is_original_SEC_HTML=False,
        source_original_sha256=None,
        network_requests=0,
        activation="none",
        publication="not_authorized",
        source_observed_at=shifted,
        imported_at="2026-10-28T02:06:32Z",
        manifest_sha256=hashlib.sha256(b"").hexdigest(),
    )
    (root / "receipts" / ("asur-reconstruction-import-" + "a" * 32 + ".json")).write_text(json.dumps(receipt))

    def do_not_reach(_):
        raise AssertionError("Forged next-day observation reached physical certification")

    monkeypatch.setattr(subject, "verify_bronze", do_not_reach)
    item = dict(
        product="asur_traffic",
        adapter="airport_group",
        period="2026M09",
        candidate_as_of="2026-10-28T02:09:26Z",
        workspace=str(root.parent / (root.name + "-candidate")),
        availability=dict(source_scope=subject.SCOPE, workspace=str(root), run_id="a" * 32),
    )
    result = dict(
        status="checks_passed",
        product="asur_traffic",
        period="2026M09",
        source_representation="authorized_visible_reconstruction",
        effective_as_of=item["candidate_as_of"],
    )
    with pytest.raises(ValueError):
        subject.verify(item, result, "2026-10-28T13:00:00Z")

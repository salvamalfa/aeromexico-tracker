"""Test consumers follow exact issuer history instead of freezing the entire site."""

import io
import json
import os
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path

from scripts.check_pages_publication import VERIFIERS, verifier_for
from src.publish import issuer_scope, movements_scope, source_data_scope
from src.publish.editorial import _git
from src.publish.financial_scope import encoded, sha
from src.publish.issuer_projection import require_scope


def verify_current_publication(site, repo, financial_checker, *, base_commit=None):
    module = verifier_for(site, repo)
    if module == "src.publish.afac_history_scope":
        from src.publish.afac_history_scope import verify_afac_history

        problems = verify_afac_history(site, repo)
    elif module == "src.publish.quarterly_story_scope":
        from src.publish.quarterly_story_scope import verify_story

        problems = verify_story(site, repo)
    elif module == "src.publish.source_data_scope":
        if base_commit:
            from tests._financial_publication_history import verify_published

            problems = verify_published(site, repo, base_commit=base_commit, module=module)
        else:
            problems = source_data_scope.verify_source_data(site, repo)
    elif module == "src.publish.movements_scope":
        problems = movements_scope.verify_movements(site, repo)
    elif module == "src.publish.issuer_scope":
        problems = issuer_scope.verify_issuer(site, repo)
    elif module == "src.publish.financial_scope":
        problems = financial_checker(site, repo)
    elif module == "src.publish.editorial":
        from src.publish.editorial import verify_editorial

        problems = verify_editorial(site, repo)
    elif module == "src.publish.verify":
        from src.publish.verify import verify_site

        problems = verify_site(site)
    else:
        raise AssertionError("Unsupported strict publication verifier: " + module)
    assert not problems, problems


@contextmanager
def official_map_baseline(site, repo, financial_checker, *, base_commit=None):
    """Select the historical site for financial/editorial parity of a map-only overlay."""
    if (
        not (site / "data/v1/official-routes.json").is_file()
        or verifier_for(site, repo) != "src.publish.source_data_scope"
    ):
        yield site
        return
    spec = source_data_scope.anchor(repo)
    if spec["product"] != "official_routes":
        yield site
        return
    if base_commit:
        verify_current_publication(site, repo, financial_checker, base_commit=base_commit)
    else:
        from src.analysis_agent.entity_adapter import code_version
        from src.publish.verify import _verify_site

        # Pages preflight replays the entire chain. Here verify the active
        # overlay and let the parity assertions replay its historical edition.
        assert code_version() == spec["producer_code_version"]
        preserved = source_data_scope.preserved_files(site, repo, spec)
        problems = _verify_site(site, preserved_approval_files=preserved)
        assert not problems, problems
    _, raw = source_data_scope.transport.baseline(repo, spec)
    archive = _git(repo, "archive", spec["baseline_commit"], "site")
    with tempfile.TemporaryDirectory(prefix="parity-before-official-map-") as folder:
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(folder, filter="data")
        previous = Path(folder) / "site"
        assert (previous / "publication_manifest.json").read_bytes() == raw
        yield previous


def _active_module(site, repo, manifest, commit):
    if commit is None:
        return verifier_for(site, repo)
    # Only selector inputs are materialized here; the strict current verifier
    # already replays the complete released baseline chain.
    with tempfile.TemporaryDirectory(prefix="parity-proof-") as temporary:
        archive = Path(temporary)
        (archive / "publication_manifest.json").write_bytes(encoded(manifest))
        names = {item["path"] for item in manifest["files"]}
        for proof, _ in VERIFIERS:
            if proof in names:
                (archive / proof).write_bytes(_git(repo, "show", f"{commit}:site/{proof}"))
        return verifier_for(archive, repo)


def _preserved_nonfinancial_financials(site, repo, manifest, commit, spec, label):
    previous = spec["baseline_commit"]
    raw = _git(repo, "show", f"{previous}:site/publication_manifest.json")
    assert sha(raw) == spec["baseline_manifest_sha256"]
    before = json.loads(raw)
    assert len(before["analysis_manifest"]) == 7
    assert manifest["analysis_manifest"] == before["analysis_manifest"], f"{label} changed approvals"
    readings = [item for item in before["files"] if item["path"].startswith("data/v1/analysis/")]
    assert len(readings) == 7, f"{label} baseline is missing a financial thesis"
    for item in readings:
        actual = (
            (site / item["path"]).read_bytes()
            if commit is None
            else _git(repo, "show", f"{commit}:site/{item['path']}")
        )
        assert sha(actual) == item["sha256"] and len(actual) == item["bytes"], item["path"]
    return before


def preserved_financial_projection(site, repo, financial_spec):
    """Every later delta must be its exact reviewed issuer slot, not a whitelist.

    The caller also invokes the strict current verifier, which checks each
    released baseline with its own pinned producer and immutable file manifest.
    Here each financial delta is checked structurally, including prior issuer
    releases, before comparing the complete original financial source replay.
    """
    current_raw = (site / issuer_scope.EXECUTIVE).read_bytes()
    current = json.loads(current_raw)
    manifest = json.loads((site / "publication_manifest.json").read_bytes())
    commit = None
    seen = set()
    nonfinancial = {
        "src.publish.movements_scope": (movements_scope, "Movement correction"),
        "src.publish.source_data_scope": (source_data_scope, "Source data update"),
    }
    while sha(encoded(current)) != financial_spec["executive_sha256"] or {
        movements_scope.PROOF,
        source_data_scope.PROOF,
    } & {item["path"] for item in manifest["files"]}:
        module = _active_module(site, repo, manifest, commit)
        if module in {"src.publish.quarterly_story_scope", "src.publish.afac_history_scope"}:
            from tests._quarterly_story_parity import industry_projection, publication

            assert commit is None, "Historical story editions need their own pinned scope consumer"
            spec, before_manifest, before = publication(site, repo)
            industry_projection(before, current)
            previous = spec["baseline_commit"]
            assert previous not in seen, "Cyclic story baseline"
            seen.add(previous)
            current_raw = _git(repo, "show", f"{previous}:site/{issuer_scope.EXECUTIVE}")
            current, manifest, commit = before, before_manifest, previous
            continue
        if module in nonfinancial:
            scope, label = nonfinancial[module]
            assert scope.PROOF in {item["path"] for item in manifest["files"]}, (
                f"Unreviewed {label.lower()} without its own receipt"
            )
            spec = json.loads(
                (repo / scope.ANCHOR).read_bytes()
                if commit is None
                else _git(repo, "show", f"{commit}:{scope.ANCHOR}")
            )
            previous = spec["baseline_commit"]
            assert previous not in seen, "Cyclic publication baseline"
            seen.add(previous)
            before_raw = _git(repo, "show", f"{previous}:site/{issuer_scope.EXECUTIVE}")
            assert current_raw == before_raw, f"{label} changed financial bytes"
            manifest = _preserved_nonfinancial_financials(site, repo, manifest, commit, spec, label)
            current_raw, current, commit = before_raw, json.loads(before_raw), previous
            continue
        assert module == "src.publish.issuer_scope", "Unreviewed financial publication profile"
        assert issuer_scope.PROOF in {item["path"] for item in manifest["files"]}, (
            "Unreviewed financial delta without an issuer receipt"
        )
        raw = (
            (repo / issuer_scope.ANCHOR).read_bytes()
            if commit is None
            else _git(repo, "show", f"{commit}:{issuer_scope.ANCHOR}")
        )
        spec = json.loads(raw)
        assert sha(encoded(current)) == spec["executive_sha256"], "Issuer output pin differs"
        assert len(encoded(current)) == spec["executive_bytes"]
        previous = spec["baseline_commit"]
        assert previous not in seen, "Cyclic issuer baseline"
        seen.add(previous)
        before_raw = _git(repo, "show", f"{previous}:site/{issuer_scope.EXECUTIVE}")
        before = json.loads(before_raw)
        if spec["stage"] == "editorial_only":
            assert current == before, "Editorial stage changed financial data"
        else:
            require_scope(before, current, spec["entity_key"], spec["period_id"])
        manifest_raw = _git(repo, "show", f"{previous}:site/publication_manifest.json")
        assert sha(manifest_raw) == spec["baseline_manifest_sha256"]
        manifest = json.loads(manifest_raw)
        current_raw, current, commit = before_raw, before, previous
    assert len(encoded(current)) == financial_spec["executive_bytes"]
    return current


def preserved_readings(site: Path, repo: Path, financial_spec):
    """Protect every original reading, not just the selected current issuer."""
    manifest = json.loads(
        _git(repo, "show", f"{financial_spec['baseline_commit']}:site/publication_manifest.json")
    )
    current = json.loads((site / "publication_manifest.json").read_bytes())
    if (site / "quarterly-story-publication.json").exists():
        from tests._quarterly_story_parity import publication

        spec, _, _ = publication(site, repo)
        for entry in manifest["analysis_manifest"]:
            assert entry in spec["retained_analysis_manifest"] + spec["superseded_analysis_manifest"]
        assert len(manifest["analysis_manifest"]) == 5
        return
    for entry in manifest["analysis_manifest"]:
        assert entry in current["analysis_manifest"], "Historical approval changed"
    readings = [item for item in manifest["files"] if item["path"].startswith("data/v1/analysis/")]
    for item in readings:
        raw = (site / item["path"]).read_bytes()
        assert sha(raw) == item["sha256"] and len(raw) == item["bytes"], item["path"]
    assert len(readings) == 5


@contextmanager
def _published_approval_config_view(repo: Path, manifest_raw: bytes):
    """Read the configuration committed with this site, not a later pending pin.

    A detached, config-only worktree keeps every production provenance check
    intact and never edits the caller's working configuration. Source and ledger
    replay still use the ordinary pinned verifier and actual private inputs.
    """
    trusted = None
    for ref in ("origin/master", "HEAD"):
        candidate = subprocess.run(
            ["git", "show", f"{ref}:site/publication_manifest.json"],
            cwd=repo,
            capture_output=True,
        )
        if candidate.returncode == 0 and candidate.stdout == manifest_raw:
            trusted = subprocess.check_output(["git", "rev-parse", ref], cwd=repo, text=True).strip()
            break
    if trusted is None:
        raise ValueError("The verified site is not committed; commit the gate output before parity replay")
    with tempfile.TemporaryDirectory(prefix="parity-published-config-") as folder:
        view = Path(folder) / "checkout"
        subprocess.run(
            ["git", "worktree", "add", "--detach", "--no-checkout", str(view), trusted],
            cwd=repo,
            env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"},
            capture_output=True,
            check=True,
        )
        try:
            archive = subprocess.check_output(["git", "archive", trusted, "config/publish"], cwd=repo)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(view, filter="data")
            yield view, trusted
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(view)], cwd=repo, capture_output=True, check=True
            )


def _with_citation_labels(text: str, citations: list[dict]) -> str:
    """Port of narrative.ts::applyCitations' text-splicing, in plain text:
    each citation's label is inserted right after the first (in reading
    order) occurrence of its ``value`` -- the same substring the DOM ends
    up with once the <sup><a> citation marker is spliced in."""

    # Sources for a shared value append to its first marker group in input
    # order. Citation labels are never searched as narrative text.
    segments: list[str | tuple[str, str]] = [text]
    for citation in citations:
        marker_position = next(
            (
                i
                for i, segment in enumerate(segments)
                if isinstance(segment, tuple) and segment[0] == citation["value"]
            ),
            None,
        )
        if marker_position is not None:
            previous = segments[marker_position]
            segments[marker_position] = (citation["value"], previous[1] + citation["label"])
            continue
        for position, segment in enumerate(segments):
            if not isinstance(segment, str):
                continue
            index = segment.find(citation["value"])
            if index == -1:
                continue
            end = index + len(citation["value"])
            segments[position : position + 1] = [
                segment[:end],
                (citation["value"], citation["label"]),
                segment[end:],
            ]
            break
    return "".join(segment if isinstance(segment, str) else segment[1] for segment in segments)



def assert_reading_parity(site_page, site_server, expected):
    checked = set()
    for period_id in sorted({period for _, period in expected}):
        site_page.goto(f"{site_server}?period={period_id}")
        site_page.wait_for_function(
            "period => document.getElementById('narrative-copy').dataset.period === period && "
            "!document.getElementById('reading-full-card').hidden", arg=period_id,
        )
        site_page.click("#tab-reading")
        site_page.locator("#reading-full > summary").click()
        quarter = {entity: value for (entity, period), value in expected.items() if period == period_id}
        articles = site_page.locator("#reading-full-copy article[data-entity]")
        assert set(articles.evaluate_all("nodes => nodes.map(node => node.dataset.entity)")) == set(quarter)
        for entity, analysis in quarter.items():
            article = site_page.locator(f'#reading-full-copy article[data-entity="{entity}"]')
            assert analysis["thesis"] in article.locator("h3").inner_text()
            citations = {claim["claim_id"]: claim["citations"] for claim in analysis["claims"]}
            # The approved four-point overview selects short claims, while
            # the complete card below preserves every approved paragraph.
            items = analysis["summary_items"][:1]
            if entity == "AEROMEXICO":
                selected = [item for claim in ("sales", "fuel", "summary_business", "summary_unit")
                            for item in analysis["summary_items"] if item["claim_id"] == claim]
                items = selected[:2] or items
            elif entity == "INDUSTRY":
                items = [next(
                    (item for item in analysis["summary_items"] if item["claim_id"] == "s_revenue"), items[0],
                )]
            short = " ".join(item["text"].replace(item.get("lead") or "", "").strip()
                             if entity == "AEROMEXICO" and period_id == "2026Q3" else item["text"]
                             for item in items)
            sources = [citation for item in items for citation in citations[item["claim_id"]]]
            summary_index = ("INDUSTRY", "AEROMEXICO", "VIVA_AEROBUS", "VOLARIS").index(entity)
            summary = site_page.locator("#narrative-copy li").nth(summary_index).locator(":scope > span")
            assert summary.inner_text() == _with_citation_labels(short, sources)
            paragraphs = article.locator("section p")
            source_paragraphs = [
                (text, claim) for section in analysis["sections"]
                for text, claim in zip(section["paragraphs"], section["claim_ids"], strict=True)
            ]
            assert paragraphs.count() == len(source_paragraphs)
            for index, (text, claim) in enumerate(source_paragraphs):
                paragraph = paragraphs.nth(index)
                assert paragraph.inner_text() == _with_citation_labels(text, citations[claim])
                actual = paragraph.locator("a.source-note").evaluate_all(
                    "nodes => nodes.map(node => node.href)"
                )
                assert sorted(actual) == sorted(c["href"] for c in citations[claim])
            checked.add((entity, period_id))
    assert checked == set(expected), f"never reached {set(expected) - checked}"

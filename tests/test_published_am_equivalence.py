"""The no-change shortcut cannot erase changed financial meaning or framing."""

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from scripts import published_am_equivalence as bridge


def documents():
    body = (
        "Grupo Aeroméxico. Revenue 1,619; net income 41. Fuel +57.6%, margin 11.7%. "
        "Scope: quarter, USD millions, consolidated and unaudited. "
        "FootnotesSee Annex A. IFRS measure.Liquidity is defined by the revolving credit facility."
        "Premium share uses total passenger revenue."
    )
    old = "MEXICO CITY, Oct. 19, 2026 (GLOBE NEWSWIRE) --" + body + bridge.CONTACT
    new = (
        "Document"
        + bridge.CONTACT
        + bridge.TITLE
        + "Mexico City, Mexico, October 19, 2026-"
        + body
        + "".join(("" if n == 1 else str(n)) + "3Q26RESULTS" for n in range(1, 13))
        + "13"
    )
    for prefix, n in [
        ("Footnotes", 1),
        ("IFRS measure.", 2),
        ("revolving credit facility.", 3),
        ("total passenger revenue.", 4),
    ]:
        new = new.replace(prefix, prefix + f"({n})")
    return old, new


def test_known_layout_changes_preserve_the_entire_financial_body():
    proof = bridge.financial_body(*documents())
    assert proof["characters_compared"] > 200
    assert len(proof["financial_body_sha256"]) == 64


@pytest.mark.parametrize(
    "before,after",
    [
        ("net income 41", "net income -41"),
        ("11.7%", "117%"),
        ("1,619", "1,629"),
        ("USD millions", "MXN millions"),
        ("Scope: quarter", "Scope: nine months"),
        ("unaudited", "audited"),
        ("consolidated", "domestic only"),
        ("Fuel +57.6%", "Fuel -57.6%"),
        ("Grupo Aeroméxico", "Grupo Another Carrier"),
    ],
)
def test_changes_in_numbers_signs_units_period_or_scope_are_material(before, after):
    old, new = documents()
    assert before in new
    with pytest.raises(ValueError, match="changed financial"):
        bridge.financial_body(old, new.replace(before, after))


def test_new_qualitative_warning_is_material_even_when_old_text_is_unchanged():
    old, new = documents()
    with pytest.raises(ValueError, match="changed financial"):
        bridge.financial_body(old, new.replace("3Q26RESULTS", "New liquidity warning.3Q26RESULTS", 1))


@pytest.mark.parametrize(
    "before,after",
    [
        ("October 19, 2026", "October 29, 2026"),
        ("123Q26RESULTS", "123Q27RESULTS"),
        ("Footnotes(1)", "Footnotes(5)"),
    ],
)
def test_only_the_known_distribution_framing_can_be_removed(before, after):
    old, new = documents()
    with pytest.raises(ValueError):
        bridge.financial_body(old, new.replace(before, after))


def test_empty_or_duplicate_candidate_metrics_never_prove_equivalence():
    old = BeautifulSoup("<table></table>" * 13, "lxml")
    for rows in ([], [dict(metric_key="total_revenue")] * 20):
        frame = pd.DataFrame(rows, columns=["metric_key"])
        with pytest.raises(ValueError, match="twenty unique"):
            bridge.compare_twenty(frame, old)


def test_proof_inputs_cannot_follow_symlinks(tmp_path):
    original = tmp_path / "record.json"
    original.write_text("{}")
    alias = tmp_path / "record-alias.json"
    alias.symlink_to(original)
    with pytest.raises(ValueError, match="physical regular"):
        bridge.load(alias)

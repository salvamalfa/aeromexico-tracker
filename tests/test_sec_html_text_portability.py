"""SEC text extraction must not depend on the libxml2 build of the platform."""

from __future__ import annotations

from src.parse.sec.common import html_text


def test_c1_numeric_references_keep_their_literal_code_point() -> None:
    """&#149; is extracted as U+0095 everywhere, as the approved evidence records."""

    assert html_text(b"<p>Results &#149; Revenue &#x95; EBITDAR</p>") == "Results \x95 Revenue \x95 EBITDAR"


def test_other_references_are_untouched() -> None:
    assert html_text(b"<p>&#8226; &#8211; &#162; &aacute;</p>") == "• – ¢ á"
    assert html_text("<p>a • b</p>".encode()) == "a • b"

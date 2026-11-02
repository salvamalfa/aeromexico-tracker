"""Reject unknown document decoration instead of allowing a byte tolerance."""


import pytest

from src.source_updates.volaris_q3_original import document_bytes

TRAILER = b"</BODY>\n</HTML>\n</TEXT>\n</DOCUMENT>\n"
SCRIPT = (
    b'<script type="text/javascript"  src="/yt0Omj4t/iRa/njL/nRf-WhIKSa/'
    b'muuQGrJDQmrGwV/UQF7/dl4/HSHxhJkA"></script>'
)
DOCUMENT = b"<DOCUMENT>\n<HTML><BODY><table><tr><td>42</td></tr></table>\n" + TRAILER


def decorated(script=SCRIPT):
    return DOCUMENT[: -len(TRAILER)] + script + TRAILER


def test_original_bytes_and_single_typed_sec_transport_decoration():
    assert document_bytes(DOCUMENT, len(DOCUMENT)) == DOCUMENT
    original_response = decorated()
    assert len(SCRIPT) == 109
    assert document_bytes(original_response, len(DOCUMENT)) == DOCUMENT
    assert original_response == decorated()  # raw bytes remain intact


@pytest.mark.parametrize(
    "raw",
    [
        decorated(SCRIPT + SCRIPT),
        decorated(SCRIPT.replace(b"></script>", b">alert(1)</script>")),
        decorated(SCRIPT.replace(b'type="text/javascript"', b'type="module"')),
        decorated(SCRIPT.replace(b'src="/', b'src="https://unknown/')),
        SCRIPT + DOCUMENT,
        decorated() + b"\n",
        decorated().replace(b">42<", b">43<") + b"unknown",
        decorated(b"x" * 109),
        decorated(b'<script type="text/javascript"  src="/unattested"></script>'),
    ],
)
def test_changed_duplicate_nonempty_relocated_or_unrecognized_script_fails(raw):
    with pytest.raises(ValueError, match="SEC"):
        document_bytes(raw, len(DOCUMENT))


def test_no_generic_109_byte_tolerance():
    with pytest.raises(ValueError, match="beyond"):
        document_bytes(decorated(), len(DOCUMENT) - 1)


@pytest.mark.parametrize("script", [SCRIPT + SCRIPT, SCRIPT.replace(b"></script>", b">alert(1)</script>")])
def test_manipulated_index_size_cannot_hide_an_unknown_script(script):
    raw = decorated(script)
    with pytest.raises(ValueError):
        document_bytes(raw, len(raw))

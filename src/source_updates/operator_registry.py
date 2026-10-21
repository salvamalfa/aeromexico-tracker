"""Verify separate primary operator-designator references, never join them to issuer totals.

Inputs are explicit retained public audit captures. These references are not
FAA IASA ratings and do not borrow its active catalogue alias. The IATA search
callback must have been discovered from the captured official search form.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from lxml import html

from src.source_updates.calendar import local_time
from src.source_updates.primary_review import normalize, sha, within

IATA = "https://www.iata.org/en/publications/directories/code-search/"
FAA = "https://www.faa.gov/air_traffic/publications/atpubs/CNT/3-3-{}.htm"
EXPECTED = (
    ("iata-vb.html", "IATA", "VB", ["Aeroenlaces Nacionales S.A. de C.V. dba Viva Aerobus", "Mexico", "VB"]),
    ("iata-fr.html", "IATA", "FR", ["Ryanair Ltd.", "Ireland", "FR"]),
    (
        "faa-viv.html",
        "ICAO_3LD_in_FAA_registry",
        "VIV",
        ["VIV", "AEROENLACES NACIONALES, S.A. DE C.V.", "MEXICO", "AEROENLACES"],
    ),
    ("faa-ryr-decode.html", "ICAO_3LD_in_FAA_registry", "RYR", ["RYR", "RYANAIR", "IRELAND", "RYANAIR"]),
)


def verify(root: Path, as_of: str) -> dict:
    cutoff = local_time(as_of)
    receipt = within(root, "capture-results.json")
    captures = json.loads(receipt.read_text())
    if not isinstance(captures, list):
        raise ValueError("Explicit list of retained audit captures required")

    def capture(filename: str) -> tuple[dict, Path]:
        matches = [r for r in captures if r.get("source_file") == filename]
        if len(matches) != 1:
            raise ValueError("Exactly one capture identity per selected registry response required")
        row = matches[0]
        body = within(root, filename)
        if (
            row.get("http_status") != 200
            or row.get("sha256") != sha(body)
            or row.get("bytes") != body.stat().st_size
        ):
            raise ValueError("Registry body/hash/size/HTTP check failed")
        if local_time(row["captured_at"]) > cutoff:
            raise ValueError("Registry capture is after the explicit cutoff")
        if (
            row.get("source_system") != "operator_registry_audit_only"
            or row.get("catalogue_registration") != "not_active_no_alias_relabelling"
        ):
            raise ValueError("Registry audit must remain separate from active source aliases")
        return row, body

    search, search_path = capture("iata-code-search.html")
    if search["source_url"] != IATA:
        raise ValueError("IATA callback requires retained official search form")
    tree = html.fromstring(search_path.read_bytes())
    forms = [f for f in tree.xpath("//form") if f.xpath('.//input[@name="airline.search"]')]
    if len(forms) != 1 or not forms[0].get("data-callback-url"):
        raise ValueError("IATA airline search callback is missing or ambiguous")
    callback = urljoin(IATA, forms[0].get("data-callback-url"))
    parsed = urlsplit(callback)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.scheme != "https"
        or parsed.fragment
        or parsed.netloc != "www.iata.org"
        or parsed.path != "/PublicationDetails/Search/"
        or set(params) != {"currentBlock", "currentPage"}
        or any(len(v) != 1 or not v[0].isdigit() for v in params.values())
    ):
        raise ValueError("Unverified public IATA callback")
    records = []
    for filename, system, code, expected in EXPECTED:
        original, path = capture(filename)
        url = (
            callback + "&" + urlencode({"airline.search": code}) if system == "IATA" else FAA.format(code[0])
        )
        if original["source_url"] != url:
            raise ValueError("Registry response URL does not match its explicit official query")
        document = html.fromstring(path.read_bytes())
        matches = []
        for row in document.xpath("//tr[not(.//tr)]"):
            values = [normalize(cell.text_content()) for cell in row.xpath("./td|./th")]
            if code in values:
                matches.append((row, values))
        if len(matches) != 1 or matches[0][1] != expected:
            raise ValueError("Registry row is missing, ambiguous or has changed; review exact entity")
        row, values = matches[0]
        records.append(
            {
                "code_system": system,
                "code": code,
                "literal_source_cells": values,
                "source_url": original["source_url"],
                "source_sha256": original["sha256"],
                "captured_at": original["captured_at"],
                "source_file": filename,
                "html_xpath": row.getroottree().getpath(row),
                "agent_eligible": False,
                "issuer_assignment": None,
                "group_to_operator_join_verified": False,
            }
        )
    return {
        "schema": "operator_designator_references_v1",
        "as_of": as_of,
        "status": "verified_literal_primary_rows",
        "records": records,
        "capture_receipt_sha256": sha(receipt),
        "parser_sha256": sha(Path(__file__)),
        "query_discovery": {"source_url": IATA, "source_sha256": search["sha256"], "callback": callback},
        "limitations": [
            "Separate literal registry rows; no issuer/group designator assignment",
            "IATA Ryanair Ltd. and FAA RYANAIR do not alone prove the exact DAC legal-entity equivalence",
            "Current capture does not prove historical designator validity or first publication date",
            "FAA source is a designator registry, not an IASA country rating",
        ],
        "failed_captures_preserved": [
            {k: r.get(k) for k in ("source_file", "source_url", "http_status", "sha256")}
            for r in captures
            if r.get("http_status") != 200
        ],
        "agent_eligible": False,
        "approval_granted": False,
        "activation": "none",
        "silver_gold_certification": False,
        "writes": 0,
        "network_requests": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.root, args.as_of)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

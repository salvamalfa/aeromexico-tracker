"""Capture and replay the original four-document Volaris 3Q26 SEC dossier.

Separate from the authorized Library reconstruction. Existing reconstructed
artifacts, timestamps, checks and approvals are never changed by this adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from src.source_updates.collection import safe_workspace
from src.source_updates.volaris_q3_reconstructed import ACCESSION, DIRECTORY, DOCUMENT, EXHIBIT, FILING, URLS

PROFILE = "volaris_sec_original_2026Q3_v1"
ROLE_URLS = {"html": URLS["exhibit"], **{k: URLS[k] for k in ("primary", "index", "submissions")}}
SEC_EMPTY_SCRIPT = (
    b'<script type="text/javascript"  src="/yt0Omj4t/iRa/njL/nRf-WhIKSa/'
    b'muuQGrJDQmrGwV/UQF7/dl4/HSHxhJkA"></script>'
)


def document_bytes(raw, indexed_size):
    """Separate SEC's observed empty trailing transport script from filing bytes.

    Raw HTTP bytes are always retained and hashed. No constant byte tolerance:
    the one exact typed script must explain the entire indexed-size difference.
    A changed, duplicate, nonempty or relocated script fails closed.
    """
    script_count = len(re.findall(rb"<script\b", raw, re.I))
    if len(raw) == indexed_size and script_count == 0:
        return raw
    pattern = re.escape(SEC_EMPTY_SCRIPT)
    matches = list(re.finditer(pattern, raw))
    if len(matches) != 1 or script_count != 1:
        raise ValueError("SEC transport decoration missing, duplicated or unrecognized")
    match = matches[0]
    if raw[match.end() :] != b"</BODY>\n</HTML>\n</TEXT>\n</DOCUMENT>\n":
        raise ValueError("SEC transport decoration must immediately precede the exact document trailer")
    document = raw[: match.start()] + raw[match.end() :]
    if len(document) != indexed_size:
        raise ValueError("SEC indexed size differs beyond its exact empty transport decoration")
    return document


def document_receipts(inputs):
    directory = json.loads(inputs["index"][0])["directory"]
    result = {}
    for role, name in (("html", EXHIBIT), ("primary", DOCUMENT)):
        item = next(i for i in directory["item"] if i["name"] == name)
        raw, metadata = inputs[role]
        document = document_bytes(raw, int(item["size"]))
        result[role] = dict(
            source_url=metadata["source_url"],
            captured_at=metadata["downloaded_at"],
            raw_http_sha256=sha(raw),
            raw_http_bytes=len(raw),
            indexed_document_bytes=int(item["size"]),
            document_sha256=sha(document),
            document_bytes=len(document),
            decoration_sha256=sha(SEC_EMPTY_SCRIPT) if document != raw else None,
            decoration_bytes=len(SEC_EMPTY_SCRIPT) if document != raw else 0,
            semantics=(
                "Exact observed SEC HTTP response; separate indexed document "
                "and attested empty transport script."
            ),
        )
    return result


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(workspace, *, execute=False):
    from src.common.http import SourceHttpClient

    workspace = safe_workspace(Path(workspace))
    plan = dict(
        schema_version=PROFILE,
        mode="capture" if execute else "dry_run",
        urls=ROLE_URLS,
        requests=4,
        paid_requests=0,
        destination=str(workspace),
        activation="none",
        publication="none",
    )
    if not execute:
        return plan
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Use a new isolated SEC capture workspace")
    folder = workspace / "data/bronze"
    folder.mkdir(parents=True, exist_ok=False)
    records = {}
    with SourceHttpClient("sec", max_attempts=2) as client:
        for role, url in ROLE_URLS.items():
            response = client.request("GET", url)
            if response.status_code != 200 or str(response.url) != url:
                raise ValueError("SEC original requires an exact-URL HTTP200 capture")
            raw = response.content
            if not raw or len(raw) > 8_000_000:
                raise ValueError("SEC original is empty or outside the bounded document size")
            extension = ".json" if role in {"index", "submissions"} else ".html"
            name = role + "-" + sha(raw) + extension
            metadata = dict(
                source_system="sec",
                source_file=name,
                source_url=url,
                sha256=sha(raw),
                bytes=len(raw),
                downloaded_at=datetime.now(UTC).isoformat(),
                http_status=200,
                content_type=response.headers.get("content-type", ""),
                download_method="httpx",
                representation_kind="original_SEC_HTTP_response",
            )
            (folder / name).write_bytes(raw)
            (folder / (name + ".meta.json")).write_text(
                json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
            )
            records[role] = metadata
    receipt = {**plan, "records": records, "captured_at": datetime.now(UTC).isoformat()}
    (workspace / "capture.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    originals(workspace)
    return receipt


def originals(workspace):
    workspace = safe_workspace(Path(workspace))
    receipt = json.loads((workspace / "capture.json").read_bytes())
    if (
        receipt.get("schema_version") != PROFILE
        or receipt.get("urls") != ROLE_URLS
        or set(receipt.get("records", {})) != set(ROLE_URLS)
    ):
        raise ValueError("Original SEC dossier identity differs")
    result = {}
    for role, metadata in receipt["records"].items():
        name = metadata.get("source_file", "")
        if Path(name).name != name or "\\" in name or "/" in name:
            raise ValueError("Original SEC artifact path must be a plain filename")
        path = workspace / "data/bronze" / name
        if any(p.is_symlink() for p in [path, *path.parents]):
            raise ValueError("Original SEC evidence cannot traverse symlinks")
        raw = path.read_bytes()
        captured = datetime.fromisoformat(metadata["downloaded_at"])
        if (
            metadata != json.loads(path.with_suffix(path.suffix + ".meta.json").read_bytes())
            or metadata["sha256"] != sha(raw)
            or metadata["bytes"] != len(raw)
            or metadata["source_url"] != ROLE_URLS[role]
            or metadata["source_system"] != "sec"
            or metadata["http_status"] != 200
            or metadata["representation_kind"] != "original_SEC_HTTP_response"
            or captured.tzinfo is None
            or not datetime.fromisoformat(FILING["acceptance_at"]) <= captured <= datetime.now(UTC)
        ):
            raise ValueError("Original SEC bytes, capture receipt, URL or chronology differs")
        result[role] = (raw, metadata)
    verify_filing(result)
    return result


def verify_filing(inputs):
    submission = json.loads(inputs["submissions"][0])
    if str(submission.get("cik")).lstrip("0") != "1520504":
        raise ValueError("Original SEC submissions issuer differs")
    recent = submission["filings"]["recent"]
    positions = [i for i, value in enumerate(recent["accessionNumber"]) if value == ACCESSION]
    if len(positions) != 1:
        raise ValueError("Original SEC accession missing or ambiguous")
    i = positions[0]
    for key, value in dict(
        form="6-K", reportDate="2026-09-30", filingDate="2026-10-27", primaryDocument=DOCUMENT
    ).items():
        if len(recent[key]) != len(recent["accessionNumber"]) or recent[key][i] != value:
            raise ValueError("Original SEC filing date, period, form or document differs")
    if datetime.fromisoformat(
        recent["acceptanceDateTime"][i].replace("Z", "+00:00")
    ) != datetime.fromisoformat(FILING["acceptance_at"]):
        raise ValueError("Original SEC acceptance timestamp differs")
    directory = json.loads(inputs["index"][0])["directory"]
    if directory["name"] != DIRECTORY:
        raise ValueError("Original SEC accession directory differs")
    for role, name in (("html", EXHIBIT), ("primary", DOCUMENT)):
        found = [r for r in directory["item"] if r["name"] == name]
        if len(found) != 1:
            raise ValueError("Original SEC index document name or byte size differs")
        document_bytes(inputs[role][0], int(found[0]["size"]))
    primary = BeautifulSoup(inputs["primary"][0], "lxml")
    text = " ".join(primary.get_text(" ", strip=True).split())
    if not all(s in text for s in ("FORM 6-K", "Controladora Vuela", "October", "2026")):
        raise ValueError("Original SEC cover identity or month differs")
    if {a["href"] for a in primary.find_all("a", href=True) if "ex99" in a["href"].lower()} != {EXHIBIT}:
        raise ValueError("Original SEC cover does not link the selected exhibit")


def native_frame(inputs):
    """Read all 446 source cells using reviewed Q3 coordinates and period units."""
    import pandas as pd

    from src.source_updates.carrier_source_contract import record
    from src.source_updates.volaris_q3_source import audit_flag, dates, reconcile
    from src.source_updates.volaris_q3_spec import TABLES
    from src.source_updates.volaris_sec_source import ENTITY, cells

    verify_filing(inputs)
    raw, source = inputs["html"]
    soup = BeautifulSoup(raw, "lxml")
    text = " ".join(soup.get_text(" ", strip=True).split())
    if not all(
        value in text
        for value in (
            "Consolidated Quarter: 3 Year: 2026",
            "October 26, 2026",
            "EBITDAR",
            "International Financial Reporting Standards (IFRS)",
            "(2) Includes scheduled and charter.",
            "(4) Includes scheduled.",
        )
    ):
        raise ValueError("Original Volaris quarter, date, accounting or aviation definitions differ")
    tables = soup.find_all("table")
    if len(tables) != 321:
        raise ValueError("Original Volaris Q3 table inventory differs")
    rows = []
    def normalized(value):
        return " ".join(value.split())
    for index, definition in TABLES.items():
        rr = cells(tables[index])
        expected = [[normalized(c) for c in r] for r in definition["header_rows"]]
        if [[normalized(c) for c in r] for r in rr[: len(expected)]] != expected:
            raise ValueError("Original Volaris table headers, duration, ordering or currency differ")
        for position, (label, key, unit, scale, scope) in definition["rows"].items():
            row = rr[position]
            actual_label = normalized(row[0])
            expected_label = "Net debt-to-LTM EBITDAR 3" if index == 279 and position == 17 else label
            if actual_label != expected_label:
                raise ValueError("Original Volaris source row label differs")
            for column in [1, 2, 4] if index == 291 else [1, 2]:
                kind, period, start, end = dates(index, column, key)
                rows.append(
                    record(
                        "volaris_sec",
                        source,
                        edition="2026Q3",
                        entity=ENTITY,
                        carrier="VOLARIS",
                        statement=definition["statement"],
                        kind=kind,
                        period_id=period,
                        start=start,
                        end=end,
                        metric=key,
                        segment="total",
                        service=None,
                        token=normalized(row[column]),
                        unit=unit,
                        scale=scale,
                        label=actual_label,
                        locator=f"html/table[{index}]/row[{position}]/cell[{column}]",
                        excerpt=" | ".join(row),
                        table=str(index),
                        row=position,
                        column=column,
                        notes="Original SEC HTTP response; printed date 2026-10-26 "
                        "is not first availability. "
                        "Booked passengers; scheduled occupancy and total capacity may have different scope.",
                        aviation=scope,
                        unaudited=audit_flag(index, column),
                    )
                )
    frame = pd.DataFrame(rows)
    frame["parser_version"] = PROFILE
    if len(frame) != 446:
        raise ValueError("Original Volaris Q3 requires all reviewed financial and operating cells")
    return frame, reconcile(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = capture(args.workspace, execute=args.execute)
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

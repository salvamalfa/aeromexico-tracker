from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

from src.common.storage import save_bronze


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_save_bronze_writes_exact_bytes_metadata_and_hash(tmp_path: Path) -> None:
    content = b"raw-source-payload\x00\xff"
    timestamp = datetime(2026, 8, 20, 12, 34, 56, tzinfo=UTC)

    saved = save_bronze(
        content,
        "sec",
        "aeromexico",
        "2026Q1",
        "pdf",
        "https://www.sec.gov/example.pdf",
        "httpx",
        http_status=200,
        content_type="application/pdf",
        bronze_root=tmp_path,
        downloaded_at=timestamp,
    )

    assert saved.read_bytes() == content
    assert saved.name == "sec_aeromexico_2026Q1_20260820T123456Z.pdf"
    expected_hash = hashlib.sha256(content).hexdigest()
    metadata = json.loads(
        saved.with_suffix(".pdf.meta.json").read_text(encoding="utf-8")
    )
    assert metadata["sha256"] == expected_hash
    assert metadata["bytes"] == len(content)
    assert metadata["download_method"] == "httpx"
    assert metadata["logical_version"] == 1
    assert _jsonl(tmp_path / "_manifest.jsonl") == [metadata]


def test_duplicate_hash_does_not_rewrite_or_append(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    arguments = (
        b"unchanged",
        "sec",
        "aeromexico",
        "2026Q1",
        "json",
        "https://data.sec.gov/example.json",
        "httpx",
    )
    first = save_bronze(*arguments, bronze_root=tmp_path, downloaded_at=timestamp)
    original_mtime = first.stat().st_mtime_ns
    second = save_bronze(
        *arguments,
        bronze_root=tmp_path,
        downloaded_at=timestamp + timedelta(days=1),
    )

    assert second == first
    assert second.stat().st_mtime_ns == original_mtime
    assert len(_jsonl(tmp_path / "_manifest.jsonl")) == 1
    assert not (tmp_path / "_restatements.jsonl").exists()


def test_changed_logical_source_creates_restatement(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    common = (
        "afac",
        "aeromexico",
        "2026M06",
        "xlsx",
        "https://www.gob.mx/afac/example.xlsx",
        "manual",
    )
    first = save_bronze(
        b"preliminary",
        *common,
        bronze_root=tmp_path,
        downloaded_at=timestamp,
    )
    second = save_bronze(
        b"revised",
        *common,
        bronze_root=tmp_path,
        downloaded_at=timestamp + timedelta(days=2),
    )

    assert first != second
    assert first.read_bytes() == b"preliminary"
    assert second.read_bytes() == b"revised"
    manifest = _jsonl(tmp_path / "_manifest.jsonl")
    restatements = _jsonl(tmp_path / "_restatements.jsonl")
    assert [record["logical_version"] for record in manifest] == [1, 2]
    assert len(restatements) == 1
    assert restatements[0]["previous_sha256"] == manifest[0]["sha256"]
    assert restatements[0]["new_sha256"] == manifest[1]["sha256"]


def test_same_timestamp_with_new_content_uses_filename_suffix(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    common = (
        "bmv",
        "aero",
        "2026Q1",
        "zip",
        "https://www.bmv.com.mx/example.zip",
        "httpx",
    )
    first = save_bronze(b"one", *common, bronze_root=tmp_path, downloaded_at=timestamp)
    second = save_bronze(b"two", *common, bronze_root=tmp_path, downloaded_at=timestamp)

    assert first.name.endswith(".zip")
    assert second.name.endswith("_v2.zip")
    assert first.read_bytes() == b"one"

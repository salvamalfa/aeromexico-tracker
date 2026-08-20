from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from src.common.storage import find_bronze_by_source_url, save_bronze


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


def test_save_bronze_supports_safe_nested_directory(tmp_path: Path) -> None:
    saved = save_bronze(
        b"filing",
        "sec",
        "document",
        "2026Q1",
        "htm",
        "https://www.sec.gov/example.htm",
        "httpx",
        bronze_root=tmp_path,
        relative_dir="sec/filings/0001193125-26-171463",
        downloaded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert saved.parent.relative_to(tmp_path).as_posix() == (
        "sec/filings/0001193125-26-171463"
    )


@pytest.mark.parametrize("relative_dir", ["../outside", "sec/../../outside", "/absolute"])
def test_save_bronze_rejects_unsafe_nested_directory(
    tmp_path: Path, relative_dir: str
) -> None:
    with pytest.raises(ValueError, match="relative_dir"):
        save_bronze(
            b"filing",
            "sec",
            "document",
            "2026Q1",
            "htm",
            "https://www.sec.gov/example.htm",
            "httpx",
            bronze_root=tmp_path,
            relative_dir=relative_dir,
            downloaded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_find_bronze_by_source_url_returns_existing_artifact(tmp_path: Path) -> None:
    source_url = "https://www.sec.gov/Archives/example.htm"
    saved = save_bronze(
        b"filing",
        "sec",
        "document",
        "2026Q1",
        "htm",
        source_url,
        "httpx",
        bronze_root=tmp_path,
        downloaded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    found = find_bronze_by_source_url(source_url, bronze_root=tmp_path)

    assert found is not None
    assert found[0] == saved
    assert found[1]["sha256"] == hashlib.sha256(b"filing").hexdigest()


def test_same_hash_from_different_url_records_alias_without_copy(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    first = save_bronze(
        b"same exhibit",
        "sec",
        "first_document",
        "filing_a",
        "htm",
        "https://www.sec.gov/Archives/a.htm",
        "httpx",
        bronze_root=tmp_path,
        downloaded_at=timestamp,
    )
    second = save_bronze(
        b"same exhibit",
        "sec",
        "second_document",
        "filing_b",
        "htm",
        "https://www.sec.gov/Archives/b.htm",
        "httpx",
        bronze_root=tmp_path,
        downloaded_at=timestamp,
    )

    assert second == first
    assert len(list(tmp_path.rglob("*.htm"))) == 1
    manifest = _jsonl(tmp_path / "_manifest.jsonl")
    assert len(manifest) == 2
    assert manifest[1]["is_content_alias"] is True
    assert find_bronze_by_source_url(
        "https://www.sec.gov/Archives/b.htm", bronze_root=tmp_path
    ) == (first, manifest[1])

"""Every contributor to a deduplicated headline retains checkable source lineage."""

import json
import shutil
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates.catalog import ROOT
from src.source_updates.checks import check_candidate
from src.source_updates.news import deduplicate


@pytest.fixture
def candidate():
    work = ROOT / "tmp/source-updates" / ("news-product-test-" + uuid4().hex)
    records = []
    for source in ("rss", "gdelt"):
        bronze = work / "data/bronze"
        path = save_bronze(
            source.encode(),
            source,
            "fixture",
            "2026M09",
            "json",
            "https://example.test/synthetic-capture",
            "manual",
            bronze_root=bronze,
        )
        metadata = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text())
        records.append(
            {
                "published_at": pd.Timestamp("2026-09-01T12:00:00Z"),
                "source_name": source,
                "title": source + " fixture headline",
                "url": "https://example.test/article?utm_source=" + source,
                "language": "en",
                "gdelt_tone": 2.5 if source == "gdelt" else None,
                "source_system": source,
                "source_file": path.relative_to(bronze).as_posix(),
                "source_hash": metadata["sha256"],
                "ingested_at": datetime.now(UTC),
                "parser_version": "synthetic_fixture",
            }
        )
    (work / "data/silver").mkdir()
    yield work, records
    shutil.rmtree(work)


def checks(work):
    return check_candidate(
        work,
        {
            "as_of": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "checks": [
                {
                    "product": source,
                    "layer": "silver",
                    "table": "news_headlines",
                    "period_column": "published_at",
                    "expected_period": "2026M09",
                    "value_columns": ["gdelt_tone"] if source == "gdelt" else ["title"],
                }
                for source in ("rss", "gdelt")
            ],
        },
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_each_source_checks_its_contribution_after_deduplication(candidate, reverse):
    work, records = candidate
    frame = pd.DataFrame(deduplicate(records[::-1] if reverse else records))
    assert len(frame) == 1
    frame.to_parquet(work / "data/silver/news_headlines.parquet")
    result = checks(work)
    assert result["status"] == "checks_passed", result
    assert all(row["rows"] == 1 and row["null_values"] == 0 for row in result["checks"])


@pytest.mark.parametrize("field", ["source_hash", "source_file", "source_system"])
def test_secondary_contributor_cannot_borrow_the_first_sources_lineage(candidate, field):
    work, records = candidate
    frame = pd.DataFrame(deduplicate(records))
    provenance = json.loads(frame.loc[0, "provenance_json"])
    # Keep the top-level RSS lineage intact; only tamper with secondary GDELT.
    provenance[1][field] = records[0][field]
    frame.loc[0, "provenance_json"] = json.dumps(provenance)
    frame.to_parquet(work / "data/silver/news_headlines.parquet")
    assert checks(work)["checks"][1]["status"] == "blocked"


@pytest.mark.parametrize(
    "field,value", [("url", "https://example.test/other"), ("published_at", "2026-08-01T12:00:00Z")]
)
def test_contributor_must_match_the_same_dated_canonical_url(candidate, field, value):
    work, records = candidate
    frame = pd.DataFrame(deduplicate(records))
    provenance = json.loads(frame.loc[0, "provenance_json"])
    provenance[1][field] = value
    frame.loc[0, "provenance_json"] = json.dumps(provenance)
    frame.to_parquet(work / "data/silver/news_headlines.parquet")
    assert checks(work)["status"] == "blocked"


@pytest.mark.parametrize("legacy", [False, True])
def test_revision_comparison_uses_each_contributors_values(candidate, legacy):
    work, records = candidate
    previous = [dict(row) for row in records]
    previous[1]["gdelt_tone"] = 1.5
    pd.DataFrame(previous if legacy else deduplicate(previous)).to_parquet(work / "baseline.parquet")
    pd.DataFrame(deduplicate(records)).to_parquet(work / "data/silver/news_headlines.parquet")
    specification = {
        "as_of": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "checks": [
            {
                "product": source,
                "layer": "silver",
                "table": "news_headlines",
                "period_column": "published_at",
                "expected_period": "2026M09",
                "value_columns": ["gdelt_tone"] if source == "gdelt" else ["title"],
                "baseline_file": "baseline.parquet",
                "revision_keys": ["published_at", "url", "source_system"],
            }
            for source in ("rss", "gdelt")
        ],
    }
    result = check_candidate(work, specification)
    assert result["status"] == "checks_passed", result
    assert result["checks"][0]["revisions"]["unchanged"] == 1
    assert result["checks"][1]["revisions"]["changed"] == 1


def test_top_level_lineage_must_be_one_of_the_preserved_contributors(candidate):
    work, records = candidate
    frame = pd.DataFrame(deduplicate(records))
    frame.loc[0, "source_hash"] = "0" * 64
    frame.to_parquet(work / "data/silver/news_headlines.parquet")
    assert checks(work)["status"] == "blocked"

"""Native reading fingerprints remain distinct from original publisher bytes."""

import hashlib
import json

import pytest

from src.conversational_analytics.evidence_index import _approved
from src.conversational_analytics.news_projection import public_sources


def observation(url):
    return {
        "url": url,
        "publisher": "Test publisher",
        "publisher_page_read": True,
        "representation": "reviewed_web_observation_not_original_publisher_bytes",
        "original_page_sha256": None,
    }


def native_record():
    readings = [observation("https://www.gob.mx/test"), observation("https://ir.aeromexico.com/test")]
    encoded = (
        json.dumps(readings[0], ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
    ).encode()
    return {
        "publisher": "Test publisher",
        "publisher_observations": readings,
        "source": {
            "id": "test-reading",
            "url": readings[0]["url"],
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "sha256_semantics": "reviewed_observation_not_original_page_bytes",
            "artifact_file": "private.json",
            "json_pointer": "/readings/0",
        },
    }


def test_all_editorial_provenance_survives_but_private_locator_does_not():
    record = native_record()
    sources = public_sources(record)
    assert len(sources) == 2
    assert all(set(source) == {"id", "url", "sha256", "publisher"} for source in sources)
    assert sources[1]["url"] == record["publisher_observations"][1]["url"]
    assert not _approved(record)  # Allowlisting a publisher never approves its record.


def test_changed_selected_observation_cannot_reuse_its_source_identity():
    record = native_record()
    record["publisher_observations"][0]["publisher"] = "Changed publisher"
    with pytest.raises(ValueError, match="recorded source hash"):
        public_sources(record)


def test_review_packet_refuses_to_overwrite_a_pending_owner_decision(monkeypatch, tmp_path):
    from scripts.news.prepare_review_package import main

    packet = tmp_path / "pending.json"
    packet.write_text("frozen owner packet")
    monkeypatch.setattr(
        "sys.argv",
        [
            "review",
            "--candidate",
            "unused.json",
            "--json",
            str(packet),
            "--markdown",
            str(tmp_path / "new.md"),
        ],
    )
    with pytest.raises(ValueError, match="immutable"):
        main()
    assert packet.read_text() == "frozen owner packet"

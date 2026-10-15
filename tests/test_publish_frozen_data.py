"""A map-only change cannot alter data or an approved analysis renderer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.publish.frozen_data import data_identities, require_preserved_analysis_implementation


def _baseline(root: Path) -> str:
    for name, content in {
        "web/index.html": '<main>unchanged analysis</main><button>Más pasajeros</button>',
        "web/src/views/analysis/reading.ts": "approved renderer",
        "data/gold/official.parquet": "pinned source",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "trusted source"], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def test_every_flight_data_byte_is_part_of_the_preservation_check(tmp_path):
    files = ["executive.json", "analysis/2026Q2.json", "flights/quarters.json", "flights/domestic/2026M06.json"]
    for name in files:
        path = tmp_path / "data/v1" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"value":1}')
    before = data_identities(tmp_path, flights=True)
    assert len(before) == len(files)
    (tmp_path / "data/v1/flights/domestic/2026M06.json").write_text('{"value":2}')
    assert before != data_identities(tmp_path, flights=True)


def test_only_the_requested_map_button_can_change_in_shared_html(tmp_path):
    commit = _baseline(tmp_path)
    page = tmp_path / "web/index.html"
    page.write_text(page.read_text().replace("Más pasajeros", "Más vuelos"))
    require_preserved_analysis_implementation(tmp_path, commit)
    page.write_text(page.read_text().replace("unchanged analysis", "new unapproved prose"))
    with pytest.raises(ValueError, match="protected analysis input"):
        require_preserved_analysis_implementation(tmp_path, commit)


@pytest.mark.parametrize("name", ["data/gold/official.parquet", "web/src/views/analysis/reading.ts"])
def test_frozen_data_gate_rejects_refreshed_sources_and_analysis_changes(tmp_path, name):
    commit = _baseline(tmp_path)
    (tmp_path / name).write_text("unapproved change")
    with pytest.raises(ValueError):
        require_preserved_analysis_implementation(tmp_path, commit)

"""A flight release cannot alter a thesis, News, or an existing gate check."""

import json
import subprocess

import pytest

from src.publish.flight_overlay import outside_flights_html, require_flight_only_changes


@pytest.fixture
def baseline(tmp_path):
    files = {
        "web/index.html": (
            '<main>News<section id="panel-flights"><section>old map</section></section>thesis</main>'
        ),
        "web/src/views/news/bootstrap.ts": "approved news",
        "src/analysis_agent/lifecycle.py": "approved lifecycle",
        "src/publish/gate.py": "def verify():\n return True\ndef main():\n return 0\n",
        "contracts/web/flights.schema.json": json.dumps(
            {"properties": {}, "$defs": {"flight_component": {"properties": {}}}}
        ),
    }
    for name, value in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline"],
        cwd=tmp_path,
        check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    return tmp_path, commit


def test_only_flights_section_can_change_in_shared_html(baseline):
    root, commit = baseline
    p = root / "web/index.html"
    p.write_text(p.read_text().replace("old map", "map + coverage"))
    require_flight_only_changes(root, commit)
    p.write_text(p.read_text().replace("thesis", "changed thesis"))
    with pytest.raises(ValueError, match="unrelated input"):
        require_flight_only_changes(root, commit)


@pytest.mark.parametrize("name", ["web/src/views/news/bootstrap.ts", "src/analysis_agent/lifecycle.py"])
def test_news_and_approval_implementation_are_protected(baseline, name):
    root, commit = baseline
    (root / name).write_text("changed")
    with pytest.raises(ValueError, match="unrelated input"):
        require_flight_only_changes(root, commit)


def test_cli_dispatch_cannot_weaken_existing_gate_function(baseline):
    root, commit = baseline
    p = root / "src/publish/gate.py"
    p.write_text(p.read_text().replace("def main():\n return 0", "def main():\n return 1"))
    require_flight_only_changes(root, commit)
    p.write_text(p.read_text().replace("return True", "return False"))
    with pytest.raises(ValueError, match="gate function"):
        require_flight_only_changes(root, commit)


def test_existing_contract_fields_cannot_change(baseline):
    root, commit = baseline
    p = root / "contracts/web/flights.schema.json"
    s = json.loads(p.read_text())
    s["properties"]["map_coverage"] = {}
    s["$defs"]["map_coverage"] = {}
    s["$defs"]["flight_component"]["properties"]["regularity"] = {}
    p.write_text(json.dumps(s))
    require_flight_only_changes(root, commit)
    s["properties"]["existing_field"] = {}
    p.write_text(json.dumps(s))
    with pytest.raises(ValueError, match="existing public data contract"):
        require_flight_only_changes(root, commit)


def test_nested_sections_are_not_a_way_to_rewrite_other_panels():
    a = (
        '<header>same</header><section id="panel-flights">'
        "<section>old</section></section><footer>same</footer>"
    )
    assert outside_flights_html(a) == outside_flights_html(a.replace("old", "new"))
    assert outside_flights_html(a) != outside_flights_html(a.replace("footer>same", "footer>changed"))

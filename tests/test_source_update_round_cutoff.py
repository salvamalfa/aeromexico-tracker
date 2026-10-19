import json

from src.source_updates.__main__ import main


def test_round_retains_historical_cutoff_and_requires_explicit_completion_policy(
    tmp_path, monkeypatch, capsys
):
    import src.source_updates.__main__ as cli

    cutoff = "2026-10-18T12:00:00-06:00"
    recipe = tmp_path / "round.json"
    recipe.write_text(json.dumps({"selection": {}, "steps": [], "checks": {"as_of": cutoff, "checks": []}}))
    monkeypatch.setattr(cli, "collect", lambda *args, **kwargs: {"status": "collected_unvalidated"})
    monkeypatch.setattr(cli, "build", lambda *args, **kwargs: {"status": "completed"})
    monkeypatch.setattr(
        cli, "check_candidate", lambda path, spec: {"status": "checks_passed", "as_of": spec["as_of"]}
    )
    args = ["round", "--recipe", str(recipe), "--workspace", str(tmp_path), "--execute"]
    assert main(args) == 0
    historical = json.loads(capsys.readouterr().out)
    assert historical["checks"]["as_of"] == cutoff
    assert historical["requested_as_of"] == cutoff
    assert main([*args, "--check-at-completion"]) == 0
    live = json.loads(capsys.readouterr().out)
    assert live["checks"]["as_of"] != cutoff
    assert live["requested_as_of"] == cutoff
    assert live["check_time_policy"] == "completion"
    assert json.loads(recipe.read_text())["checks"]["as_of"] == cutoff

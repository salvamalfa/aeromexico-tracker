"""Keep only required chat configuration in the Docker build context."""

import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_runtime_configuration_is_reincluded_in_docker_context():
    rules = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    dockerfile = (ROOT / "Dockerfile.chat").read_text(encoding="utf-8")

    # Docker applies ignore rules to parent directories too, so both directory
    # levels and each nested runtime input must be explicitly re-included.
    required_rules = {
        "!config/",
        "!config/chat/",
        "!config/chat/models.json",
        "!config/chat/metrics-candidates.json",
        "!config/chat/system_prompt.txt",
        "!config/chat/evidence/",
        "!config/chat/evidence/approved-index.json",
        "!config/chat/prompt_candidates/",
        "!config/chat/prompt_candidates/system_prompt_r2-proposed.txt",
        "!config/chat/prompt_candidates/system_prompt_r2-proposed.json",
    }
    assert required_rules <= rules
    copied_config_files: set[str] = set()
    copied_files: set[str] = set()
    for line in dockerfile.splitlines():
        parts = line.split()
        if not parts or parts[0] != "COPY" or any(part.startswith("--from") for part in parts):
            continue
        for source in parts[1:-1]:
            matches = [ROOT / source] if not any(char in source for char in "*?[") else list(ROOT.glob(source))
            assert matches, f"COPY source {source} has no local build input"
            for match in matches:
                if match.is_file():
                    relpath = match.relative_to(ROOT).as_posix()
                    copied_files.add(relpath)
                    if relpath.startswith("config/chat/"):
                        copied_config_files.add(relpath)

    assert {
        "config/chat/models.json",
        "config/chat/metrics-candidates.json",
        "config/chat/system_prompt.txt",
        "config/chat/evidence/approved-index.json",
        "config/chat/prompt_candidates/system_prompt_r2-proposed.txt",
        "config/chat/prompt_candidates/system_prompt_r2-proposed.json",
    } <= copied_config_files
    assert "config/chat/runtime.example.env" not in copied_files

    # Every copied configuration file and each directory leading to it must
    # have an explicit allow rule; the broad default remains deny-all.
    for relpath in copied_config_files:
        assert any(
            rule.startswith("!") and fnmatch.fnmatchcase(relpath, rule[1:])
            for rule in rules
        ), relpath
        parents = Path(relpath).parents
        for parent in parents:
            if str(parent) == ".":
                continue
            parent_rule = f"!{parent.as_posix()}/"
            assert parent_rule in rules, parent_rule

    # Keep candidate records, inbox contents, and local state out of the image.
    assert "!config/chat/evidence/**" not in rules
    assert "!config/chat/prompt_candidates/**" not in rules
    assert "!config/chat/**" not in rules

"""Keep required chat configuration in the Docker build context."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_runtime_configuration_is_reincluded_in_docker_context():
    rules = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    dockerfile = (ROOT / "Dockerfile.chat").read_text(encoding="utf-8")

    # Docker applies ignore rules to parent directories too, so both directory
    # levels and each non-YAML runtime input must be explicitly re-included.
    required_rules = {
        "!config/",
        "!config/chat/",
        "!config/chat/models.json",
        "!config/chat/system_prompt.txt",
    }
    assert required_rules <= rules
    assert "COPY config/chat/*.json ./config/chat/" in dockerfile
    assert "COPY config/chat/system_prompt.txt ./config/chat/system_prompt.txt" in dockerfile

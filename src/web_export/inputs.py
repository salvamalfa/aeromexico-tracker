"""Fail explicitly when required official Gold inputs are missing.

Paid-provider estimates are historical optional warehouse extensions, never
inputs to the active export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config import PATHS

WEB_INPUTS_PATH = PATHS.root / "config" / "web_inputs.yaml"

RESTORE_HINT = (
    "Restore the verified official Gold from the repository or the private "
    "github.com/salvamalfa/aeromexico-tracker-data snapshot to {path}, or rebuild "
    "it offline from retained official sources. Paid-provider estimates are not required."
)


class MissingWebInput(RuntimeError):
    """A required Gold input for a web_export view is absent."""


def load_web_inputs_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path if path is not None else WEB_INPUTS_PATH
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if "views" not in config:
        raise MissingWebInput(f"{config_path} is missing the required 'views' key")
    return config


def require_inputs(view: str, config: dict[str, Any] | None = None) -> None:
    """Raise MissingWebInput naming every absent file the view needs to publish.

    Optional-for-development files are never checked here: their absence is
    tolerated by the existing dashboard generators and produces a smaller,
    still-valid payload.
    """

    active_config = config if config is not None else load_web_inputs_config()
    views = active_config.get("views", {})
    if view not in views:
        raise MissingWebInput(
            f"{view!r} is not declared in {WEB_INPUTS_PATH}; add it under 'views' before exporting it."
        )
    required = views[view].get("required_for_publish", [])
    missing = [rel for rel in required if not (PATHS.root / rel).exists()]
    if missing:
        lines = [
            f"web_export cannot publish '{view}': {len(missing)} required Gold "
            f"input(s) declared in {WEB_INPUTS_PATH} are absent:"
        ]
        for rel in missing:
            path = PATHS.root / rel
            lines.append(f"  - {rel}\n    {RESTORE_HINT.format(path=path)}")
        raise MissingWebInput("\n".join(lines))

"""Loud, declared failure for missing private Gold inputs.

Replaces the silent ``if path.exists()`` pattern in
``src/transform/stage6_warehouse.py`` and ``src/dashboard/*_routes.py`` *for
the exporter only*: those keep tolerating a missing estimate table so the
existing HTML build still works in a fresh clone without the private data
repo (see docs/arquitectura/auditoria-arquitectura-20260926.md §4.2.7). The
exporter instead refuses to publish an incomplete view.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config import PATHS

WEB_INPUTS_PATH = PATHS.root / "config" / "web_inputs.yaml"

RESTORE_HINT = (
    "Restore it from the private data repo "
    "github.com/salvamalfa/aeromexico-tracker-data (Git LFS): copy the "
    "matching file under derived/aerodatabox/ (domestic) or "
    "derived/aerodatabox_international/ (international) to {path} — see "
    "docs/etapas/aerodatabox-agosto-captura-20260925.md."
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

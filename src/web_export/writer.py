"""Deterministic JSON writer shared by every src/web_export exporter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dumps_deterministic(payload: Any) -> str:
    """Sorted keys, compact separators, ASCII-safe: two runs hash the same."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def write_json(path: Path, payload: Any) -> Path:
    """Write payload as deterministic JSON, creating parent directories."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_deterministic(payload) + "\n", encoding="utf-8")
    return path

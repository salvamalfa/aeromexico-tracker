"""Export the executive v1 payload as a single file.

No split by period: ``build_executive_payload()`` already keeps every
quarter's view keyed by ``period_id`` inside one small payload (≈80 KB), and
the front-end still selects a period client-side. See
``src/web_export/README.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.web_export.inputs import require_inputs
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import EXECUTIVE_SCHEMA
from src.web_export.writer import write_json


def export_executive(
    payload: dict[str, Any],
    out_dir: Path,
    *,
    skip_input_check: bool = False,
) -> list[Path]:
    """Write out_dir/executive.json. Returns the single path written, as a list."""

    if not skip_input_check:
        require_inputs("executive")

    validator = Draft202012Validator(EXECUTIVE_SCHEMA)
    errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
    if errors:
        raise ValueError(f"executive.json does not match its schema: {errors[:5]}")

    check_privacy(payload, load_privacy_rules())
    return [write_json(out_dir / "executive.json", payload)]

"""Export the v2 Mercado card payload as a single file (``market.json``).

One small document (≈150 KB): monthly and quarterly AFAC shares for the
three carriers. The front-end selects period, segment and carriers
client-side. See src/dashboard/market.py for the definitions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.web_export.inputs import require_inputs
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import MARKET_SCHEMA
from src.web_export.writer import write_json


def export_market(
    payload: dict[str, Any],
    out_dir: Path,
    *,
    skip_input_check: bool = False,
) -> list[Path]:
    """Write out_dir/market.json. Returns the single path written, as a list."""

    if not skip_input_check:
        require_inputs("market")

    validator = Draft202012Validator(MARKET_SCHEMA)
    errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
    if errors:
        raise ValueError(f"market.json does not match its schema: {errors[:5]}")

    check_privacy(payload, load_privacy_rules())
    return [write_json(out_dir / "market.json", payload)]

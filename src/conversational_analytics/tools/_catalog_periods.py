"""Lossless calendar-run encoding for the chat catalog's tool transport."""

from __future__ import annotations

import copy
import re
from typing import Any

_PERIOD = re.compile(r"([0-9]{4})(?:M(0[1-9]|1[0-2])|Q([1-4]))\Z")
_ENCODING = (
    "Lists inside periods and route_periods may contain start..end: inclusive "
    "contiguous calendar IDs of the same grain. Gaps split ranges. Expand to "
    "exact period IDs before querying; export presence does not establish "
    "complete coverage or eligibility. M and Q retain their own grains "
    "regardless of a legacy field name."
)


def _encode_ids(values: list[Any]) -> list[Any]:
    if len(values) <= 8 or any(not isinstance(value, str) for value in values):
        return copy.deepcopy(values)
    parsed = [_PERIOD.fullmatch(value) for value in values]
    if not all(parsed) or len(set(values)) != len(values):
        return copy.deepcopy(values)
    encoded = []
    for frequency, field in ((12, 2), (4, 3)):
        periods = sorted(
            (int(match[1]) * frequency + int(match[field]) - 1, value)
            for match, value in zip(parsed, values)
            if match[field] is not None
        )
        runs: list[list[tuple[int, str]]] = []
        for ordinal, value in periods:
            if not runs or ordinal != runs[-1][-1][0] + 1:
                runs.append([])
            runs[-1].append((ordinal, value))
        for run in runs:
            if len(run) >= 3:
                encoded.append(f"{run[0][1]}..{run[-1][1]}")
            else:
                encoded.extend(value for _, value in run)
    return encoded


def _compact_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _compact_tree(child) for key, child in value.items()}
    if isinstance(value, list):
        return _encode_ids(value)
    return copy.deepcopy(value)


def compact_catalog_periods(catalog: dict[str, Any]) -> dict[str, Any]:
    """Keep every exported ID and all metadata; encode only long calendar lists.

    The full catalog remains unchanged for HTTP and internal ID discovery.
    Only get_data_catalog's model-facing result uses this reversible encoding.
    No boundary range is inferred across an absent period or across grains.
    """
    result = copy.deepcopy(catalog)
    for key in ("periods", "route_periods"):
        if key in result:
            result[key] = _compact_tree(result[key])
    if result != catalog:
        result["period_id_encoding"] = _ENCODING
    return result

"""Enforce contracts/web/privacy.yaml against any payload before it is exported.

Two independent checks, both recursive over the whole payload tree:

- ``forbidden_fields``: no dict key anywhere may match a name on the list
  (raw provider identifiers, per-flight detail, provider-scheduled times).
- ``allowed_estimated_carriers``: every ``carrier_key`` value anywhere must be
  one of the group's own keys. In the current payloads this key only ever
  appears inside an estimated monthly item, but the check does not rely on
  that: any stray non-group carrier key anywhere is a violation.

Used by ``src/web_export`` before writing a file, and by
``tests/test_web_privacy.py`` against the real embedded payload (local_data)
and the public synthetic fixtures (CI). See contracts/web/README.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config import PATHS


PRIVACY_PATH = PATHS.root / "contracts" / "web" / "privacy.yaml"


class PrivacyViolation(ValueError):
    """Raised when a payload or an exported file breaks a privacy.yaml rule."""


def load_privacy_rules(path: Path | None = None) -> dict[str, Any]:
    rules_path = path if path is not None else PRIVACY_PATH
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    for key in ("allowed_estimated_carriers", "forbidden_fields", "max_file_size_bytes"):
        if key not in rules:
            raise PrivacyViolation(f"{rules_path} is missing required key {key!r}")
    return rules


def _walk(obj: Any, path: str) -> list[tuple[str, Any]]:
    """Yield (path, value) for every dict key found anywhere under obj."""

    found: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.append((f"{path}.{key}" if path else str(key), value))
            found.extend(_walk(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            found.extend(_walk(item, f"{path}[{index}]"))
    return found


def find_forbidden_fields(payload: Any, forbidden_fields: list[str]) -> list[str]:
    """Return dotted paths of every forbidden key found anywhere in payload."""

    forbidden = set(forbidden_fields)
    violations = []
    for path, _value in _walk(payload, ""):
        key = path.rsplit(".", 1)[-1].split("[")[0]
        if key in forbidden:
            violations.append(path)
    return violations


def find_disallowed_carriers(payload: Any, allowed_carriers: list[str]) -> list[str]:
    """Return dotted paths of every carrier_key value outside the allow-list."""

    allowed = set(allowed_carriers)
    violations = []
    for path, value in _walk(payload, ""):
        key = path.rsplit(".", 1)[-1].split("[")[0]
        if key == "carrier_key" and value is not None and value not in allowed:
            violations.append(f"{path}={value!r}")
    return violations


def check_privacy(payload: Any, rules: dict[str, Any] | None = None) -> None:
    """Raise PrivacyViolation with every offending path, or return silently."""

    active_rules = rules if rules is not None else load_privacy_rules()
    forbidden = find_forbidden_fields(payload, active_rules["forbidden_fields"])
    carriers = find_disallowed_carriers(payload, active_rules["allowed_estimated_carriers"])
    if forbidden or carriers:
        messages = []
        if forbidden:
            messages.append(f"forbidden field(s): {', '.join(sorted(forbidden)[:10])}")
        if carriers:
            messages.append(f"disallowed carrier_key value(s): {', '.join(sorted(carriers)[:10])}")
        raise PrivacyViolation("; ".join(messages))


def check_file_size(path: Path, rules: dict[str, Any] | None = None) -> None:
    """Raise PrivacyViolation if a file on disk exceeds the size limit."""

    active_rules = rules if rules is not None else load_privacy_rules()
    limit = int(active_rules["max_file_size_bytes"])
    size = path.stat().st_size
    if size > limit:
        raise PrivacyViolation(f"{path} is {size} bytes, over the {limit}-byte limit in privacy.yaml")

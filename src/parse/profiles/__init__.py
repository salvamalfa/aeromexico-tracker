"""Carrier-specific parsing profiles used by the generalized peer pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT


PROFILE_ROOT = PROJECT_ROOT / "src" / "parse" / "profiles"


@dataclass(frozen=True, slots=True)
class MetricPattern:
    metric_key: str
    patterns: tuple[str, ...]
    unit_raw: str
    unit_normalized: str
    scale_multiplier: float
    table_name: str


@dataclass(frozen=True, slots=True)
class CarrierProfile:
    carrier_key: str
    cik: str | None
    reporting_currency: str
    unit_system: str
    fiscal_year_end_month: int
    forms: tuple[str, ...]
    metric_patterns: tuple[MetricPattern, ...]


def load_profile(carrier_key: str) -> CarrierProfile:
    """Load and validate one declarative YAML carrier profile."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency gate is explicit
        raise RuntimeError(
            "PyYAML is required to load carrier profiles; install project dependencies"
        ) from exc
    path = PROFILE_ROOT / f"{carrier_key.lower()}.yaml"
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if str(payload.get("carrier_key", "")).upper() != carrier_key.upper():
        raise ValueError(f"Profile carrier_key mismatch in {path}")
    month = int(payload["fiscal_year_end_month"])
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid fiscal year end month in {path}")
    metrics = tuple(
        MetricPattern(
            metric_key=str(metric_key),
            patterns=tuple(str(item) for item in spec["patterns"]),
            unit_raw=str(spec["unit_raw"]),
            unit_normalized=str(spec["unit_normalized"]),
            scale_multiplier=float(spec["scale_multiplier"]),
            table_name=str(spec["table_name"]),
        )
        for metric_key, spec in payload.get("metric_patterns", {}).items()
    )
    return CarrierProfile(
        carrier_key=str(payload["carrier_key"]),
        cik=str(payload["cik"]).zfill(10) if payload.get("cik") else None,
        reporting_currency=str(payload["reporting_currency"]),
        unit_system=str(payload["unit_system"]),
        fiscal_year_end_month=month,
        forms=tuple(str(value) for value in payload.get("forms", [])),
        metric_patterns=metrics,
    )


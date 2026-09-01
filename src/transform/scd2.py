"""Deterministic SCD2 history construction for versioned source observations.

The helper in this module is intentionally source-agnostic.  SEC, AFAC, and
other parsers can pass their source-faithful rows through it before mapping the
result into a Gold fact.  A new SCD2 version is created only when one of the
declared value columns changes; repeated observations of the same state do not
inflate ``restatement_count``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Number
from typing import Any, Sequence

import pandas as pd
from pandas.api.types import is_scalar


SCD2_COLUMNS = ("valid_from", "valid_to", "is_current", "restatement_count")


class SCD2ValidationError(ValueError):
    """Raised when observations cannot form an unambiguous SCD2 history."""


def _as_columns(columns: str | Sequence[str], *, argument: str) -> tuple[str, ...]:
    normalized = (columns,) if isinstance(columns, str) else tuple(columns)
    if not normalized or any(not isinstance(column, str) or not column.strip() for column in normalized):
        raise SCD2ValidationError(f"{argument} must contain at least one non-empty column name")
    if len(normalized) != len(set(normalized)):
        raise SCD2ValidationError(f"{argument} contains duplicate column names")
    return normalized


def _is_null(value: Any) -> bool:
    """Return a scalar null result without treating list-like values as null."""

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if is_scalar(result) else False


def _canonical_scalar(value: Any) -> str:
    """Create a stable, type-aware token used only for ordering and equality."""

    if _is_null(value):
        return "null:"
    if isinstance(value, bool):
        return f"bool:{int(value)}"
    if isinstance(value, Number):
        try:
            return f"number:{Decimal(str(value)).normalize()}"
        except InvalidOperation:
            return f"number:{value!r}"
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return f"datetime:{pd.Timestamp(value).isoformat()}"
    if isinstance(value, bytes):
        return f"bytes:{value.hex()}"
    return f"{type(value).__module__}.{type(value).__qualname__}:{value!r}"


def _row_token(row: pd.Series, columns: Sequence[str]) -> tuple[str, ...]:
    return tuple(f"{column}={_canonical_scalar(row[column])}" for column in columns)


def _invalid_key(value: Any) -> bool:
    if _is_null(value):
        return True
    return isinstance(value, str) and not value.strip()


def build_scd2_history(
    observations: pd.DataFrame,
    *,
    key_columns: str | Sequence[str],
    value_columns: str | Sequence[str] = "value",
    timestamp_column: str = "ingested_at",
) -> pd.DataFrame:
    """Build a deterministic SCD2 history from source observations.

    Parameters
    ----------
    observations:
        Source-faithful observations. All non-system columns are preserved from
        the first observation that introduced each distinct state.
    key_columns:
        Columns that identify one logical record (for example carrier, period,
        metric, and segment).
    value_columns:
        One or more columns whose null-aware value determines whether a real
        restatement occurred. Null-to-null is unchanged; null-to-value and
        value-to-null each create a new version.
    timestamp_column:
        Observation time. Values are parsed as UTC and emitted as timezone-naive
        UTC timestamps to match the Gold timestamp convention.

    Notes
    -----
    Histories use inclusive ``valid_to`` boundaries: each closed version ends
    one microsecond before the next version's ``valid_from``. Conflicting values
    for the same logical key and timestamp are rejected because their ordering
    cannot be inferred safely.
    """

    if not isinstance(observations, pd.DataFrame):
        raise TypeError("observations must be a pandas DataFrame")

    keys = _as_columns(key_columns, argument="key_columns")
    values = _as_columns(value_columns, argument="value_columns")
    if not isinstance(timestamp_column, str) or not timestamp_column.strip():
        raise SCD2ValidationError("timestamp_column must be a non-empty column name")
    if set(keys) & set(values):
        raise SCD2ValidationError("key_columns and value_columns must not overlap")
    if timestamp_column in {*keys, *values}:
        raise SCD2ValidationError("timestamp_column must be separate from keys and values")

    required = {*keys, *values, timestamp_column}
    missing = sorted(required - set(observations.columns))
    if missing:
        raise SCD2ValidationError(f"missing required columns: {', '.join(missing)}")
    conflicting = sorted(set(SCD2_COLUMNS) & set(observations.columns))
    if conflicting:
        raise SCD2ValidationError(f"observations already contain SCD2 columns: {', '.join(conflicting)}")

    frame = observations.copy(deep=True)
    for column in keys:
        invalid = frame[column].map(_invalid_key)
        if invalid.any():
            rows = frame.index[invalid].tolist()
            raise SCD2ValidationError(f"invalid logical key in {column!r} at rows {rows}")

    parsed_timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True, format="mixed")
    invalid_timestamps = parsed_timestamps.isna()
    if invalid_timestamps.any():
        rows = frame.index[invalid_timestamps].tolist()
        raise SCD2ValidationError(f"invalid timestamp in {timestamp_column!r} at rows {rows}")
    frame[timestamp_column] = parsed_timestamps.dt.tz_convert(None)

    if frame.empty:
        frame["valid_from"] = pd.Series(dtype="datetime64[ns]")
        frame["valid_to"] = pd.Series(dtype="datetime64[ns]")
        frame["is_current"] = pd.Series(dtype=bool)
        frame["restatement_count"] = pd.Series(dtype="int64")
        return frame

    original_columns = tuple(frame.columns)
    stable_columns = tuple(sorted(original_columns))
    frame["_scd2_key_token"] = frame.apply(lambda row: _row_token(row, keys), axis=1)
    frame["_scd2_value_token"] = frame.apply(lambda row: _row_token(row, values), axis=1)
    frame["_scd2_row_token"] = frame.apply(lambda row: _row_token(row, stable_columns), axis=1)
    frame = frame.sort_values(
        ["_scd2_key_token", timestamp_column, "_scd2_row_token"],
        kind="mergesort",
    ).reset_index(drop=True)

    same_instant = frame.groupby(
        ["_scd2_key_token", timestamp_column], sort=False, dropna=False
    )["_scd2_value_token"].nunique(dropna=False)
    ambiguous = same_instant[same_instant > 1]
    if not ambiguous.empty:
        key_token, timestamp = ambiguous.index[0]
        raise SCD2ValidationError(
            "conflicting values for the same logical key and timestamp: "
            f"key={key_token!r}, {timestamp_column}={timestamp!s}"
        )

    # Exact-time repeats are reduced first. Later observations of the same
    # state are then ignored, retaining the row that established the version.
    frame = frame.drop_duplicates(
        ["_scd2_key_token", timestamp_column, "_scd2_value_token"], keep="first"
    )
    previous = frame.groupby("_scd2_key_token", sort=False)["_scd2_value_token"].shift()
    state_changed = previous.isna() | frame["_scd2_value_token"].ne(previous)
    versions = frame[state_changed].copy()

    next_valid_from = versions.groupby("_scd2_key_token", sort=False)[timestamp_column].shift(-1)
    versions["valid_from"] = versions[timestamp_column]
    versions["valid_to"] = next_valid_from - pd.Timedelta(1, unit="us")
    versions["is_current"] = next_valid_from.isna()
    versions["restatement_count"] = versions.groupby("_scd2_key_token", sort=False).cumcount()

    versions = versions.sort_values(
        ["_scd2_key_token", "valid_from", "_scd2_row_token"], kind="mergesort"
    ).reset_index(drop=True)
    return versions[[*original_columns, *SCD2_COLUMNS]]


__all__ = ["SCD2ValidationError", "build_scd2_history"]

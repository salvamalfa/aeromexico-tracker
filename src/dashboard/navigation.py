"""Navigation metadata for the portable business dashboard's reader tabs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReaderTabSpec:
    """Navigation metadata for one tab in the portable business dashboard."""

    key: str
    title: str


READER_TAB_SPECS: tuple[ReaderTabSpec, ...] = (
    ReaderTabSpec("reading", "Lectura ejecutiva"),
    ReaderTabSpec("economy", "Economía unitaria"),
    ReaderTabSpec("flights", "Vuelos"),
)


def validate_navigation() -> None:
    """Reject duplicate or incomplete reader-tab metadata."""

    if len({spec.key for spec in READER_TAB_SPECS}) != len(READER_TAB_SPECS):
        raise ValueError("Portable dashboard tab keys must be unique")
    if any(not value.strip() for spec in READER_TAB_SPECS for value in (spec.key, spec.title)):
        raise ValueError("Portable dashboard tab metadata cannot be blank")


validate_navigation()

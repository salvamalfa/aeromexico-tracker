"""Validation and collection of source references returned by OpenAI tools."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

ALLOWED_REFERENCE_HOSTS = frozenset(
    {
        "sec.gov",
        "www.sec.gov",
        "gob.mx",
        "www.gob.mx",
        "github.com",
        "salvamalfa.github.io",
        "ir.aeromexico.com",
        "cdn.investorcloud.net",
        "www.flightglobal.com",
        "www.bmv.com.mx",
    }
)


def references_from_results(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("references", "source_references"):
                refs = value.get(key)
                if not isinstance(refs, list):
                    continue
                for ref in refs:
                    if not isinstance(ref, dict):
                        continue
                    label, url = ref.get("label"), ref.get("url")
                    if not isinstance(label, str) or not isinstance(url, str):
                        continue
                    parsed = urlparse(url)
                    if parsed.scheme == "https" and parsed.hostname in ALLOWED_REFERENCE_HOSTS:
                        found.append(
                            {
                                "label": label,
                                "url": url,
                                **({"metric_id": ref["metric_id"]} if isinstance(ref.get("metric_id"), str) else {}),
                            }
                        )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for result in results:
        walk(result)
    unique: dict[str, dict[str, Any]] = {}
    for ref in found:
        key = ref["url"]
        previous = unique.get(key)
        if previous is None:
            unique[key] = ref
            continue
        if ref["label"] not in previous["label"].split("; "):
            previous["label"] = "; ".join((previous["label"], ref["label"]))
        if ref.get("metric_id") != previous.get("metric_id"):
            previous.pop("metric_id", None)
    return list(unique.values())

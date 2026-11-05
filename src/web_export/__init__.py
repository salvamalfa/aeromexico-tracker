"""Exporters that split the v1 web payloads into files under web/public/data/v1/.

See ``README.md`` in this package. Nothing here
changes ``src/dashboard/`` or the published HTML; it reads the same payloads
those generators already build and writes a validated, privacy-checked copy
split by period. Publication itself is out of scope for this package
(see ``src/publish``): running this CLI never touches Analysis Agent
approvals.
"""

from importlib import import_module

# The chat image imports lightweight helpers such as writer and schema readers.
# Loading an unrelated exporter here would also require its offline dashboard
# dependencies, which deliberately are not part of that runtime image.
_EXPORT_MODULES = {
    "export_executive": "executive",
    "export_flights": "flights",
    "export_market": "market",
    "recombine_flights": "flights",
    "require_inputs": "inputs",
    "MissingWebInput": "inputs",
    "check_privacy": "privacy",
    "PrivacyViolation": "privacy",
}


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value

__all__ = [
    "export_executive",
    "export_flights",
    "export_market",
    "recombine_flights",
    "require_inputs",
    "MissingWebInput",
    "check_privacy",
    "PrivacyViolation",
]

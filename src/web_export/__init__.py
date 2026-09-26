"""Exporters that split the v1 web payloads into files under web/public/data/v1/.

See ``README.md`` in this package and
``docs/arquitectura/auditoria-arquitectura-20260926.md`` Fase 2. Nothing here
changes ``src/dashboard/`` or the published HTML; it reads the same payloads
those generators already build and writes a validated, privacy-checked copy
split by period. Publication itself is out of scope for this package
(P3/P6): running this CLI never touches ``stage18`` or Analysis Agent
approvals.
"""

from src.web_export.executive import export_executive
from src.web_export.flights import export_flights, recombine_flights
from src.web_export.inputs import MissingWebInput, require_inputs
from src.web_export.privacy import PrivacyViolation, check_privacy

__all__ = [
    "export_executive",
    "export_flights",
    "recombine_flights",
    "require_inputs",
    "MissingWebInput",
    "check_privacy",
    "PrivacyViolation",
]

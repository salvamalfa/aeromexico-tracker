"""Export only a physically replayed official-route candidate; no legacy writes."""

from pathlib import Path

from src.dashboard.official_routes_contract import encoded, validate
from src.web_export.privacy import PrivacyViolation, check_privacy, load_privacy_rules


def export_official_routes(payload: dict, out: Path) -> Path:
    validate(payload)
    check_privacy(payload)
    raw = encoded(payload)
    if len(raw) > load_privacy_rules()["max_file_size_bytes"]:
        raise PrivacyViolation("Official routes payload exceeds the public JSON size limit")
    target = Path(out) / "official-routes.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return target

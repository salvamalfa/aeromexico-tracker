"""Export approved news only; absent approval pin yields an explicit empty view."""

import os
from pathlib import Path
import json
from jsonschema import Draft202012Validator
from src.config import PATHS
from src.web_export.privacy import check_privacy
from src.conversational_analytics.evidence_index import APPROVED_INDEX_SHA256_ENV
from src.dashboard.news import build_news_payload
from src.web_export.writer import write_json


def news_export_payload() -> dict:
    if os.environ.get(APPROVED_INDEX_SHA256_ENV, "").strip():
        payload = build_news_payload()
    else:
        payload = {
            "schema_version": "monthly_news_v1",
            "mode": "evidence_unavailable",
            "coverage_note": "El índice aprobado no está habilitado en este build. No se cargan candidatas.",
            "months": [],
            "records": [],
            "limits": [],
        }
    return payload


def export_news(out_dir: Path) -> list[Path]:
    payload = news_export_payload()
    schema = json.loads((PATHS.root / "contracts/web/news.schema.json").read_text())
    Draft202012Validator(schema).validate(payload)
    check_privacy(payload)
    return [write_json(out_dir / "news.json", payload)]

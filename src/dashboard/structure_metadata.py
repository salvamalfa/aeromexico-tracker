"""Validated, bounded metadata for the interactive data-structure page."""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
import pyarrow.parquet as pq

from src.config import PATHS
from src.dashboard.navigation import PAGE_SPECS
from src.dashboard.structure_presentation import (
    FEATURED_ARTIFACT_SOURCE_KEYS,
    FEATURED_GOLD_TABLES,
    SOURCE_GROUPS,
    TABLE_PRESENTATION,
)
from src.pipeline.model import PipelinePhase
from src.pipeline.registry import PIPELINE_STEPS
from src.transform.silver_contracts import load_silver_contracts
from src.transform.stage6_contracts import load_contracts
from src.transform.stage9_lineage import load_source_catalog


_RELATION_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+\"?([a-z][a-z0-9_]*)", re.IGNORECASE | re.MULTILINE
)
_VIEW_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([a-z][a-z0-9_]*)\s+AS\s+",
    re.IGNORECASE,
)
_CTE_ALIAS_RE = re.compile(
    r"(?:\bWITH(?:\s+RECURSIVE)?|,)\s*\"?([a-z][a-z0-9_]*)\"?\s+AS\s*\(",
    re.IGNORECASE,
)
_SAFE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_PRESENTATION_KEYS = {
    "url",
    "href",
    "grain",
    "fields",
    "columns",
    "edges",
    "relationships",
}
_LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|file://|\\\\|/(?:home|Users)/)", re.IGNORECASE)
_ASCII_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
PUBLIC_VALIDATION_RECEIPT = PATHS.gold / "_stage9_public_validation.json"
PUBLIC_VALIDATION_SCHEMA = "stage10_public_validation_v1"


def validate_public_url(url: str, allowed_hosts: list[str] | tuple[str, ...]) -> str:
    """Return a catalog-authorized HTTPS URL or raise before HTML generation."""

    if not isinstance(url, str) or not url.strip():
        raise ValueError("Public URL must be a non-empty string")
    normalized = url.strip()
    if _ASCII_CONTROL_OR_SPACE.search(normalized):
        raise ValueError("Public URL cannot contain whitespace or control characters")
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Public URL must be absolute HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("Public URL cannot embed credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Public URL has an invalid port") from exc
    if port not in {None, 443}:
        raise ValueError("Public URL cannot use a non-HTTPS port")
    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Public URL cannot use a local or private IP")
    if host in {"localhost", "example.com", "example.org", "example.net"}:
        raise ValueError("Public URL cannot use a local or placeholder host")
    normalized_hosts = [item.lower().rstrip(".") for item in allowed_hosts]
    if not any(host == item or host.endswith(f".{item}") for item in normalized_hosts):
        raise ValueError(f"Public URL host is not authorized: {host}")
    return normalized


def _validate_relative_path(value: str) -> str:
    path = str(value).strip()
    if not path or _LOCAL_PATH.search(path) or "\\" in path or path.startswith("/"):
        raise ValueError(f"Technical path must be repository-relative: {value!r}")
    normalized = path.rstrip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError(f"Technical path must stay inside the project: {value!r}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parquet_rows(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"Required public Gold artifact is missing: {path.name}")
    return int(pq.read_metadata(path).num_rows)


def materialize_public_validation_receipt() -> dict[str, Any]:
    """Publish the compact, deployment-safe subset of validated Stage 9 evidence."""

    lineage = _read_json(PATHS.quality / "stage9_lineage.json")
    acceptance = _read_json(PATHS.quality / "stage9_acceptance.json")
    silver_contracts = load_silver_contracts()
    validation = lineage.get("validation", {})
    if validation.get("status") != "passed" or not acceptance.get("all_passed"):
        raise ValueError("Stage 9 must pass before its public validation receipt is materialized")

    record_table_rows = {
        str(table_name): int(row_count)
        for table_name, row_count in sorted(validation.get("record_tables", {}).items())
    }
    if not record_table_rows:
        raise ValueError("Stage 9 validation did not declare record-table counts")
    observed_rows = {
        table_name: _parquet_rows(PATHS.gold / f"{table_name}.parquet")
        for table_name in record_table_rows
    }
    if observed_rows != record_table_rows:
        raise ValueError("Stage 9 record counts no longer match the public Gold snapshot")

    receipt = {
        "schema_version": PUBLIC_VALIDATION_SCHEMA,
        "contract_version": str(lineage["parser_version"]),
        "silver_contract_version": str(silver_contracts["version"]),
        "validation_status": "passed",
        "upstream_receipt_sha256": {
            "stage9_acceptance": _sha256_file(PATHS.quality / "stage9_acceptance.json"),
            "stage9_lineage": _sha256_file(PATHS.quality / "stage9_lineage.json"),
        },
        "source_catalog_sha256": _sha256_file(PATHS.root / "config" / "source_catalog.yaml"),
        "gold_contract_sha256": _sha256_file(
            PATHS.root / "config" / "gold_schema_contracts.yaml"
        ),
        "silver_contract_sha256": _sha256_file(
            PATHS.root / "config" / "silver_schema_contracts.yaml"
        ),
        "pipeline_registry_sha256": _sha256_file(
            PATHS.root / "src" / "pipeline" / "registry.py"
        ),
        "source_count": int(lineage["catalog_sources"]),
        "artifact_count": int(lineage["bronze_artifacts"]),
        "artifact_catalog_sha256": _sha256_file(
            PATHS.gold / "dim_source_artifact.parquet"
        ),
        "record_table_rows": record_table_rows,
        "lineage_records_expected": int(validation["records_expected"]),
        "lineage_records_declared": int(validation["records_declared"]),
        "lineage_coverage": float(validation["coverage_pct"]),
        "declared_without_exact_link_records": int(
            validation["declared_without_exact_link_records"]
        ),
        "unknown_parent_records": int(validation["unknown_parent_records"]),
        "unknown_artifact_records": int(validation["unknown_artifact_records"]),
        "quality_issue_count": int(
            acceptance["quality_reconciliation"]["canonical_rows"]
        ),
        "quality_ledger_sha256": _sha256_file(
            PATHS.gold / "fact_data_quality_issues.parquet"
        ),
        "bridge_rows": _parquet_rows(PATHS.gold / "bridge_record_lineage.parquet"),
        "bridge_sha256": _sha256_file(PATHS.gold / "bridge_record_lineage.parquet"),
    }
    temporary = PUBLIC_VALIDATION_RECEIPT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(PUBLIC_VALIDATION_RECEIPT)
    return receipt


def _load_public_validation_receipt(
    *,
    catalog: dict[str, Any],
    artifacts: pd.DataFrame,
    gold_contracts: dict[str, Any],
    silver_contracts: dict[str, Any],
) -> dict[str, Any]:
    receipt = _read_json(PUBLIC_VALIDATION_RECEIPT)
    if receipt.get("schema_version") != PUBLIC_VALIDATION_SCHEMA:
        raise ValueError("The public Stage 9 validation receipt has an unknown schema")
    if (
        receipt.get("validation_status") != "passed"
        or receipt.get("contract_version") != gold_contracts.get("version")
        or receipt.get("silver_contract_version") != silver_contracts.get("version")
    ):
        raise ValueError("The public Stage 9 validation receipt is not current")
    if receipt.get("source_count") != len(catalog["sources"]):
        raise ValueError("The source catalog no longer matches its public validation receipt")
    if receipt.get("artifact_count") != len(artifacts):
        raise ValueError("The artifact catalog no longer matches its public validation receipt")
    if (
        receipt.get("source_catalog_sha256")
        != _sha256_file(PATHS.root / "config" / "source_catalog.yaml")
        or receipt.get("gold_contract_sha256")
        != _sha256_file(PATHS.root / "config" / "gold_schema_contracts.yaml")
        or receipt.get("silver_contract_sha256")
        != _sha256_file(PATHS.root / "config" / "silver_schema_contracts.yaml")
        or receipt.get("pipeline_registry_sha256")
        != _sha256_file(PATHS.root / "src" / "pipeline" / "registry.py")
        or receipt.get("artifact_catalog_sha256")
        != _sha256_file(PATHS.gold / "dim_source_artifact.parquet")
    ):
        raise ValueError("The public catalog or contract fingerprint is stale")

    contract_tables = gold_contracts["tables"]
    expected_record_tables = {
        name
        for name, definition in contract_tables.items()
        if "record_id" in definition["columns"] and name != "bridge_record_lineage"
    }
    record_table_rows = receipt.get("record_table_rows", {})
    if set(record_table_rows) != expected_record_tables:
        raise ValueError("The lineage receipt does not cover every record-bearing Gold table")
    observed_rows = {
        table_name: _parquet_rows(PATHS.gold / f"{table_name}.parquet")
        for table_name in sorted(expected_record_tables)
    }
    if observed_rows != record_table_rows:
        raise ValueError("The record-bearing Gold snapshot has changed since Stage 9 validation")
    if (
        sum(observed_rows.values()) != receipt.get("lineage_records_expected")
        or receipt.get("lineage_records_declared")
        != receipt.get("lineage_records_expected")
        or receipt.get("unknown_parent_records") != 0
        or receipt.get("unknown_artifact_records") != 0
    ):
        raise ValueError("The lineage record total is inconsistent")
    if float(receipt.get("lineage_coverage", -1)) != 1.0:
        raise ValueError("The validated lineage coverage must be complete")
    quality_path = PATHS.gold / "fact_data_quality_issues.parquet"
    if (
        _parquet_rows(quality_path) != receipt.get("quality_issue_count")
        or _sha256_file(quality_path) != receipt.get("quality_ledger_sha256")
    ):
        raise ValueError("The quality ledger no longer matches its Stage 9 validation receipt")
    bridge_path = PATHS.gold / "bridge_record_lineage.parquet"
    if (
        _parquet_rows(bridge_path) != receipt.get("bridge_rows")
        or _sha256_file(bridge_path) != receipt.get("bridge_sha256")
    ):
        raise ValueError("The lineage bridge no longer matches its Stage 9 validation receipt")
    return receipt


def validate_public_validation_receipt_full() -> dict[str, Any]:
    """Verify fingerprints plus optional local Stage 9 upstream receipts."""

    receipt = _read_json(PUBLIC_VALIDATION_RECEIPT)
    actual = {
        "bridge_sha256": _sha256_file(PATHS.gold / "bridge_record_lineage.parquet"),
        "artifact_catalog_sha256": _sha256_file(
            PATHS.gold / "dim_source_artifact.parquet"
        ),
        "quality_ledger_sha256": _sha256_file(
            PATHS.gold / "fact_data_quality_issues.parquet"
        ),
    }
    for key, value in actual.items():
        if receipt.get(key) != value:
            raise ValueError(f"Public validation receipt fingerprint mismatch: {key}")
    upstream = receipt.get("upstream_receipt_sha256", {})
    for key, path in {
        "stage9_acceptance": PATHS.quality / "stage9_acceptance.json",
        "stage9_lineage": PATHS.quality / "stage9_lineage.json",
    }.items():
        if path.is_file() and upstream.get(key) != _sha256_file(path):
            raise ValueError(f"Public validation receipt upstream mismatch: {key}")
    return receipt


def _relations_in_text(text: str) -> set[str]:
    return {relation.lower() for relation in _RELATION_RE.findall(text)}


def _discover_views() -> dict[str, dict[str, Any]]:
    views: dict[str, dict[str, Any]] = {}
    for sql_path in sorted((PATHS.root / "sql" / "gold").glob("*.sql")):
        text = sql_path.read_text(encoding="utf-8")
        matches = list(_VIEW_RE.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            name = match.group(1)
            block = text[match.end() : end]
            cte_aliases = {alias.lower() for alias in _CTE_ALIAS_RE.findall(block)}
            views[name] = {
                "name": name,
                "depends_on": sorted(_relations_in_text(block) - {name} - cte_aliases),
                "source_file": sql_path.relative_to(PATHS.root).as_posix(),
            }
    return dict(sorted(views.items()))


def _function_dependencies(paths: list[Path]) -> dict[str, set[str]]:
    raw_relations: dict[str, set[str]] = {}
    raw_calls: dict[str, set[str]] = {}
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            relations: set[str] = set()
            calls: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    relations.update(_relations_in_text(child.value))
                if isinstance(child, ast.Call):
                    name = child.func.id if isinstance(child.func, ast.Name) else None
                    if name:
                        calls.add(name)
                    if (
                        name == "load_gold_table"
                        and child.args
                        and isinstance(child.args[0], ast.Constant)
                        and isinstance(child.args[0].value, str)
                    ):
                        relations.add(child.args[0].value)
            raw_relations[node.name] = relations
            raw_calls[node.name] = calls

    resolved = {name: set(relations) for name, relations in raw_relations.items()}
    changed = True
    while changed:
        changed = False
        for name, calls in raw_calls.items():
            before = len(resolved[name])
            for called in calls:
                resolved[name].update(resolved.get(called, set()))
            changed = changed or len(resolved[name]) != before
    return resolved


def _page_direct_dependencies() -> dict[str, set[str]]:
    helper_dependencies = _function_dependencies(
        [
            PATHS.root / "src" / "dashboard" / "data.py",
            PATHS.root / "src" / "dashboard" / "pages" / "common.py",
        ]
    )
    pages: dict[str, set[str]] = {}
    for spec in PAGE_SPECS:
        path = PATHS.root / "src" / "dashboard" / "pages" / f"{spec.module_name}.py"
        if not path.exists():
            raise FileNotFoundError(f"Registered dashboard page is missing: {path}")
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        relations: set[str] = set()
        calls: set[str] = set()
        for child in ast.walk(tree):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                relations.update(_relations_in_text(child.value))
            if isinstance(child, ast.Call):
                name = child.func.id if isinstance(child.func, ast.Name) else None
                if name:
                    calls.add(name)
                if (
                    name == "load_gold_table"
                    and child.args
                    and isinstance(child.args[0], ast.Constant)
                    and isinstance(child.args[0].value, str)
                ):
                    relations.add(child.args[0].value)
        for called in calls:
            relations.update(helper_dependencies.get(called, set()))
        pages[spec.module_name] = relations
    return pages


def _expand_relation(
    name: str,
    *,
    views: dict[str, dict[str, Any]],
    seen: set[str] | None = None,
) -> set[str]:
    if name not in views:
        return {name}
    visited = set() if seen is None else set(seen)
    if name in visited:
        raise ValueError(f"Circular semantic-view dependency: {name}")
    visited.add(name)
    expanded: set[str] = set()
    for dependency in views[name]["depends_on"]:
        expanded.update(_expand_relation(dependency, views=views, seen=visited))
    return expanded


def _page_consumers(
    *,
    views: dict[str, dict[str, Any]],
    gold_tables: set[str],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    page_titles = {spec.module_name: spec.title for spec in PAGE_SPECS}
    direct = _page_direct_dependencies()
    known_assets = gold_tables | set(views)
    expanded: dict[str, set[str]] = {}
    for page, relations in direct.items():
        relations.intersection_update(known_assets)
        tables: set[str] = set()
        for relation in relations:
            tables.update(_expand_relation(relation, views=views))
        expanded[page] = tables & gold_tables

    table_consumers: dict[str, list[str]] = {}
    for table in sorted(gold_tables):
        table_consumers[table] = [
            page_titles[spec.module_name]
            for spec in PAGE_SPECS
            if table in expanded.get(spec.module_name, set())
            and spec.module_name != "estructura_datos"
        ]
    page_assets = {
        page_titles[spec.module_name]: sorted(
            direct.get(spec.module_name, set()) & known_assets
        )
        for spec in PAGE_SPECS
        if spec.module_name != "estructura_datos"
    }
    return table_consumers, page_assets


def _source_cards(
    catalog: dict[str, Any], artifacts: pd.DataFrame
) -> list[dict[str, Any]]:
    sources = catalog["sources"]
    active_public = {
        key
        for key, definition in sources.items()
        if definition["source_kind"] == "public" and definition["is_active"]
    }
    grouped = [
        str(source_key)
        for group in SOURCE_GROUPS
        for source_key in group["source_keys"]
    ]
    if Counter(grouped).most_common(1)[0][1] != 1 or set(grouped) != active_public:
        raise ValueError(
            "Source presentation must cover every active public source exactly once"
        )

    cards: list[dict[str, Any]] = []
    for group in SOURCE_GROUPS:
        source_rows: list[dict[str, Any]] = []
        artifact_total = 0
        for source_key_value in group["source_keys"]:
            source_key = str(source_key_value)
            definition = sources[source_key]
            official_url = validate_public_url(
                definition["official_page_url"], definition["allowed_hosts"]
            )
            source_artifacts = artifacts[artifacts["source_key"].eq(source_key)]
            artifact_total += len(source_artifacts)
            featured_artifact: dict[str, Any] | None = None
            if source_key in FEATURED_ARTIFACT_SOURCE_KEYS:
                candidates = source_artifacts[
                    source_artifacts["source_url"].eq(official_url)
                    & source_artifacts["is_direct_public_artifact"].fillna(False)
                ]
                if len(candidates) != 1:
                    raise ValueError(
                        f"Featured artifact selector must resolve once: {source_key}"
                    )
                artifact = candidates.iloc[0]
                artifact_url = validate_public_url(
                    str(artifact["source_url"]), definition["allowed_hosts"]
                )
                featured_artifact = {
                    "url": artifact_url,
                    "source_file": _validate_relative_path(str(artifact["source_file"])),
                    "artifact_format": str(artifact["artifact_format"]),
                    "artifact_sha256": str(artifact["artifact_sha256"]),
                    "downloaded_at": pd.Timestamp(artifact["downloaded_at"]).isoformat(),
                }

            if featured_artifact is not None:
                artifact_note = "El catálogo identifica un archivo público estable y preservado."
            elif definition["artifact_link_policy"] == "landing_page_only":
                artifact_note = "El archivo cambia o no tiene un enlace estable; se abre la página de origen."
            elif source_artifacts.empty:
                artifact_note = "No existe un artefacto Bronze para esta fuente en el corte actual."
            else:
                artifact_note = "Hay varios documentos; no se elige uno arbitrariamente como archivo principal."

            source_rows.append(
                {
                    "source_key": source_key,
                    "display_name": definition["display_name"],
                    "institution": definition["institution"],
                    "description": definition["business_description"],
                    "coverage": definition["coverage"],
                    "update_frequency": definition["update_frequency"],
                    "access_method": definition["access_method"],
                    "limitations": definition["limitations"],
                    "official_url": official_url,
                    "artifact_count": int(len(source_artifacts)),
                    "featured_artifact": featured_artifact,
                    "artifact_note": artifact_note,
                }
            )

        cards.append(
            {
                "card_id": f"source-{group['group_key']}",
                "card_type": "source",
                "title": group["label"],
                "summary": group["summary"],
                "owner": " · ".join(dict.fromkeys(row["institution"] for row in source_rows)),
                "coverage": f"{len(source_rows)} fuente{'s' if len(source_rows) != 1 else ''} · {artifact_total:,} artefactos preservados",
                "update": " · ".join(dict.fromkeys(row["update_frequency"] for row in source_rows)),
                "explanation": group["summary"],
                "sources": source_rows,
                "technical": {
                    "Claves de catálogo": ", ".join(row["source_key"] for row in source_rows),
                    "Metadata": "config/source_catalog.yaml",
                },
            }
        )
    return cards


def _process_card(
    card_id: str,
    title: str,
    summary: str,
    *,
    owner: str,
    coverage: str,
    update: str,
    explanation: str,
    technical: dict[str, str],
    examples: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    for path in technical.values():
        if "/" in path and not path.startswith(("Etapa", "Contrato", "Registro")):
            for candidate in [part.strip() for part in path.split(" · ")]:
                if "/" in candidate and not candidate.startswith(("http", "32 ")):
                    _validate_relative_path(candidate)
    return {
        "card_id": card_id,
        "card_type": "process",
        "title": title,
        "summary": summary,
        "owner": owner,
        "coverage": coverage,
        "update": update,
        "explanation": explanation,
        "technical": technical,
        "examples": examples or [],
    }


def _normalization_examples() -> list[dict[str, str]]:
    profile_path = PATHS.root / "src" / "parse" / "profiles" / "aeromexico.yaml"
    profile_text = profile_path.read_text(encoding="utf-8")
    if "scale_multiplier: 0.01" not in profile_text or "scale_multiplier: 1000000" not in profile_text:
        raise ValueError("Aeromexico parsing profile no longer supports the displayed examples")
    q1_fixture_path = PATHS.root / "tests" / "fixtures" / "sec" / "earnings_2026Q1.htm"
    q2_fixture_path = PATHS.root / "tests" / "fixtures" / "sec" / "earnings_2026Q2.htm"
    q1_fixture = q1_fixture_path.read_text(encoding="utf-8")
    q2_fixture = q2_fixture_path.read_text(encoding="utf-8")
    if "84.4" not in q1_fixture or "1Q26" not in q1_fixture or "1,479" not in q2_fixture:
        raise ValueError("SEC frozen fixtures no longer support the displayed examples")
    return [
        {
            "kind": "Porcentaje",
            "before": "84.4 %",
            "after": "0.844",
            "explanation": "La fuente publica puntos porcentuales; el modelo guarda una fracción comparable.",
            "evidence": "tests/fixtures/sec/earnings_2026Q1.htm · src/parse/profiles/aeromexico.yaml · load_factor_total × 0.01",
        },
        {
            "kind": "Moneda",
            "before": "1,479 USD millions",
            "after": "1,479,000,000 USD",
            "explanation": "La escala reportada se conserva y el valor normalizado queda en unidades completas.",
            "evidence": "tests/fixtures/sec/earnings_2026Q2.htm · src/parse/profiles/aeromexico.yaml · total_revenue × 1,000,000",
        },
        {
            "kind": "Periodo",
            "before": "1Q26",
            "after": "2026Q1",
            "explanation": "Una etiqueta textual se convierte en la clave de trimestre usada por todo el modelo.",
            "evidence": "tests/fixtures/sec/earnings_2026Q1.htm · convención period_id",
        },
    ]


def _table_metadata(
    *,
    contracts: dict[str, Any],
    views: dict[str, dict[str, Any]],
    table_consumers: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables = contracts["tables"]
    if set(TABLE_PRESENTATION) != set(tables):
        missing = sorted(set(tables) - set(TABLE_PRESENTATION))
        unknown = sorted(set(TABLE_PRESENTATION) - set(tables))
        raise ValueError(f"Table presentation mismatch; missing={missing}, unknown={unknown}")
    for definition in TABLE_PRESENTATION.values():
        if _FORBIDDEN_PRESENTATION_KEYS & set(definition):
            raise ValueError("Presentation registry cannot declare technical schema")

    reverse_tables: dict[str, set[str]] = defaultdict(set)
    reverse_views: dict[str, set[str]] = defaultdict(set)
    edges: list[dict[str, Any]] = []
    for child, definition in tables.items():
        for foreign_key in definition.get("foreign_keys", []):
            parent = foreign_key["references"]["table"]
            reverse_tables[parent].add(child)
            edges.append(
                {
                    "parent": parent,
                    "child": child,
                    "parent_columns": list(foreign_key["references"]["columns"]),
                    "child_columns": list(foreign_key["columns"]),
                }
            )
    for view_name, view in views.items():
        for dependency in view["depends_on"]:
            if dependency in tables:
                reverse_views[dependency].add(view_name)

    metadata: list[dict[str, Any]] = []
    technical_suffixes = {
        "record_id",
        "source_file",
        "source_hash",
        "ingested_at",
        "parser_version",
        "artifact_sha256",
        "lineage_fingerprint",
    }
    for table_name, definition in tables.items():
        presentation = TABLE_PRESENTATION[table_name]
        grain = list(definition["grain"])
        business_fields = [
            name
            for name in definition["columns"]
            if name not in technical_suffixes and name not in grain
        ]
        main_fields = list(dict.fromkeys([*grain, *business_fields[:6]]))
        inputs = [
            foreign_key["references"]["table"]
            for foreign_key in definition.get("foreign_keys", [])
        ]
        outputs = sorted(reverse_tables[table_name] | reverse_views[table_name])
        metadata.append(
            {
                "table_name": table_name,
                "label": presentation["label"],
                "role": presentation["role"],
                "purpose": presentation["purpose"],
                "stage": int(definition.get("stage", 6)),
                "grain": grain,
                "primary_key": list(definition.get("primary_key", [])),
                "main_fields": main_fields,
                "inputs": list(dict.fromkeys(inputs)),
                "outputs": outputs,
                "consumer_pages": table_consumers[table_name],
                "featured": table_name in FEATURED_GOLD_TABLES,
                "contract_source": "config/gold_schema_contracts.yaml",
            }
        )
    return metadata, sorted(edges, key=lambda row: (row["child"], row["parent"]))


def build_structure_metadata() -> dict[str, Any]:
    """Build deterministic page metadata without loading the large lineage bridge."""

    catalog = load_source_catalog()
    gold_contracts = load_contracts()
    silver_contracts = load_silver_contracts()
    artifacts = pd.read_parquet(PATHS.gold / "dim_source_artifact.parquet")
    validation_receipt = _load_public_validation_receipt(
        catalog=catalog,
        artifacts=artifacts,
        gold_contracts=gold_contracts,
        silver_contracts=silver_contracts,
    )

    views = _discover_views()
    gold_tables = set(gold_contracts["tables"])
    table_consumers, page_assets = _page_consumers(
        views=views, gold_tables=gold_tables
    )
    tables, fk_edges = _table_metadata(
        contracts=gold_contracts,
        views=views,
        table_consumers=table_consumers,
    )
    examples = _normalization_examples()

    phase_counts = Counter(step.phase.value for step in PIPELINE_STEPS)
    source_cards = _source_cards(catalog, artifacts)
    silver_table_count = len(silver_contracts["tables"])
    silver_field_count = sum(
        len(definition["required_columns"])
        for definition in silver_contracts["tables"].values()
    )
    gold_column_count = sum(
        len(definition["columns"])
        for definition in gold_contracts["tables"].values()
    )
    quality_rows = int(validation_receipt["quality_issue_count"])

    capture_cards = [
        _process_card(
            "capture-receipt",
            "Descarga con recibo",
            "Cada intento declara qué esperaba, qué obtuvo y por qué una fuente no estuvo disponible.",
            owner="Registro central del pipeline",
            coverage=f"{phase_counts[PipelinePhase.INGEST.value]} pasos de ingesta · obligatorios y opcionales explícitos",
            update="En cada corrida de ingesta",
            explanation="Una ausencia opcional queda como not_available; una entrada obligatoria detiene la corrida.",
            technical={"Registro": "src/pipeline/registry.py", "Manifiesto": "data/bronze/_manifest.jsonl"},
        ),
        _process_card(
            "capture-bronze",
            "Original inmutable",
            "El archivo público se preserva tal como llegó y recibe un SHA-256 verificable.",
            owner="Capa Bronze",
            coverage=f"{len(artifacts):,} artefactos públicos catalogados",
            update="Al incorporar una descarga nueva",
            explanation="Los parsers nunca sustituyen el original; trabajan sobre una copia preservada.",
            technical={"Capa": "data/bronze/", "Catálogo público": "data/gold/dim_source_artifact.parquet"},
        ),
        _process_card(
            "capture-versions",
            "Versiones sin sobrescribir",
            "Cuando cambia el contenido, la versión anterior sigue disponible para auditoría.",
            owner="Manifiesto Bronze y SCD2",
            coverage=f"{int((artifacts['logical_version'] > 1).sum()):,} artefactos corresponden a versiones posteriores",
            update="Cuando cambia el hash de una identidad lógica",
            explanation="El hash del archivo original y la huella de una derivación tienen significados separados.",
            technical={"Versionado": "data/bronze/_restatements.jsonl", "Historial": "data/gold/fact_carrier_metrics.parquet"},
        ),
    ]

    clean_cards = [
        _process_card(
            "clean-parsing",
            "Extracción por fuente",
            "Cada formato se convierte en filas fieles antes de mezclarlo con otras fuentes.",
            owner="Parsers SEC, BMV, AFAC, BTS y complementarios",
            coverage=f"{phase_counts[PipelinePhase.PARSE.value]} pasos · {silver_table_count} datasets Silver",
            update="Después de validar el snapshot Bronze",
            explanation="HTML, XBRL, Excel, PDF, CSV y JSON conservan su procedencia mientras adoptan una estructura tabular.",
            technical={"Código": "src/parse/", "Contratos": "config/silver_schema_contracts.yaml"},
            examples=examples,
        ),
        _process_card(
            "clean-contracts",
            "Tipos y reglas explícitas",
            "El pipeline rechaza granos duplicados, dominios inválidos y relaciones huérfanas.",
            owner="Contratos Silver",
            coverage=f"{silver_table_count} datasets · {silver_field_count} campos requeridos",
            update="En cada parse y rebuild",
            explanation="Una validación fallida no se publica como si fuera un dato correcto.",
            technical={"Contrato": "config/silver_schema_contracts.yaml", "Gate": "data/quality/stage9_silver_contracts.json"},
        ),
        _process_card(
            "clean-standardization",
            "Periodos, monedas y unidades comparables",
            "Porcentajes, escalas monetarias, meses y trimestres usan convenciones consistentes.",
            owner="Perfiles de parsing y modelo de periodos",
            coverage="Porcentaje, moneda, unidad, calendario y entidad",
            update="Durante parsing y transformación",
            explanation="El valor reportado se conserva junto al normalizado para poder reconstruir la conversión.",
            technical={"Perfiles": "src/parse/profiles/", "Dimensión temporal": "data/gold/dim_period.parquet"},
            examples=examples,
        ),
    ]

    model_cards = [
        _process_card(
            "model-dimensional",
            "Modelo de negocio conectado",
            "Aerolíneas, periodos, métricas y lugares se conectan con los hechos que ocurrieron.",
            owner="Capa Gold",
            coverage=f"{len(gold_tables)} tablas · {len(fk_edges)} relaciones declaradas · {gold_column_count} columnas descritas",
            update="En cada transformación validada",
            explanation="El formato largo evita duplicar KPIs y las reglas impiden sumar ratios o márgenes.",
            technical={"Contrato": "config/gold_schema_contracts.yaml", "Capa": "data/gold/"},
        ),
        _process_card(
            "model-semantic",
            "Vistas listas para preguntar",
            "La precedencia, consolidación y comparabilidad se resuelven antes de dibujar una gráfica.",
            owner="DuckDB y SQL semántico",
            coverage=f"{len(views)} vistas de negocio locales",
            update="Al reconstruir Gold y el warehouse",
            explanation="Python y SQL consumen la misma política de fuente preferida.",
            technical={"SQL": "sql/gold/", "Warehouse": "data/warehouse.duckdb"},
        ),
        _process_card(
            "model-analytics",
            "Análisis precomputado",
            "Forecast, anomalías, lenguaje, clusters y estudios llegan evaluados al dashboard.",
            owner="Capa analítica",
            coverage=f"{phase_counts[PipelinePhase.ANALYTICS.value]} pasos registrados · resultados con record_id",
            update="Después de validar el modelo Gold",
            explanation="El dashboard no entrena modelos ni inventa hallazgos durante la visita.",
            technical={"Código": "src/analytics/", "Resultados": "data/gold/fact_forecasts.parquet"},
        ),
            _process_card(
                "model-trust",
                "Calidad y linaje visibles",
                "Cada registro tiene una ruta a archivos, registros padre o una declaración explícita de curación.",
                owner="Ledger de calidad y puente de linaje",
                coverage=(
                    f"{validation_receipt['lineage_records_declared']:,}/"
                    f"{validation_receipt['lineage_records_expected']:,} registros con linaje · "
                    f"{quality_rows} incidencias canónicas"
                ),
                update="En el cierre validado de cada rebuild",
                explanation=(
                    f"{validation_receipt['declared_without_exact_link_records']:,} registros "
                    "declaran que no existe un enlace exacto; no se les inventa uno."
                ),
            technical={"Calidad": "data/gold/fact_data_quality_issues.parquet", "Linaje": "data/gold/bridge_record_lineage.parquet"},
        ),
    ]

    product_cards = [
        _process_card(
            "product-duckdb",
            "Consultas locales y reproducibles",
            "DuckDB combina los Parquet Gold sin depender de una base de datos externa.",
            owner="Warehouse local",
            coverage=f"{len(gold_tables)} tablas y {len(views)} vistas semánticas",
            update="Con cada reconstrucción validada",
            explanation="La interfaz puede funcionar offline porque los datos ya están preparados.",
            technical={"Warehouse": "data/warehouse.duckdb", "Acceso": "src/dashboard/data.py"},
        ),
        _process_card(
            "product-pages",
            "Preguntas de negocio",
            "Cada página responde una pregunta concreta y conserva su fuente y alcance.",
            owner="Streamlit",
            coverage=f"{len(PAGE_SPECS)} páginas registradas en un solo catálogo de navegación",
            update="Cuando cambia el producto analítico",
            explanation="Resumen, impulsores, competencia, red, finanzas, forecast y confianza comparten la misma capa semántica.",
            technical={"Navegación": "src/dashboard/navigation.py", "Aplicación": "src/dashboard/app.py"},
        ),
        _process_card(
            "product-narrative",
            "Gráficas con contexto y límites",
            "Cada visual combina una cifra, su interpretación y lo que todavía no puede afirmarse.",
            owner="Componentes del dashboard",
            coverage="KPI, series, comparaciones, mapas, forecast, narrativa y salud",
            update="Al regenerar los resultados o el diseño",
            explanation="Los faltantes se muestran como faltantes y las estimaciones conservan su etiqueta.",
            technical={"Componentes": "src/dashboard/components/", "Estilos": "src/dashboard/assets/style.css"},
        ),
    ]

    levels = [
        {"level_key": "sources", "number": 1, "title": "Fuentes públicas", "subtitle": "Quién publica la evidencia y qué aporta al negocio.", "cards": source_cards},
        {"level_key": "capture", "number": 2, "title": "Captura y preservación", "subtitle": "Cómo se conserva el original y se detectan cambios.", "cards": capture_cards},
        {"level_key": "clean", "number": 3, "title": "Limpieza y estandarización", "subtitle": "Cómo formatos distintos se vuelven comparables sin perder su procedencia.", "cards": clean_cards},
        {"level_key": "model", "number": 4, "title": "Modelo de negocio y análisis", "subtitle": "Cómo los datos se conectan, priorizan, validan y convierten en hallazgos.", "cards": model_cards},
        {"level_key": "product", "number": 5, "title": "Producto", "subtitle": "Cómo una persona consulta la evidencia y sus límites.", "cards": product_cards},
    ]

    fact_options = [
        table
        for table in tables
        if table["table_name"]
        in {
            "fact_carrier_metrics",
            "fact_route_traffic",
            "fact_airport_traffic",
            "fact_airport_group_traffic",
            "fact_market_data",
            "fact_macro",
        }
    ]
    dimension_tables = [
        table
        for table in tables
        if table["table_name"]
        in {
            "dim_carrier",
            "dim_period",
            "dim_metric",
            "dim_route",
            "dim_airport",
            "dim_airport_group",
        }
    ]

    return {
        "version": "stage10_v1.0.0",
        "levels": levels,
        "normalization_examples": examples,
        "gold": {
            "contract_version": gold_contracts["version"],
            "tables": tables,
            "fk_edges": fk_edges,
            "fact_options": fact_options,
            "dimension_tables": dimension_tables,
            "default_fact": "fact_carrier_metrics",
            "views": list(views.values()),
            "page_assets": page_assets,
        },
        "summary": {
            "sources": len(catalog["sources"]),
            "active_public_sources": sum(len(group["source_keys"]) for group in SOURCE_GROUPS),
            "artifacts": len(artifacts),
            "pipeline_steps": len(PIPELINE_STEPS),
            "silver_tables": silver_table_count,
            "gold_tables": len(gold_tables),
            "semantic_views": len(views),
            "dashboard_pages": len(PAGE_SPECS),
            "lineage_records": int(validation_receipt["lineage_records_declared"]),
            "lineage_coverage": float(validation_receipt["lineage_coverage"]),
        },
        "provenance": [
            "config/source_catalog.yaml",
            "src/pipeline/registry.py",
            "config/silver_schema_contracts.yaml",
            "config/gold_schema_contracts.yaml",
            "src/parse/profiles/aeromexico.yaml",
            "tests/fixtures/sec/earnings_2026Q1.htm",
            "tests/fixtures/sec/earnings_2026Q2.htm",
            "sql/gold/",
            "src/dashboard/navigation.py",
            "data/gold/_stage9_public_validation.json",
        ],
    }

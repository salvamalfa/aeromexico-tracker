"""Parse the lossless XBRL JSON model distributed in BMV packages."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import zipfile

import polars as pl

from src.common.storage import find_bronze_by_source_url
from src.config import PATHS, SOURCE_URLS
from src.ingest.bmv.download import BmvReport, parse_catalog_html


PARSER_VERSION = "bmv_xbrl_json_v1"
STANDARD_LABEL_ROLE = "http://www.xbrl.org/2003/role/label"
PRIMARY_STATEMENT_CODES = ("210000", "310000", "410000", "520000", "610000")
STATEMENT_CODE_PATTERN = re.compile(r"\[(\d{6})\]")


FACT_SCHEMA: dict[str, pl.DataType] = {
    "carrier_key": pl.String,
    "ticker": pl.String,
    "package_period_id": pl.String,
    "package_report_type": pl.String,
    "fact_id": pl.String,
    "context_id": pl.String,
    "unit_id": pl.String,
    "period_id": pl.String,
    "period_type": pl.String,
    "period_start_date": pl.Date,
    "period_end_date": pl.Date,
    "context_period_type": pl.String,
    "taxonomy": pl.String,
    "taxonomy_namespace": pl.String,
    "concept": pl.String,
    "concept_name": pl.String,
    "concept_label_es": pl.String,
    "concept_label_en": pl.String,
    "concept_is_extension": pl.Boolean,
    "dimension_axis": pl.String,
    "dimension_member": pl.String,
    "dimensions_json": pl.String,
    "dimension_count": pl.Int64,
    "value": pl.Float64,
    "value_raw": pl.String,
    "unit": pl.String,
    "currency": pl.String,
    "decimals": pl.String,
    "scale": pl.Int64,
    "statement_type": pl.String,
    "statement_name": pl.String,
    "presentation_order": pl.Float64,
    "parent_concept": pl.String,
    "presentation_roles_json": pl.String,
    "is_consolidated": pl.Boolean,
    "is_derived": pl.Boolean,
    "is_ytd": pl.Boolean,
    "derivation_formula": pl.String,
    "derivation_source_file_prior": pl.String,
    "derivation_source_hash_prior": pl.String,
    "source_system": pl.String,
    "source_file": pl.String,
    "source_hash": pl.String,
    "ingested_at": pl.String,
    "parser_version": pl.String,
}


CONCEPT_SCHEMA: dict[str, pl.DataType] = {
    "concept": pl.String,
    "concept_name": pl.String,
    "taxonomy": pl.String,
    "taxonomy_namespace": pl.String,
    "concept_label_es": pl.String,
    "concept_label_en": pl.String,
    "concept_is_extension": pl.Boolean,
    "data_type": pl.String,
    "period_type": pl.String,
    "balance_type": pl.String,
    "statement_types": pl.String,
    "statement_names": pl.String,
    "tickers": pl.String,
    "package_periods": pl.String,
    "fact_count": pl.Int64,
}


def _source_record(source_url: str) -> tuple[Path, dict[str, Any]]:
    found = find_bronze_by_source_url(source_url)
    if found is None:
        raise FileNotFoundError(f"Missing bronze artifact for {source_url}")
    path, metadata = found
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError(f"Bronze hash mismatch for {path}")
    return path, metadata


def rebuild_package_index_from_bronze() -> pl.DataFrame:
    """Reconstruct the BMV package inventory without network access."""

    catalog_path, _ = _source_record(SOURCE_URLS["bmv_xbrl"])
    reports = parse_catalog_html(catalog_path.read_bytes())
    complete: list[BmvReport] = []
    for report in reports:
        zip_path, zip_metadata = _source_record(report.zip_url)
        with zipfile.ZipFile(zip_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) != 1:
            raise ValueError(f"Expected one member in {report.zip_url}; found {len(members)}")
        member_name = members[0].filename
        member_url = f"{report.zip_url}#member={member_name}"
        member_path, member_metadata = _source_record(member_url)
        complete.append(
            replace(
                report,
                zip_source_file=zip_path.relative_to(PATHS.bronze).as_posix(),
                zip_source_hash=str(zip_metadata["sha256"]),
                member_name=member_name,
                member_source_url=member_url,
                member_source_file=member_path.relative_to(PATHS.bronze).as_posix(),
                member_source_hash=str(member_metadata["sha256"]),
                ingested_at=str(member_metadata["downloaded_at"]),
            )
        )
    rows = [report.as_record() for report in complete]
    return pl.DataFrame(rows, strict=False).sort(["ticker", "package_period_id", "report_type"])


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _quarter(value: date) -> int:
    return (value.month - 1) // 3 + 1


def _period_fields(period: dict[str, Any]) -> tuple[str, str, date, date, str, bool]:
    period_type = int(period.get("Tipo") or 0)
    if period_type == 1:
        instant = _date(period.get("FechaInstante"))
        if instant is None:
            raise ValueError("Instant context has no FechaInstante")
        return f"{instant.year}Q{_quarter(instant)}", "quarter", instant, instant, "instant", False
    if period_type != 2:
        raise ValueError(f"Unsupported BMV context period type: {period_type}")
    start = _date(period.get("FechaInicio"))
    end = _date(period.get("FechaFin"))
    if start is None or end is None or start > end:
        raise ValueError(f"Invalid BMV duration context: {period}")
    days = (end - start).days + 1
    end_quarter = _quarter(end)
    is_calendar_year = start == date(start.year, 1, 1) and end == date(end.year, 12, 31)
    is_ytd = start == date(start.year, 1, 1) and end_quarter > 1
    if is_calendar_year:
        return str(end.year), "year", start, end, "duration", True
    if 330 <= days <= 380:
        return f"{end.year}Q{end_quarter}TTM", "ttm", start, end, "duration", False
    return f"{end.year}Q{end_quarter}", "quarter", start, end, "duration", is_ytd


def _role_code(role: dict[str, Any]) -> str | None:
    match = STATEMENT_CODE_PATTERN.search(str(role.get("Nombre", "")))
    return match.group(1) if match else None


def _presentation_map(taxonomy: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for role in taxonomy.get("RolesPresentacion") or []:
        code = _role_code(role)
        sequence = 0

        def visit(nodes: list[dict[str, Any]], parent: str | None = None) -> None:
            nonlocal sequence
            for node in nodes:
                sequence += 1
                concept = str(node["IdConcepto"])
                result[concept].append(
                    {
                        "statement_type": code,
                        "statement_name": role.get("Nombre"),
                        "role_uri": role.get("Uri"),
                        "presentation_order": float(node.get("Orden") or sequence),
                        "parent_concept": parent,
                        "preferred_label_role": node.get("RolEtiquetaPreferido"),
                    }
                )
                visit(node.get("SubEstructuras") or [], concept)

        visit(role.get("Estructuras") or [])
    return result


def _primary_presentation(roles: list[dict[str, Any]]) -> dict[str, Any]:
    def rank(role: dict[str, Any]) -> tuple[int, str]:
        code = role.get("statement_type")
        if code in PRIMARY_STATEMENT_CODES:
            return PRIMARY_STATEMENT_CODES.index(code), str(code)
        return len(PRIMARY_STATEMENT_CODES), str(code or "999999")

    return sorted(roles, key=rank)[0] if roles else {}


def _label(concept: dict[str, Any], language: str, preferred_role: str | None = None) -> str | None:
    labels = (concept.get("Etiquetas") or {}).get(language) or {}
    for role in (preferred_role, STANDARD_LABEL_ROLE):
        if role and role in labels:
            return labels[role].get("Valor")
    for value in labels.values():
        if value.get("Valor"):
            return str(value["Valor"])
    return None


def _unit(unit: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not unit:
        return None, None
    measures = unit.get("Medidas") or []
    numerator = unit.get("MedidasNumerador") or []
    denominator = unit.get("MedidasDenominador") or []
    if measures:
        labels = [str(item.get("Etiqueta") or item.get("Nombre")) for item in measures]
        currency = next((str(item.get("Nombre")) for item in measures if "iso4217" in str(item.get("EspacioNombres", "")).casefold()), None)
        return " * ".join(labels), currency
    rendered_numerator = " * ".join(str(item.get("Etiqueta") or item.get("Nombre")) for item in numerator)
    rendered_denominator = " * ".join(str(item.get("Etiqueta") or item.get("Nombre")) for item in denominator)
    currency = next((str(item.get("Nombre")) for item in numerator if "iso4217" in str(item.get("EspacioNombres", "")).casefold()), None)
    return f"{rendered_numerator} / {rendered_denominator}", currency


def _dimensions(context: dict[str, Any]) -> list[dict[str, Any]]:
    values = list(context.get("ValoresDimension") or [])
    entity = context.get("Entidad") or {}
    values.extend(entity.get("ValoresDimension") or [])
    normalized = [
        {
            "axis": value.get("IdDimension"),
            "member": value.get("IdItemMiembro"),
            "axis_qname": value.get("QNameDimension"),
            "member_qname": value.get("QNameItemMiembro"),
            "typed_member": value.get("ElementoMiembroTipificado"),
            "is_explicit": value.get("Explicita"),
        }
        for value in values
    ]
    return sorted(normalized, key=lambda value: (str(value["axis"]), str(value["member"])))


def _taxonomy_prefix(concept_id: str) -> str:
    return concept_id.split("_", 1)[0]


def _is_extension(concept_id: str) -> bool:
    return _taxonomy_prefix(concept_id) not in {"ifrs-full", "ifrs-mc"}


def parse_payload(
    payload: dict[str, Any], package: dict[str, Any]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Parse one BMV JSON package into numeric facts and concept occurrences."""

    required = {"Taxonomia", "ContextosPorId", "UnidadesPorId", "HechosPorId"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"BMV package is missing required keys: {sorted(missing)}")
    taxonomy = payload["Taxonomia"]
    concepts = taxonomy.get("ConceptosPorId") or {}
    contexts = payload["ContextosPorId"]
    units = payload["UnidadesPorId"]
    presentations = _presentation_map(taxonomy)
    fact_counts = {key: len(value or []) for key, value in (payload.get("HechosPorIdConcepto") or {}).items()}
    concept_rows: list[dict[str, object]] = []
    for concept_id, count in fact_counts.items():
        metadata = concepts.get(concept_id) or {}
        roles = presentations.get(concept_id, [])
        primary = _primary_presentation(roles)
        concept_rows.append(
            {
                "concept": concept_id,
                "concept_name": metadata.get("Nombre") or concept_id.split("_", 1)[-1],
                "taxonomy": _taxonomy_prefix(concept_id),
                "taxonomy_namespace": metadata.get("EspacioNombres"),
                "concept_label_es": _label(metadata, "es", primary.get("preferred_label_role")),
                "concept_label_en": _label(metadata, "en", primary.get("preferred_label_role")),
                "concept_is_extension": _is_extension(concept_id),
                "data_type": metadata.get("TipoDato"),
                "period_type": metadata.get("TipoPeriodo"),
                "balance_type": metadata.get("Balance"),
                "statement_types": "|".join(sorted({str(role["statement_type"]) for role in roles if role.get("statement_type")})) or None,
                "statement_names": "|".join(sorted({str(role["statement_name"]) for role in roles if role.get("statement_name")})) or None,
                "ticker": package["ticker"],
                "package_period_id": package["package_period_id"],
                "fact_count": count,
            }
        )

    rows: list[dict[str, object]] = []
    for fact_id, fact in payload["HechosPorId"].items():
        if not fact.get("EsNumerico"):
            continue
        context_id = str(fact.get("IdContexto"))
        if context_id not in contexts:
            raise ValueError(f"Fact {fact_id} references unknown context {context_id}")
        context = contexts[context_id]
        period_id, period_type, period_start, period_end, context_period_type, is_ytd = _period_fields(context["Periodo"])
        concept_id = str(fact["IdConcepto"])
        concept = concepts.get(concept_id) or {}
        roles = presentations.get(concept_id, [])
        primary = _primary_presentation(roles)
        dimensions = _dimensions(context)
        unit_id = fact.get("IdUnidad")
        rendered_unit, currency = _unit(units.get(unit_id))
        entity = context.get("Entidad") or {}
        value = fact.get("ValorNumerico")
        rows.append(
            {
                "carrier_key": package["carrier_key"],
                "ticker": package["ticker"],
                "package_period_id": package["package_period_id"],
                "package_report_type": package["report_type"],
                "fact_id": fact_id,
                "context_id": context_id,
                "unit_id": unit_id,
                "period_id": period_id,
                "period_type": period_type,
                "period_start_date": period_start,
                "period_end_date": period_end,
                "context_period_type": context_period_type,
                "taxonomy": _taxonomy_prefix(concept_id),
                "taxonomy_namespace": concept.get("EspacioNombres") or fact.get("EspacioNombres"),
                "concept": concept_id,
                "concept_name": concept.get("Nombre") or fact.get("NombreConcepto"),
                "concept_label_es": _label(concept, "es", primary.get("preferred_label_role")),
                "concept_label_en": _label(concept, "en", primary.get("preferred_label_role")),
                "concept_is_extension": _is_extension(concept_id),
                "dimension_axis": "|".join(str(value["axis"]) for value in dimensions) or None,
                "dimension_member": "|".join(str(value["member"]) for value in dimensions) or None,
                "dimensions_json": json.dumps(dimensions, ensure_ascii=False, sort_keys=True),
                "dimension_count": len(dimensions),
                "value": float(value) if value is not None else None,
                "value_raw": fact.get("Valor"),
                "unit": rendered_unit,
                "currency": currency,
                "decimals": fact.get("Decimales"),
                "scale": 0,
                "statement_type": primary.get("statement_type"),
                "statement_name": primary.get("statement_name"),
                "presentation_order": primary.get("presentation_order"),
                "parent_concept": primary.get("parent_concept"),
                "presentation_roles_json": json.dumps(roles, ensure_ascii=False, sort_keys=True),
                "is_consolidated": not bool(entity.get("ContieneInformacionDimensional")) and entity.get("Segmento") is None,
                "is_derived": False,
                "is_ytd": is_ytd,
                "derivation_formula": None,
                "derivation_source_file_prior": None,
                "derivation_source_hash_prior": None,
                "source_system": "bmv",
                "source_file": package["member_source_file"],
                "source_hash": package["member_source_hash"],
                "ingested_at": package["ingested_at"],
                "parser_version": PARSER_VERSION,
            }
        )
    return rows, concept_rows


def _aggregate_concepts(rows: list[dict[str, object]]) -> pl.DataFrame:
    aggregated: dict[str, dict[str, Any]] = {}
    for row in rows:
        concept = str(row["concept"])
        current = aggregated.setdefault(
            concept,
            {
                **{key: row.get(key) for key in CONCEPT_SCHEMA if key not in {"tickers", "package_periods", "fact_count"}},
                "tickers_set": set(),
                "package_periods_set": set(),
                "fact_count": 0,
                "statement_types_set": set(),
                "statement_names_set": set(),
            },
        )
        current["tickers_set"].add(str(row["ticker"]))
        current["package_periods_set"].add(str(row["package_period_id"]))
        current["fact_count"] += int(row["fact_count"])
        current["statement_types_set"].update(str(row.get("statement_types") or "").split("|"))
        current["statement_names_set"].update(str(row.get("statement_names") or "").split("|"))
        for label in ("concept_label_es", "concept_label_en"):
            if not current.get(label) and row.get(label):
                current[label] = row[label]
    output = []
    for current in aggregated.values():
        output.append(
            {
                **{key: current.get(key) for key in CONCEPT_SCHEMA if key not in {"tickers", "package_periods", "statement_types", "statement_names"}},
                "tickers": "|".join(sorted(current["tickers_set"])),
                "package_periods": "|".join(sorted(current["package_periods_set"])),
                "statement_types": "|".join(sorted(value for value in current["statement_types_set"] if value)) or None,
                "statement_names": "|".join(sorted(value for value in current["statement_names_set"] if value)) or None,
            }
        )
    return pl.DataFrame(output, schema=CONCEPT_SCHEMA, strict=False).sort(["taxonomy", "concept"])


def parse_all_packages(packages: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    fact_rows: list[dict[str, object]] = []
    concept_rows: list[dict[str, object]] = []
    for package in packages.iter_rows(named=True):
        path = PATHS.bronze / str(package["member_source_file"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != package["member_source_hash"]:
            raise ValueError(f"Bronze hash mismatch for {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        parsed_facts, parsed_concepts = parse_payload(payload, package)
        fact_rows.extend(parsed_facts)
        concept_rows.extend(parsed_concepts)
    facts = pl.DataFrame(fact_rows, schema=FACT_SCHEMA, strict=False).sort(
        ["ticker", "package_period_id", "period_end_date", "concept", "fact_id"]
    )
    return facts, _aggregate_concepts(concept_rows)
